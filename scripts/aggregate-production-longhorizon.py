#!/usr/bin/env python3
"""Summarize the preserved private traces without publishing conversations."""
import argparse, collections, datetime, decimal, hashlib, json, pathlib, re, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pilot_codex_result import classify_turn

parser = argparse.ArgumentParser()
parser.add_argument('--base', required=True, type=pathlib.Path)
parser.add_argument('--out', required=True, type=pathlib.Path)
args = parser.parse_args()
base = args.base
def load(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def events(path):
    rows = []
    for line in path.read_text().splitlines():
        try: rows.append(json.loads(line))
        except ValueError: pass
    return rows
def usage_total(rows, keys):
    return {key: sum((row or {}).get(key, 0) for row in rows) for key in keys}
def review_scores(directory, name):
    key = load(directory / f'{name}-key.json')
    out = []
    for model in ('gpt-6.1-sol', 'claude-haiku-4-5', 'adjudication'):
        path = directory / f'{name}-{model}.json'
        if not path.exists():
            out.append({'reviewer': model, 'status': 'NOT RUN'})
            continue
        row = load(path); ratings = row.get('ratings') or {}
        out.append({'reviewer': model, 'status': row.get('status'),
                    'scores': {key[x['id']]: x['score'] for x in ratings.get('candidates', [])},
                    'reasons': {key[x['id']]: x['reason'] for x in ratings.get('candidates', [])},
                    'materialDisagreement': ratings.get('materialDisagreement'), 'error': row.get('error')})
    return out

registration = load(base / 'registration.json')
tasks = []
codex_usage, codex_missing, codex_stages = [], 0, []
for task in registration['tasks']:
    name = task['id']; arms = {}
    for arm in ('baseline', 'memex'):
        outcome = load(base / 'results' / f'{name}-{arm}-outcome.json')
        stages = []
        for number in (1, 2, 3):
            path = base / 'results' / f'{name}-{arm}-s{number}.json'
            if not path.exists(): continue
            row = load(path); trace = base / 'traces' / f'{name}-{arm}-s{number}-events.jsonl'
            observed = classify_turn(events(trace), exit_code=row['exitCode'], timed_out=row['timeout'])
            calls = collections.Counter(x['tool'] for x in row['calls'] if x['server'] == 'memex')
            usage = row['usage'][0] if row['usage'] else None
            if usage is None: codex_missing += 1
            else: codex_usage.append(usage)
            stage = {'number': number, 'exitCode': row['exitCode'], 'timeout': row['timeout'],
                     'turnCompleted': observed['turnCompleted'], 'answerPresent': observed['answerPresent'],
                     'processStatus': observed['processStatus'], 'usage': usage,
                     'memoryCalls': dict(calls), 'traceSha256': sha(trace)}
            stages.append(stage); codex_stages.append(stage)
        arms[arm] = {'stages': stages, 'strictCompletedSessions': outcome['sessionsCompleted'],
                     'fixedVerifierExitCode': outcome['testExitCode'], 'patchSha256': outcome['patchSha256'],
                     'patchBytes': outcome['patchBytes']}
    tasks.append({'id': name, 'repo': task['repo'], 'issueUrl': task['issueUrl'],
                  'sourceCommit': task['sourceCommit'], 'sourceView': task['sourceView'],
                  'arms': arms, 'reviews': review_scores(base / 'reviews', name)})

recovery = base / 'claude-recovery'
budget_results = [load(p) for p in sorted((recovery / 'results').glob('*-s[123].json'))]
budget_events = sorted((recovery / 'traces').glob('*-events.jsonl'))
budget_no_result = [p.name for p in budget_events if not any(e.get('type') == 'result' for e in events(p))]
capped = base / 'claude-capped'
claude_rows = {}
claude_keys = ['input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens', 'output_tokens']
for arm in ('baseline', 'memex'):
    paths = sorted((capped / 'results').glob(f'lodash-{arm}-s[123].json'))
    paths += sorted((capped / 'results').glob(f'lodash-{arm}-resume-s[123].json'))
    rows = [load(p) for p in paths]
    claude_rows[arm] = {'stages': [{k: x.get(k) for k in ('stage', 'responseCompleted', 'timeout',
                         'resultSubtype', 'shutdownTimeoutAfterResult', 'usage', 'clientListPriceUsd')} for x in rows],
                        'reportedUsage': usage_total([x.get('usage') for x in rows], claude_keys),
                        'clientListPriceUsd': str(sum((decimal.Decimal(str(x.get('clientListPriceUsd') or 0)) for x in rows), decimal.Decimal(0)))}
    primary = load(capped / 'results' / f'lodash-{arm}-outcome.json')
    claude_rows[arm]['originalAttempt'] = {k: primary[k] for k in ('sessionsCompleted', 'testExitCode', 'patchSha256')}
    if arm == 'memex':
        resumed = load(capped / 'results' / 'lodash-memex-resume-outcome.json')
        claude_rows[arm]['posthocResume'] = {k: resumed[k] for k in ('sessionsCompleted', 'testExitCode', 'patchSha256')}
        claude_rows[arm]['posthocResume']['distinctSessionIds'] = len(set(resumed['sessionIds']))

def claude_memory_calls(filename):
    calls = collections.Counter()
    for event in events(capped / 'traces' / filename):
        if event.get('type') == 'assistant':
            for item in (event.get('message') or {}).get('content', []):
                if item.get('type') == 'tool_use' and item.get('name', '').startswith('mcp__memex__'):
                    calls[item['name'].removeprefix('mcp__memex__')] += 1
    return dict(calls)

def memory_chain():
    written_tool_ids, written_ids, opened_ids = set(), set(), set()
    for event in events(capped / 'traces' / 'lodash-memex-resume-s2-events.jsonl'):
        if event.get('type') == 'assistant':
            for item in (event.get('message') or {}).get('content', []):
                if item.get('type') == 'tool_use' and item.get('name') == 'mcp__memex__memory_write':
                    written_tool_ids.add(item.get('id'))
        if event.get('type') == 'user':
            for item in (event.get('message') or {}).get('content', []):
                if item.get('type') == 'tool_result' and item.get('tool_use_id') in written_tool_ids:
                    written_ids.update(re.findall(r'mem_[0-9a-f]{10}', str(item.get('content'))))
    for event in events(capped / 'traces' / 'lodash-memex-resume-s3-events.jsonl'):
        if event.get('type') == 'assistant':
            for item in (event.get('message') or {}).get('content', []):
                if item.get('type') == 'tool_use' and item.get('name') == 'mcp__memex__memory_open':
                    opened_ids.add((item.get('input') or {}).get('id'))
    same = written_ids & opened_ids
    answer = load(capped / 'results' / 'lodash-memex-resume-outcome.json')['final']
    return bool(same), any(record_id in answer for record_id in same)

review_events = []
for directory in (base / 'reviews', capped / 'reviews', capped / 'reviews-resume'):
    for path in directory.glob('*-gateway.jsonl'):
        review_events += [x for x in events(path) if x.get('status') != 'started']
review_usage = usage_total([x.get('usage') for x in review_events], ['prompt_tokens', 'completion_tokens'])
assert len(review_events) == 15 and all(x['status'] == 'ok' for x in review_events)

# Values read from the APIMaster usage-log UI. Review rows match model, input,
# output and start/finish time; solver rows are only time-window candidates.
billing = {
    'observedAfter': '2026-11-01T14:42:46Z',
    'reviewRows': 15, 'reviewCandidateUsd': '0.019720',
    'reviewMatching': 'Unique UI rows matched by model, prompt/output tokens and local request time; cache creation included in prompt. Not receipt-level linkage.',
    'solverWindows': [
        {'name': 'interrupted Claude recovery', 'fromAsiaShanghai': '22:28:00', 'toAsiaShanghai': '22:30:29', 'chargedRows': 51, 'candidateUsd': '0.027716', 'pendingRows': 1},
        {'name': 'budgeted Claude canary', 'fromAsiaShanghai': '22:32:26', 'toAsiaShanghai': '22:35:20', 'chargedRows': 37, 'candidateUsd': '0.019618', 'pendingRows': 0},
        {'name': 'post-hoc Claude continuation', 'fromAsiaShanghai': '22:39:10', 'toAsiaShanghai': '22:40:05', 'chargedRows': 13, 'candidateUsd': '0.006806', 'pendingRows': 0},
    ],
    'solverMatching': 'Account-level time windows, not individual request attribution; unrelated activity could be included.',
    'combinedCandidateUsd': '0.073860',
    'unknown': ['At least one canceled request is pending reconciliation.', 'Two interrupted Claude sessions lack final usage.',
                'Four Codex turns lack usage.', 'Codex subscription allocation, compute, storage and labor are unknown.'],
}
assert sum(decimal.Decimal(x['candidateUsd']) for x in billing['solverWindows']) + decimal.Decimal(billing['reviewCandidateUsd']) == decimal.Decimal(billing['combinedCandidateUsd'])

result = {
    'generatedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'kind': 'three-issue-historical-replay-with-interrupted-and-posthoc-recoveries',
    'registrationSha256': sha(base / 'registration.json'),
    'originalCodex': {'tasks': tasks, 'plannedTasks': 3, 'completeStrictPairs': sum(all(x['arms'][a]['strictCompletedSessions'] == 3 for a in ('baseline', 'memex')) for x in tasks),
        'startedSessions': len(codex_stages), 'timeouts': sum(x['timeout'] for x in codex_stages),
        'completedTurnShutdownTimeouts': sum(x['processStatus'] == 'timeout_after_turn' for x in codex_stages),
        'missingUsageSessions': codex_missing, 'reportedUsage': usage_total(codex_usage, ['input_tokens', 'cached_input_tokens', 'output_tokens'])},
    'interruptedClaudeRecovery': {'startedStreams': len(budget_events), 'resultRecords': len(budget_results),
        'budgetFailures': sum(x.get('resultSubtype') == 'error_max_budget_usd' for x in budget_results),
        'streamsWithoutResult': budget_no_result, 'reportedUsage': usage_total([x.get('usage') for x in budget_results], claude_keys),
        'clientListPriceUsd': str(sum((decimal.Decimal(str(x.get('clientListPriceUsd') or 0)) for x in budget_results), decimal.Decimal(0))),
        'operatorStopSha256': sha(recovery / 'operator-stop.json')},
    'claudeCanary': {'task': 'lodash', 'notNewIndependentTask': True, 'arms': claude_rows,
        'reviewsBeforeResume': review_scores(capped / 'reviews', 'lodash'),
        'reviewsAfterResume': review_scores(capped / 'reviews-resume', 'lodash'),
        'memoryCalls': {name: claude_memory_calls('lodash-memex-' + name + '-events.jsonl') for name in ('s1', 's2', 'resume-s2', 'resume-s3')},
        'memoryWriteOpenSameRecord': memory_chain()[0], 'finalCitedRecordId': memory_chain()[1],
        'supplementalSetterExitCodes': {arm: row['exitCode'] for arm, row in load(capped / 'posthoc-setter-results.json')['results'].items()}},
    'originalCodexPosthocSetterExitCodes': {x['arm']: x['exitCode'] for x in load(base / 'posthoc-setter-results.json')['results']},
    'reviewUsage': {'attempts': len(review_events), **review_usage}, 'billing': billing,
    'limits': registration['limits'] + ['Claude recovery was selected after observing failures and is not a fresh independent task.',
              'The supplemental setter check was added after the original Codex candidate and AI reviews.',
              'A write/open chain does not establish memory correctness or causal necessity.'],
}
args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'tasks': len(tasks), 'strictPairs': result['originalCodex']['completeStrictPairs'],
                  'codexUsage': result['originalCodex']['reportedUsage'], 'reviews': len(review_events)}))
