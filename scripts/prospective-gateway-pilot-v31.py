#!/usr/bin/env python3
"""Three new issue pairs, registered after earlier batch outcomes."""
import importlib.util
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pilot_v29', REPO / 'scripts/prospective-gateway-pilot-v29.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot
pilot.TASKS = {'2442': 'dayjs', '2036': 'validator', '3604': 'mathjs'}
pilot.SEED = 2026103136
pilot.BASES = {p: f'/opt/memex-pilot/workspaces/{p}-base' for p in pilot.TASKS.values()}
pilot.COMMITS = {'dayjs': '436bde0bcded312781cbe45dc2b0ef079a36d8e3',
                 'validator': '9ff342479591ca5a43cb30000195bcf55c1bbed9',
                 'mathjs': '4f5d049e8d6790d6774acbf73e774c19f5e20db7'}
pilot.ROOT = '/opt/memex-pilot/workspaces/gateway-recovery-v31'
previous.previous.previous.OWNERS = {'dayjs': 'iamkun/dayjs', 'validator': 'validatorjs/validator.js', 'mathjs': 'josdejong/mathjs'}
previous.previous.previous.GUEST_HASHES = {
    '/opt/memex-pilot/node/bin/node': '6bf69d0eda41a12030d5f28d958cd09ce323bc0c13f1ab4d8bb426933aa08812',
    '/home/mk-q.guest/staging/mathjs-runtime-20261031/package-lock.json': '2195cbcd933fd1a2ed008d97cbb5862e13fea87b78739ce9a4b28961ee46973e'}


def prepare(root, snapshot):
    previous.prepare(root, snapshot)
    manifest = pilot.integrity(root)
    manifest['kind'] = 'registered-three-new-issue-pairs-v31'
    manifest['runtime'] = 'Node 24.18.0 and pinned math.js runtime dependencies; test-only hooks load source ESM.'
    manifest['costTarget'] = 'Below $1 estimated for three pairs, not a hard cap; proxy usage may exceed requested token limits.'
    manifest['limitations'] = [
        'Selection follows previous outcomes and an ongoing trial; issue identities are new but statistical independence is not established.',
        'All projects also appear in earlier batches; public issues or PRs may disclose fixes or be present in model training.',
        'Different retrieved comment IDs do not control history content, length, or quality.',
        'Frozen checks are partial, and proposed references do not establish maintainer acceptance.',
        'The validator reference changes a proposed option default to satisfy the reported default-denial behavior; its broader compatibility is untested.',
        'The math.js check selects the complex LogGamma branch described in the discussion, although the issue initially requested a real value.',
        'Distinct AI model labels share a proxy with unverified provenance.',
        'Short, pre-seeded issue histories do not establish production value or autonomous memory management.'
    ]
    manifest['files']['scripts/prospective-gateway-pilot-v31.py'] = pilot.SHA(pathlib.Path(__file__).read_bytes())
    pilot.save(root / 'manifest.json', manifest)
    pilot.integrity(root)
    print('final v31 manifest sha256:', pilot.SHA((root / 'manifest.json').read_bytes()))


pilot.prepare = prepare
if __name__ == '__main__':
    pilot.main()
