#!/usr/bin/env python3
"""Apply the same separately registered rescue procedure to the follow-up."""
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('canary_rescue', ROOT / 'scripts/rescue-task-state-reviews-20261102.py')
rescue = importlib.util.module_from_spec(spec); spec.loader.exec_module(rescue)
rescue.BASE = pathlib.Path.home() / '.local/share/memex-forward-20261102/task-state-canary-triage'
rescue.OUT = rescue.BASE / 'reviews/posthoc-rescue'
rescue.PUBLISHED = ROOT / 'docs/assets/benchmarks/production-task-state-canary-20261102/packet-commitments.json'

def prepare():
    rescue.prepare()
    path = rescue.OUT / 'registration.json'; reg = rescue.load(path)
    reg['canaryRescueWrapperSha256'] = rescue.sha(pathlib.Path(__file__))
    path.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'finalRegistrationSha256': rescue.sha(path)}), flush=True)

def run():
    assert rescue.load(rescue.OUT / 'registration.json')['canaryRescueWrapperSha256'] == rescue.sha(pathlib.Path(__file__))
    rescue.run()

if __name__ == '__main__':
    if sys.argv[1:] == ['prepare']: prepare()
    elif sys.argv[1:] == ['run']: run()
    else: raise SystemExit('usage: rescue-task-state-canary-20261102.py prepare|run')
