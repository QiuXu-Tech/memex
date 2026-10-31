#!/usr/bin/env python3
"""Two isolated validator.js issue pairs with a lower-cost adjudication route."""
import importlib.util
import json
import pathlib

import prospective_gateway

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pilot_v20', REPO / 'scripts/prospective-gateway-pilot-v20.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot
pilot.TASKS = {'2295': 'validator', '1309': 'validator'}
pilot.SEED = 2026103124
pilot.BASES = {'validator': '/opt/memex-pilot/workspaces/validator-base'}
pilot.COMMITS = {'validator': '9ff342479591ca5a43cb30000195bcf55c1bbed9'}
pilot.ROOT = '/opt/memex-pilot/workspaces/gateway-recovery-v21'
pilot.ADJUDICATOR = 'gpt-6-astra'
NODE_SHA = '6bf69d0eda41a12030d5f28d958cd09ce323bc0c13f1ab4d8bb426933aa08812'


def prepare(root, snapshot):
    if root.exists():
        raise SystemExit('output exists; refusing overwrite')
    source = json.loads(pathlib.Path(snapshot).read_text())['issues']
    if set(source) != {f'validator-{number}' for number in pilot.TASKS}:
        raise SystemExit('unexpected issue set')
    issues = {str(issue['number']): issue for issue in source.values()}
    for number, issue in issues.items():
        comments = issue['comments']
        if (issue['url'] != f'https://github.com/validatorjs/validator.js/issues/{number}' or
                issue['state'] != 'OPEN' or comments['pageInfo']['hasNextPage'] or
                comments['totalCount'] != len(comments['nodes'])):
            raise SystemExit('issue is closed, mismatched, or comment snapshot is incomplete')
    root.mkdir(parents=True, mode=0o700)
    contexts = {number: pilot.store_context(issue, root / 'stores' / number) for number, issue in issues.items()}
    pilot.save(root / 'issues.json', issues)
    pilot.save(root / 'contexts.json', contexts)
    checks = {n: {name: pilot.SHA(path.read_bytes()) for name, path in pilot.check_paths(n, project).items()}
              for n, project in pilot.TASKS.items()}
    names = ['prospective-gateway-pilot-v21.py', 'prospective-gateway-pilot-v20.py', 'prospective-gateway-pilot-v18.py',
             'prospective-gateway-pilot-v17.py', 'prospective-gateway-pilot-v16.py', 'prospective-gateway-pilot-v15.py',
             'prospective-real-agent-pilot-v14.py', 'prospective_gateway.py', 'prospective-agent-worker-v3.py',
             'prospective-vm-sandbox.sh', 'production-pilot-store.mjs']
    manifest = {'kind': 'registered-two-validator-issue-pairs', 'createdAt': pilot.NOW(),
        'sourceCommit': pilot.COMMITS, 'runtime': {'nodeVersion': 'v24.18.0', 'nodeBinarySha256': NODE_SHA,
        'dependencies': 'Node module hooks load source ESM without external npm packages.'},
        'memexCoreCommit': '27b2a1f106c7d717be443614e6bf40226e613074', 'tasks': pilot.TASKS, 'checks': checks,
        'files': {f'scripts/{name}': pilot.SHA((REPO / 'scripts' / name).read_bytes()) for name in names},
        'issuesSha256': pilot.SHA((root / 'issues.json').read_bytes()), 'contextsSha256': pilot.SHA((root / 'contexts.json').read_bytes()),
        'seed': pilot.SEED, 'schedule': pilot.schedule(), 'solver': pilot.SOLVER,
        'reviewers': list(pilot.REVIEWERS), 'adjudicator': pilot.ADJUDICATOR,
        'maxTurns': pilot.MAX_TURNS, 'maxForcedFinalCalls': 1, 'maxForcedFinalTokens': 1200,
        'maxToolCallsPerTurn': 4, 'maxOutputTokens': 1000,
        'reviewOutputTokenLimits': {'deepseek-flash': 700, 'qwen3.8-flash': 2048}, 'adjudicationOutputTokenLimit': 700,
        'gatewayPolicy': {'maxAttempts': 3, 'retryOnly': 'explicit HTTP 503',
                          'backoffSeconds': list(prospective_gateway.BACKOFF_SECONDS),
                          'maxRetryAfterSeconds': prospective_gateway.MAX_RETRY_AFTER_SECONDS, 'retryTimeouts': False},
        'stopRule': 'Stop launching calls within a stage after provider failure or missing usage; preserve all attempts and unknown fees. Never retry a timeout.',
        'costTarget': 'Below $1 estimated, not a hard cap; unknown fees reported separately.',
        'limitations': ['Two pairs selected after earlier batches; not a pre-registered 30–50-task independent cohort.',
            'Public discussions and PRs can disclose solutions or appear in training; shared project and source exposure can correlate.',
            'Source-only references and small custom tests do not establish upstream acceptance.',
            'The adjudicator has the same model name as the solver; all model names share a proxy with unverified provenance.',
            'Pre-seeded short issue discussions are not long production sessions or autonomous memory management.',
            'Retrieved context content and size differ between arms; no production effect or savings claim.']}
    pilot.save(root / 'manifest.json', manifest)
    print(json.dumps({'manifestSha256': pilot.SHA((root / 'manifest.json').read_bytes()), 'schedule': manifest['schedule']}))


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
    base = pilot.BASES['validator']
    status = pilot.guest(['git', '-C', base, 'status', '--porcelain=v1'])
    head = pilot.guest(['git', '-C', base, 'rev-parse', 'HEAD'])
    node = pilot.guest(['sha256sum', '/opt/memex-pilot/node/bin/node'])
    if (status.returncode or status.stdout.strip() or head.returncode or head.stdout.strip() != manifest['sourceCommit']['validator'] or
            node.returncode or not node.stdout.startswith(NODE_SHA + ' ')):
        raise SystemExit('guest source or runtime mismatch')


pilot.prepare = prepare
pilot.verify_guest = verify_guest

if __name__ == '__main__':
    pilot.main()
