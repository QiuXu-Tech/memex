#!/usr/bin/env python3
"""Separately registered, budgeted post-hoc re-review of batch 15."""
import argparse
import importlib.util
import pathlib

import prospective_gateway

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('posthoc_v15', REPO / 'scripts/prospective-gateway-posthoc-v15.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot


def budgeted_api(key, model, messages, max_tokens, trace, label, tools=None):
    budget = 2048 if model in ('qwen3.8-flash', 'gemini-3.8-flash') else max_tokens
    return prospective_gateway.call(key, model, messages, budget, trace, label, tools)


pilot.api = budgeted_api


def prepare(source, out, superseded_manifest):
    previous.prepare(source, out)
    manifest = pilot.integrity(out)
    manifest['kind'] = 'posthoc-three-candidate-budgeted-blinded-rereview'
    manifest['supersededNotRunManifestSha256'] = pilot.SHA(superseded_manifest.read_bytes())
    manifest['reviewOutputTokenLimits'] = {'deepseek-flash': 700, 'qwen3.8-flash': 2048}
    manifest['adjudicationOutputTokenLimit'] = 2048
    manifest['limitations'].append('The increased reasoning-model budgets were selected after observing truncation and a separate synthetic probe; this is not the original registered assessment.')
    manifest['files'][str(pathlib.Path(__file__).relative_to(REPO))] = pilot.SHA(pathlib.Path(__file__).read_bytes())
    pilot.save(out / 'manifest.json', manifest)
    pilot.integrity(out)
    print('budgeted manifest sha256:', pilot.SHA((out / 'manifest.json').read_bytes()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source')
    parser.add_argument('--superseded-manifest')
    parser.add_argument('--out', required=True)
    parser.add_argument('--stage', required=True, choices=('prepare', 'review', 'adjudicate'))
    args = parser.parse_args()
    root = pathlib.Path(args.out).resolve()
    if args.stage == 'prepare':
        if not args.source or not args.superseded_manifest:
            raise SystemExit('--source and --superseded-manifest are required')
        prepare(pathlib.Path(args.source).resolve(), root, pathlib.Path(args.superseded_manifest).resolve())
    elif args.stage == 'review':
        pilot.review(root)
    else:
        pilot.adjudicate(root)


if __name__ == '__main__':
    main()
