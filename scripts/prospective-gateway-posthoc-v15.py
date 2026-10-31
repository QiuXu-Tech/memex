#!/usr/bin/env python3
"""Post-hoc blinded re-review of the three v15 candidates with empty Haiku reviews."""
import argparse
import importlib.util
import json
import pathlib
import shutil

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pilot_v15', REPO / 'scripts/prospective-gateway-pilot-v15.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot
pilot.REVIEWERS = ('deepseek-flash', 'qwen3.8-flash')
pilot.ADJUDICATOR = 'gemini-3.8-flash'
pilot.SEED = 2026103117
original_integrity = pilot.integrity


def check_run_hashes(root, manifest):
    for relative, expected in manifest['runHashes'].items():
        if pilot.SHA((root / relative).read_bytes()) != expected:
            raise SystemExit('copied source result changed: ' + relative)


def integrity(root):
    manifest = original_integrity(root)
    check_run_hashes(root, manifest)
    return manifest


def prepare(source, out):
    if out.exists():
        raise SystemExit('output exists; refusing overwrite')
    manifest = original_integrity(source)
    mapping = json.loads((source / 'blind-key.json').read_text())
    if len(mapping) != 3:
        raise SystemExit('unexpected original review candidate count')
    original_reviews = {}
    for blind in mapping:
        for model in ('deepseek-flash', 'claude-haiku-4-5'):
            path = source / 'reviews' / f'{blind}-{model}.json'
            data = json.loads(path.read_text())
            if model == 'deepseek-flash' and not data['parsed']['valid']:
                raise SystemExit('original first review was not valid')
            if model == 'claude-haiku-4-5' and data['parsed'].get('error') != 'empty_or_truncated':
                raise SystemExit('original second review was not empty or truncated')
            original_reviews[path.name] = pilot.SHA(path.read_bytes())
    out.mkdir(parents=True, mode=0o700)
    for name in ('issues.json', 'contexts.json'):
        shutil.copyfile(source / name, out / name)
        (out / name).chmod(0o600)
    hashes = {}
    for slot in range(1, len(manifest['schedule']) + 1):
        source_dir = source / 'runs' / f'{slot:02d}'
        target_dir = out / 'runs' / f'{slot:02d}'
        target_dir.mkdir(parents=True, mode=0o700)
        for name in ('result.json', 'candidate.diff'):
            src = source_dir / name
            if not src.exists():
                raise SystemExit('missing original run file: ' + str(src))
            target = target_dir / name
            shutil.copyfile(src, target)
            target.chmod(0o600)
            hashes[str(target.relative_to(out))] = pilot.SHA(target.read_bytes())
    manifest.update({
        'kind': 'posthoc-three-candidate-blinded-rereview', 'createdAt': pilot.NOW(),
        'sourceManifestSha256': pilot.SHA((source / 'manifest.json').read_bytes()),
        'originalReviewHashes': original_reviews, 'runHashes': hashes,
        'selection': 'All three candidates from batch 15 with an original valid DeepSeek rating and an empty or truncated original Haiku rating; the unreviewable fourth attempt remains excluded.',
        'seed': pilot.SEED, 'reviewers': list(pilot.REVIEWERS), 'adjudicator': pilot.ADJUDICATOR,
        'limitations': ['Post-hoc model replacement and candidate selection after observing empty reviews; original ratings remain unchanged.',
                        'Two AI reviewers and a third AI adjudicator use the same proxy, not independent human assessment.',
                        'Short public histories and partial tests do not establish production value.'],
    })
    manifest['files'][str(pathlib.Path(__file__).relative_to(REPO))] = pilot.SHA(pathlib.Path(__file__).read_bytes())
    pilot.save(out / 'manifest.json', manifest)
    print(json.dumps({'candidates': len(mapping), 'manifestSha256': pilot.SHA((out / 'manifest.json').read_bytes())}))


pilot.integrity = integrity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source')
    parser.add_argument('--out', required=True)
    parser.add_argument('--stage', required=True, choices=('prepare', 'review', 'adjudicate'))
    args = parser.parse_args()
    out = pathlib.Path(args.out).resolve()
    if args.stage == 'prepare':
        if not args.source:
            raise SystemExit('--source is required')
        prepare(pathlib.Path(args.source).resolve(), out)
    elif args.stage == 'review':
        pilot.review(out)
    else:
        pilot.adjudicate(out)


if __name__ == '__main__':
    main()
