#!/usr/bin/env python3
"""Five new issue pairs with preregistered nonidentical retrieved histories."""
import importlib.util
import json
import pathlib

import prospective_gateway

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pilot_v25', REPO / 'scripts/prospective-gateway-pilot-v25.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot
pilot.TASKS = {'2430': 'validator', '2137': 'ramda', '4096': 'datefns', '3134': 'mathjs', '2281': 'dayjs'}
pilot.SEED = 2026103132
pilot.BASES = {p: f'/opt/memex-pilot/workspaces/{p}-base' for p in pilot.TASKS.values()}
pilot.COMMITS = {'validator': '9ff342479591ca5a43cb30000195bcf55c1bbed9',
                 'ramda': 'f4b2e35ff433e18c751326b82acc3c6ab3585e18',
                 'datefns': 'a9739fb3e5384a810e90d7376446f6d84ecc5029',
                 'mathjs': '4f5d049e8d6790d6774acbf73e774c19f5e20db7',
                 'dayjs': '436bde0bcded312781cbe45dc2b0ef079a36d8e3'}
pilot.ROOT = '/opt/memex-pilot/workspaces/gateway-recovery-v27'
pilot.REVIEWERS = ('deepseek-flash', 'qwen3.8-flash')
pilot.ADJUDICATOR = 'gpt-6.1-sol'
OWNERS = {'validator': 'validatorjs/validator.js', 'ramda': 'ramda/ramda', 'datefns': 'date-fns/date-fns',
          'mathjs': 'josdejong/mathjs', 'dayjs': 'iamkun/dayjs'}
GUEST_HASHES = {'/opt/memex-pilot/node/bin/node': '6bf69d0eda41a12030d5f28d958cd09ce323bc0c13f1ab4d8bb426933aa08812',
                '/opt/memex-pilot/workspaces/datefns-base/node_modules/typescript/package.json': '822ef7ca6452205657b6288b066481ecf508bfbf43455d715cf7d3ec457561e6',
                '/opt/memex-pilot/workspaces/datefns-base/node_modules/typescript/lib/typescript.js': '3ae902c92cc44dace175c0e69e13a4b0899f6983c6121d76b9ab8dd5795e7675',
                '/home/mk-q.guest/staging/mathjs-runtime-20261031/package-lock.json': '2195cbcd933fd1a2ed008d97cbb5862e13fea87b78739ce9a4b28961ee46973e'}


def api(key, model, messages, max_tokens, trace, label, tools=None):
    limit = {'qwen3.8-flash': 2048, 'gpt-6.1-sol': 1200}.get(model, max_tokens)
    return prospective_gateway.call(key, model, messages, limit, trace, label, tools)


pilot.api = api


def distinct_history(context):
    return bool(context['keywordIds']) and set(context['keywordIds']) != set(context['memexIds'] or [])


