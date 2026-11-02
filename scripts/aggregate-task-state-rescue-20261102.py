#!/usr/bin/env python3
"""Independently verify a preregistered, post-hoc blind-review rescue."""
import collections
import datetime
import importlib.util
import json
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result); return result

rescue = module(ROOT / 'scripts/rescue-task-state-reviews-20261102.py', 'task_state_rescue')
primary = module(ROOT / 'scripts/aggregate-task-state-20261102.py', 'task_state_primary')

def load(path): return json.loads(path.read_text())

def checked_rating(events, label, expected, evidence, adjudication=False):
    terminal = [x for x in events if x.get('operationLabel') == label and x.get('status') != 'started']
    assert terminal, f'missing terminal event: {label}'
    event = terminal[-1]
    try: actual = rescue.reviewer.parse(event, evidence, adjudication)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError): actual = None
    assert actual == expected, f'saved rating differs from gateway event: {label}'
    return actual

def evaluate_one(task, result, original_plan, original_events, rescue_events, packet, key):
    tid = task['task']; evidence = packet['evidence']; models = original_plan['reviewers']
    assert result['task'] == tid and len(result['reviews']) == len(models) == 2
    replaced = result['replacedModels']
    assert len(replaced) <= 1 and len(set(replaced)) == len(replaced) and all(x in models for x in replaced)
    assert bool(replaced) == (task['reason'] == 'REPLACE_ONE')
    ratings = []
    for model, row in zip(models, result['reviews']):
        if model in replaced:
            assert row.get('model') == 'gpt-6.1-terra'
            events, label = rescue_events, f'{tid}:fallback'
        else:
            assert row.get('model') == model
            events, label = original_events, f'{tid}:{model}'
        ratings.append(checked_rating(events, label, row.get('rating'), evidence))
    if any(not row for row in ratings): return None
    rows = [rescue.keyed({'rating': rating}) for rating in ratings]
    if any(set(row) != set(key) or any(value[0] is None for value in row.values()) for row in rows): return None
    different = rows[0] != rows[1]
    numeric = any(rows[0][label][0] != rows[1][label][0] for label in key)
    final = rows[0]
    adjud = result['adjudication']
    if different:
        assert adjud.get('model') == original_plan['adjudicator']
        rating = checked_rating(rescue_events, f'{tid}:adjudication', adjud.get('rating'), evidence, True)
        if not rating: return None
        final = rescue.keyed({'rating': rating})
        if set(final) != set(key) or any(type(value[0]) is not int or value[0] not in (0, 1, 2) for value in final.values()): return None
    else:
        assert adjud.get('status') == 'NOT_RUN'
    return {'scores': {key[label]: value[0] for label, value in final.items()},
            'adjudicated': different, 'numericReviewerDisagreement': numeric,
            'reviewerScores': [{key[label]: value[0] for label, value in row.items()} for row in rows]}

def reconcile():
    reg = load(rescue.OUT / 'registration.json'); rescue.verify(reg)
    public = primary.PUBLISHED / 'rescue-registration.json'
    assert rescue.sha(public) == rescue.sha(rescue.OUT / 'registration.json')
    assert (rescue.OUT / 'finished.json').exists()
    primary_result, _ = primary.reconcile(); plan = load(rescue.BASE / 'reviews/plan.json')
    replacements = {}; usage = collections.defaultdict(lambda: {'attempts': 0, 'promptTokens': 0, 'completionTokens': 0, 'failedOrMissingUsage': 0})
    for task in reg['tasks']:
        tid = task['task']; folder = rescue.BASE / 'reviews' / tid
        result_path = rescue.OUT / f'{tid}-result.json'
        assert result_path.exists(), f'missing result: {tid}'
        result = load(result_path); packet = load(folder / 'packet.json'); key = load(folder / 'key.json')
        original_events = rescue.audit.a.events(folder / 'gateway.jsonl')
        rescue_events = rescue.audit.a.events(rescue.OUT / f'{tid}-gateway.jsonl')
        score = evaluate_one(task, result, plan, original_events, rescue_events, packet, key)
        replacements[tid] = {'status': 'VALID' if score else 'MISSING_OR_INSUFFICIENT', 'blindReview': score,
                             'replacementModels': result['replacedModels'], 'reason': task['reason']}
        for event in rescue_events:
            if event.get('status') == 'started': continue
            row = usage[event.get('model', 'UNKNOWN')]; row['attempts'] += 1; tokens = event.get('usage') or {}
            if event.get('status') == 'ok' and type(tokens.get('prompt_tokens')) is int and type(tokens.get('completion_tokens')) is int:
                row['promptTokens'] += tokens['prompt_tokens']; row['completionTokens'] += tokens['completion_tokens']
            else: row['failedOrMissingUsage'] += 1
    scores = []
    for row in primary_result['tasks']:
        if not row['completePair']: continue
        original, replacement = row['blindReview'], replacements.get(row['id'])
        assert not (original and replacement), f'post-hoc score would overwrite primary score: {row["id"]}'
        chosen = original or (replacement or {}).get('blindReview')
        if chosen: scores.append(chosen['scores'])
    directions = collections.Counter('memexHigher' if x['memex'] > x['baseline'] else 'baselineHigher' if x['baseline'] > x['memex'] else 'tie' for x in scores)
    return {'generatedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'registrationSha256': rescue.sha(rescue.OUT / 'registration.json'),
            'primaryValidRatedPairs': primary_result['validRatedPairs'], 'rescueRegistered': len(reg['tasks']),
            'rescueValidRatedPairs': sum(x['status'] == 'VALID' for x in replacements.values()),
            'postHocValidRatedPairs': len(scores),
            'postHocScoreDirections': {x: directions[x] for x in ('memexHigher', 'tie', 'baselineHigher')},
            'postHocMeanScore': {arm: statistics.mean(x[arm] for x in scores) if scores else None for arm in ('baseline', 'memex')},
            'reviewUsageByModel': dict(usage), 'tasks': replacements,
            'limits': ['Post-hoc replacement is a sensitivity analysis; original missing and failed reviews remain unchanged.',
                       'AI review is not human assessment. Failed requests may have unknown charges.']}

def main():
    output = reconcile(); path = pathlib.Path(sys.argv[1]); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: output[key] for key in ('primaryValidRatedPairs', 'rescueRegistered', 'rescueValidRatedPairs', 'postHocValidRatedPairs', 'postHocScoreDirections')}))

if __name__ == '__main__': main()
