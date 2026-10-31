#!/usr/bin/env python3
"""Three additional isolated Day.js and math.js issue pairs."""
import importlib.util
import json
import pathlib

import prospective_gateway

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pilot_v17', REPO / 'scripts/prospective-gateway-pilot-v17.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot
pilot.TASKS = {'3062': 'dayjs', '3528': 'mathjs', '3563': 'mathjs'}
pilot.SEED = 2026103121
pilot.BASES = {p: f'/opt/memex-pilot/workspaces/{p}-base' for p in ('dayjs', 'mathjs')}
pilot.COMMITS = {'dayjs': '436bde0bcded312781cbe45dc2b0ef079a36d8e3',
                 'mathjs': '4f5d049e8d6790d6774acbf73e774c19f5e20db7'}
pilot.ROOT = '/opt/memex-pilot/workspaces/gateway-recovery-v18'


def prepare(root, snapshot):
    if root.exists():
        raise SystemExit('output exists; refusing overwrite')
    source = json.loads(pathlib.Path(snapshot).read_text())['issues']
    if set(source) != {f'{project}-{number}' for number, project in pilot.TASKS.items()}:
        raise SystemExit('unexpected issue set')
    issues = {str(issue['number']): issue for issue in source.values()}
    owners = {'dayjs': 'iamkun/dayjs', 'mathjs': 'josdejong/mathjs'}
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
    names = ['prospective-gateway-pilot-v18.py', 'prospective-gateway-pilot-v17.py',
             'prospective-gateway-pilot-v16.py', 'prospective-gateway-pilot-v15.py',
             'prospective-real-agent-pilot-v14.py', 'prospective_gateway.py', 'prospective-agent-worker-v3.py',
             'prospective-vm-sandbox.sh', 'production-pilot-store.mjs']
    manifest = {
        'kind': 'registered-three-dayjs-mathjs-issue-pairs', 'createdAt': pilot.NOW(),
        'sourceCommit': pilot.COMMITS, 'mathjsRuntimeLockSha256': previous.LOCK_SHA,
        'runtime': {'nodeVersion': 'v24.18.0', 'nodeBinarySha256': previous.previous.NODE_SHA256,
                    'dayjs': 'Node module hooks load unbundled source without npm packages.',
                    'mathjs': 'Runtime dependencies installed from generated lock without lifecycle scripts.'},
        'memexCoreCommit': '27b2a1f106c7d717be443614e6bf40226e613074',
        'tasks': pilot.TASKS, 'checks': checks,
        'files': {f'scripts/{name}': pilot.SHA((REPO / 'scripts' / name).read_bytes()) for name in names},
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
        'limitations': ['Three additional pairs selected after observing earlier batches; not a pre-registered 30–50-task independent cohort.',
                        'Public discussions and PRs can disclose solutions or appear in training; common repositories and related issues can correlate.',
                        'Source-only references and small custom tests do not establish full upstream acceptance.',
                        'Pre-seeded short issue discussions are not long production sessions or autonomous memory management.',
                        'Same-proxy AI model provenance is unverified; larger model budgets were selected after observing truncation.',
                        'Retrieved context content and size differ between arms; no production effect or savings claim.'],
    }
    pilot.save(root / 'manifest.json', manifest)
    print(json.dumps({'manifestSha256': pilot.SHA((root / 'manifest.json').read_bytes()), 'schedule': manifest['schedule']}))


pilot.prepare = prepare
pilot.verify_guest = previous.verify_guest

if __name__ == '__main__':
    pilot.main()
