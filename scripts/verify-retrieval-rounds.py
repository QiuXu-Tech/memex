"""Regrade paired wire logs, recheck corpus identity and emit the compact result."""
import argparse
import hashlib
import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from collections import Counter, defaultdict
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
for name in ('archive','evidence'):
    parser.add_argument(name, type=Path)
args = parser.parse_args()
archive, root = args.archive.resolve(), args.evidence.resolve()
frozen = json.loads((root/'freeze.json').read_bytes())
manifest = frozen['manifest']
digest = lambda data: hashlib.sha256(data).hexdigest()
assert digest((root/'queries.jsonl').read_bytes()) == frozen['requestsSha256']
assert digest((archive/'bodies.jsonl').read_bytes()) == frozen['bodyLedgerSha256']
assert digest((Path(manifest['root'])/'index.db').read_bytes()) == frozen['originalIndexSha256']
labels={r['id']:r for r in map(json.loads,(root/'queries.jsonl').read_bytes().splitlines())}
assert len(labels) == frozen['requests'] >= 600
sha = hashlib.sha256()
ledger = {r['id']:r for r in map(json.loads,(archive/'bodies.jsonl').read_bytes().splitlines())}
with sqlite3.connect((root/'store/index.db').as_uri()+'?mode=ro&immutable=1',uri=True) as db:
    seen = set()
    for eid,filename,tokens,cold,status in db.execute('select id,path,tokens,cold,status from records order by rowid'):
        seen.add(eid)
        assert Path(filename).resolve().is_relative_to(root/'store')
        body=Path(filename).read_bytes().split(b'\n---\n',1)[1][:-1]
        bodyhash=digest(body)
        assert bodyhash==ledger[eid]['sha256']
        sha.update(f'{eid} {tokens} {bodyhash} {cold} {status}\n'.encode())
    assert seen==set(ledger)
assert sha.hexdigest()==manifest['datasetSha256']

pairs=defaultdict(dict)
arms=defaultdict(list)
for round_no in (1,2,3):
    for arm in ('baseline','candidate'):
        prefix=f'{arm}-r{round_no}'
        declared=json.loads((root/f'{prefix}-summary.json').read_bytes())
        data=list(map(json.loads,(root/f'{prefix}.jsonl').read_bytes().splitlines()))
        assert len(data)==len(labels) and {r['id'] for r in data}==set(labels)
        assert declared['querySha256']==frozen['requestsSha256']
        pairs[round_no][arm]=[r['id'] for r in data]
        successes=Counter()
        partition=defaultdict(Counter)
        for r in data:
            q=labels[r['id']]
            assert r['request']['params']['arguments']==q['request']
            result=r['response']['result']
            assert not result['isError'] and r['ok']
            ids=re.findall(r'^\d+\. (\S+) ',result['content'][0]['text'],re.M)
            assert len(ids)<=5 and ids==r['hits']
            assert ids or result['content'][0]['text'].startswith('No matching memory records.')
            if arm=='candidate':
                assert [h['id'] for h in result['structuredContent']['hits']]==ids
            for eid in ids:
                assert ledger[eid]['visible']
                assert ledger[eid]['status']!='superseded' or q['request'].get('status')=='superseded'
            success=bool(set(ids)&set(q['relevant'])) if q['relevant'] else not ids
            assert r['success']==success
            group='positive' if q['relevant'] else 'negative'
            successes[group]+=success
            partition[group]['n']+=1
            if q['tiers']:
                tier='-'.join(q['tiers'])
                partition[tier]['n']+=1
                partition[tier]['success']+=success
        series=sorted(r['ms'] for r in data)
        p50=series[math.ceil(len(data)*.5)-1]
        p95=series[math.ceil(len(data)*.95)-1]
        assert (p50,p95)==(declared['all']['p50'],declared['all']['p95'])
        for key in successes:
            assert declared[key]['success']==successes[key]
        file_status = (root/f'{prefix}.jsonl').stat()
        wire_times = dict(firstFileCreationUtc=datetime.fromtimestamp(file_status.st_birthtime, timezone.utc).isoformat(),
                          lastWriteUtc=datetime.fromtimestamp(file_status.st_mtime, timezone.utc).isoformat())
        arms[arm].append(dict(wireTimes=wire_times, round=round_no,positiveHits=successes['positive'],negativeCorrect=successes['negative'],
                              p50ms=p50,p95ms=p95,meetsTargets=p50<=120 and p95<=300 and successes['positive']/partition['positive']['n']>=.95,
                              tierCounts={k:v for k,v in partition.items() if k not in ('positive','negative')},
                              wireSha256=digest((root/f'{prefix}.jsonl').read_bytes()),sources=declared['sources']))
    assert pairs[round_no]['baseline']==pairs[round_no]['candidate']
assert len({tuple(d['baseline']) for d in pairs.values()})==3
for runs in arms.values():
    assert all(run['sources']==runs[0]['sources'] for run in runs)
summary=dict(datasetSha256=sha.hexdigest(),originalIndexSha256=frozen['originalIndexSha256'],
             verifiedCloneBodies=len(ledger),queriesSha256=frozen['requestsSha256'],
             requests=len(labels),positives=sum(bool(q['relevant']) for q in labels.values()),
             negatives=sum(not q['relevant'] for q in labels.values()),perRound=arms,
             extraReadback=json.loads((root/'readback-summary.json').read_bytes()),
             limitations=frozen['limits'],roundOrder=['B1','C1','C2','B2','B3','C3'])
(root/'verified-results.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({arm:[[r['positiveHits'],r['negativeCorrect'],r['p50ms'],r['p95ms']] for r in runs] for arm,runs in arms.items()}))
