#!/usr/bin/env python3
"""Registered, budgeted real-issue replay using the existing isolated agent harness."""
import hashlib
import importlib.util
import json
import pathlib
import random
import secrets
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PRIVATE = pathlib.Path.home() / '.local/share/memex-forward-20261102'
BASE = PRIVATE / 'integrity-triage'
SOURCE = PRIVATE / 'integrity-source'
RUNNER = ROOT / 'scripts/prospective-issue-triage-recovery-20261102.py'
REVIEW = ROOT / 'scripts/prospective-review-triage-recovery-20261102.py'
sys.path.insert(0, str(ROOT / 'scripts'))

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

agent = module(RUNNER, 'integrity_agent')
reviewer = module(REVIEW, 'integrity_reviewer')
agent.BASE, agent.SRC = BASE, SOURCE
agent.FIRST_BUDGET, agent.RECOVERY_BUDGET = 0.10, 0.04
agent.BUDGET, agent.TOTAL_BUDGET, agent.CONCURRENCY = 0.15, 4.5, 1
reviewer.BASE, reviewer.SRC = BASE, SOURCE

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def source_hashes():
    files = [*ROOT.glob('packages/memex-core/**/*.js'), *ROOT.glob('packages/memex-claude/**/*.mjs'),
             *ROOT.glob('packages/memex-mcp/**/*.mjs'), ROOT / 'scripts/prospective-agent-mcp-v5.mjs',
             ROOT / 'scripts/prospective-agent-worker-v7.py']
    return {str(path.relative_to(ROOT)): digest(path) for path in sorted(files)}

def verify():
    reg = agent.load(BASE / 'registration.json')
    assert reg['wrapperSha256'] == digest(pathlib.Path(__file__))
    assert reg['manifestSha256'] == digest(SOURCE / 'manifest.json')
    assert reg['sourceHashes'] == source_hashes()
    assert reg['allocationCommitmentSha256'] == digest(BASE / 'allocation.json')
    for task in reg['tasks']:
        assert task['issueSha256'] == digest(SOURCE / f"{task['id']}.issue.json")
        assert task['archiveSha256'] == digest(SOURCE / f"{task['id']}.tar.gz")

def freeze():
    BASE.mkdir(mode=0o700, parents=True, exist_ok=False)
    tasks = agent.load(SOURCE / 'manifest.json')
    assert len(tasks) == 8 and len({task['repo'].split('/')[0].lower() for task in tasks}) == len(tasks)
    prior = [agent.load(PRIVATE / name / 'manifest.json') for name in ('cohort30-source', 'supplement-source')]
    assert not ({task['repo'].lower() for task in tasks} & {task['repo'].lower() for cohort in prior for task in cohort})
    order = [task['id'] for task in tasks]
    rng = random.SystemRandom()
    rng.shuffle(order)
    arms = {}
    for task in order:
        arms[task] = ['baseline', 'memex']
        rng.shuffle(arms[task])
    agent.save(BASE / 'allocation.json', {'taskOrder': order, 'armOrder': arms, 'nonce': secrets.token_hex(32)})
    reg = {'registeredAt': agent.now(), 'kind': 'new-historical-issue-triage-integrity-followup', 'tasks': tasks,
           'memexCommit': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
           'manifestSha256': digest(SOURCE / 'manifest.json'), 'allocationCommitmentSha256': digest(BASE / 'allocation.json'),
           'runnerSha256': digest(RUNNER), 'wrapperSha256': digest(pathlib.Path(__file__)), 'sourceHashes': source_hashes(),
           'bridgeSha256': digest(ROOT / 'scripts/prospective-agent-mcp-v5.mjs'),
           'workerSha256': digest(ROOT / 'scripts/prospective-agent-worker-v7.py'),
           'model': 'claude-haiku-4-5', 'prompts': agent.PROMPTS,
           'perSessionClientListBudgetUsd': agent.FIRST_BUDGET, 'sameSessionRecoveryExtraUsd': agent.RECOVERY_BUDGET,
           'aggregateClientListReservationUsd': agent.TOTAL_BUDGET, 'maxConcurrentTasks': 1,
           'protocol': 'Random arm order; two separate Claude Code sessions per arm, same public issue, staged comments, read-only source tools and own handoff; treatment adds Memex hooks and MCP. Run two tasks first, inspect infrastructure, then continue.',
           'recovery': 'One tool-free continuation of the same session on a budget-exhausted response; preserve both attempts and treat cumulative token use as unknown when not reconciled.',
           'completion': 'Both arms must produce valid second-session responses; retain incomplete and failed sessions.',
           'limits': ['Public historical issues and discussions may be in model training.', 'Source snapshots can postdate discussion and include later changes.',
                      'Compressed read-only triage is not live production work, an executable fix or a measure of deployed task correctness.',
                      'AI judges are not human reviewers. Token usage and client list price are not an APIMaster invoice.']}
    agent.save(BASE / 'registration.json', reg)
    reviewer.plan()
    verify()
    print(json.dumps({'tasks': len(tasks), 'registrationSha256': digest(BASE / 'registration.json'), 'reviewPlanSha256': digest(BASE / 'reviews/plan.json')}), flush=True)

def run_phase(phase):
    verify()
    agent.run(phase)

def packets():
    verify()
    reviewer.prepare_packets()
    commitments = []
    for item in agent.load(BASE / 'reviews/packets.json')['packets']:
        folder = BASE / 'reviews' / item['task']
        nonce = secrets.token_hex(32)
        key = agent.load(folder / 'key.json')
        encoded = json.dumps(key, sort_keys=True, separators=(',', ':'))
        commitment = hashlib.sha256((nonce + '\0' + encoded).encode()).hexdigest()
        agent.save(folder / 'salt.json', {'nonce': nonce})
        commitments.append({**item, 'saltedKeyCommitmentSha256': commitment})
    agent.save(BASE / 'reviews/commitments.json', {'createdAt': agent.now(), 'packets': commitments})
    print(json.dumps({'commitmentsSha256': digest(BASE / 'reviews/commitments.json')}), flush=True)

def review():
    verify()
    assert (BASE / 'reviews/commitments.json').exists()
    reviewer.run()

if __name__ == '__main__':
    actions = {'freeze': freeze, 'first': lambda: run_phase('first'), 'rest': lambda: run_phase('rest'), 'packets': packets, 'review': review}
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        raise SystemExit('usage: prospective-integrity-20261102.py freeze|first|rest|packets|review')
    actions[sys.argv[1]]()
