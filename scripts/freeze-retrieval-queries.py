"""Freeze the paired research workload from a separate byte-for-byte archive clone."""
import argparse
import hashlib
import json
import random
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
for name in ('archive', 'evidence'):
    parser.add_argument(name, type=Path)
args = parser.parse_args()
archive, evidence = args.archive.resolve(), args.evidence.resolve()
clone = evidence / 'store'
manifest = json.loads((archive / 'manifest.json').read_bytes())
original = Path(manifest['root']).resolve()
assert clone.resolve() != original and (clone / 'index.db').is_file()
assert not (evidence / 'queries.jsonl').exists()
sha = lambda data: hashlib.sha256(data).hexdigest()
assert sha((clone / 'index.db').read_bytes()) == sha((original / 'index.db').read_bytes())
ledger = {r['id']: r for r in map(json.loads, (archive / 'bodies.jsonl').read_bytes().splitlines())}
assert len(ledger) == manifest['verifiedUniqueBodies']
rng = random.Random(2026112601)
with sqlite3.connect(clone / 'index.db') as db:
    db.row_factory = sqlite3.Row
    rows = [dict(r) for r in db.execute('select id,title,status,scope,session_id,workspace_key,cold,path,tokens,kind,provenance_json from records order by id')]
    assert len(rows) == len(ledger)
    relocations = []
    for r in rows:
        eid = r['id']
        path = clone / Path(r['path']).relative_to(original)
        assert path.resolve().is_relative_to(clone) and path.is_file()
        front, body = path.read_bytes().split(b'\n---\n', 1)
        assert sha(body[:-1]) == ledger[eid]['sha256'] and body.endswith(b'\n')
        assert r['tokens'] == ledger[eid]['tokens'] and bool(r['cold']) == ledger[eid]['cold']
        assert r['status'] == ledger[eid]['status']
        assert (r['workspace_key'] == manifest['workspaceKey'] and
                (r['scope'] == 'workspace' or r['session_id'] == manifest['sessionId'])) == ledger[eid]['visible']
        r['source'] = json.loads(r.pop('provenance_json'))['evidence']
        assert json.loads(front.split(b'\nprovenance: ')[1].splitlines()[0])['evidence'] == r['source']
        if eid.startswith('scale-note-'):
            header = body.decode().splitlines()[0]
            topic, context = header[2:].split(' — ')
            r['topic'], r['context'] = topic, context
            assert r['title'].startswith(topic + ' ' + context + ' ')
            r['ref'] = r['title'].split()[-1]
            r['quote'] = re.search(r'(?:after|during) [0-9]+ ms|[0-9]+ inspected objects', body.decode())
            if r['quote']:
                r['quote'] = r['quote'][0]
        r['path'] = path
        relocations.append((str(path), eid))
    db.executemany('update records set path=? where id=?', relocations)
byid = {r['id']: r for r in rows}
ordinary = [r for r in rows if 'topic' in r]
groups = defaultdict(list)
for r in ordinary:
    groups[r['topic'], r['context']].append(r)
cases = []
def add(group, query, allowed, **filters):
    labels = sorted(allowed)
    cases.append(dict(group=group, request=dict(query=query, limit=5, **filters), relevant=labels,
                      tiers=sorted({'cold' if ledger[i]['cold'] else 'hot' for i in labels})))

# Queries name a notebook reference, a descriptive topic, a remembered observation,
# or a provenance filter. No query contains the primary key or a signed answer.
for r in rng.sample(ordinary, 150):
    add('notebook-reference', f"Find the engineering handoff for {r['ref']}", [r['id']])
for (topic, context), members in rng.sample(sorted(groups.items()), 180):
    add('shared-topic', f'{context} for {topic}', [r['id'] for r in members])
for (topic, context), members in rng.sample(sorted(groups.items()), 60):
    observed = [r for r in members if r['quote']]
    assert observed
    phrase = rng.choice(observed)['quote']
    quoted = f'"{phrase}"'
    labels = [r['id'] for r in members if phrase in r['path'].read_bytes().split(b'\n---\n', 1)[1].decode()]
    add('body-observation', f'{topic} {context} {quoted}', labels)
for r in rng.sample(ordinary, 100):
    add('source-version', f"{r['context']} for {r['topic']}", [r['id']],
        source=r['source']['source'], version=r['source']['version'])
for r in rng.sample(ordinary, 60):
    add('wrong-version', r['topic'], [], source=r['source']['source'], version='unpublished-revision')
for n in range(44):
    # Physically absent source, even though the queried topic is present in other sources.
    r = rng.choice(ordinary)
    source = f'synthetic://retention/missing/{n}'
    assert all(e['source']['source'] != source for e in rows)
    add('missing-source', r['topic'], [], source=source)
for eid in ['scale-fern-final', 'scale-alder-current', 'scale-sable-checkpoint', 'scale-heliotrope-checkpoint']:
    r = byid[eid]
    add('decision-distractors', r['title'].split(' – ')[0], [eid])
for eid in ['scale-fern-foreign', 'scale-indigo-private', 'scale-alder-retired']:
    r = byid[eid]
    assert not ledger[eid]['visible'] or r['status'] == 'superseded'
    add('hidden-or-superseded', r['title'], [], source=r['source']['source'], version=r['source']['version'])
r = byid['scale-alder-retired']
add('explicit-history', r['title'], [r['id']], status='superseded', source=r['source']['source'], version=r['source']['version'])
assert len(cases) >= 600 and len({json.dumps(c['request'], sort_keys=True) for c in cases}) == len(cases)
rng.shuffle(cases)
with (evidence / 'queries.jsonl').open('x') as f:
    for i, c in enumerate(cases):
        f.write(json.dumps(dict(id=f'Q{i+1:03d}', **c), ensure_ascii=False) + '\n')
protocol = dict(manifest=manifest, originalIndexSha256=sha((original/'index.db').read_bytes()),
                bodyLedgerSha256=sha((archive/'bodies.jsonl').read_bytes()),
                allClonedBodiesVerified=len(rows), clone=str(clone), requests=len(cases),
                sourceValidityDeadlines=sum('validUntil' in r['source'] for r in rows),
                requestsSha256=sha((evidence/'queries.jsonl').read_bytes()), seed=2026112601,
                metric='A positive succeeds when any of its prelabelled relevant ids appears in the returned top 5. A negative succeeds only with zero hits. Nearest-rank end-to-end MCP p50 and p95 across all requests, including misses. New service per round, warm machine cache allowed. Same request order within a pair; independent seeded shuffles across rounds.',
                limits='Synthetic engineering archive. Topic items have multiple correct records. Notebook-reference and source/version inputs are known locators. Body observations require the topic and quoted phrase in the persisted body. Expiry timestamps absent here; supersession and wrong revisions exist.')
(evidence / 'freeze.json').write_text(json.dumps(protocol, indent=2) + '\n')
print(json.dumps({k: protocol[k] for k in ['allClonedBodiesVerified','requests','requestsSha256','sourceValidityDeadlines']}))
