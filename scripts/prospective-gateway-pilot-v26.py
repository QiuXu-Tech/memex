#!/usr/bin/env python3
"""Re-register only the never-started Chart.js pair after a transport stop."""
import importlib.util
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pilot_v25', REPO / 'scripts/prospective-gateway-pilot-v25.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot
pilot.TASKS = {'12191': 'chartjs'}
pilot.SEED = 2026103129
pilot.BASES = {'chartjs': '/opt/memex-pilot/workspaces/chartjs-base'}
pilot.COMMITS = {'chartjs': '71d44219e79e3ac41e6f9dc907022eebf574868d'}
pilot.ROOT = '/opt/memex-pilot/workspaces/gateway-recovery-v26'


def unstarted(source):
    manifest = json.loads((source / 'manifest.json').read_text())
    slots = [i for i, row in enumerate(manifest['schedule'], 1) if row['issue'] == '12191']
    if len(slots) != 2:
        raise SystemExit('unexpected prior assignment set')
    trace = [json.loads(line) for line in (source / 'solver-calls.jsonl').read_text().splitlines()]
    hashes = {}
    for slot in slots:
        path = source / 'runs' / f'{slot:02d}' / 'result.json'
        if json.loads(path.read_text()).get('status') != 'NOT_RUN_AFTER_STOP':
            raise SystemExit('prior assignment already started')
        if any(row.get('operationLabel', '').startswith(f'{slot:02d}:') for row in trace):
            raise SystemExit('prior solver request already started')
        hashes[f'runs/{slot:02d}/result.json'] = pilot.SHA(path.read_bytes())
    return hashes


def prepare(root, snapshot):
    source = root.parent / '20261031-mixed-batch25'
    hashes = unstarted(source)
    previous.prepare(root, snapshot)
    manifest = pilot.integrity(root)
    manifest['kind'] = 'registered-previously-unstarted-chartjs-pair'
    manifest['previousManifestSha256'] = pilot.SHA((source / 'manifest.json').read_bytes())
    manifest['previousSolverLogSha256'] = pilot.SHA((source / 'solver-calls.jsonl').read_bytes())
    manifest['previousUnstartedResultHashes'] = hashes
    manifest['files']['scripts/prospective-gateway-pilot-v26.py'] = pilot.SHA(pathlib.Path(__file__).read_bytes())
    manifest['limitations'][0] = 'One previously registered but never-started pair selected after a transport failure; not a pre-registered independent cohort.'
    manifest['limitations'] = [s for s in manifest['limitations'] if 'Validator #912' not in s]
    pilot.save(root / 'manifest.json', manifest)
    pilot.integrity(root)
    print('final manifest sha256:', pilot.SHA((root / 'manifest.json').read_bytes()))


pilot.prepare = prepare

if __name__ == '__main__':
    pilot.main()
