#!/usr/bin/env python3
"""Audit native cumulative usage without inventing billing or compaction costs.

This produces an observation audit, not experiment.py's billable delta ledger.
Only notifications whose cumulative change exactly matches `last` are added.
Repeated snapshots, inherited/reset prefixes and compaction counters are kept
separate. No price, request invoice identity, or hidden usage is inferred.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path

FIELDS = ('inputTokens', 'cachedInputTokens', 'cacheWriteInputTokens',
          'outputTokens', 'reasoningOutputTokens', 'totalTokens')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def breakdown(value):
    if not isinstance(value, dict):
        raise ValueError('invalid_counter_object')
    counts = {key: value.get(key, 0) if key == 'cacheWriteInputTokens' else value.get(key) for key in FIELDS}
    if any(not isinstance(n, int) or isinstance(n, bool) or not 0 <= n <= 2**53 - 1 for n in counts.values()):
        raise ValueError('invalid_counter_quantity')
    if counts['totalTokens'] != counts['inputTokens'] + counts['outputTokens']:
        raise ValueError('non_generation_total_counter')
    if (counts['cachedInputTokens'] > counts['inputTokens'] or counts['cacheWriteInputTokens'] > counts['inputTokens']
            or counts['reasoningOutputTokens'] > counts['outputTokens']):
        raise ValueError('invalid_counter_subset')
    return counts


def audit_events(rows):
    compactions = {(r.get('threadId'), r.get('turnId')) for r in rows
                   if r.get('item', {}).get('type') == 'contextCompaction'}
    compactions.update((r.get('threadId'), r.get('turnId')) for r in rows
                       if 'compaction' in str(r.get('phase', '')))
    completed = {(r.get('threadId'), r.get('turnId')) for r in rows if r.get('event') == 'turn/completed'}
    previous, seen, reconciled, unresolved, unmetered = {}, set(), [], [], []
    totals = dict.fromkeys(FIELDS, 0); duplicates = 0; issues = set()
    for index, row in enumerate(rows):
        if row.get('event') != 'thread/tokenUsage/updated':
            continue
        identity = {k: row.get(k) for k in ('threadId', 'turnId', 'tokenUsage')}
        key = canonical(identity)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        thread, turn = row.get('threadId'), row.get('turnId')
        record = {'row_index': index, 'threadId': thread, 'turnId': turn,
                  'phase': row.get('phase'), 'raw_notification': identity}
        if not isinstance(thread, str) or not isinstance(turn, str):
            record['reason'] = 'missing_thread_or_turn'; unresolved.append(record)
            issues.add(record['reason']); continue
        if (thread, turn) in compactions:
            record['reason'] = 'compaction_counter_is_not_a_reconciled_billing_measurement'
            unmetered.append(record); issues.add('compaction_usage_unmeasured')
            # Preserve an observed cumulative boundary, without billing its change.
            try:
                previous[thread] = breakdown(row['tokenUsage']['total'])
            except (KeyError, ValueError):
                previous.pop(thread, None)
            continue
        try:
            total = breakdown(row['tokenUsage']['total'])
            last = breakdown(row['tokenUsage']['last'])
            prior = previous.get(thread)
            delta = {k: total[k] - (prior[k] if prior else 0) for k in FIELDS}
            previous[thread] = total
            if prior is None and total != last:
                raise ValueError('unobserved_or_inherited_prefix')
            if any(n < 0 for n in delta.values()):
                raise ValueError('cumulative_counter_reset')
            if delta != last or delta['totalTokens'] <= 0:
                raise ValueError('cumulative_delta_does_not_match_last')
            record.update({'observed_delta': delta, 'counter_start': 'zero_equals_last' if prior is None else 'previous_observed_total'})
            reconciled.append(record)
            for field in FIELDS:
                totals[field] += delta[field]
        except (KeyError, TypeError, ValueError) as error:
            record['reason'] = str(error); unresolved.append(record); issues.add(str(error))
    metered_turns = {(r['threadId'], r['turnId']) for r in reconciled}
    missing = sorted(completed - compactions - metered_turns, key=str)
    if missing:
        issues.add('generation_turn_without_reconciled_usage')
    phase_totals = defaultdict(lambda: dict.fromkeys(FIELDS, 0))
    for row in reconciled:
        for field in FIELDS:
            phase_totals[str(row['phase'])][field] += row['observed_delta'][field]
    return {'schema': 1, 'kind': 'native_usage_observation_audit',
        'reconciled_generation_notifications': len(reconciled), 'duplicate_notifications': duplicates,
        'unmetered_compaction_notifications': len(unmetered),
        'observed_generation_totals': totals if reconciled else None,
        'phase_totals': dict(phase_totals), 'reconciled': reconciled, 'unreconciled': unresolved,
        'unmetered_compactions': unmetered,
        'generation_turns_without_reconciled_usage': [{'threadId': a, 'turnId': b} for a, b in missing],
        'issues': sorted(issues), 'full_cost_available': False, 'standardized_cost': None, 'actual_spend': None,
        'limits': ['Native counters are observations, not provider invoice IDs.',
                   'Totals cover reconciled generation notifications only; missing telemetry is not zero.',
                   'Compaction usage and provider pricing are not established.',
                   'Cached input is a subset of input; reasoning output is a subset of output.',
                   'This audit is not a ready-to-join experiment cost ledger.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if len(args.events) > 16 or args.output.exists():
        parser.error('at most 16 input files and a new output path are required')
    rows, inputs = [], []
    for path in args.events:
        if path.stat().st_size > 8 * 1024 * 1024:
            parser.error('input file exceeds 8 MiB')
        data = path.read_bytes()
        if data and not data.endswith(b'\n'):
            parser.error('input capture has an incomplete final row')
        values = [json.loads(line) for line in data.splitlines() if line.strip()]
        if len(values) > 10000 or any(not isinstance(r, dict) for r in values):
            parser.error('invalid or oversized event stream')
        rows.extend(values)
        inputs.append({'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'rows': len(values)})
    # Each file is kept in capture order. Independent host files may be grouped;
    # comparisons are per thread, so unrelated wall clocks need not be sorted.
    result = audit_events(rows); result['inputs'] = inputs
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False); stream.write('\n')
    print(json.dumps({k: result[k] for k in ('reconciled_generation_notifications',
        'duplicate_notifications', 'unmetered_compaction_notifications', 'observed_generation_totals', 'issues')}))


if __name__ == '__main__':
    main()
