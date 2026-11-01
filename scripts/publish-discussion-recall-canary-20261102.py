#!/usr/bin/env python3
"""Publish redacted observations for the post-hoc, reused-issue recall canary."""
import importlib.util,json,pathlib,re
ROOT=pathlib.Path(__file__).resolve().parent.parent
PRIVATE=pathlib.Path('/Users/mk-q/.local/share/memex-forward-20261102')
BASE=PRIVATE/'discussion-recall-canary';OLD=PRIVATE/'supplement-triage';SOURCE=PRIVATE/'supplement-source'
p=ROOT/'scripts/aggregate-production-autonomy-20261102.py';s=importlib.util.spec_from_file_location('aggregate',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def load(p):return json.loads(p.read_text())
def scrub(s):
 s=re.sub(r'/Users/mk-q/[^\s\'"\]]+','[local-path]',s)
 s=re.sub(r'\bmem_[a-z0-9]{10}\b','[memory-id]',s,flags=re.I)
 return re.sub(r'\b(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b','[redacted]',s)
def exposure(base,task,arm):
 trace=base/task/'traces';events=m.events(trace/f'{arm}-s2-events.jsonl')+m.events(trace/f'{arm}-s2-recovery-events.jsonl')
 return m.later_discussion_exposure(SOURCE/f'{task}.issue.json',events)
reg=load(BASE/'registration.json');done=load(BASE/'finished.json');tasks=[];cost=0
for t in reg['tasks']:
 tid=t['id'];folder=BASE/tid;arms={}
 for arm in ('baseline','memex'):
  sessions=[]
  for stage in (1,2):
   p=folder/'results'/f'{arm}-s{stage}.json'
   if not p.exists():continue
   d=load(p);price=d.get('clientListPriceUsd')
   if isinstance(price,(int,float)):cost+=price
   sessions.append({k:d.get(k) for k in ('stage','status','responseCompleted','clientListPriceUsd','usage','usageNote','unexpectedTools','unavailableToolAttempts')})
  final=load(folder/'results'/f'{arm}-s2.json').get('final','') if (folder/'results'/f'{arm}-s2.json').exists() else ''
  arms[arm]={'sessions':sessions,'laterDiscussion':exposure(BASE,tid,arm),'finalAnswer':scrub(final[:12000]),'answerTruncated':len(final)>12000}
 tasks.append({'id':tid,'issueUrl':t['issueUrl'],'sourceCommit':t['sourceCommit'],'arms':arms,
               'originalMemexLaterDiscussion':exposure(OLD,tid,'memex'),
               'runnerError':{'type':load(folder/'runner-error.json').get('type')} if (folder/'runner-error.json').exists() else None})
assert abs(cost-done['clientListCommittedOrReservedUnknownUsd'])<1e-6 and done['unknownSessionCharges']==0
out={'status':'FINISHED','kind':reg['kind'],'selection':reg['selection'],'limits':reg['limits'],
 'productCommit':reg['productCommit'],'clientListPriceUsd':round(cost,6),'tasks':tasks,
 'note':'These two selected reused issues are a post-hoc mechanism check; no new blinded quality assessment or independent effectiveness estimate is claimed.'}
target=ROOT/'docs/assets/benchmarks/production-autonomy-20261102/discussion-recall-canary-results.json'
target.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print('published',target)
