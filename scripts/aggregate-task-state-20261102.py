#!/usr/bin/env python3
"""Independently reconcile a registered three-session replay and blind reviews."""
import collections
import datetime
import importlib.util
import json
import pathlib
import re
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PRIVATE = pathlib.Path.home() / '.local/share/memex-forward-20261102'
BASE = PRIVATE / 'task-state-triage'
PUBLISHED = ROOT / 'docs/assets/benchmarks/production-task-state-20261102'

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

audit = module(ROOT / 'scripts/aggregate-integrity-followup-20261102.py', 'integrity_audit')
a = audit.a

def load(path):
    return json.loads(path.read_text())

def traces(task, name):
    folder = BASE / task / 'traces'
    return a.events(folder / f'{name}-events.jsonl') + a.events(folder / f'{name}-recovery-events.jsonl')

def contents(item):
    return json.dumps(item.get('content'), ensure_ascii=False)

def memory_evidence(task, sessions):
    writes, opens, recalled = {}, {}, {}
    for stage in (1, 2, 3):
        events = traces(task, f'memex-s{stage}')
        calls = {x.get('id'): x for x in a.call_entries(events)}
        writes[stage], opens[stage] = set(), set()
        recalled[stage] = '\n'.join(str(x.get('stdout', '')) for x in events if x.get('subtype') == 'hook_response' and x.get('hook_name') == 'UserPromptSubmit')
        for event in events:
            if event.get('type') != 'user':
                continue
            for item in (event.get('message') or {}).get('content', []):
                if not isinstance(item, dict) or item.get('type') != 'tool_result' or item.get('is_error'):
                    continue
                call = calls.get(item.get('tool_use_id')) or {}
                if call.get('name') == 'mcp__memex__memory_write':
                    writes[stage].update(re.findall(r'Stored (mem_[0-9a-f]{10})', contents(item)))
                if call.get('name') == 'mcp__memex__memory_open':
                    record = (call.get('input') or {}).get('id')
                    if isinstance(record, str) and record in contents(item):
                        opens[stage].add(record)
    checkpoints = {1: set(), 2: set()}
    records = BASE / task / 'memory/memex/records'
    for file in records.rglob('mem_*.md') if records.exists() else []:
        try:
            head = file.read_text().split('\n---\n', 1)[0]
            match = re.search(r'^provenance: (\{.*\})$', head, re.M)
            provenance = json.loads(match.group(1)) if match else {}
            for stage in (1, 2):
                session_id = sessions.get(f'memex-s{stage}', {}).get('sessionId')
                if session_id and provenance.get('source') == 'claude-stop' and provenance.get('sourceSession') == session_id:
                    checkpoints[stage].add(file.stem)
        except (OSError, UnicodeError, ValueError):
            pass
    prior_writes = writes[1] | writes[2]
    write_open = bool(writes[1] & (opens[2] | opens[3]) or writes[2] & opens[3])
    checkpoint_open = bool(checkpoints[1] & (opens[2] | opens[3]) or checkpoints[2] & opens[3])
    write_recall = any(record in recalled[stage] for stage in (2, 3) for earlier in range(1, stage) for record in writes[earlier])
    checkpoint_recall = any(record in recalled[stage] for stage in (2, 3) for earlier in range(1, stage) for record in checkpoints[earlier])
    return {'agentSuccessfulWrites': len(prior_writes), 'agentWriteThenSuccessfulOpen': write_open,
            'agentWriteThenAutomaticRecall': write_recall, 'automaticCheckpoints': sum(map(len, checkpoints.values())),
            'automaticCheckpointThenSuccessfulOpen': checkpoint_open, 'automaticCheckpointThenRecall': checkpoint_recall}

