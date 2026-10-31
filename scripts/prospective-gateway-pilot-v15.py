#!/usr/bin/env python3
"""Two-issue registered instrumentation pilot using bounded 503 recovery."""
import importlib.util
import json
import pathlib

import prospective_gateway

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('registered_pilot', REPO / 'scripts/prospective-real-agent-pilot-v14.py')
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)

pilot.TASKS = {'16126': 'prettier', '17487': 'prettier'}
pilot.SEED = 2026103115
pilot.SOLVER = 'gpt-6-astra'
pilot.REVIEWERS = ('deepseek-flash', 'claude-haiku-4-5')
pilot.ADJUDICATOR = 'qwen3.8-flash'
pilot.ROOT = '/opt/memex-pilot/workspaces/gateway-recovery-v15'
pilot.api = prospective_gateway.call


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
                issue['url'] != 'https://github.com/prettier/prettier/issues/' + number):
            raise SystemExit('issue is closed, mismatched, or has an incomplete comment snapshot')
        contexts[number] = pilot.store_context(issue, root / 'stores' / number)
    pilot.save(root / 'issues.json', issues)
    pilot.save(root / 'contexts.json', contexts)
    checks = {n: {name: pilot.SHA(path.read_bytes()) for name, path in pilot.check_paths(n, project).items()}
              for n, project in pilot.TASKS.items()}
    files = [pathlib.Path(__file__), REPO / 'scripts/prospective-real-agent-pilot-v14.py',
             REPO / 'scripts/prospective_gateway.py', REPO / 'scripts/prospective-agent-worker-v3.py',
             REPO / 'scripts/prospective-vm-sandbox.sh', REPO / 'scripts/production-pilot-store.mjs']
    manifest = {
        'kind': 'registered-two-issue-gateway-recovery-instrumentation',
        'createdAt': pilot.NOW(), 'repo': 'prettier/prettier',
        'sourceCommit': pilot.COMMITS, 'runtimeLockSha256': pilot.LOCKS,
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
        'stopRule': 'After bounded 503 retries, stop launching calls within the stage after a provider failure, malformed response or missing usage. Preserve every attempt, missing result and unknown fee. Never automatically retry a timeout.',
        'costTarget': 'Under $1 estimated for this two-issue instrumentation pilot, not a hard cap. Failed or unreported charges remain unknown.',
        'limitations': [
            'Two issues selected after the previous study and gateway failures; not a pre-registered 30–50-task cohort.',
            'Public issue discussions and proposed PRs can disclose solutions or appear in model training.',
            'The YAML issue and an earlier task touch a common source file, though the cited patches change different functions.',
            'Pre-seeded issue comments are short and are not production sessions or autonomous memory lifecycle management.',
            'Exact retrieval content and token counts differ by condition even though tools and limits are shared.',
            'Source-only references, the manually ported JSX reference and custom checks are not full upstream acceptance.',
            'The reviewers and adjudicator are AI model names through the same proxy, with provenance unverified.',
            'No production effectiveness or cost-savings claim.',
        ],
    }
    pilot.save(root / 'manifest.json', manifest)
    print(json.dumps({'manifestSha256': pilot.SHA((root / 'manifest.json').read_bytes()),
                      'schedule': manifest['schedule'],
                      'contexts': {n: {'keywordIds': c['keywordIds'], 'memexIds': c['memexIds'],
                                       'memexTokens': c['memexTokens']} for n, c in contexts.items()}},
                     ensure_ascii=False))


pilot.prepare = prepare

if __name__ == '__main__':
    pilot.main()
