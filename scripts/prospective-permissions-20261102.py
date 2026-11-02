#!/usr/bin/env python3
"""Registered two-issue smoke after the POSIX database-permissions repair."""
import importlib.util
import pathlib
import random
import secrets
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
long_path = ROOT / 'scripts/prospective-long-20261102.py'
spec = importlib.util.spec_from_file_location('long_study', long_path)
long = importlib.util.module_from_spec(spec)
spec.loader.exec_module(long)
study = long.study
study.BASE = study.PRIVATE / 'integrity-post-permissions-triage'
study.SOURCE = study.PRIVATE / 'integrity-post-permissions-source'
study.agent.BASE, study.agent.SRC = study.BASE, study.SOURCE
study.reviewer.BASE, study.reviewer.SRC = study.BASE, study.SOURCE
study.agent.BUDGET, study.agent.TOTAL_BUDGET, study.agent.CONCURRENCY = 0.18, 1.50, 2


def verify():
    study.verify()
    reg = study.agent.load(study.BASE / 'registration.json')
    assert reg['postRunnerSha256'] == study.digest(pathlib.Path(__file__))
    assert reg['longPromptRunnerSha256'] == study.digest(long_path)
    assert reg['sourceRejectionsSha256'] == study.digest(study.SOURCE / 'rejections.json')


def freeze():
    tasks = study.agent.load(study.SOURCE / 'manifest.json')
    assert len(tasks) == 2 and all(t['discussionSpanDays'] >= 7 for t in tasks)
    owners = {t['repo'].split('/')[0].lower() for t in tasks}
    prior = [study.agent.load(study.PRIVATE / name / 'manifest.json') for name in ('cohort30-source', 'supplement-source', 'integrity-source', 'integrity-long-source')]
    assert len(owners) == 2 and not owners & {t['repo'].split('/')[0].lower() for cohort in prior for t in cohort}
    study.BASE.mkdir(mode=0o700, parents=True, exist_ok=False)
    order = [t['id'] for t in tasks]
    rng = random.SystemRandom(); rng.shuffle(order)
    arms = {}
    for task in order:
        arms[task] = ['baseline', 'memex']; rng.shuffle(arms[task])
    study.agent.save(study.BASE / 'allocation.json', {'taskOrder': order, 'armOrder': arms, 'nonce': secrets.token_hex(32)})
    reg = {'registeredAt': study.agent.now(), 'kind': 'post-permissions-repair-independent-issue-smoke', 'tasks': tasks,
           'memexCommit': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
           'manifestSha256': study.digest(study.SOURCE / 'manifest.json'),
           'sourceRejectionsSha256': study.digest(study.SOURCE / 'rejections.json'),
           'allocationCommitmentSha256': study.digest(study.BASE / 'allocation.json'),
           'runnerSha256': study.digest(study.RUNNER), 'wrapperSha256': study.digest(ROOT / 'scripts/prospective-integrity-20261102.py'),
           'postRunnerSha256': study.digest(pathlib.Path(__file__)), 'longPromptRunnerSha256': study.digest(long_path),
           'sourceHashes': study.source_hashes(), 'bridgeSha256': study.digest(ROOT / 'scripts/prospective-agent-mcp-v5.mjs'),
           'workerSha256': study.digest(ROOT / 'scripts/prospective-agent-worker-v7.py'),
           'model': 'claude-haiku-4-5', 'prompts': study.agent.PROMPTS, 'maxConcurrentTasks': 2,
           'perSessionClientListBudgetUsd': study.agent.FIRST_BUDGET, 'sameSessionRecoveryExtraUsd': study.agent.RECOVERY_BUDGET,
           'perSessionReservationUsd': study.agent.BUDGET, 'aggregateClientListReservationUsd': study.agent.TOTAL_BUDGET,
           'protocol': 'Two new owner-disjoint real issues, randomized paired arms, two distinct Claude Code sessions per arm, read-only source and staged public comments. Both arms get their own handoff; Memex adds hooks and MCP.',
           'completion': 'All four sessions must finish for a complete pair; keep failures and missing usage.',
           'limits': ['Selected after the 25-task cohort had started and after discovering the permissions defect, but before these calls.',
                      'This is a small functional follow-up, not a randomized test of the permissions repair itself.',
                      'Historical public-issue triage is not deployed production work; source may postdate discussion and training data may contain it.',
                      'AI judges are not humans and client list prices are not gateway charges.']}
    study.agent.save(study.BASE / 'registration.json', reg)
    study.reviewer.plan(); verify()
    print({'tasks': len(tasks), 'registrationSha256': study.digest(study.BASE / 'registration.json'), 'reviewPlanSha256': study.digest(study.BASE / 'reviews/plan.json')}, flush=True)


def run(phase):
    verify(); study.agent.run(phase)


def packets():
    verify(); study.packets()


def review():
    verify(); study.review()


if __name__ == '__main__':
    actions = {'freeze': freeze, 'first': lambda: run('first'), 'rest': lambda: run('rest'), 'packets': packets, 'review': review}
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        raise SystemExit('usage: prospective-permissions-20261102.py freeze|first|rest|packets|review')
    actions[sys.argv[1]]()
