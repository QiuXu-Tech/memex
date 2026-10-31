#!/usr/bin/env python3
"""Three new issue pairs, registered after earlier batch outcomes."""
import importlib.util
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pilot_v29', REPO / 'scripts/prospective-gateway-pilot-v29.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot
pilot.TASKS = {'2214': 'underscore', '2433': 'validator', '2252': 'yup'}
pilot.SEED = 2026103137
pilot.BASES = {p: f'/opt/memex-pilot/workspaces/{p}-base' for p in pilot.TASKS.values()}
pilot.COMMITS = {'underscore': '5c1e5f686f8500af9c9d15614ed60289d6d35d6b',
                 'validator': '9ff342479591ca5a43cb30000195bcf55c1bbed9',
                 'yup': 'ff31eee8a2b10c938bb3a22544d9e33957a8cf01'}
pilot.ROOT = '/opt/memex-pilot/workspaces/gateway-recovery-v32'
previous.previous.previous.OWNERS = {'underscore': 'jashkenas/underscore', 'validator': 'validatorjs/validator.js', 'yup': 'jquense/yup'}
previous.previous.previous.GUEST_HASHES = {
    '/opt/memex-pilot/node/bin/node': '6bf69d0eda41a12030d5f28d958cd09ce323bc0c13f1ab4d8bb426933aa08812',
    '/home/mk-q.guest/staging/yup-runtime-20261031/package-lock.json': 'a004425bf6fe075461651fe021057fcc8b552f154b9abf5e439a384530b4ed3c',
    '/opt/memex-pilot/workspaces/yup-base/node_modules/typescript/package.json': '822ef7ca6452205657b6288b066481ecf508bfbf43455d715cf7d3ec457561e6',
    '/opt/memex-pilot/workspaces/yup-base/node_modules/typescript/lib/typescript.js': '3ae902c92cc44dace175c0e69e13a4b0899f6983c6121d76b9ab8dd5795e7675'}


def prepare(root, snapshot):
    previous.prepare(root, snapshot)
    manifest = pilot.integrity(root)
    manifest['kind'] = 'registered-three-new-issue-pairs-v32'
    manifest['runtime'] = 'Node 24.18.0 and pinned Yup runtime dependencies; test-only hooks load source ESM and TypeScript.'
    manifest['costTarget'] = 'Below $1 estimated for three pairs, not a hard cap; proxy usage may exceed requested token limits.'
    manifest['limitations'] = [
        'Selection follows previous outcomes and an ongoing trial; issue identities are new but statistical independence is not established.',
        'Validator and Yup also appear in earlier batches; public issues or PRs may disclose fixes or be present in model training.',
        'Different retrieved comment IDs do not control history content, length, or quality.',
        'Frozen checks are partial, and proposed references do not establish maintainer acceptance.',
        'The Underscore reference manually ports a proposed native bind fallback to the current module layout.',
        'The Yup check exercises a selected abortEarly:false sorting case; it does not establish a deterministic abortEarly:true contract.',
        'Distinct AI model labels share a proxy with unverified provenance.',
        'Short, pre-seeded issue histories do not establish production value or autonomous memory management.'
    ]
    manifest['files']['scripts/prospective-gateway-pilot-v32.py'] = pilot.SHA(pathlib.Path(__file__).read_bytes())
    pilot.save(root / 'manifest.json', manifest)
    pilot.integrity(root)
    print('final v32 manifest sha256:', pilot.SHA((root / 'manifest.json').read_bytes()))


pilot.prepare = prepare
if __name__ == '__main__':
    pilot.main()
