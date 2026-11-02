#!/usr/bin/env python3
"""Recount streamed input usage; does not impute missing final telemetry."""
import collections
import json
import pathlib
import sys

base, destination = map(pathlib.Path, sys.argv[1:3])
reg = json.loads((base / 'registration.json').read_text())
fields = ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens')
messages = {}; owners = {}; duplicate_ids = set(); missing_usage = 0; recovered = collections.Counter()
per_session = {}
for task in reg['tasks']:
    for arm in ('baseline', 'memex'):
        for stage in (1, 2, 3):
            name = f'{arm}-s{stage}'; folder = base / task['id']; path = folder / 'results' / f'{name}.json'
            summary = json.loads(path.read_text()) if path.exists() else None
            attempt_totals = []
            for suffix in ('', '-recovery'):
                stream = folder / 'traces' / f'{name}{suffix}-events.jsonl'; seen = {}
                if stream.exists():
                    for line in stream.read_text().splitlines():
                        try: event = json.loads(line)
                        except ValueError: continue
                        message = event.get('message') or {}; usage = message.get('usage')
                        if event.get('type') == 'assistant' and message.get('id') and isinstance(usage, dict):
                            seen[message['id']] = usage
                amount = None
                if seen and all(all(type(usage.get(k)) is int and usage[k] >= 0 for k in fields) for usage in seen.values()):
                    amount = sum(sum(usage[k] for k in fields) for usage in seen.values())
                attempt_totals.append(amount)
                for identifier, usage in seen.items():
                    owner = (task['id'], arm, stage, suffix)
                    if identifier in owners and owners[identifier] != owner: duplicate_ids.add(identifier)
                    owners[identifier] = owner; messages[identifier] = usage
            per_session[(task['id'], arm, stage)] = (summary, attempt_totals)
            if summary and summary.get('recovery'):
                raw = (summary.get('initialAttempt') or {}).get('usage') or {}
                initial = sum(raw[k] for k in fields) if all(type(raw.get(k)) is int and raw[k] >= 0 for k in fields) else None
                observed = attempt_totals[0]
                recovered['initialMatches'] += int(initial is not None and observed is not None and initial == observed)
                recovered['initialDiffers'] += int(initial is not None and observed is not None and initial != observed)
                recovered['initialMissing'] += int(initial is None or observed is None)
for usage in messages.values():
    if any(type(usage.get(k)) is not int or usage[k] < 0 for k in fields): missing_usage += 1
valid_messages = [usage for usage in messages.values() if all(type(usage.get(k)) is int and usage[k] >= 0 for k in fields)]
complete = []; comparable = []
for task in reg['tasks']:
    records = [per_session[(task['id'], arm, stage)] for arm in ('baseline', 'memex') for stage in (1, 2, 3)]
    if not all(summary and summary.get('responseCompleted') for summary, _ in records): continue
    complete.append(task['id']); paired = {}
    for arm in ('baseline', 'memex'):
        amounts = []
        for stage in (1, 2, 3):
            summary, attempts = per_session[(task['id'], arm, stage)]
            needed = 2 if summary.get('recovery') else 1
            if any(x is None for x in attempts[:needed]): break
            amounts.append(sum(attempts[:needed]))
        paired[arm] = sum(amounts) if len(amounts) == 3 else None
    if all(paired[arm] is not None for arm in paired): comparable.append(paired)
result = {'kind': 'post-hoc-streamed-input-observation', 'distinctAssistantMessageIds': len(messages),
          'duplicateMessageIdsAcrossAttempts': len(duplicate_ids), 'messagesWithMissingInputUsage': missing_usage,
          'streamedInputTotals': {field: sum(usage[field] for usage in valid_messages) for field in fields},
          'recoveredInitialSummaryComparison': {key: recovered[key] for key in ('initialMatches', 'initialDiffers', 'initialMissing')},
          'completePairs': len(complete), 'completePairsWithAllStreamedInput': len(comparable),
          'streamedInputByArmForThosePairs': {arm: sum(row[arm] for row in comparable) for arm in ('baseline', 'memex')},
          'limits': ['These are streamed message inputs, not independently reconciled final per-session totals.',
                     'Recovered sessions with differing terminal and streamed inputs remain unknown in the primary paired-token analysis.',
                     'Account-wide gateway rows may corroborate totals but do not prove individual or per-arm attribution.',
                     'Streamed output-token fields are not final output usage and are intentionally omitted.']}
destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n');print(json.dumps(result))
