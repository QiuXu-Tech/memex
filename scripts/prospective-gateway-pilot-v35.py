#!/usr/bin/env python3
"""One new issue and one previously unstarted pair after a timeout."""
import importlib.util
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
PRIVATE = pathlib.Path.home() / '.local/share/memex-prospective-pilot'
spec = importlib.util.spec_from_file_location('pilot_v29', REPO / 'scripts/prospective-gateway-pilot-v29.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot
pilot.TASKS = {'2252': 'yup', '3608': 'mathjs'}
pilot.SEED = 2026103140
pilot.BASES = {p: f'/opt/memex-pilot/workspaces/{p}-base' for p in pilot.TASKS.values()}
pilot.COMMITS = {'yup': 'ff31eee8a2b10c938bb3a22544d9e33957a8cf01', 'mathjs': '4f5d049e8d6790d6774acbf73e774c19f5e20db7'}
pilot.ROOT = '/opt/memex-pilot/workspaces/gateway-recovery-v35'
previous.previous.previous.OWNERS = {'yup': 'jquense/yup', 'mathjs': 'josdejong/mathjs'}
previous.previous.previous.GUEST_HASHES = {
    '/opt/memex-pilot/node/bin/node': '6bf69d0eda41a12030d5f28d958cd09ce323bc0c13f1ab4d8bb426933aa08812',
    '/home/mk-q.guest/staging/yup-runtime-20261031/package-lock.json': 'a004425bf6fe075461651fe021057fcc8b552f154b9abf5e439a384530b4ed3c',
    '/home/mk-q.guest/staging/mathjs-runtime-20261031/package-lock.json': '2195cbcd933fd1a2ed008d97cbb5862e13fea87b78739ce9a4b28961ee46973e',
    '/opt/memex-pilot/workspaces/yup-base/node_modules/typescript/package.json': '822ef7ca6452205657b6288b066481ecf508bfbf43455d715cf7d3ec457561e6',
    '/opt/memex-pilot/workspaces/yup-base/node_modules/typescript/lib/typescript.js': '3ae902c92cc44dace175c0e69e13a4b0899f6983c6121d76b9ab8dd5795e7675'}
prior_solve = pilot.solve


def unstarted_evidence():
    source = PRIVATE / '20261031-independent-batch32'
    manifest = json.loads((source/'manifest.json').read_text());trace=source/'solver-calls.jsonl'
    events = [json.loads(line) for line in trace.read_text().splitlines()]
    paths = [source/'manifest.json',trace];slots=[]
    for slot,assignment in enumerate(manifest['schedule'],1):
        if assignment['issue']!='2252':continue
        result=source/'runs'/f'{slot:02d}'/'result.json';data=json.loads(result.read_text())
        if data.get('status')!='NOT_RUN_AFTER_STOP' or any(str(x.get('label','')).startswith(f'{slot:02d}:') for x in events):
            raise SystemExit('Yup assignment was started')
        paths.append(result);slots.append(slot)
    if len(slots)!=2:raise SystemExit('unexpected unstarted pair')
    return {'slots':slots,'sourceHashes':{str(p.relative_to(PRIVATE)):pilot.SHA(p.read_bytes()) for p in paths}}


def prepare(root, snapshot):
    evidence=unstarted_evidence()
    previous.prepare(root, snapshot)
    manifest=pilot.integrity(root);manifest['kind']='registered-unstarted-and-new-issue-pairs-v35';manifest['unstartedEvidence']=evidence
    manifest['runtime']='Node 24.18.0 with pinned Yup and math.js runtime dependencies; test-only TypeScript hook for Yup.'
    manifest['costTarget']='Below $1 estimated for two pairs, not a hard cap; proxy usage may exceed requested token limits.'
    manifest['limitations']=['Selection follows previous results and a timeout; the Yup pair was previously registered but neither arm started.',
        'These projects appear in earlier batches; distinct issue identities do not establish statistical independence.',
        'Public issues and PRs may reveal solutions and may appear in model training.',
        'Different retrieved comment IDs do not control content, length, or quality.',
        'Frozen custom checks and proposed references are partial and do not establish maintainer acceptance.',
        'The Yup check covers selected abortEarly:false sorting, not the complete form integration.',
        'Distinct AI model names share one proxy of unverified provenance.',
        'Pre-seeded short issue discussions are not production sessions or autonomous memory management.']
    manifest['files']['scripts/prospective-gateway-pilot-v35.py']=pilot.SHA(pathlib.Path(__file__).read_bytes())
    pilot.save(root/'manifest.json',manifest);pilot.integrity(root)
    print('final v35 manifest sha256:',pilot.SHA((root/'manifest.json').read_bytes()))


def solve(root):
    manifest=pilot.integrity(root)
    if unstarted_evidence()!=manifest['unstartedEvidence']:raise SystemExit('unstarted evidence changed')
    prior_solve(root)


pilot.prepare=prepare
pilot.solve=solve
if __name__=='__main__':pilot.main()
