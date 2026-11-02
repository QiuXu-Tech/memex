#!/usr/bin/env python3
"""Post-hoc count of caller-asserted metadata in stored replay records."""
import collections
import datetime
import json
import pathlib
import re
import sys

base = pathlib.Path(sys.argv[1]) if len(sys.argv) == 3 else pathlib.Path.home() / '.local/share/memex-forward-20261102/task-state-triage'
registration = json.loads((base / 'registration.json').read_text())
counts = collections.Counter()
tasks_with = collections.Counter()
errors = []
for task in registration['tasks']:
    tid = task['id']; folder = base / tid / 'memory/memex/records'; seen = set()
    for file in folder.rglob('mem_*.md') if folder.exists() else []:
        try:
            header = file.read_text().split('\n---\n', 1)[0]
            match = re.search(r'^provenance: (\{.*\})$', header, re.M)
            provenance = json.loads(match.group(1)) if match else {}
            evidence = provenance.get('evidence')
            counts['storedRecords'] += 1
            if provenance.get('source') == 'claude-stop': counts['automaticCheckpoints'] += 1
            if isinstance(evidence, dict):
                counts['recordsWithEvidence'] += 1; seen.add('evidence')
                for field in ('source', 'version', 'observedAt', 'validUntil'):
                    if isinstance(evidence.get(field), str) and evidence[field]: counts[field] += 1; seen.add(field)
        except (OSError, UnicodeError, ValueError) as error:
            errors.append({'task': tid, 'errorType': type(error).__name__})
    tasks_with.update(seen)
output = {'generatedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'kind': 'post-hoc-stored-record-metadata-count',
          'recordCounts': {key: counts[key] for key in ('storedRecords', 'automaticCheckpoints', 'recordsWithEvidence', 'source', 'version', 'observedAt', 'validUntil')},
          'tasksWithAtLeastOne': {key: tasks_with[key] for key in ('evidence', 'source', 'version', 'observedAt', 'validUntil')},
          'unreadableRecordErrors': errors,
          'limits': ['This counts metadata in records present at inspection, not all writes or records that were subsequently removed.',
                     'Source, version, observation time and expiry are caller assertions, not independently verified facts.']}
path = pathlib.Path(sys.argv[-1]); path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n');print(json.dumps(output['recordCounts']))
