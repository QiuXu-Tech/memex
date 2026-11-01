#!/usr/bin/env python3
"""Summarize one frozen agent replay and its reviews without publishing private traces."""
import argparse, collections, datetime, decimal, hashlib, json, pathlib

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

def totals(rows, keys):
    return {key: sum((row or {}).get(key, 0) for row in rows) for key in keys}

registration = load(base / 'registration.json')
task = registration['tasks'][0]
usage_keys = ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens', 'output_tokens')
arms = {}
for arm in ('baseline', 'memex'):
    stages = []
    for stage in (1, 2, 3):
        p = base / 'results' / f'chalk-{arm}-s{stage}.json'
        if not p.exists(): continue
        row = load(p)
        trace = base / 'traces' / f'chalk-{arm}-s{stage}-events.jsonl'
        tools = collections.Counter()
        for event in events(trace):
            if event.get('type') != 'assistant': continue
            for item in (event.get('message') or {}).get('content', []):
                if item.get('type') == 'tool_use': tools[item.get('name', '')] += 1
        stages.append({**{k: row.get(k) for k in ('stage', 'startedAt', 'finishedAt', 'elapsedSeconds', 'exitCode', 'timeout', 'shutdownTimeoutAfterResult', 'unexpectedTool', 'responseCompleted', 'usage', 'clientListPriceUsd', 'resultSubtype')},
                       'toolCalls': dict(tools), 'traceSha256': sha(trace)})
    result_path = base / 'results' / f'chalk-{arm}-outcome.json'
    outcome = load(result_path) if result_path.exists() else None
    arms[arm] = {'stages': stages, 'reportedUsage': totals([s['usage'] for s in stages], usage_keys),
                 'missingUsageSessions': sum(s['usage'] is None for s in stages),
                 'clientListPriceUsd': str(sum((decimal.Decimal(str(s['clientListPriceUsd'] or 0)) for s in stages), decimal.Decimal(0))),
                 'outcome': ({k: outcome[k] for k in ('sessionsCompleted', 'testExitCode', 'patchSha256', 'patchBytes')} if outcome else None)}
review_dir = base / 'reviews'
review_key_path = review_dir / 'chalk-key.json'
reviews = []
key = load(review_key_path) if review_key_path.exists() else {}
for model in ('gpt-6.1-sol', 'claude-haiku-4-5', 'adjudication'):
    path = review_dir / f'chalk-{model}.json'
    if not path.exists():
        reviews.append({'reviewer': model, 'status': 'NOT RUN'})
        continue
    row = load(path); ratings = row.get('ratings') or {}
    reviews.append({'reviewer': model, 'status': row.get('status'),
                    'scores': {key[x['id']]: x['score'] for x in ratings.get('candidates', [])},
                    'reasons': {key[x['id']]: x['reason'] for x in ratings.get('candidates', [])},
                    'materialDisagreement': ratings.get('materialDisagreement'), 'error': row.get('error')})
gateway = review_dir / 'chalk-gateway.jsonl'
review_events = [x for x in events(gateway) if x.get('status') != 'started'] if gateway.exists() else []
billing_path = base / 'billing.json'
billing = load(billing_path) if billing_path.exists() else {'status': 'UNKNOWN'}
strict_pair = all(arms[a]['outcome'] and arms[a]['outcome']['sessionsCompleted'] == 3 for a in arms)
result = {'generatedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'kind': registration['kind'], 'registrationSha256': sha(base / 'registration.json'),
          'issueUrl': task['issueUrl'], 'sourceCommit': task['sourceCommit'],
          'criteria': task['criteria'], 'strictCompletePair': bool(strict_pair),
          'arms': arms, 'reviews': reviews,
          'reviewUsage': {'attempts': len(review_events), **totals([x.get('usage') for x in review_events], ('prompt_tokens', 'completion_tokens')),
                          'missingUsageAttempts': sum(x.get('usage') is None for x in review_events)},
          'billing': billing, 'limits': registration['limits']}
args.out.parent.mkdir(parents=True, exist_ok=True)
args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'strictCompletePair': result['strictCompletePair'], 'arms': {a: x['outcome'] for a, x in arms.items()}, 'reviewAttempts': len(review_events)}))
