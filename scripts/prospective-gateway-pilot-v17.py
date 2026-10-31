#!/usr/bin/env python3
"""Four additional isolated Moment and math.js issue pairs."""
import importlib.util
import json
import pathlib

import prospective_gateway

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pilot_v16', REPO / 'scripts/prospective-gateway-pilot-v16.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot
pilot.TASKS = {'3980': 'moment', '4641': 'moment', '3600': 'mathjs', '3614': 'mathjs'}
pilot.SEED = 2026103119
pilot.BASES = {p: f'/opt/memex-pilot/workspaces/{p}-base' for p in ('moment', 'mathjs')}
pilot.COMMITS = {'moment': 'c2a703a4d84aa57ee2722ff8fb4a8016279fb3c4',
                 'mathjs': '4f5d049e8d6790d6774acbf73e774c19f5e20db7'}
pilot.ROOT = '/opt/memex-pilot/workspaces/gateway-recovery-v17'
LOCK_SHA = '2195cbcd933fd1a2ed008d97cbb5862e13fea87b78739ce9a4b28961ee46973e'


def budgeted_api(key, model, messages, max_tokens, trace, label, tools=None):
    limit = 2048 if model in ('qwen3.8-flash', 'gemini-3.8-flash') else max_tokens
    return prospective_gateway.call(key, model, messages, limit, trace, label, tools)


pilot.api = budgeted_api


def prepare(root, snapshot):
    if root.exists():
        raise SystemExit('output exists; refusing overwrite')
    source = json.loads(pathlib.Path(snapshot).read_text())['issues']
    if set(source) != {f'{project}-{number}' for number, project in pilot.TASKS.items()}:
        raise SystemExit('unexpected issue set')
    issues = {str(issue['number']): issue for issue in source.values()}
    owners = {'moment': 'moment/moment', 'mathjs': 'josdejong/mathjs'}
    for number, issue in issues.items():
        expected = f"https://github.com/{owners[pilot.TASKS[number]]}/issues/{number}"
        comments = issue['comments']
        if (issue['url'] != expected or issue['state'] != 'OPEN' or comments['pageInfo']['hasNextPage'] or
                comments['totalCount'] != len(comments['nodes'])):
            raise SystemExit('issue is closed, mismatched, or comment snapshot is incomplete')
    root.mkdir(parents=True, mode=0o700)
    contexts = {number: pilot.store_context(issue, root / 'stores' / number) for number, issue in issues.items()}
    pilot.save(root / 'issues.json', issues)
    pilot.save(root / 'contexts.json', contexts)
    checks = {n: {name: pilot.SHA(path.read_bytes()) for name, path in pilot.check_paths(n, project).items()}
              for n, project in pilot.TASKS.items()}
    files = [pathlib.Path(__file__), REPO / 'scripts/prospective-gateway-pilot-v16.py',
             REPO / 'scripts/prospective-gateway-pilot-v15.py', REPO / 'scripts/prospective-real-agent-pilot-v14.py',
             REPO / 'scripts/prospective_gateway.py', REPO / 'scripts/prospective-agent-worker-v3.py',
             REPO / 'scripts/prospective-vm-sandbox.sh', REPO / 'scripts/production-pilot-store.mjs']
    manifest = {
        'kind': 'registered-four-moment-mathjs-issue-pairs', 'createdAt': pilot.NOW(),
        'sourceCommit': pilot.COMMITS, 'mathjsRuntimeLockSha256': LOCK_SHA,
        'runtime': {'nodeVersion': 'v24.18.0', 'nodeBinarySha256': previous.NODE_SHA256,
                    'moment': 'Node module hooks load unbundled source without npm packages.',
                    'mathjs': 'Runtime dependencies installed from generated lock without lifecycle scripts.'},
        'memexCoreCommit': '27b2a1f106c7d717be443614e6bf40226e613074',
        'tasks': pilot.TASKS, 'checks': checks,
        'files': {str(path.relative_to(REPO)): pilot.SHA(path.read_bytes()) for path in files},
        'issuesSha256': pilot.SHA((root / 'issues.json').read_bytes()),
        'contextsSha256': pilot.SHA((root / 'contexts.json').read_bytes()),
        'seed': pilot.SEED, 'schedule': pilot.schedule(), 'solver': pilot.SOLVER,
        'reviewers': list(pilot.REVIEWERS), 'adjudicator': pilot.ADJUDICATOR,
        'maxTurns': pilot.MAX_TURNS, 'maxForcedFinalCalls': 1, 'maxForcedFinalTokens': 1200,
        'maxToolCallsPerTurn': 4, 'maxOutputTokens': 1000,
        'reviewOutputTokenLimits': {'deepseek-flash': 700, 'qwen3.8-flash': 2048},
        'adjudicationOutputTokenLimit': 2048,
        'gatewayPolicy': {'maxAttempts': 3, 'retryOnly': 'explicit HTTP 503',
                          'backoffSeconds': list(prospective_gateway.BACKOFF_SECONDS),
                          'maxRetryAfterSeconds': prospective_gateway.MAX_RETRY_AFTER_SECONDS, 'retryTimeouts': False},
        'stopRule': 'Stop launching calls within a stage after a provider failure or missing usage; preserve all attempts and unknown fees. Never retry a timeout.',
        'costTarget': 'Below $2 estimated, not a hard cap; unknown fees reported separately.',
        'limitations': ['Four additional pairs selected after observing previous batches; not an independent pre-registered 30–50-task cohort.',
                        'Public discussions and PRs can disclose solutions or appear in training; shared repositories and related date issues can correlate.',
                        'Source-only references and small custom tests do not establish full upstream acceptance.',
                        'Pre-seeded short issue discussions are not long production sessions or autonomous memory management.',
                        'Same-proxy AI model provenance is unverified; larger model budgets were selected after observing truncation.',
                        'Retrieved context content and size differ between arms; no production effect or savings claim.'],
    }
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
    for project, base in pilot.BASES.items():
        status = pilot.guest(['git', '-C', base, 'status', '--porcelain=v1'])
        head = pilot.guest(['git', '-C', base, 'rev-parse', 'HEAD'])
        if status.returncode or status.stdout.strip() or head.returncode or head.stdout.strip() != manifest['sourceCommit'][project]:
            raise SystemExit('guest source tree or commit mismatch: ' + project)
    lock = pilot.guest(['bash', '-lc', 'sha256sum "$HOME/staging/mathjs-runtime-20261031/package-lock.json"'])
    node = pilot.guest(['sha256sum', '/opt/memex-pilot/node/bin/node'])
    if lock.returncode or not lock.stdout.startswith(LOCK_SHA + ' ') or node.returncode or not node.stdout.startswith(previous.NODE_SHA256 + ' '):
        raise SystemExit('guest runtime mismatch')


pilot.prepare = prepare
pilot.verify_guest = verify_guest

if __name__ == '__main__':
    pilot.main()
