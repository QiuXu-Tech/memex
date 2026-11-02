#!/usr/bin/env python3
"""Publish failure metadata without publishing private model responses."""
import collections
import json
import pathlib
import sys

base, destination = map(pathlib.Path, sys.argv[1:3])
reg = json.loads((base / 'registration.json').read_text())
plan = json.loads((base / 'reviews/plan.json').read_text())
failures = []
for task in reg['tasks']:
    tid = task['id']; folder = base / 'reviews' / tid
    status = folder / 'review-status.json'
    if status.exists():
        row = json.loads(status.read_text())
        failures.append({'task': tid, 'stage': 'pair', 'status': row.get('status'), 'reason': row.get('reason')})
        continue
    trace = folder / 'gateway.jsonl'
    events = [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
    for model in plan['reviewers']:
        path = folder / f'{model}.json'; row = json.loads(path.read_text()) if path.exists() else {}
        if row.get('rating') is not None: continue
        relevant = [event for event in events if event.get('operationLabel') == f'{tid}:{model}' and event.get('status') != 'started']
        terminal = relevant[-1] if relevant else {}
        failures.append({'task': tid, 'stage': 'review', 'model': model, 'status': row.get('status', 'MISSING'),
                         'errorType': terminal.get('errorType'), 'httpStatus': terminal.get('httpStatus'), 'validationError': row.get('error')})
    path = folder / 'adjudication.json'; row = json.loads(path.read_text()) if path.exists() else {}
    if row.get('model') and row.get('rating') is None:
        relevant = [event for event in events if event.get('operationLabel') == f'{tid}:adjudication' and event.get('status') != 'started']
        terminal = relevant[-1] if relevant else {}
        failures.append({'task': tid, 'stage': 'adjudication', 'model': row.get('model'), 'status': row.get('status', 'MISSING'),
                         'errorType': terminal.get('errorType'), 'httpStatus': terminal.get('httpStatus'), 'validationError': row.get('error')})
counts = collections.Counter(row['stage'] for row in failures)
output = {'kind': 'original-review-failures', 'failures': failures, 'countsByStage': dict(counts),
          'limits': ['Original failures remain unchanged even when a separately registered post-hoc replacement is successful.',
                     'Timeout charges can remain unsettled or unknown. Raw model responses remain local.']}
destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n'); print(json.dumps(output['countsByStage']))
