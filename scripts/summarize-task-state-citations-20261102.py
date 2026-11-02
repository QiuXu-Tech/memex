#!/usr/bin/env python3
"""Count final references linked to earlier written or automatic memory records."""
import json
import pathlib
import re
import sys

base, destination = map(pathlib.Path, sys.argv[1:3])
tasks = json.loads((base / 'registration.json').read_text())['tasks']
summary = {'completePairs': 0, 'finalCitesEarlierRecord': 0, 'finalCitesEarlierOpenedRecord': 0, 'finalCitesEarlierRecalledRecord': 0}
for task in tasks:
    folder = base / task['id']; sessions = {}
    for arm in ('baseline', 'memex'):
        for stage in (1, 2, 3):
            path = folder / 'results' / f'{arm}-s{stage}.json'
            if path.exists(): sessions[(arm, stage)] = json.loads(path.read_text())
    if not all(sessions.get((arm, stage), {}).get('responseCompleted') for arm in ('baseline', 'memex') for stage in (1, 2, 3)): continue
    summary['completePairs'] += 1; calls = {}; writes = {1: set(), 2: set()}; opened = {2: set(), 3: set()}; recalled = {2: '', 3: ''}
    for stage in (1, 2, 3):
        for suffix in ('', '-recovery'):
            path = folder / 'traces' / f'memex-s{stage}{suffix}-events.jsonl'
            if not path.exists(): continue
            for line in path.read_text().splitlines():
                try: event = json.loads(line)
                except ValueError: continue
                if stage > 1 and event.get('subtype') == 'hook_response' and event.get('hook_name') == 'UserPromptSubmit': recalled[stage] += str(event.get('stdout', '')) + '\n'
                for item in (event.get('message') or {}).get('content', []):
                    if not isinstance(item, dict): continue
                    if event.get('type') == 'assistant' and item.get('type') == 'tool_use' and item.get('id'):
                        calls[item['id']] = (stage, item)
                    if event.get('type') != 'user' or item.get('type') != 'tool_result' or item.get('is_error'): continue
                    call_stage, call = calls.get(item.get('tool_use_id'), (None, {})); content = json.dumps(item.get('content'), ensure_ascii=False)
                    if call.get('name') == 'mcp__memex__memory_write' and call_stage in (1, 2): writes[call_stage].update(re.findall(r'Stored (mem_[0-9a-f]{10})', content))
                    if call.get('name') == 'mcp__memex__memory_open' and call_stage in (2, 3):
                        identifier = (call.get('input') or {}).get('id')
                        if isinstance(identifier, str) and identifier in content: opened[call_stage].add(identifier)
    automatic = {1: set(), 2: set()}; earlier_sessions = {sessions[('memex', stage)].get('sessionId'): stage for stage in (1, 2) if sessions[('memex', stage)].get('sessionId')}
    records = folder / 'memory/memex/records'
    for file in records.rglob('mem_*.md') if records.exists() else []:
        try:
            head = file.read_text().split('\n---\n', 1)[0]; match = re.search(r'^provenance: (\{.*\})$', head, re.M)
            provenance = json.loads(match.group(1)) if match else {}
            if provenance.get('source') == 'claude-stop' and provenance.get('sourceSession') in earlier_sessions: automatic[earlier_sessions[provenance['sourceSession']]].add(file.stem)
        except (OSError, UnicodeError, ValueError): continue
    earlier = {stage: writes[stage] | automatic[stage] for stage in (1, 2)}
    cited = set(re.findall(r'mem_[0-9a-f]{10}', sessions[('memex', 3)].get('final', ''))) & (earlier[1] | earlier[2])
    opened_later = (earlier[1] & (opened[2] | opened[3])) | (earlier[2] & opened[3])
    recalled_later = {identifier for stage in (2, 3) for previous in range(1, stage) for identifier in earlier[previous] if identifier in recalled[stage]}
    summary['finalCitesEarlierRecord'] += int(bool(cited))
    summary['finalCitesEarlierOpenedRecord'] += int(bool(cited & opened_later))
    summary['finalCitesEarlierRecalledRecord'] += int(bool(cited & recalled_later))
result = {'kind': 'post-hoc-explicit-memory-citations', **summary,
          'limits': ['An identifier in the answer and a successful earlier read are trace evidence, not proof the cited content was necessary or correct.',
                     'Answers that use memory without citing its identifier are not counted.',
                     'Automatic checkpoint attribution depends on records still present when inspected.']}
destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n');print(json.dumps(summary))
