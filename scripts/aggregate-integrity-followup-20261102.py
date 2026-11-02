#!/usr/bin/env python3
"""Reconcile the two integrity replays and verify their blind commitments."""
import collections
import datetime
import hashlib
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = pathlib.Path.home() / '.local/share/memex-forward-20261102'
spec = importlib.util.spec_from_file_location('autonomy_aggregate', ROOT / 'scripts/aggregate-production-autonomy-20261102.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)
a.P = BASE


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_blind(base, published):
    assert digest(base / 'reviews/commitments.json') == digest(published)
    commitments = read(base / 'reviews/commitments.json')['packets']
    unblinded = []
    for item in commitments:
        folder = base / 'reviews' / item['task']
        assert digest(folder / 'packet.json') == item['packetSha256']
        key = read(folder / 'key.json')
        salt = read(folder / 'salt.json')['nonce']
        encoded = json.dumps(key, sort_keys=True, separators=(',', ':'))
        assert hashlib.sha256((salt + '\0' + encoded).encode()).hexdigest() == item['saltedKeyCommitmentSha256']
        unblinded.append({'task': item['task'], 'nonce': salt, 'labels': key})
    return unblinded


def independent_scores(base, task):
    folder = base / 'reviews' / task
    if not (folder / 'key.json').exists():
        return None
    key = read(folder / 'key.json')
    paths = [folder / 'gpt-6.1-sol.json', folder / 'deepseek-flash.json']
    if not all(p.exists() for p in paths):
        return None
    ratings = [read(p).get('rating') for p in paths]
    if any(not isinstance(r, dict) or len(r.get('candidates', [])) != 2 for r in ratings):
        return None
    evidence = set(read(folder / 'packet.json')['evidence'])
    def rows(r):
        for candidate in r['candidates']:
            assert candidate['references'] and set(candidate['references']) <= evidence
            assert any(f'{kind}:{candidate["id"]}' in candidate['references'] for kind in ('final', 'source', 'session'))
        return {v['id']: (v['score'], tuple(sorted(v['unsupportedClaims']))) for v in r['candidates']}
    original = [rows(r) for r in ratings]
    if any(set(x) != set(key) or any(v[0] is not None and (type(v[0]) is not int or v[0] not in (0, 1, 2)) for v in x.values()) for x in original):
        return None
    different = original[0] != original[1]
    numeric_difference = any(original[0][k][0] != original[1][k][0] for k in key)
    final = original[0]
    if different:
        path = folder / 'adjudication.json'
        if not path.exists() or not read(path).get('rating'):
            return None
        final = rows(read(path)['rating'])
        if set(final) != set(key) or any(type(v[0]) is not int or v[0] not in (0, 1, 2) for v in final.values()):
            return None
    if any(type(v[0]) is not int or v[0] not in (0, 1, 2) for v in final.values()):
        return None
    return {'scores': {key[k]: v[0] for k, v in final.items()}, 'adjudicated': different,
            'numericReviewerDisagreement': numeric_difference,
            'reviewerScores': [{key[k]: v[0] for k, v in review.items()} for review in original]}


def successful_opens(base, row):
    chain = row.get('memoryChain') or {}
    trace = base / row['id'] / 'traces'
    events = a.events(trace / 'memex-s2-events.jsonl') + a.events(trace / 'memex-s2-recovery-events.jsonl')
    calls, opened = {}, set()
    for event in events:
        for item in (event.get('message') or {}).get('content', []):
            if not isinstance(item, dict):
                continue
            if item.get('type') == 'tool_use' and item.get('name') == 'mcp__memex__memory_open':
                calls[item.get('id')] = (item.get('input') or {}).get('id')
            elif item.get('type') == 'tool_result' and not item.get('is_error'):
                record = calls.get(item.get('tool_use_id'))
                if record and record in json.dumps(item.get('content'), ensure_ascii=False):
                    opened.add(record)
    return {'agentWriteThenSuccessfulOpen': bool(opened & set(chain.get('successfulWriteIds') or [])),
            'automaticCheckpointThenSuccessfulOpen': bool(opened & set(chain.get('automaticCheckpointIds') or []))}


def verified_input_totals(base, row):
    if not row['completePair']:
        return None
    total = {}
    for arm in ('baseline', 'memex'):
        total[arm] = 0
        for stage in (1, 2):
            name = f'{arm}-s{stage}'
            expected = a.model_tokens(row['sessions'][name])
            trace = base / row['id'] / 'traces'
            events = a.events(trace / f'{name}-events.jsonl') + a.events(trace / f'{name}-recovery-events.jsonl')
            observed = a.message_contexts([events])
            if expected is None or observed is None or expected['input'] != observed['inputTokens']:
                return None
            total[arm] += expected['input']
    return total


def cohort(name, source):
    base = BASE / name
    data = a.cohort(name)
    if data.get('status') == 'NOT_REGISTERED':
        return data, []
    reg = read(base / 'registration.json')
    tasks = {t['id']: t for t in reg['tasks']}
    finished_review = (base / 'reviews/finished.json').exists()
    published = ROOT / ('docs/assets/benchmarks/production-integrity-20261102/packet-commitments.json' if name == 'integrity-triage' else 'docs/assets/benchmarks/production-long-integrity-20261102/packet-commitments.json')
    unblind = verify_blind(base, published) if finished_review else []
    assert not data['rawConsistencyProblems'], data['rawConsistencyProblems']
    simplified = []
    verified_inputs = []
    directions = collections.Counter()
    later = {arm: collections.Counter() for arm in ('baseline', 'memex')}
    for row in data['tasks']:
        tid = row['id']
        score = independent_scores(base, tid) if finished_review and row['completePair'] else None
        if score:
            assert row['review']['status'] == 'VALID' and score['scores'] == row['review']['scoresByArm']
            delta = score['scores']['memex'] - score['scores']['baseline']
            directions['memexHigher' if delta > 0 else 'baselineHigher' if delta < 0 else 'tie'] += 1
        elif row['review']['status'] == 'VALID' and row['completePair'] and all(type(row['review'].get('scoresByArm', {}).get(arm)) is int for arm in ('baseline', 'memex')):
            raise AssertionError(f'{tid}: independent scoring mismatch')
        for arm in ('baseline', 'memex'):
            if not row['completePair']:
                continue
            path = base / tid / 'traces'
            trace = a.events(path / f'{arm}-s2-events.jsonl') + a.events(path / f'{arm}-s2-recovery-events.jsonl')
            exposure = a.later_discussion_exposure(BASE / source / f'{tid}.issue.json', trace)
            for k, v in exposure.items(): later[arm][k] += int(bool(v))
        opens = successful_opens(base, row) if row.get('started') else {'agentWriteThenSuccessfulOpen': False, 'automaticCheckpointThenSuccessfulOpen': False}
        verified = verified_input_totals(base, row)
        if verified:
            verified_inputs.append(verified)
        simplified.append({'id': tid, 'issueUrl': row['issueUrl'], 'sourceCommit': row['sourceCommit'],
            'discussionSpanDays': tasks[tid].get('discussionSpanDays'), 'completePair': row['completePair'],
            'started': row['started'], 'finished': row['finished'],
            'runnerErrorType': (row['runnerError'] or {}).get('type'),
            'sessionStatuses': {k: {'status': v.get('status'), 'completed': v.get('responseCompleted'),
                                    'timeout': v.get('timeout'), 'unavailableToolAttempts': len(v.get('unavailableToolAttempts') or [])} for k, v in row['sessions'].items()},
            'missingSessions': sorted({f'{arm}-s{stage}' for arm in ('baseline', 'memex') for stage in (1, 2)} - set(row['sessions'])),
            'sessionRecoveries': sum(bool(v.get('recovery')) for v in row['sessions'].values()),
            'reviewStatus': row['review']['status'], 'blindReview': score,
            **opens})
    assert dict(directions) == data['scoreDirections']
    result = {k: v for k, v in data.items() if k != 'tasks'}
    result.update({'sourceCommit': reg['memexCommit'], 'registrationSha256': digest(base / 'registration.json'),
                   'independentlyRecountedDirections': dict(directions), 'laterDiscussionExposure': {k: dict(v) for k, v in later.items()},
                   'verifiedInputPairs': len(verified_inputs),
                   'verifiedInputTotals': {arm: sum(item[arm] for item in verified_inputs) for arm in ('baseline', 'memex')},
                   'successfulOpens': {key: sum(t[key] for t in simplified) for key in ('agentWriteThenSuccessfulOpen', 'automaticCheckpointThenSuccessfulOpen')},
                   'tasks': simplified if finished_review else []})
    return result, unblind


def main():
    output = pathlib.Path(sys.argv[1])
    first, first_unblind = cohort('integrity-triage', 'integrity-source')
    long, long_unblind = cohort('integrity-long-triage', 'integrity-long-source')
    result = {'generatedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'firstEight': first, 'longFollowup': long,
              'limits': ['Different commits and prompts: do not pool as one randomized protocol.',
                         'Open-source historical triage replay is not a deployed production outcome.',
                         'AI judges and model client list prices do not establish human-rated correctness or actual wallet cost.',
                         'Memory calls and matching IDs do not establish that the memory caused the answer.']}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    unblind = {'firstEight': first_unblind, 'longFollowup': long_unblind}
    (output.parent / 'packet-unblinding.json').write_text(json.dumps(unblind, indent=2) + '\n')
    print(json.dumps({'firstRated': first.get('validRatedPairs'), 'longRated': long.get('validRatedPairs'),
                      'firstDirections': first.get('scoreDirections'), 'longDirections': long.get('scoreDirections')}))


if __name__ == '__main__':
    main()
