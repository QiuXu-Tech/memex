#!/usr/bin/env python3
"""Run the independently checked aggregation against the follow-up cohort."""
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PRIVATE = pathlib.Path.home() / '.local/share/memex-forward-20261102/task-state-canary-triage'
PUBLIC = ROOT / 'docs/assets/benchmarks/production-task-state-canary-20261102'

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec); spec.loader.exec_module(obj); return obj

def main():
    if sys.argv[1:] == ['primary']:
        agg = module(ROOT / 'scripts/aggregate-task-state-20261102.py', 'canary_primary')
        agg.BASE, agg.PUBLISHED = PRIVATE, PUBLIC
        output, unblind = agg.reconcile()
        (PUBLIC / 'results.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
        (PUBLIC / 'packet-unblinding.json').write_text(json.dumps(unblind, indent=2) + '\n')
        print(json.dumps({key: output[key] for key in ('registered', 'completePairs', 'validRatedPairs', 'scoreDirections')}))
    elif sys.argv[1:] == ['rescue']:
        agg = module(ROOT / 'scripts/aggregate-task-state-rescue-20261102.py', 'canary_rescue_aggregate')
        agg.rescue.BASE, agg.rescue.OUT, agg.rescue.PUBLISHED = PRIVATE, PRIVATE / 'reviews/posthoc-rescue', PUBLIC / 'packet-commitments.json'
        agg.primary.BASE, agg.primary.PUBLISHED = PRIVATE, PUBLIC
        reg = agg.load(agg.rescue.OUT / 'registration.json')
        assert reg['canaryRescueWrapperSha256'] == agg.rescue.sha(ROOT / 'scripts/rescue-task-state-canary-20261102.py')
        output = agg.reconcile()
        (PUBLIC / 'rescue-results.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({key: output[key] for key in ('primaryValidRatedPairs', 'rescueValidRatedPairs', 'postHocValidRatedPairs', 'postHocScoreDirections')}))
    else: raise SystemExit('usage: aggregate-task-state-canary-20261102.py primary|rescue')

if __name__ == '__main__': main()
