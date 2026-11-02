#!/usr/bin/env python3
"""Pre-registered three-session randomized replay with anonymous AI review."""
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
BASE, SOURCE = PRIVATE / 'task-state-triage', PRIVATE / 'task-state-source'
RUNNER = ROOT / 'scripts/prospective-task-state-runner-20261102.py'
REVIEWER = ROOT / 'scripts/prospective-task-state-review-20261102.py'
AUDIT_FILES = [ROOT / 'scripts/aggregate-task-state-20261102.py', ROOT / 'scripts/aggregate-integrity-followup-20261102.py', ROOT / 'scripts/aggregate-production-autonomy-20261102.py']
sys.path.insert(0, str(ROOT / 'scripts'))

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

agent = module(RUNNER, 'task_state_agent')
reviewer = module(REVIEWER, 'task_state_reviewer')
agent.BASE, agent.SRC = BASE, SOURCE
agent.FIRST_BUDGET, agent.RECOVERY_BUDGET = 0.10, 0.04
agent.BUDGET, agent.TOTAL_BUDGET, agent.CONCURRENCY = 0.18, 12.0, 2
reviewer.BASE, reviewer.SRC = BASE, SOURCE

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def source_hashes():
    files = [p for p in ROOT.glob('packages/memex-*/**/*') if p.is_file() and p.suffix in ('.js', '.mjs')]
    files += list(ROOT.glob('packages/memex-*/package.json'))
    files += [ROOT / 'package.json', ROOT / 'test/register.mjs', ROOT / 'scripts/prospective-agent-mcp-v5.mjs', ROOT / 'scripts/prospective-agent-worker-v7.py']
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(files)}

def audit_hashes():
    return {str(path.relative_to(ROOT)): digest(path) for path in AUDIT_FILES}

def verify():
    reg = agent.load(BASE / 'registration.json')
    assert reg['wrapperSha256'] == digest(pathlib.Path(__file__))
    assert reg['runnerSha256'] == digest(RUNNER)
    assert reg['reviewerSha256'] == digest(REVIEWER)
    assert reg['manifestSha256'] == digest(SOURCE / 'manifest.json')
    assert reg['sourceHashes'] == source_hashes()
    assert reg['auditHashes'] == audit_hashes()
    assert reg['allocationCommitmentSha256'] == digest(BASE / 'allocation.json')
    assert reg['prompts'] == agent.PROMPTS
    assert reg['aggregateClientListReservationUsd'] == agent.TOTAL_BUDGET
    for task in reg['tasks']:
        assert task['issueSha256'] == digest(SOURCE / f"{task['id']}.issue.json")
        assert task['archiveSha256'] == digest(SOURCE / f"{task['id']}.tar.gz")

def verify_vm_worker():
    actual = agent.remote('sha256sum', agent.VROOT + '/prospective-agent-worker-v7.py').split()[0]
    assert actual == digest(ROOT / 'scripts/prospective-agent-worker-v7.py'), 'VM worker does not match registered worker'

def freeze():
    verify_vm_worker()
    tasks = agent.load(SOURCE / 'manifest.json')
    assert 30 <= len(tasks) <= 50 and len({t['repo'].split('/')[0].lower() for t in tasks}) == len(tasks)
    prior_owners = set(agent.load(PRIVATE / 'task-state-screen/prior-owners.json'))
    assert not ({t['repo'].split('/')[0].lower() for t in tasks} & prior_owners)
    assert all(t['discussionSpanDays'] >= 7 and t['frozenAcceptance'] for t in tasks)
    BASE.mkdir(mode=0o700, parents=True, exist_ok=False)
    order = [t['id'] for t in tasks]
    rng = random.SystemRandom()
    rng.shuffle(order)
    arms = {}
    for task in order:
        arms[task] = ['baseline', 'memex']
        rng.shuffle(arms[task])
    agent.save(BASE / 'allocation.json', {'taskOrder': order, 'armOrder': arms, 'nonce': secrets.token_hex(32)})
    reg = {'registeredAt': agent.now(), 'kind': 'three-session-owner-disjoint-historical-issue-triage-replay',
           'tasks': tasks, 'memexCommit': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
           'manifestSha256': digest(SOURCE / 'manifest.json'), 'allocationCommitmentSha256': digest(BASE / 'allocation.json'),
           'runnerSha256': digest(RUNNER), 'reviewerSha256': digest(REVIEWER), 'wrapperSha256': digest(pathlib.Path(__file__)),
           'sourceHashes': source_hashes(), 'auditHashes': audit_hashes(), 'bridgeSha256': digest(ROOT / 'scripts/prospective-agent-mcp-v5.mjs'),
           'workerSha256': digest(ROOT / 'scripts/prospective-agent-worker-v7.py'), 'model': 'claude-haiku-4-5',
           'prompts': agent.PROMPTS, 'perSessionClientListBudgetUsd': agent.FIRST_BUDGET,
           'sameSessionRecoveryExtraUsd': agent.RECOVERY_BUDGET, 'perSessionReservationUsd': agent.BUDGET,
           'aggregateClientListReservationUsd': agent.TOTAL_BUDGET, 'maxConcurrentTasks': agent.CONCURRENCY,
           'protocol': 'Random task order and per-task arm order; three distinct Claude Code sessions per arm; same issue, staged discussion, read-only source tools and own handoffs. Treatment additionally has Memex hooks and the four default MCP tools. Run two tasks first, inspect infrastructure and charges, then continue.',
           'selection': 'Public open issues with discussions spanning at least seven days, one previously unused owner per task, source archives and criteria fixed before model calls. Selected after earlier studies and reported separately.',
           'completion': 'Both arms must produce successful nonempty final responses in three distinct client sessions. Retain every failure and all started attempts.',
           'recovery': 'One tool-free continuation of the same session on budget exhaustion; retain both attempts. Reserve the session budget if cost is unknown.',
           'limits': ['Historical public content may be in model training; source snapshots may postdate discussion.',
                      'Compressed read-only triage is not live production work, a code fix, or deployed task correctness.',
                      'AI reviewers are not humans. Client list prices do not determine gateway billing; missing usage remains unknown.']}
    agent.save(BASE / 'registration.json', reg)
    reviewer.plan()
    verify()
    print(json.dumps({'tasks': len(tasks), 'registrationSha256': digest(BASE / 'registration.json'),
                      'reviewPlanSha256': digest(BASE / 'reviews/plan.json')}), flush=True)

def run_phase(phase):
    verify()
    verify_vm_worker()
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
        raise SystemExit('usage: prospective-task-state-study-20261102.py freeze|first|rest|packets|review')
    actions[sys.argv[1]]()
