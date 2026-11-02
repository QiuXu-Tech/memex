#!/usr/bin/env python3
"""Separately registered blind replacement for missing task-state reviews."""
import concurrent.futures
import datetime
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import prospective_gateway_review as gateway

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path); result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result); return result

REVIEW = ROOT / 'scripts/prospective-task-state-review-20261102.py'
AUDIT = ROOT / 'scripts/aggregate-integrity-followup-20261102.py'
reviewer, audit = module(REVIEW, 'task_state_rescue_reviewer'), module(AUDIT, 'task_state_rescue_audit')
BASE = pathlib.Path.home() / '.local/share/memex-forward-20261102/task-state-triage'
OUT = BASE / 'reviews/posthoc-rescue'
PUBLISHED = ROOT / 'docs/assets/benchmarks/production-task-state-20261102/packet-commitments.json'

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path): return json.loads(path.read_text())
def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as output: json.dump(obj, output, ensure_ascii=False, indent=2); output.write('\n')

def keyed(row):
    rating = row.get('rating')
    if not isinstance(rating, dict): return None
    return {candidate['id']: (candidate.get('score'), tuple(sorted(candidate.get('unsupportedClaims') or []))) for candidate in rating['candidates']}

def classify(folder, reviewers):
    if (folder / 'review-status.json').exists(): return 'NOT_REVIEWABLE'
    rows = [load(folder / f'{model}.json') if (folder / f'{model}.json').exists() else {'rating': None} for model in reviewers]
    missing = sum(not row.get('rating') for row in rows)
    if missing > 1: return 'MULTIPLE_MISSING'
    if any(any(value[0] is None for value in keyed(row).values()) for row in rows if row.get('rating')): return 'INSUFFICIENT_EVIDENCE'
    if missing == 1: return 'REPLACE_ONE'
    different = keyed(rows[0]) != keyed(rows[1])
    adjud = load(folder / 'adjudication.json') if (folder / 'adjudication.json').exists() else {}
    if different and not adjud.get('rating'): return 'RETRY_ADJUDICATION'
    return 'NO_RESCUE_NEEDED'

def prepare():
    assert (BASE / 'reviews/finished.json').exists() and not OUT.exists()
    unblinded = audit.verify_blind(BASE, PUBLISHED)
    assert len(unblinded) == len(load(BASE / 'registration.json')['tasks'])
    plan = load(BASE / 'reviews/plan.json'); checks = []; excluded = []
    for task in load(BASE / 'registration.json')['tasks']:
        tid = task['id']; folder = BASE / 'reviews' / tid; reason = classify(folder, plan['reviewers'])
        if reason in ('NOT_REVIEWABLE', 'MULTIPLE_MISSING', 'INSUFFICIENT_EVIDENCE'):
            excluded.append({'task': tid, 'reason': reason}); continue
        if reason == 'NO_RESCUE_NEEDED': continue
        checks.append({'task': tid, 'reason': reason, 'packetSha256': sha(folder / 'packet.json'),
                       'originalReviewSha256': {model: sha(folder / f'{model}.json') if (folder / f'{model}.json').exists() else None for model in plan['reviewers']},
                       'originalAdjudicationSha256': sha(folder / 'adjudication.json') if (folder / 'adjudication.json').exists() else None})
    reg = {'registeredAt': now(), 'kind': 'post-hoc-blind-review-rescue', 'tasks': checks, 'excluded': excluded,
           'primaryRegistrationSha256': sha(BASE / 'registration.json'), 'primaryReviewPlanSha256': sha(BASE / 'reviews/plan.json'),
           'packetCommitmentsSha256': sha(PUBLISHED), 'runnerSha256': sha(pathlib.Path(__file__)),
           'reviewerSha256': sha(REVIEW), 'auditSha256': sha(AUDIT), 'gatewayHelperSha256': sha(ROOT / 'scripts/prospective_gateway_review.py'),
           'fallbackReviewer': 'gpt-6.1-terra', 'adjudicator': plan['adjudicator'], 'reviewPrompt': plan['reviewPrompt'],
           'adjudicationPrompt': plan['adjudicationPrompt'], 'reviewMaxOutputTokens': plan['reviewMaxOutputTokens'],
           'adjudicationMaxOutputTokens': plan['adjudicationMaxOutputTokens'],
           'maxConcurrentTasks': 2,
           'protocol': 'Retain primary results. Replace at most one missing or invalid reviewer with a fresh blind Terra review. Re-adjudicate disagreements or a previously invalid adjudication using the unchanged packet. Do not replace explicit insufficient-evidence scores.',
           'limits': ['Post-hoc sensitivity analysis, not the primary review.', 'A timed-out request may have incurred an unknown charge.', 'Model identity and independence are not independently verified.']}
    save(OUT / 'registration.json', reg)
    print(json.dumps({'eligible': len(checks), 'excluded': len(excluded), 'registrationSha256': sha(OUT / 'registration.json')}), flush=True)

