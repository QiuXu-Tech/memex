"""Verify readback from actual returned ids and record unscoped absent-topic behavior."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

directory, archive = map(lambda p: Path(p).resolve(), sys.argv[1:3])
protocol = json.loads((directory/'freeze.json').read_bytes())
manifest = protocol['manifest']
key = json.loads((archive/'key.json').read_bytes())
repo = Path(__file__).resolve().parent.parent
cmd = [shutil.which('node'), str(repo/'packages/memex-mcp/bin/server.mjs'),
       '--evidence-search', '--root', protocol['clone'], '--cwd', manifest['workspace'],
       '--levels','l2,l3','--session',manifest['sessionId'],'--all-tools',
       '--capacity',str(manifest['archiveCapacity']),'--session-capacity',str(manifest['archiveCapacity'])]
with (directory/'readback.jsonl').open('x') as raw, (directory/'readback.stderr').open('x') as err:
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True)
    def rpc(method, params):
        req = dict(jsonrpc='2.0', id=1, method=method, params=params)
        p.stdin.write(json.dumps(req)+'\n')
        p.stdin.flush()
        data=json.loads(p.stdout.readline())
        raw.write(json.dumps(dict(request=req, response=data), ensure_ascii=False)+'\n')
        return data['result']
    def call(name, **arguments):
        return rpc('tools/call', dict(name=name, arguments=arguments))
    findings = []
    try:
        rpc('initialize', dict(protocolVersion='2024-11-05',capabilities={},clientInfo=dict(name='readback',version='1')))
        p.stdin.write(json.dumps(dict(jsonrpc='2.0',method='notifications/initialized',params={}))+'\n')
        p.stdin.flush()
        for name,query in [('alder','Alder Circuit export contract'),('fern','Fern Lantern continuity ledger'),('sable','Sable Orchard checkpoint register'),('heliotrope','Heliotrope Pier intake checkpoint')]:
            found=call('memory_search',query=query,limit=5)
            top=found['structuredContent']['hits'][0]
            opened=call('memory_open',id=top['id'],maxChars=2000)
            confirmed=top['id'] in key[name]['evidence'] and key[name]['value'] in opened['content'][0]['text']
            findings.append(dict(probe=name,returned=top['id'],source=top['evidence']['source'],version=top['evidence']['version'],openedSignedValue=confirmed))
        for eid in ('scale-fern-foreign','scale-indigo-private'):
            denied=call('memory_open',id=eid)
            findings.append(dict(probe=eid,denied=bool(denied.get('isError'))))
        for query in ('Marigold Narrows post recovery confirmation signature','Indigo Lantern signed maintenance waiver','unknown-receipt-824901','"Marigold Narrows" confirmation'):
            result=call('memory_search',query=query,limit=5)
            visible=[h['id'] for h in result['structuredContent']['hits']]
            findings.append(dict(probe=query,unscopedAbsence=True,returned=visible,empty=not visible))
    finally:
        p.stdin.close()
        assert p.wait(timeout=15)==0
    (directory/'readback-summary.json').write_text(json.dumps(findings,indent=2)+'\n')
    assert all(f.get('openedSignedValue',True) and f.get('denied',True) for f in findings)
    print(json.dumps(findings))
