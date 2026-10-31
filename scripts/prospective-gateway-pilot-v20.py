#!/usr/bin/env python3
"""Two additional isolated math.js issue pairs."""
import importlib.util
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pilot_v18', REPO / 'scripts/prospective-gateway-pilot-v18.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot
pilot.TASKS = {'3644': 'mathjs', '1905': 'mathjs'}
pilot.SEED = 2026103123
pilot.BASES = {'mathjs': '/opt/memex-pilot/workspaces/mathjs-base'}
pilot.COMMITS = {'mathjs': '4f5d049e8d6790d6774acbf73e774c19f5e20db7'}
pilot.ROOT = '/opt/memex-pilot/workspaces/gateway-recovery-v20'


def prepare(root, snapshot):
    previous.prepare(root, snapshot)
    manifest = pilot.integrity(root)
    manifest['kind'] = 'registered-two-mathjs-issue-pairs'
    manifest['runtime'].pop('dayjs', None)
    manifest['files']['scripts/prospective-gateway-pilot-v20.py'] = pilot.SHA(pathlib.Path(__file__).read_bytes())
    manifest['limitations'][0] = 'Two additional pairs selected after earlier batches; not a pre-registered 30–50-task independent cohort.'
    pilot.save(root / 'manifest.json', manifest)
    pilot.integrity(root)
    print('final manifest sha256:', pilot.SHA((root / 'manifest.json').read_bytes()))


pilot.prepare = prepare

if __name__ == '__main__':
    pilot.main()
