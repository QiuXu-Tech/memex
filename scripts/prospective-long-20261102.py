#!/usr/bin/env python3
"""Separate registered 25-task long-discussion follow-up with bounded costs."""
import importlib.util
import pathlib
import random
import secrets
import subprocess
import sys

path = pathlib.Path(__file__).with_name('prospective-integrity-20261102.py')
spec = importlib.util.spec_from_file_location('integrity_study', path)
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)
study.BASE = study.PRIVATE / 'integrity-long-triage'
study.SOURCE = study.PRIVATE / 'integrity-long-source'
study.agent.BASE, study.agent.SRC = study.BASE, study.SOURCE
study.reviewer.BASE, study.reviewer.SRC = study.BASE, study.SOURCE
study.agent.BUDGET, study.agent.TOTAL_BUDGET, study.agent.CONCURRENCY = 0.18, 9.0, 2
study.agent.PROMPTS = {
    'stage1': 'Investigate this real issue against the pinned repository and early discussion. Use targeted source and discussion lookups; do not repeat a lookup unless new information makes it useful. Once you have a relevant source location and a relevant discussion record, stop searching and give a concise handoff with evidence and unresolved questions. If evidence is unavailable, state that. Do not edit code.',
    'stage2': 'Continue the earlier investigation using the later discussion and your own prior handoff, available in the archive. Use targeted lookups only for specific remaining uncertainties; do not repeat information already retrieved. Once the available evidence suffices, produce a concise triage with source file and line, discussion or disagreement with comment IDs, a recommended next check, and uncertainty. Do not edit code.',
}


def verify():
    study.verify()
    registration = study.agent.load(study.BASE / 'registration.json')
    assert registration['extensionRunnerSha256'] == study.digest(pathlib.Path(__file__))


def freeze():
    study.BASE.mkdir(mode=0o700, parents=True, exist_ok=False)
    tasks = study.agent.load(study.SOURCE / 'manifest.json')
    assert len(tasks) == 25 and all(task['discussionSpanDays'] >= 7 for task in tasks)
    owners = {task['repo'].split('/')[0].lower() for task in tasks}
    assert len(owners) == len(tasks)
    prior = [study.agent.load(study.PRIVATE / name / 'manifest.json') for name in ('cohort30-source', 'supplement-source', 'integrity-source')]
    assert not owners & {task['repo'].split('/')[0].lower() for cohort in prior for task in cohort}
    order = [task['id'] for task in tasks]
    rng = random.SystemRandom()
    rng.shuffle(order)
    arms = {}
    for task in order:
        arms[task] = ['baseline', 'memex']
        rng.shuffle(arms[task])
    study.agent.save(study.BASE / 'allocation.json', {'taskOrder': order, 'armOrder': arms, 'nonce': secrets.token_hex(32)})
    reg = {'registeredAt': study.agent.now(), 'kind': 'separate-long-discussion-real-issue-triage', 'tasks': tasks,
           'memexCommit': subprocess.check_output(['git', '-C', str(study.ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
           'manifestSha256': study.digest(study.SOURCE / 'manifest.json'),
           'sourceRejectionsSha256': study.digest(study.SOURCE / 'rejections.json'),
           'allocationCommitmentSha256': study.digest(study.BASE / 'allocation.json'),
           'runnerSha256': study.digest(study.RUNNER), 'wrapperSha256': study.digest(path),
           'extensionRunnerSha256': study.digest(pathlib.Path(__file__)), 'sourceHashes': study.source_hashes(),
           'bridgeSha256': study.digest(study.ROOT / 'scripts/prospective-agent-mcp-v5.mjs'),
           'workerSha256': study.digest(study.ROOT / 'scripts/prospective-agent-worker-v7.py'),
           'model': 'claude-haiku-4-5', 'prompts': study.agent.PROMPTS,
           'perSessionClientListBudgetUsd': study.agent.FIRST_BUDGET,
           'sameSessionRecoveryExtraUsd': study.agent.RECOVERY_BUDGET,
           'aggregateClientListReservationUsd': study.agent.TOTAL_BUDGET, 'perSessionReservationUsd': study.agent.BUDGET,
           'maxConcurrentTasks': 2,
           'protocol': 'Randomized paired arms; two distinct Claude Code sessions per arm, identical public issue, staged discussion, read-only source tools and own handoff; treatment also gets Memex hooks and MCP. Run the first two tasks, inspect execution, then continue.',
           'selection': 'Twenty-five additional distinct repository owners, each with at least seven days between issue creation and the last captured comment; a time span is not proof of continuous work.',
           'recovery': 'One tool-free continuation of the same session after budget exhaustion; retain both attempts and mark unresolved cumulative usage unknown.',
           'completion': 'Both arms must produce valid second-session responses; retain incomplete and failed sessions.',
           'limits': ['Selected after earlier cohorts and after observing initial trial tool and cost behavior, but before these solver and reviewer calls.',
                      'Historical public issues and source may be in model training; current source snapshots can postdate the discussion.',
                      'Compressed read-only triage is not a deployed fix, live production work, or direct measurement of production correctness.',
                      'AI judges are not human reviewers. Client list prices do not establish actual gateway charges.']}
    study.agent.save(study.BASE / 'registration.json', reg)
    study.reviewer.plan()
    verify()
    print({'tasks': len(tasks), 'registrationSha256': study.digest(study.BASE / 'registration.json'), 'reviewPlanSha256': study.digest(study.BASE / 'reviews/plan.json')}, flush=True)


def run(phase):
    verify()
    study.agent.run(phase)


if __name__ == '__main__':
    actions = {'freeze': freeze, 'first': lambda: run('first'), 'rest': lambda: run('rest'), 'packets': study.packets, 'review': study.review}
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        raise SystemExit('usage: prospective-long-20261102.py freeze|first|rest|packets|review')
    actions[sys.argv[1]]()
