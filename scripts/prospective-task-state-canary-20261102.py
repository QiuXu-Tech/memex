#!/usr/bin/env python3
"""Four separately registered follow-up issues after the trial-tool repair."""
import importlib.util
import pathlib
import random
import secrets
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
STUDY = ROOT / 'scripts/prospective-task-state-study-20261102.py'
spec = importlib.util.spec_from_file_location('task_state_study', STUDY)
study = importlib.util.module_from_spec(spec); spec.loader.exec_module(study)
study.BASE, study.SOURCE = study.PRIVATE / 'task-state-canary-triage', study.PRIVATE / 'task-state-canary-source'
study.agent.BASE, study.agent.SRC = study.BASE, study.SOURCE
study.reviewer.BASE, study.reviewer.SRC = study.BASE, study.SOURCE
study.agent.TOTAL_BUDGET, study.agent.CONCURRENCY = 4.0, 2

def verify():
    study.verify()
    reg = study.agent.load(study.BASE / 'registration.json')
    assert reg['canaryRunnerSha256'] == study.digest(pathlib.Path(__file__))
    assert reg['previousRegistrationSha256'] == study.digest(study.PRIVATE / 'task-state-triage/registration.json')

def freeze():
    study.verify_vm_worker()
    tasks = study.agent.load(study.SOURCE / 'manifest.json')
    previous = study.agent.load(study.PRIVATE / 'task-state-source/manifest.json')
    owners = {t['repo'].split('/')[0].lower() for t in tasks}
    old_owners = {t['repo'].split('/')[0].lower() for t in previous} | set(study.agent.load(study.PRIVATE / 'task-state-screen/prior-owners.json'))
    assert len(tasks) == len(owners) == 4 and not owners & old_owners
    assert all(t['discussionSpanDays'] >= 7 and t['frozenAcceptance'] for t in tasks)
    study.BASE.mkdir(mode=0o700, parents=True, exist_ok=False)
    order = [t['id'] for t in tasks]; rng = random.SystemRandom(); rng.shuffle(order); arms = {}
    for task in order:
        arms[task] = ['baseline', 'memex']; rng.shuffle(arms[task])
    study.agent.save(study.BASE / 'allocation.json', {'taskOrder': order, 'armOrder': arms, 'nonce': secrets.token_hex(32)})
    reg = {'registeredAt': study.agent.now(), 'kind': 'post-trial-repair-four-issue-canary', 'tasks': tasks,
           'memexCommit': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
           'manifestSha256': study.digest(study.SOURCE / 'manifest.json'), 'allocationCommitmentSha256': study.digest(study.BASE / 'allocation.json'),
           'runnerSha256': study.digest(study.RUNNER), 'reviewerSha256': study.digest(study.REVIEWER), 'wrapperSha256': study.digest(STUDY),
           'canaryRunnerSha256': study.digest(pathlib.Path(__file__)),
           'previousRegistrationSha256': study.digest(study.PRIVATE / 'task-state-triage/registration.json'),
           'sourceHashes': study.source_hashes(), 'auditHashes': study.audit_hashes(),
           'bridgeSha256': study.digest(ROOT / 'scripts/prospective-agent-mcp-v5.mjs'),
           'workerSha256': study.digest(ROOT / 'scripts/prospective-agent-worker-v7.py'),
           'model': 'claude-haiku-4-5', 'prompts': study.agent.PROMPTS,
           'perSessionClientListBudgetUsd': study.agent.FIRST_BUDGET, 'sameSessionRecoveryExtraUsd': study.agent.RECOVERY_BUDGET,
           'perSessionReservationUsd': study.agent.BUDGET, 'aggregateClientListReservationUsd': study.agent.TOTAL_BUDGET,
           'maxConcurrentTasks': study.agent.CONCURRENCY,
           'protocol': 'Four new owner-disjoint public issues; randomized arm order and three distinct Claude Code sessions per arm using the repaired read-only bridge; both arms have their own handoffs and the treatment adds Memex.',
           'selection': 'Separately registered after the 30-issue study exposed tool parameter errors. Report separately; do not pool as if it had the earlier frozen bridge.',
           'completion': 'Both arms must produce successful nonempty responses in three distinct sessions; retain failures.',
           'limits': ['Compressed historical source triage, not a deployed production outcome.', 'AI reviewers are not human reviewers; client list price is not a gateway bill.']}
    study.agent.save(study.BASE / 'registration.json', reg); study.reviewer.plan(); verify()
    print({'tasks': len(tasks), 'registrationSha256': study.digest(study.BASE / 'registration.json'), 'reviewPlanSha256': study.digest(study.BASE / 'reviews/plan.json')}, flush=True)

def run(phase):
    verify(); study.verify_vm_worker(); study.agent.run(phase)

def packets():
    verify(); study.packets()

def review():
    verify(); study.review()

if __name__ == '__main__':
    actions = {'freeze': freeze, 'first': lambda: run('first'), 'rest': lambda: run('rest'), 'packets': packets, 'review': review}
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        raise SystemExit('usage: prospective-task-state-canary-20261102.py freeze|first|rest|packets|review')
    actions[sys.argv[1]]()