def verify(reg):
    assert reg['runnerSha256'] == sha(pathlib.Path(__file__)) and reg['reviewerSha256'] == sha(REVIEW)
    assert reg['auditSha256'] == sha(AUDIT) and reg['gatewayHelperSha256'] == sha(ROOT / 'scripts/prospective_gateway_review.py')
    assert reg['primaryRegistrationSha256'] == sha(BASE / 'registration.json') and reg['primaryReviewPlanSha256'] == sha(BASE / 'reviews/plan.json')
    assert reg['packetCommitmentsSha256'] == sha(PUBLISHED)
    audit.verify_blind(BASE, PUBLISHED)
    plan = load(BASE / 'reviews/plan.json')
    for task in reg['tasks']:
        folder = BASE / 'reviews' / task['task']; assert sha(folder / 'packet.json') == task['packetSha256']
        for model in plan['reviewers']:
            path = folder / f'{model}.json'; assert (sha(path) if path.exists() else None) == task['originalReviewSha256'][model]
        path = folder / 'adjudication.json'; assert (sha(path) if path.exists() else None) == task['originalAdjudicationSha256']

def run():
    reg = load(OUT / 'registration.json'); verify(reg)
    key = subprocess.run(['ruby', '-ryaml', '-e', 'print YAML.load_file(File.expand_path("~/.dsh/.credentials.yaml")).dig("refs","APIMASTER_API_KEY")'], capture_output=True, text=True, check=True).stdout
    assert key; save(OUT / 'started.json', {'at': now()}); plan = load(BASE / 'reviews/plan.json')
    def review_one(task):
        tid = task['task']; folder = BASE / 'reviews' / tid; packet = load(folder / 'packet.json'); rows = []; replacements = []
        for model in plan['reviewers']:
            path = folder / f'{model}.json'; row = load(path) if path.exists() else {'model': model, 'rating': None, 'status': 'MISSING'}
            if not row.get('rating'):
                event = gateway.call(key, reg['fallbackReviewer'], [{'role': 'system', 'content': 'Review anonymous engineering triage from the evidence only.'},
                    {'role': 'user', 'content': reg['reviewPrompt'] + '\n\n' + json.dumps(packet, ensure_ascii=False)}], reg['reviewMaxOutputTokens'], OUT / f'{tid}-gateway.jsonl', tid + ':fallback', timeout=120)
                try: rating, error = reviewer.parse(event, packet['evidence']), None
                except Exception as exc: rating, error = None, str(exc)
                row = {'model': reg['fallbackReviewer'], 'status': event.get('status'), 'rating': rating, 'error': error}; replacements.append(model)
            rows.append(row)
        adjud = {'status': 'NOT_RUN', 'reason': 'At least one review is invalid.'}
        if all(row.get('rating') for row in rows) and any(any(value[0] is None for value in keyed(row).values()) for row in rows):
            adjud = {'status': 'NOT_RUN', 'reason': 'At least one reviewer found insufficient evidence.'}
        elif all(row.get('rating') for row in rows):
            if keyed(rows[0]) == keyed(rows[1]): adjud = {'status': 'NOT_RUN', 'reason': 'No numeric or unsupported-claim disagreement.'}
            else:
                event = gateway.call(key, reg['adjudicator'], [{'role': 'system', 'content': 'Adjudicate anonymous engineering reviews using evidence.'},
                    {'role': 'user', 'content': reg['adjudicationPrompt'] + '\n\n' + json.dumps({'packet': packet, 'reviews': rows}, ensure_ascii=False)}], reg['adjudicationMaxOutputTokens'], OUT / f'{tid}-gateway.jsonl', tid + ':adjudication', timeout=120)
                try: rating, error = reviewer.parse(event, packet['evidence'], True), None
                except Exception as exc: rating, error = None, str(exc)
                adjud = {'model': reg['adjudicator'], 'status': event.get('status'), 'rating': rating, 'error': error}
        save(OUT / f'{tid}-result.json', {'task': tid, 'replacedModels': replacements, 'reviews': rows, 'adjudication': adjud})
        print(json.dumps({'task': tid, 'validReviews': sum(bool(row.get('rating')) for row in rows), 'adjudicationStatus': adjud.get('status'), 'adjudicationValid': bool(adjud.get('rating'))}), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=reg['maxConcurrentTasks']) as pool:
        for future in [pool.submit(review_one, task) for task in reg['tasks']]:
            future.result()
    save(OUT / 'finished.json', {'at': now()})

if __name__ == '__main__':
    if sys.argv[1:] == ['prepare']: prepare()
    elif sys.argv[1:] == ['run']: run()
    else: raise SystemExit('usage: rescue-task-state-reviews-20261102.py prepare|run')
