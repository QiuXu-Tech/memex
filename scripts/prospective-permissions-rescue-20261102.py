#!/usr/bin/env python3
"""A separately registered independent issue after observed incomplete pairs."""
import importlib.util,pathlib,random,secrets,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parent.parent
post_path=ROOT/'scripts/prospective-permissions-20261102.py'
spec=importlib.util.spec_from_file_location('post_study',post_path);post=importlib.util.module_from_spec(spec);spec.loader.exec_module(post);study=post.study
study.BASE=study.PRIVATE/'integrity-permissions-rescue-triage';study.SOURCE=study.PRIVATE/'integrity-permissions-rescue-source'
study.agent.BASE,study.agent.SRC=study.BASE,study.SOURCE;study.reviewer.BASE,study.reviewer.SRC=study.BASE,study.SOURCE
study.agent.BUDGET=0.18;study.agent.TOTAL_BUDGET=1.0;study.agent.CONCURRENCY=1

def verify():
 study.verify();r=study.agent.load(study.BASE/'registration.json')
 assert r['extraRunnerSha256']==study.digest(pathlib.Path(__file__)) and r['postRunnerSha256']==study.digest(post_path)
 assert r['model']=='claude-haiku-4-5' and r['prompts']==study.agent.PROMPTS and r['aggregateClientListReservationUsd']==study.agent.TOTAL_BUDGET

def freeze():
 tasks=study.agent.load(study.SOURCE/'manifest.json');assert len(tasks)==1 and tasks[0]['discussionSpanDays']>=7
 owner=tasks[0]['repo'].split('/')[0].lower()
 prior=[study.agent.load(study.PRIVATE/name/'manifest.json') for name in ('cohort30-source','supplement-source','integrity-source','integrity-long-source','integrity-post-permissions-source','integrity-permissions-extra-source')]
 assert owner not in {t['repo'].split('/')[0].lower() for group in prior for t in group}
 study.BASE.mkdir(mode=0o700,parents=True,exist_ok=False);arms=['baseline','memex'];random.SystemRandom().shuffle(arms)
 study.agent.save(study.BASE/'allocation.json',{'taskOrder':[tasks[0]['id']],'armOrder':{tasks[0]['id']:arms},'nonce':secrets.token_hex(32)})
 reg={'registeredAt':study.agent.now(),'kind':'post-permissions-rescue-issue-after-invalid-adjudication','tasks':tasks,
  'memexCommit':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),
  'manifestSha256':study.digest(study.SOURCE/'manifest.json'),'allocationCommitmentSha256':study.digest(study.BASE/'allocation.json'),
  'runnerSha256':study.digest(study.RUNNER),'wrapperSha256':study.digest(ROOT/'scripts/prospective-integrity-20261102.py'),
  'extraRunnerSha256':study.digest(pathlib.Path(__file__)),'postRunnerSha256':study.digest(post_path),'sourceHashes':study.source_hashes(),
  'bridgeSha256':study.digest(ROOT/'scripts/prospective-agent-mcp-v5.mjs'),'workerSha256':study.digest(ROOT/'scripts/prospective-agent-worker-v7.py'),
  'model':'claude-haiku-4-5','prompts':study.agent.PROMPTS,'maxConcurrentTasks':1,
  'perSessionClientListBudgetUsd':study.agent.FIRST_BUDGET,'sameSessionRecoveryExtraUsd':study.agent.RECOVERY_BUDGET,
  'perSessionReservationUsd':study.agent.BUDGET,'aggregateClientListReservationUsd':study.agent.TOTAL_BUDGET,
  'protocol':'One new owner-disjoint public issue, randomized paired arms, two distinct Claude Code sessions per arm, read-only source and staged comments; both arms have their own handoff and Memex adds hooks and MCP.',
  'selection':'Added after observing an invalid adjudication and before this task or its review calls; report separately from the original preregistered cohorts.',
  'limits':['Historical issue material may be in model training and source may postdate comments.', 'Compressed triage is not a deployed production outcome.', 'AI reviewers are not humans and client list prices are not gateway charges.']}
 study.agent.save(study.BASE/'registration.json',reg);study.reviewer.plan();verify();print({'tasks':1,'registrationSha256':study.digest(study.BASE/'registration.json'),'reviewPlanSha256':study.digest(study.BASE/'reviews/plan.json')},flush=True)

def run(phase):verify();study.agent.run(phase)
def packets():verify();study.packets()
def review():verify();study.review()
if __name__=='__main__':
 actions={'freeze':freeze,'first':lambda:run('first'),'rest':lambda:run('rest'),'packets':packets,'review':review}
 if len(sys.argv)!=2 or sys.argv[1] not in actions:raise SystemExit('usage: prospective-permissions-rescue-20261102.py freeze|first|rest|packets|review')
 actions[sys.argv[1]]()