def reconcile():
    assert audit.digest(BASE / 'registration.json') == audit.digest(PUBLISHED / 'registration.json')
    assert audit.digest(BASE / 'reviews/plan.json') == audit.digest(PUBLISHED / 'review-plan.json')
    unblind = audit.verify_blind(BASE, PUBLISHED / 'packet-commitments.json')
    reg = load(BASE / 'registration.json')
    rows, errors = [], []
    all_cost, missing_cost = 0.0, 0
    usage_by_model = collections.defaultdict(lambda: {'attempts': 0, 'promptTokens': 0, 'completionTokens': 0, 'failedOrMissingUsage': 0})
    for task in reg['tasks']:
        tid = task['id']; folder = BASE / tid
        sessions, token_arms = {}, {}
        for arm in ('baseline', 'memex'):
            for stage in (1, 2, 3):
                name = f'{arm}-s{stage}'; path = folder / 'results' / f'{name}.json'
                if not path.exists():
                    if (folder / 'traces' / f'{name}-events.jsonl').exists(): missing_cost += 1
                    continue
                row = load(path); sessions[name] = row
                if row.get('status') != 'NOT_RUN_BUDGET':
                    price = row.get('clientListPriceUsd')
                    if isinstance(price, (int, float)) and not isinstance(price, bool) and price >= 0: all_cost += price
                    else: missing_cost += 1
                source = a.events(folder / 'traces' / f'{name}-recovery-events.jsonl') or a.events(folder / 'traces' / f'{name}-events.jsonl')
                terminal = next((event for event in reversed(source) if event.get('type') == 'result'), None)
                if row.get('responseCompleted') and (not terminal or terminal.get('subtype') != 'success' or terminal.get('result') != row.get('final')):
                    errors.append(f'{tid}:{name}:completion differs from raw event')
                if row.get('recovery') and row['recovery'].get('sessionId') != (row.get('initialAttempt') or {}).get('sessionId'):
                    errors.append(f'{tid}:{name}:recovery session mismatch')
        complete = all(sessions.get(f'{arm}-s{stage}', {}).get('responseCompleted') for arm in ('baseline', 'memex') for stage in (1, 2, 3))
        if complete:
            for arm in ('baseline', 'memex'):
                ids = [sessions[f'{arm}-s{stage}'].get('sessionId') for stage in (1, 2, 3)]
                if not all(ids) or len(set(ids)) != 3:
                    errors.append(f'{tid}:{arm}:sessions not distinct'); complete = False
        if complete:
            for arm in ('baseline', 'memex'):
                counts = []
                for stage in (1, 2, 3):
                    name = f'{arm}-s{stage}'
                    expected = a.model_tokens(sessions[name]); observed = a.message_contexts([traces(tid, name)])
                    if not expected or not observed or expected['input'] != observed['inputTokens']:
                        counts = []; break
                    counts.append(expected)
                token_arms[arm] = {key: sum(x[key] for x in counts) for key in ('input', 'output', 'cacheRead', 'cacheWrite')} if counts else None
        score = audit.independent_scores(BASE, tid) if complete else None
        review = a.review_summary(BASE, tid)
        if score:
            if review.get('status') != 'VALID' or review.get('scoresByArm') != score['scores']:
                errors.append(f'{tid}:independent score disagreement')
        for event in a.events(BASE / 'reviews' / tid / 'gateway.jsonl'):
            if event.get('status') == 'started': continue
            item = usage_by_model[event.get('model', 'UNKNOWN')]; item['attempts'] += 1; usage = event.get('usage') or {}
            if event.get('status') == 'ok' and type(usage.get('prompt_tokens')) is int and type(usage.get('completion_tokens')) is int:
                item['promptTokens'] += usage['prompt_tokens']; item['completionTokens'] += usage['completion_tokens']
            else: item['failedOrMissingUsage'] += 1
        tools = {name: a.tool_counts([traces(tid, name)]) for name in sessions}
        rows.append({'id': tid, 'issueUrl': task['issueUrl'], 'sourceCommit': task['sourceCommit'],
                     'discussionSpanDays': task['discussionSpanDays'], 'started': folder.exists(), 'completePair': complete,
                     'runnerErrorType': (load(folder / 'runner-error.json').get('type') if (folder / 'runner-error.json').exists() else None),
                     'sessions': {name: {'status': row.get('status'), 'completed': row.get('responseCompleted'), 'recovered': bool(row.get('recovery')),
                                         'timeout': row.get('timeout'), 'unavailableTools': len(row.get('unavailableToolAttempts') or []),
                                         'unexpectedTools': len(row.get('unexpectedTools') or []), 'clientListPriceUsd': row.get('clientListPriceUsd')} for name, row in sessions.items()},
                     'missingSessions': sorted({f'{arm}-s{stage}' for arm in ('baseline', 'memex') for stage in (1, 2, 3)} - set(sessions)),
                     'tools': tools, 'tokenByArm': token_arms, 'reviewStatus': review.get('status'), 'blindReview': score,
                     'memory': memory_evidence(tid, sessions) if folder.exists() else None})
    if errors:
        raise AssertionError(errors)
    complete = [x for x in rows if x['completePair']]
    reviewed = [x for x in complete if x['blindReview']]
    directions = collections.Counter()
    for x in reviewed:
        scores = x['blindReview']['scores']; delta = scores['memex'] - scores['baseline']
        directions['memexHigher' if delta > 0 else 'baselineHigher' if delta < 0 else 'tie'] += 1
    token_pairs = [x for x in complete if all(x['tokenByArm'].get(arm) is not None for arm in ('baseline', 'memex'))]
    memory_keys = ('agentSuccessfulWrites', 'agentWriteThenSuccessfulOpen', 'agentWriteThenAutomaticRecall', 'automaticCheckpoints', 'automaticCheckpointThenSuccessfulOpen', 'automaticCheckpointThenRecall')
    output = {'generatedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'memexCommit': reg['memexCommit'],
              'registrationSha256': audit.digest(BASE / 'registration.json'), 'reviewPlanSha256': audit.digest(BASE / 'reviews/plan.json'),
              'registered': len(rows), 'started': sum(x['started'] for x in rows), 'completePairs': len(complete), 'validRatedPairs': len(reviewed),
              'scoreDirections': {key: directions[key] for key in ('memexHigher', 'tie', 'baselineHigher')},
              'meanScore': {arm: statistics.mean(x['blindReview']['scores'][arm] for x in reviewed) if reviewed else None for arm in ('baseline', 'memex')},
              'adjudicatedPairs': sum(x['blindReview']['adjudicated'] for x in reviewed),
              'numericReviewerDisagreements': sum(x['blindReview']['numericReviewerDisagreement'] for x in reviewed),
              'verifiedTokenPairs': len(token_pairs),
              'verifiedTokens': {arm: {key: sum(x['tokenByArm'][arm][key] for x in token_pairs) for key in ('input', 'output', 'cacheRead', 'cacheWrite')} for arm in ('baseline', 'memex')},
              'memoryEvents': {key: sum(x['memory'][key] for x in rows if x['memory']) for key in memory_keys},
              'clientListPriceKnownUsd': round(all_cost, 6), 'clientListPriceMissingSessions': missing_cost,
              'reviewUsageByModel': dict(usage_by_model), 'tasks': rows,
              'limits': ['Owner-disjoint public issue triage in compressed historical sessions is not deployed production task correctness.',
                         'Recorded memory reads and automatic recall do not prove that memory caused an answer.',
                         'AI reviews are not human assessments. Client list prices are not gateway invoices; unknown usage and other costs remain unknown.']}
    return output, unblind

def main():
    output, unblind = reconcile()
    path = pathlib.Path(sys.argv[1]); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    (path.parent / 'packet-unblinding.json').write_text(json.dumps(unblind, indent=2) + '\n')
    print(json.dumps({key: output[key] for key in ('registered', 'started', 'completePairs', 'validRatedPairs', 'scoreDirections', 'verifiedTokenPairs', 'clientListPriceKnownUsd', 'clientListPriceMissingSessions')}))

if __name__ == '__main__':
    main()
