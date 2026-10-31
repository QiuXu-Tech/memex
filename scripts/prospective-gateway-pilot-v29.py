#!/usr/bin/env python3
"""Four additional pre-registered issue pairs after the batch 28 stop."""
import importlib.util
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pilot_v28', REPO / 'scripts/prospective-gateway-pilot-v28.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot
pilot.TASKS = {'827': 'koa', '2179': 'dayjs', '1134': 'datefns', '7362': 'express'}
pilot.SEED = 2026103134
pilot.BASES = {p: f'/opt/memex-pilot/workspaces/{p}-base' for p in pilot.TASKS.values()}
pilot.COMMITS = {'koa': 'b786e7b456782c2cff1d6549cd4c8dba3feeb262',
                 'dayjs': '436bde0bcded312781cbe45dc2b0ef079a36d8e3',
                 'datefns': 'a9739fb3e5384a810e90d7376446f6d84ecc5029',
                 'express': '1c6f1b0fe4000977b9a7b4f34097e4d527dd9824'}
pilot.ROOT = '/opt/memex-pilot/workspaces/gateway-recovery-v29'
previous.previous.OWNERS = {'koa': 'koajs/koa', 'dayjs': 'iamkun/dayjs',
                           'datefns': 'date-fns/date-fns', 'express': 'expressjs/express'}
previous.previous.GUEST_HASHES = {
    '/opt/memex-pilot/node/bin/node': '6bf69d0eda41a12030d5f28d958cd09ce323bc0c13f1ab4d8bb426933aa08812',
    '/opt/memex-pilot/workspaces/datefns-base/node_modules/typescript/package.json': '822ef7ca6452205657b6288b066481ecf508bfbf43455d715cf7d3ec457561e6',
    '/opt/memex-pilot/workspaces/datefns-base/node_modules/typescript/lib/typescript.js': '3ae902c92cc44dace175c0e69e13a4b0899f6983c6121d76b9ab8dd5795e7675',
    '/home/mk-q.guest/staging/koa-runtime-v29/package-lock.json': '8ca21884dcc06055f777877b19ffb9fae927e0d8f9716314750bc5c7506c3942',
    '/home/mk-q.guest/staging/express-runtime-v27/package-lock.json': '7469cd3624c70242507cb024f3fe6912c7200323e028d34893e3032b0cf6cd4a'}


def prepare(root, snapshot):
    previous.prepare(root, snapshot)
    manifest = pilot.integrity(root)
    manifest['kind'] = 'registered-four-new-issue-pairs-v29'
    manifest['runtime'] = 'Node 24.18.0 and pinned runtime dependencies; date-fns TypeScript uses a test-only transpile hook.'
    manifest['costTarget'] = 'Below $1 estimated for four pairs, not a hard cap; proxy usage may exceed requested token limits.'
    manifest['limitations'] = [
        'Selection follows earlier trial results and the batch 28 stop; issue identities are new but statistical independence is not established.',
        'Some projects also appear in earlier batches; source and task dependence remain.',
        'Public issues and PRs may reveal solutions and may appear in model training.',
        'Different retrieved comment IDs do not control history content, length, or quality.',
        'Custom checks and proposed references are partial and do not establish maintainer acceptance.',
        'The Koa reference is a narrow manual port; the date-fns reference corrects a source-only PR that failed the ordinal check.',
        'The Express test calls the response prototype directly rather than running a network server.',
        'Distinct AI model labels share a proxy with unverified provenance.',
        'Short, pre-seeded issue histories do not establish production value or autonomous memory management.'
    ]
    manifest['files']['scripts/prospective-gateway-pilot-v29.py'] = pilot.SHA(pathlib.Path(__file__).read_bytes())
    pilot.save(root / 'manifest.json', manifest)
    pilot.integrity(root)
    print('final v29 manifest sha256:', pilot.SHA((root / 'manifest.json').read_bytes()))


pilot.prepare = prepare
if __name__ == '__main__':
    pilot.main()
