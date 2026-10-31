#!/usr/bin/env python3
"""Post-hoc exact reference-label mapping; never changes original model outputs."""
import argparse
import importlib.util
import json
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pilot_v14', REPO / 'scripts/prospective-real-agent-pilot-v14.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)
ALIASES = {'issue': 'issue', 'candidate': 'candidate', 'candidateDiff': 'candidate',
           'candidateFinal': 'candidate', 'checks': 'checks', 'acceptance': 'checks',
           'regressionControls': 'checks'}


def normalize(content, finish):
    original = pilot.check_rating(content, finish)
    if original['valid']:
        return {'status': 'VALID_UNCHANGED', 'parsed': original, 'changes': []}
    if finish != 'stop' or not isinstance(content, str):
        return {'status': 'INVALID', 'original': original}
    try:
        value = json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', content.strip()))
        refs = value['references']
        if not isinstance(refs, list) or not refs or any(not isinstance(x, str) or x not in ALIASES for x in refs):
            raise ValueError('unknown reference')
        changes = [{'original': x, 'normalized': ALIASES[x]} for x in refs if x != ALIASES[x]]
        value['references'] = list(dict.fromkeys(ALIASES[x] for x in refs))
        parsed = pilot.check_rating(json.dumps(value, ensure_ascii=False), finish)
        if not parsed['valid']:
            raise ValueError('other invalid field')
        return {'status': 'POSTHOC_NORMALIZED', 'parsed': parsed, 'changes': changes, 'original': original}
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return {'status': 'INVALID', 'original': original}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--trace', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    path = pathlib.Path(args.trace)
    out = pathlib.Path(args.out)
    if out.exists():
        raise SystemExit('output exists; refusing overwrite')
    rows = {}
    for line in path.read_text().splitlines():
        event = json.loads(line)
        if event['status'] == 'started':
            continue
        rows[event['label']] = normalize((event.get('message') or {}).get('content'), event.get('finishReason'))
    pilot.save(out, {'kind': 'posthoc-exact-reference-label-normalization',
                     'inputSha256': pilot.SHA(path.read_bytes()),
                     'scriptSha256': pilot.SHA(pathlib.Path(__file__).read_bytes()),
                     'mapping': ALIASES, 'rows': rows})
    print(json.dumps({k: v['status'] for k, v in rows.items()}))


if __name__ == '__main__':
    main()
