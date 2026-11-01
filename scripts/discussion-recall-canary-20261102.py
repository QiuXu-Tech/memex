#!/usr/bin/env python3
"""Post-hoc two-issue replay after clarifying that recalled memory is incomplete."""
import concurrent.futures,datetime,hashlib,importlib.util,json,pathlib,random,secrets,subprocess,sys
ROOT=pathlib.Path(__file__).resolve().parent.parent
PRIVATE=pathlib.Path('/Users/mk-q/.local/share/memex-forward-20261102')
BASE=PRIVATE/'discussion-recall-canary';ORIGINAL=PRIVATE/'supplement-triage/registration.json'
RUNNER=ROOT/'scripts/prospective-issue-triage-recovery-20261102.py'
spec=importlib.util.spec_from_file_location('pilot_runner',RUNNER);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def load(p):return json.loads(p.read_text())
def save(p,data):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
def prepare():
 assert not BASE.exists();old=load(ORIGINAL);tasks=[x for x in old['tasks'] if x['id'] in ('37','40')];assert len(tasks)==2
 order=[x['id'] for x in tasks];rng=random.SystemRandom();rng.shuffle(order);arms={}
 for task in order:
  a=['baseline','memex'];rng.shuffle(a);arms[task]=a
 save(BASE/'allocation.json',{'taskOrder':order,'armOrder':arms,'nonce':secrets.token_hex(32)})
 reg={'registeredAt':now(),'kind':'exploratory-post-hoc-reused-issue-replay','tasks':tasks,
  'selection':'These two issues were selected after their earlier Memex answers incorrectly claimed that discussion was absent; they are reused cases, not new independent tasks.',
  'intervention':'Default automatic recall says earlier context can be incomplete or stale and asks the agent to check current sources and later discussion before concluding information is absent.',
  'productCommit':subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip(),
  'productFilesSha256':{str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'packages/memex-core/lib/manual.js',ROOT/'packages/memex-claude/bin/cli.mjs',ROOT/'packages/memex-mcp/bin/server.mjs']},
  'pilotRunnerSha256':sha(RUNNER),'runnerSha256':sha(pathlib.Path(__file__)),'bridgeSha256':sha(ROOT/'scripts/prospective-agent-mcp-v5.mjs'),
  'workerSha256':sha(ROOT/'scripts/prospective-agent-worker-v7.py'),'allocationCommitmentSha256':sha(BASE/'allocation.json'),
  'protocol':'Same two-session recovery-protocol prompts, source snapshots, model and per-session budgets as the registered supplemental cohort; fresh isolated workspaces and randomized arm order.',
  'aggregateClientListTargetUsd':1.25,'primaryObservation':'Record whether each second session opens a C-prefixed discussion record and whether the response still claims no discussion; retain all outputs and failures.',
  'limits':['Post-hoc, selected after observing failure, and reuses tasks: exploratory mechanism check only.','The original cohort used an earlier product commit; do not attribute these outcomes to it.','Client list price is not the gateway bill.']}
 save(BASE/'registration.json',reg);print(json.dumps({'tasks':order,'registrationSha256':sha(BASE/'registration.json')}),flush=True)
def run():
 reg=load(BASE/'registration.json');allocation=load(BASE/'allocation.json')
 assert sha(pathlib.Path(__file__))==reg['runnerSha256'] and sha(RUNNER)==reg['pilotRunnerSha256'] and sha(BASE/'allocation.json')==reg['allocationCommitmentSha256']
 assert all(sha(ROOT/p)==h for p,h in reg['productFilesSha256'].items())
 assert sha(ROOT/'scripts/prospective-agent-mcp-v5.mjs')==reg['bridgeSha256'] and sha(ROOT/'scripts/prospective-agent-worker-v7.py')==reg['workerSha256']
 m.BASE=BASE;m.ROOT=ROOT;m.LOADER=ROOT/'test/register.mjs';m.TOTAL_BUDGET=reg['aggregateClientListTargetUsd'];m.budget=m.Budget()
 m.vwork=lambda t,arm:f'{m.VROOT}/workspaces/discussion-canary-20261102/{t["id"]}/{arm}'
 m.vupload=lambda t:f'{m.VROOT}/uploads/triage-recovery-20261102/discussion-canary-{t["id"]}.tar.gz'
 key=m.cmd('ruby','-ryaml','-e','print YAML.load_file(File.expand_path("~/.dsh/.credentials.yaml")).dig("refs","APIMASTER_API_KEY")');assert key
 save(BASE/'started.json',{'at':now()});tasks={x['id']:x for x in reg['tasks']}
 def pair(t):
  out=BASE/t['id'];out.mkdir(exist_ok=False)
  try:
   m.setup(t)
   for arm in allocation['armOrder'][t['id']]:
    first=m.session(t,arm,1,key)
    if first['responseCompleted']:m.session(t,arm,2,key)
   save(out/'finished.json',{'at':now()})
  except Exception as exc:
   save(out/'runner-error.json',{'at':now(),'type':type(exc).__name__,'message':str(exc)[:500]})
   print(json.dumps({'task':t['id'],'runnerError':type(exc).__name__}),flush=True)
  finally:
   try:m.remote('rm','-rf',f'{m.VROOT}/workspaces/discussion-canary-20261102/{t["id"]}',m.vupload(t))
   except Exception:pass
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda x:pair(tasks[x]),allocation['taskOrder']))
 save(BASE/'finished.json',{'at':now(),'clientListCommittedOrReservedUnknownUsd':m.budget.committed,'unknownSessionCharges':m.budget.unknown})
if __name__=='__main__':
 if sys.argv[1:]==['prepare']:prepare()
 elif sys.argv[1:]==['run']:run()
 else:raise SystemExit('prepare|run')
