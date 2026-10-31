#!/usr/bin/env python3
"""Six-issue Day.js instrumentation using the registered gateway policy."""
import importlib.util
import json
import pathlib

import prospective_gateway

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pilot_v15', REPO / 'scripts/prospective-gateway-pilot-v15.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot
pilot.TASKS = {str(number): 'dayjs' for number in (2951, 2479, 2956, 1271, 1923, 2511)}
pilot.SEED = 2026103116
pilot.REVIEWERS = ('deepseek-flash', 'qwen3.8-flash')
pilot.ADJUDICATOR = 'gemini-3.8-flash'
pilot.BASES = {'dayjs': '/opt/memex-pilot/workspaces/dayjs-base'}
pilot.COMMITS = {'dayjs': '436bde0bcded312781cbe45dc2b0ef079a36d8e3'}
pilot.LOCKS = {}
pilot.ROOT = '/opt/memex-pilot/workspaces/gateway-recovery-v16'
NODE_SHA256 = '6bf69d0eda41a12030d5f28d958cd09ce323bc0c13f1ab4d8bb426933aa08812'


def prepare(root, snapshot):
    if root.exists():
        raise SystemExit('output exists; refusing overwrite')
    root.mkdir(parents=True, mode=0o700)
    source = json.loads(pathlib.Path(snapshot).read_text())['data']['repository']
    issues = {str(value['number']): value for value in source.values()}
    if set(issues) != set(pilot.TASKS):
        raise SystemExit('unexpected issue set')
    contexts = {}
    for number, issue in issues.items():
        if (issue['state'] != 'OPEN' or issue['comments']['pageInfo']['hasNextPage'] or
                issue['comments']['totalCount'] != len(issue['comments']['nodes']) or
                issue['url'] != 'https://github.com/iamkun/dayjs/issues/' + number):
            raise SystemExit('issue is closed, mismatched, or has an incomplete comment snapshot')
        contexts[number] = pilot.store_context(issue, root / 'stores' / number)
    pilot.save(root / 'issues.json', issues)
    pilot.save(root / 'contexts.json', contexts)
    checks = {n: {name: pilot.SHA(path.read_bytes()) for name, path in pilot.check_paths(n, project).items()}
              for n, project in pilot.TASKS.items()}
    files = [pathlib.Path(__file__), REPO / 'scripts/prospective-gateway-pilot-v15.py',
             REPO / 'scripts/prospective-real-agent-pilot-v14.py', REPO / 'scripts/prospective_gateway.py',
             REPO / 'scripts/prospective-agent-worker-v3.py', REPO / 'scripts/prospective-vm-sandbox.sh',
             REPO / 'scripts/production-pilot-store.mjs']
    manifest = {
        'kind': 'registered-six-issue-dayjs-instrumentation', 'createdAt': pilot.NOW(),
        'repo': 'iamkun/dayjs', 'sourceCommit': pilot.COMMITS,
        'runtime': {'nodeVersion': 'v24.18.0', 'nodeBinarySha256': NODE_SHA256,
                    'dependencies': 'No external npm packages; checks use Node module hooks to load source ESM.'},
        'memexCoreCommit': '27b2a1f106c7d717be443614e6bf40226e613074',
        'tasks': list(pilot.TASKS), 'checks': checks,
        'files': {str(path.relative_to(REPO)): pilot.SHA(path.read_bytes()) for path in files},
        'issuesSha256': pilot.SHA((root / 'issues.json').read_bytes()),
        'contextsSha256': pilot.SHA((root / 'contexts.json').read_bytes()),
        'seed': pilot.SEED, 'schedule': pilot.schedule(), 'solver': pilot.SOLVER,
        'reviewers': list(pilot.REVIEWERS), 'adjudicator': pilot.ADJUDICATOR,
        'maxTurns': pilot.MAX_TURNS, 'maxForcedFinalCalls': 1, 'maxForcedFinalTokens': 1200,
        'maxToolCallsPerTurn': 4, 'maxOutputTokens': 1000, 'maxReviewTokens': 700,
        'gatewayPolicy': {'maxAttempts': 3, 'retryOnly': 'explicit HTTP 503',
                          'backoffSeconds': list(prospective_gateway.BACKOFF_SECONDS),
                          'maxRetryAfterSeconds': prospective_gateway.MAX_RETRY_AFTER_SECONDS,
                          'retryTimeouts': False},
        'stopRule': 'After bounded 503 retries, stop launching calls within the stage after a provider failure, malformed response or missing usage. Preserve every attempt and unknown fee. Never automatically retry a timeout.',
        'costTarget': 'Under $2 estimated for this six-issue instrumentation batch, not a hard cap. Failed or unreported charges remain unknown.',
        'limitations': [
            'Selected after prior batches and some results were observed; not one pre-registered 30–50-task cohort.',
            'Six issues touch different functional areas, but common project and source exposure prevent an independence guarantee.',
            'Public issue discussions and PRs may disclose proposed solutions or appear in model training.',
            'Source references and issue-specific tests are partial and do not establish maintainer acceptance.',
            'Checks use Node source ESM hooks rather than the published compiled npm package.',
            'Retrieved contexts have different actual lengths and pre-seeded short issue discussions are not production sessions.',
            'Reviews and adjudications are AI through a common proxy; model provenance is unverified.',
            'Autonomous memory lifecycle, production effectiveness and cost savings are not established.',
        ],
    }
    pilot.save(root / 'manifest.json', manifest)
    print(json.dumps({'manifestSha256': pilot.SHA((root / 'manifest.json').read_bytes()),
                      'schedule': manifest['schedule'],
                      'contexts': {n: {'keywordIds': c['keywordIds'], 'memexIds': c['memexIds'],
                                       'memexTokens': c['memexTokens']} for n, c in contexts.items()}},
                     ensure_ascii=False))


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
    source = pilot.BASES['dayjs']
    status = pilot.guest(['git', '-C', source, 'status', '--porcelain=v1'])
    head = pilot.guest(['git', '-C', source, 'rev-parse', 'HEAD'])
    node = pilot.guest(['sha256sum', '/opt/memex-pilot/node/bin/node'])
    if status.returncode or status.stdout.strip() or head.returncode or head.stdout.strip() != manifest['sourceCommit']['dayjs']:
        raise SystemExit('guest Day.js source tree or commit mismatch')
    if node.returncode or not node.stdout.startswith(manifest['runtime']['nodeBinarySha256'] + ' '):
        raise SystemExit('guest Node binary mismatch')


pilot.prepare = prepare
pilot.verify_guest = verify_guest

if __name__ == '__main__':
    pilot.main()