def prepare(root, snapshot):
    if root.exists():
        raise SystemExit('output exists; refusing overwrite')
    source = json.loads(pathlib.Path(snapshot).read_text())['issues']
    if set(source) != {f'{project}-{number}' for number, project in pilot.TASKS.items()}:
        raise SystemExit('unexpected issue set')
    issues = {str(issue['number']): issue for issue in source.values()}
    root.mkdir(parents=True, mode=0o700)
    contexts = {}
    for number, issue in issues.items():
        comments = issue['comments']
        if (issue['url'] != f'https://github.com/{OWNERS[pilot.TASKS[number]]}/issues/{number}' or
                issue['state'] != 'OPEN' or comments['pageInfo']['hasNextPage'] or
                comments['totalCount'] != len(comments['nodes']) or not comments['nodes']):
            raise SystemExit('issue closed, mismatched or missing complete discussion: ' + number)
        context = pilot.store_context(issue, root / 'stores' / number)
        if not distinct_history(context):
            raise SystemExit('retrieved history IDs identical or empty: ' + number)
        contexts[number] = context
    pilot.save(root / 'issues.json', issues)
    pilot.save(root / 'contexts.json', contexts)
    names = ['prospective-gateway-pilot-v27.py', 'prospective-gateway-pilot-v25.py', 'prospective-gateway-pilot-v24.py',
             'prospective-gateway-pilot-v23.py', 'prospective-gateway-pilot-v22.py', 'prospective-gateway-pilot-v21.py',
             'prospective-gateway-pilot-v20.py', 'prospective-gateway-pilot-v18.py', 'prospective-gateway-pilot-v17.py',
             'prospective-gateway-pilot-v16.py', 'prospective-gateway-pilot-v15.py', 'prospective-real-agent-pilot-v14.py',
             'prospective_gateway.py', 'prospective-agent-worker-v3.py', 'prospective-vm-sandbox.sh', 'production-pilot-store.mjs']
    manifest = {'kind': 'registered-five-distinct-project-issue-pairs-v27', 'createdAt': pilot.NOW(),
                'sourceCommit': pilot.COMMITS, 'tasks': pilot.TASKS,
                'memexCoreCommit': '27b2a1f106c7d717be443614e6bf40226e613074', 'guestHashes': GUEST_HASHES,
                'runtime': 'Node 24.18.0; date-fns uses the test-only TypeScript 5.9.3 transpile hook from the existing Yup runtime. math.js uses the pinned runtime lock.',
                'files': {f'scripts/{name}': pilot.SHA((REPO / 'scripts' / name).read_bytes()) for name in names},
                'checks': {n: {name: pilot.SHA(path.read_bytes()) for name, path in pilot.check_paths(n, project).items()}
                           for n, project in pilot.TASKS.items()},
                'issuesSha256': pilot.SHA((root / 'issues.json').read_bytes()), 'contextsSha256': pilot.SHA((root / 'contexts.json').read_bytes()),
                'seed': pilot.SEED, 'schedule': pilot.schedule(), 'solver': pilot.SOLVER,
                'reviewers': list(pilot.REVIEWERS), 'adjudicator': pilot.ADJUDICATOR,
                'maxTurns': pilot.MAX_TURNS, 'maxForcedFinalCalls': 1, 'maxForcedFinalTokens': 1200,
                'maxToolCallsPerTurn': 4, 'maxOutputTokens': 1000,
                'reviewOutputTokenLimits': {'deepseek-flash': 700, 'qwen3.8-flash': 2048}, 'adjudicationOutputTokenLimit': 1200,
                'gatewayPolicy': {'maxAttempts': 3, 'retryOnly': 'explicit HTTP 503', 'backoffSeconds': list(prospective_gateway.BACKOFF_SECONDS),
                                  'maxRetryAfterSeconds': prospective_gateway.MAX_RETRY_AFTER_SECONDS, 'retryTimeouts': False},
                'stopRule': 'Stop launching calls within each stage after provider failure or missing usage; preserve failed, missing and unknown costs. No timeout retry.',
                'costTarget': 'Below $1 estimated for the five pairs; not a hard cap. Requested model limits may be exceeded according to earlier gateway usage.',
                'limitations': ['Selection follows previous outcomes; new issue identities are distinct but statistical independence is not established.',
                                'Public comments or PRs may reveal solutions and be present in model training; some cases include explicit proposed fixes.',
                                'Distinct retrieved comment IDs do not control content, length, quality, or eliminate task dependence.',
                                'Source-only proposed references and small custom checks do not establish maintainer acceptance.',
                                'The date-fns check executes TypeScript source through a test-only hook rather than the published package.',
                                'The distinct reviewer and adjudicator model names share a proxy whose actual provenance is not verified.',
                                'Pre-seeded short issue discussions are not production sessions or autonomous memory management.']}
    pilot.save(root / 'manifest.json', manifest)
    print(json.dumps({'manifestSha256': pilot.SHA((root / 'manifest.json').read_bytes()), 'schedule': manifest['schedule'],
                      'contexts': {n: {'keywordIds': c['keywordIds'], 'memexIds': c['memexIds']} for n, c in contexts.items()}}))


def verify_guest(manifest):
    pairs = [(REPO / 'scripts/prospective-agent-worker-v3.py', '/opt/memex-pilot/prospective-agent-worker-v3.py'),
             (REPO / 'scripts/prospective-vm-sandbox.sh', '/opt/memex-pilot/prospective-vm-sandbox.sh')]
    for number, project in pilot.TASKS.items():
        paths = pilot.check_paths(number, project)
        pairs.extend([(paths['public'], f'{pilot.CHECKS}/{project}-{number}-public/verify.js'),
                      (paths['acceptance'], f'{pilot.CHECKS}/{project}-{number}-acceptance/verify.js'),
                      (paths['regressionControls'], f'{pilot.CHECKS}/regression-{project}-{number}/verify.js')])
    for local, remote in pairs:
        result = pilot.guest(['sha256sum', remote])
        if result.returncode or not result.stdout.startswith(pilot.SHA(local.read_bytes()) + ' '):
            raise SystemExit('guest file mismatch: ' + remote)
    for project, base in pilot.BASES.items():
        status = pilot.guest(['git', '-C', base, 'status', '--porcelain=v1'])
        head = pilot.guest(['git', '-C', base, 'rev-parse', 'HEAD'])
        if status.returncode or status.stdout.strip() or head.returncode or head.stdout.strip() != manifest['sourceCommit'][project]:
            raise SystemExit('guest source mismatch: ' + project)
    for path, digest in manifest['guestHashes'].items():
        result = pilot.guest(['sha256sum', path])
        if result.returncode or not result.stdout.startswith(digest + ' '):
            raise SystemExit('guest runtime mismatch: ' + path)


pilot.prepare = prepare
pilot.verify_guest = verify_guest

if __name__ == '__main__':
    pilot.main()
