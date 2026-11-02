#!/usr/bin/env python3
"""Replay recorded over-limit search arguments through the repaired MCP bridge."""
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
base, destination = map(pathlib.Path, sys.argv[1:3])
arguments = []
for path in sorted(base.glob('state-*/traces/*-tools.jsonl')):
    for line in path.read_text().splitlines():
        event = json.loads(line); args = event.get('arguments') or {}
        if event.get('name') == 'repo_search' and event.get('status') == 'error' and type(args.get('limit')) is int and args['limit'] > 30:
            arguments.append(args)
with tempfile.TemporaryDirectory() as directory:
    worker = pathlib.Path(directory) / 'worker.py'
    worker.write_text("import json,sys\nfor line in sys.stdin:\n r=json.loads(line); limit=r.get('limit',20)\n if not 1 <= limit <= 30: print(json.dumps({'ok':False,'error':'invalid query'}),flush=True)\n else: print(json.dumps({'ok':True,'result':{'matches':[],'actualLimit':limit}}),flush=True)\n")
    process = subprocess.Popen(['node', str(ROOT / 'scripts/prospective-agent-mcp-v5.mjs'), '--read-only', '--', 'python3', str(worker)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    successes = 0
    try:
        for i, args in enumerate(arguments):
            request = {'jsonrpc': '2.0', 'id': i, 'method': 'tools/call', 'params': {'name': 'repo_search', 'arguments': args}}
            process.stdin.write(json.dumps(request) + '\n'); process.stdin.flush()
            response = json.loads(process.stdout.readline())['result']
            if not response.get('isError'):
                result = json.loads(response['content'][0]['text'])
                successes += int(result.get('actualLimit') == 30 and result.get('limitAdjustment') == {'requested': args['limit'], 'applied': 30})
    finally:
        process.stdin.close(); process.wait(timeout=10); process.stdout.close(); process.stderr.close()
output = {'recordedOverLimitFailures': len(arguments), 'argumentsAdjustedByRepairedBridge': successes,
          'limits': ['Uses an offline mock worker and recorded arguments, without a model call.',
                     'A mock accepting the adjusted limit does not prove real search relevance or answer quality.']}
destination.write_text(json.dumps(output, indent=2) + '\n')
print(json.dumps(output))
if successes != len(arguments): raise SystemExit('A recorded argument was not adjusted correctly')
