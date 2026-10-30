#!/usr/bin/env python3
"""Extract private, time-cutoff replay inputs from one DSH JSONL.zstd session."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--session', required=True)
parser.add_argument('--out', required=True)
args = parser.parse_args()
source = Path(args.session)
if Path(args.out).exists():
    raise SystemExit('output already exists; refusing to overwrite private replay data')
source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
raw = subprocess.run(['zstd', '-dc', str(source)], capture_output=True, text=True, check=True).stdout
if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
    raise SystemExit('session changed during extraction; no output written')
events, malformed = [], 0
for line in raw.splitlines():
    try:
        events.append(json.loads(line))
    except json.JSONDecodeError:
        malformed += 1
success = {}
for event in events:
    if event.get('type') == 'tool/result':
        msg = event.get('data', {}).get('message', {})
        if msg.get('toolCallId'):
            success[msg['toolCallId']] = (event.get('seq'), event.get('time'), not msg.get('isError', False))

skip = ('[MEMORY', 'Current runtime', 'Time sampled', '## Memory', 'Extra-context', '[测试]', 'Background subagent', 'Agent ', '<l1-eviction>', '<model changed', 'background job', 'Reply with exactly', 'You are running a controlled', 'Your parent agent id', 'You are repeating', 'This is an automatically', 'The available skill catalog', '[visual:')
writes, chat, candidates = [], [], []
for event in events:
    typ, data, seq = event.get('type'), event.get('data', {}), event.get('seq', 0)
    if typ == 'tool/call' and data.get('name') == 'memory_write':
        result = success.get(data.get('callId'))
        if result and result[2]:
            try:
                body = json.loads(data.get('arguments', '{}'))
            except json.JSONDecodeError:
                continue
            writes.append({'id': f'write-{seq}', 'kind': body.get('kind', 'fact'), 'title': body.get('title', ''), 'summary': body.get('summary', ''), 'useWhen': body.get('use_when', ''), 'body': body.get('body', ''), 'sequence': seq, 'availableAfter': result[0], 'availableAfterTime': result[1]})
    elif typ in ('user/message', 'assistant/message'):
        content = data.get('content')
        text = ' '.join(block.get('text', '') for block in content if isinstance(block, dict) and block.get('type') == 'text') if isinstance(content, list) else ''
        text = ' '.join(text.split())
        if not text or any(text.startswith(prefix) for prefix in skip):
            continue
        prior = [write for write in writes if write['availableAfter'] < seq]
        if typ == 'user/message' and 12 <= len(text) <= 500 and len(prior) >= 3 and ('？' in text or '?' in text or any(term in text for term in ('如何', '什么', '为什么', '多少', '哪些', '分析', '解释', '比较', '评估', '总结', '建议'))):
            candidates.append({'querySeq': seq, 'queryTime': event.get('time'), 'question': text, 'pages': prior.copy(), 'tail': chat[-4:].copy()})
        if len(text) <= 3000:
            chat.append({'role': 'user' if typ == 'user/message' else 'assistant', 'text': text[:1200], 'seq': seq})
n = min(10, len(candidates))
indices = sorted(set(round(i * (len(candidates) - 1) / max(1, n - 1)) for i in range(n))) if n else []
episodes = [dict(candidates[i], id=f'replay-{j + 1:02d}') for j, i in enumerate(indices)]
result = {'kind': 'asof-successful-memory-write-snapshot', 'sourceSha256': source_hash, 'malformedLinesSkipped': malformed, 'candidates': len(candidates), 'episodes': episodes, 'limitations': ['One session only', 'Successful write arguments are not a complete historical store snapshot', 'Historical workspace scope is reconstructed', 'No human relevance labels', 'No actual agent tool-use replay', 'Recent chat tail truncated per message']}
Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps({'malformedLinesSkipped': malformed, 'successfulWrites': len(writes), 'candidateQuestions': len(candidates), 'selected': len(episodes)}))
