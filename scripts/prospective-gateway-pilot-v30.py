#!/usr/bin/env python3
"""Register the four unattempted v29 issues after a pre-call setup failure."""
import importlib.util
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pilot_v29', REPO / 'scripts/prospective-gateway-pilot-v29.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot
pilot.SEED = 2026103135
pilot.ROOT = '/opt/memex-pilot/workspaces/gateway-recovery-v30'


def prepare(root, snapshot):
    previous.prepare(root, snapshot)
    manifest = pilot.integrity(root)
    manifest['kind'] = 'registered-four-unattempted-issues-after-setup-failure-v30'
    manifest['limitations'].append('Batch 29 stopped on a missing workspace parent before any solver call; all four issue pairs were unattempted. This registration uses a new seed after repair and preserves the stopped batch separately.')
    manifest['files']['scripts/prospective-gateway-pilot-v30.py'] = pilot.SHA(pathlib.Path(__file__).read_bytes())
    pilot.save(root / 'manifest.json', manifest)
    pilot.integrity(root)
    print('final v30 manifest sha256:', pilot.SHA((root / 'manifest.json').read_bytes()))


pilot.prepare = prepare
if __name__ == '__main__':
    pilot.main()
