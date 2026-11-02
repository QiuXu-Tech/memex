#!/usr/bin/env python3
"""Post-hoc tool outcome and repeated-call counts without publishing arguments."""
import collections
import json
import pathlib
import sys

base, destination = map(pathlib.Path, sys.argv[1:3])
registration = json.loads((base / 'registration.json').read_text())
outcomes = {arm: collections.defaultdict(collections.Counter) for arm in ('baseline', 'memex')}
repeats = {arm: 0 for arm in outcomes}; pilot_errors = collections.Counter()
tasks_with_success = collections.defaultdict(set)
for task in registration['tasks']:
    tid = task['id']; trace = base / tid / 'traces'
    for arm in outcomes:
        for stage in (1, 2, 3):
            calls = {}; results = {}; seen = set()
            for suffix in ('', '-recovery'):
                path = trace / f'{arm}-s{stage}{suffix}-events.jsonl'
                if not path.exists(): continue
                for line in path.read_text().splitlines():
                    try: event = json.loads(line)
                    except ValueError: continue
                    for item in (event.get('message') or {}).get('content', []):
                        if not isinstance(item, dict): continue
                        if event.get('type') == 'assistant' and item.get('type') == 'tool_use' and item.get('id'):
                            calls[item['id']] = item
                        if event.get('type') == 'user' and item.get('type') == 'tool_result' and item.get('tool_use_id'):
                            results[item['tool_use_id']] = 'error' if item.get('is_error') else 'success'
            for identifier, call in calls.items():
                name = call.get('name', 'UNKNOWN'); status = results.get(identifier, 'missingResult')
                key = (name, json.dumps(call.get('input') or {}, sort_keys=True, ensure_ascii=False))
                repeats[arm] += int(key in seen); seen.add(key); outcomes[arm][name][status] += 1
                if status == 'success': tasks_with_success[(arm, name)].add(tid)
            pilot = trace / f'{arm}-s{stage}-tools.jsonl'
            if pilot.exists():
                for line in pilot.read_text().splitlines():
                    try: event = json.loads(line)
                    except ValueError: continue
                    if event.get('name') == 'repo_search' and event.get('status') == 'ok' and isinstance((event.get('result') or {}).get('limitAdjustment'), dict):
                        pilot_errors['searchLimitsAdjusted'] += 1
                    if event.get('status') != 'error': continue
                    name, error = event.get('name', 'UNKNOWN'), event.get('error', '')
                    if name == 'repo_search' and error == 'invalid query':
                        limit = (event.get('arguments') or {}).get('limit')
                        pilot_errors['searchAboveMaximum'] += int(type(limit) is int and limit > 30)
                        pilot_errors['searchInvalidOther'] += int(not (type(limit) is int and limit > 30))
                    else: pilot_errors['otherPilotToolErrors'] += 1
result = {'kind': 'post-hoc-tool-health', 'exactRepeatedCallsByArm': repeats,
          'toolOutcomesByArm': {arm: {name: dict(counts) for name, counts in values.items()} for arm, values in outcomes.items()},
          'tasksWithSuccessfulTool': {f'{arm}:{name}': len(tasks) for (arm, name), tasks in tasks_with_success.items()},
          'pilotErrors': {key: pilot_errors[key] for key in ('searchAboveMaximum', 'searchInvalidOther', 'searchLimitsAdjusted', 'otherPilotToolErrors')},
          'limits': ['A successful tool result proves an operation returned, not that its content was correct or caused the final answer.',
                     'Exact repeated calls are counted within a single client session, including a same-session continuation.',
                     'This count includes started sessions from incomplete pairs and is an exploratory post-hoc analysis.']}
destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n');print(json.dumps({'repeats': repeats, 'pilotErrors': result['pilotErrors'], 'successfulMemoryTools': {key: value for key, value in result['tasksWithSuccessfulTool'].items() if 'mcp__memex__' in key}}))
