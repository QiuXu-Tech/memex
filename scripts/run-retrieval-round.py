"""Run one frozen workload on the normal stdio MCP server. Keep wire responses and errors."""
import argparse
import hashlib
import json
import math
import random
import re
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('evidence', type=Path)
parser.add_argument('repo', type=Path)
parser.add_argument('arm', choices=('baseline','candidate'))
parser.add_argument('round', type=int, choices=(1,2,3))
args = parser.parse_args()
directory, repo = args.evidence.resolve(), args.repo.resolve()
frozen = json.loads((directory / 'freeze.json').read_bytes())
query_bytes = (directory / 'queries.jsonl').read_bytes()
assert hashlib.sha256(query_bytes).hexdigest() == frozen['requestsSha256']
cases = list(map(json.loads, query_bytes.splitlines()))
random.Random(20261126 + args.round).shuffle(cases)
manifest = frozen['manifest']
prefix = f'{args.arm}-r{args.round}'
node = shutil.which('node')
command = [node, str(repo / 'packages/memex-mcp/bin/server.mjs'), '--root', frozen['clone'],
           '--cwd', manifest['workspace'], '--session', manifest['sessionId'], '--levels', 'l2,l3',
           '--capacity', str(manifest['archiveCapacity']), '--session-capacity', str(manifest['archiveCapacity']),
           '--all-tools']
if args.arm == 'candidate':
    command.append('--evidence-search')
def source_hash(path):
    return hashlib.sha256((repo / path).read_bytes()).hexdigest()
sources = {f: source_hash(f) for f in ['packages/memex-mcp/bin/server.mjs','packages/memex-core/lib/engine.js','packages/memex-core/lib/store.js']}
output = []
with (directory / f'{prefix}.jsonl').open('x') as wire, (directory / f'{prefix}.stderr').open('x') as err:
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True)
    def rpc(method, params, seq=None):
        request = dict(jsonrpc='2.0', method=method, params=params)
        if seq is not None:
            request['id'] = seq
        line = json.dumps(request) + '\n'
        start = time.perf_counter_ns()
        proc.stdin.write(line)
        proc.stdin.flush()
        if seq is None:
            return
        response = proc.stdout.readline()
        ms = (time.perf_counter_ns()-start) / 1e6
        data = json.loads(response)
        assert data['id'] == seq
        return request, data, ms
    try:
        rpc('initialize', dict(protocolVersion='2024-11-05', capabilities={}, clientInfo=dict(name='paired-retrieval', version='1')), 1)
        rpc('notifications/initialized', {})
        for seq, case in enumerate(cases, 2):
            req, response, ms = rpc('tools/call', dict(name='memory_search', arguments=case['request']), seq)
            result = response.get('result', {})
            content = '\n'.join(block['text'] for block in result.get('content', []))
            ids = re.findall(r'^\d+\. (\S+) ', content, re.M)
            ok = 'error' not in response and not result.get('isError') and bool(result)
            assert not ok or ids or content.startswith('No matching memory records.'), content
            match = bool(set(case['relevant']) & set(ids)) if case['relevant'] else not ids
            row = dict(id=case['id'], group=case['group'], positive=bool(case['relevant']),
                       hits=ids, success=ok and match, ok=ok, ms=ms)
            wire.write(json.dumps(dict(**row, request=req, response=response), ensure_ascii=False)+'\n')
            wire.flush()
            output.append(row)
    finally:
        proc.stdin.close()
        assert proc.wait(timeout=30) == 0
def metrics(rows):
    series = sorted(r['ms'] for r in rows)
    return dict(n=len(rows), success=sum(r['success'] for r in rows),
                p50=series[math.ceil(len(rows)*.5)-1], p95=series[math.ceil(len(rows)*.95)-1])
summary = dict(arm=args.arm, round=args.round, command=command, sources=sources, querySha256=frozen['requestsSha256'],
               all=metrics(output), positive=metrics([r for r in output if r['positive']]),
               negative=metrics([r for r in output if not r['positive']]),
               groups={g:metrics([r for r in output if r['group']==g]) for g in Counter(r['group'] for r in output)},
               failed=[r['id'] for r in output if not r['success']], errors=[r['id'] for r in output if not r['ok']])
(directory/f'{prefix}-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(prefix, summary['all'], summary['positive'], summary['negative'], flush=True)
