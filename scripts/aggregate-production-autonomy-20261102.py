#!/usr/bin/env python3
"""Reconcile frozen replay results, raw events and blinded reviews without filling gaps."""
import collections,datetime,json,pathlib,re,statistics,sys
P=pathlib.Path('/Users/mk-q/.local/share/memex-forward-20261102')
INPUT_FIELDS=('input_tokens','cache_creation_input_tokens','cache_read_input_tokens')
def load(p):return json.loads(p.read_text())
def events(p):
 if not p.exists():return []
 out=[]
 for line in p.read_text().splitlines():
  try:out.append(json.loads(line))
  except ValueError:pass
 return out
def model_tokens(s):
 u=s.get('usage');price=s.get('clientListPriceUsd')
 if not isinstance(u,dict) or any(type(u.get(k)) is not int or u[k]<0 for k in (*INPUT_FIELDS,'output_tokens')):return None
 if sum(u[k] for k in (*INPUT_FIELDS,'output_tokens'))==0 and isinstance(price,(int,float)) and price>0:return None
 return {'input':sum(u[k] for k in INPUT_FIELDS),'output':u['output_tokens'],'cacheRead':u['cache_read_input_tokens'],'cacheWrite':u['cache_creation_input_tokens']}
def call_entries(e):
 return [x for y in e if y.get('type')=='assistant' for x in (y.get('message') or {}).get('content',[]) if isinstance(x,dict) and x.get('type')=='tool_use']
def writes_and_opens(base,task):
 t=base/task/'traces';one=events(t/'memex-s1-events.jsonl')+events(t/'memex-s1-recovery-events.jsonl');two=events(t/'memex-s2-events.jsonl')+events(t/'memex-s2-recovery-events.jsonl')
 writes={x['id'] for x in call_entries(one) if x.get('name')=='mcp__memex__memory_write' and x.get('id')}
 ids=set()
 for e in one:
  if e.get('type')!='user':continue
  for x in (e.get('message') or {}).get('content',[]):
   if isinstance(x,dict) and x.get('type')=='tool_result' and x.get('tool_use_id') in writes and not x.get('is_error'):
    ids.update(re.findall(r'Stored (mem_[0-9a-f]{10})',json.dumps(x.get('content'),ensure_ascii=False)))
 opens={x.get('input',{}).get('id') for x in call_entries(two) if x.get('name')=='mcp__memex__memory_open'}
 recall='\n'.join(e.get('stdout','') for e in two if e.get('subtype')=='hook_response' and e.get('hook_name')=='UserPromptSubmit')
 return {'writeCalls':len(writes),'successfulWriteIds':sorted(ids),'writtenIdOpenedNext':bool(ids & opens),
         'writtenIdInAutomaticRecall':any(i in recall for i in ids),'unverifiedRecallLabel':any(f'{i} [unverified]' in recall for i in ids)}
def review_summary(base,task):
 folder=base/'reviews'/task
 if not (folder/'key.json').exists():return {'status':'NOT_PREPARED'}
 key=load(folder/'key.json');reviews=[]
 for model in ('gpt-6.1-sol','deepseek-flash'):
  f=folder/f'{model}.json';reviews.append(load(f) if f.exists() else {'model':model,'status':'MISSING','rating':None})
 adjud=load(folder/'adjudication.json') if (folder/'adjudication.json').exists() else {'status':'MISSING'}
 if (folder/'review-status.json').exists():return {'status':load(folder/'review-status.json')['status'],'reviews':reviews,'adjudication':adjud}
 if any(not x.get('rating') for x in reviews):return {'status':'MISSING_VALID_REVIEW','reviews':reviews,'adjudication':adjud}
 scores=[{r['id']:r['score'] for r in x['rating']['candidates']} for x in reviews]
 claims=[{r['id']:tuple(sorted(r['unsupportedClaims'])) for r in x['rating']['candidates']} for x in reviews]
 disagreement=scores[0]!=scores[1] or claims[0]!=claims[1]
 if disagreement:
  if not adjud.get('rating'):return {'status':'UNRESOLVED_DISAGREEMENT','reviews':reviews,'adjudication':adjud,'disagreement':True}
  final={r['id']:r['score'] for r in adjud['rating']['candidates']}
 else:final=scores[0]
 return {'status':'VALID','scoresByArm':{key[label]:score for label,score in final.items()},'disagreement':disagreement,
         'reviewerScoresByArm':[{key[label]:score for label,score in scoremap.items()} for scoremap in scores],
         'reviews':reviews,'adjudication':adjud}
def cohort(name):
 base=P/name
 if not (base/'registration.json').exists():return {'status':'NOT_REGISTERED'}
 reg=load(base/'registration.json');rows=[];cost=0;missing_cost=0;problems=[];review_usage=collections.defaultdict(lambda:{'calls':0,'promptTokens':0,'completionTokens':0,'missingUsageOrFailedAttempts':0})
 for t in reg['tasks']:
  tid=t['id'];folder=base/tid;ss={}
  for arm in ('baseline','memex'):
   for stage in (1,2):
    path=folder/'results'/f'{arm}-s{stage}.json'
    if not path.exists():continue
    s=load(path);ss[(arm,stage)]=s
    if s.get('status')!='NOT_RUN_BUDGET':
     price=s.get('clientListPriceUsd')
     if isinstance(price,(int,float)) and not isinstance(price,bool) and price>=0:cost+=price
     else:missing_cost+=1
    tr=folder/'traces';raw=events(tr/f'{arm}-s{stage}-recovery-events.jsonl') or events(tr/f'{arm}-s{stage}-events.jsonl')
    last=next((x for x in reversed(raw) if x.get('type')=='result'),None)
    if s.get('responseCompleted') and (not last or last.get('subtype')!='success' or last.get('result')!=s.get('final')):
     problems.append(f'{tid}:{arm}:s{stage}:saved completion differs from raw result')
    if s.get('recovery') and s['recovery'].get('sessionId')!=s.get('initialAttempt',{}).get('sessionId'):
     problems.append(f'{tid}:{arm}:s{stage}:resume session mismatch')
  paired=all(ss.get((a,k),{}).get('responseCompleted') for a in ('baseline','memex') for k in (1,2))
  if paired:
   for arm in ('baseline','memex'):
    if not ss[(arm,1)].get('sessionId') or ss[(arm,1)].get('sessionId')==ss[(arm,2)].get('sessionId'):
     problems.append(f'{tid}:{arm}:sessions not distinct');paired=False
  token_by_arm={}
  if paired:
   for arm in ('baseline','memex'):
    u=[model_tokens(ss[(arm,k)]) for k in (1,2)]
    token_by_arm[arm]=None if any(x is None for x in u) else {k:sum(x[k] for x in u) for k in ('input','output','cacheRead','cacheWrite')}
  r=review_summary(base,tid)
  for ev in events(base/'reviews'/tid/'gateway.jsonl'):
   if ev.get('status')=='started':continue
   model=ev.get('model','UNKNOWN');entry=review_usage[model];entry['calls']+=1;usage=ev.get('usage') or {}
   if ev.get('status')=='ok' and type(usage.get('prompt_tokens')) is int and type(usage.get('completion_tokens')) is int:
    entry['promptTokens']+=usage['prompt_tokens'];entry['completionTokens']+=usage['completion_tokens']
   else:entry['missingUsageOrFailedAttempts']+=1
  rows.append({'id':tid,'repo':t['repo'],'issue':t['issue'],'issueUrl':t['issueUrl'],'started':folder.exists(),
   'finished':(folder/'finished.json').exists(),'runnerError':load(folder/'runner-error.json') if (folder/'runner-error.json').exists() else None,
   'completePair':paired,'sessions':{f'{a}-s{k}':{z:s.get(z) for z in ('status','responseCompleted','normalExit','timeout','shutdownTimeoutAfterResult','usage','usageNote','clientListPriceUsd','unexpectedTools','unavailableToolAttempts','initialAttempt','recovery')} for (a,k),s in ss.items()},
   'tokenByArm':token_by_arm,'memoryChain':writes_and_opens(base,tid) if folder.exists() else None,'review':r})
 complete=[x for x in rows if x['completePair']];reviewed=[x for x in complete if x['review']['status']=='VALID' and all(type(x['review']['scoresByArm'].get(a)) is int for a in ('baseline','memex'))]
 directions=collections.Counter()
 for x in reviewed:
  d=x['review']['scoresByArm']['memex']-x['review']['scoresByArm']['baseline'];directions['memexHigher' if d>0 else 'baselineHigher' if d<0 else 'tie']+=1
 tokenpairs=[x for x in complete if all(x['tokenByArm'].get(a) is not None for a in ('baseline','memex'))]
 token_totals={a:{k:sum(x['tokenByArm'][a][k] for x in tokenpairs) for k in ('input','output','cacheRead','cacheWrite')} for a in ('baseline','memex')}
 return {'status':'FINISHED' if (base/'finished-rest.json').exists() else 'IN_PROGRESS','registered':len(rows),'started':sum(x['started'] for x in rows),
  'finished':sum(x['finished'] for x in rows),'completePairs':len(complete),'validRatedPairs':len(reviewed),'scoreDirections':dict(directions),
  'meanScore':{a:statistics.mean(x['review']['scoresByArm'][a] for x in reviewed) if reviewed else None for a in ('baseline','memex')},
  'fullTokenPairs':len(tokenpairs),'tokenTotals':token_totals,'clientListPriceKnownUsd':round(cost,6),'clientListPriceMissingSessions':missing_cost,
  'agentWrites':sum(bool(x['memoryChain'] and x['memoryChain']['successfulWriteIds']) for x in rows),
  'writtenRecordOpenedNext':sum(bool(x['memoryChain'] and x['memoryChain']['writtenIdOpenedNext']) for x in rows),
  'writtenRecordAutomaticallyRecalled':sum(bool(x['memoryChain'] and x['memoryChain']['writtenIdInAutomaticRecall']) for x in rows),
  'reviewUsageByModel':dict(review_usage),
  'rawConsistencyProblems':problems,'tasks':rows}
def aggregate():
 return {'generatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'kind':'descriptive-evidence-reconciliation',
        'original':cohort('cohort30-triage'),'supplement':cohort('supplement-triage'),
        'caveats':['The two cohorts use different fixed protocols and must not be pooled as one preregistered treatment-effect estimate.',
                   'A written record opened later is an observed tool sequence, not proof of causal use or factual correctness.',
                   'Client list price is distinct from gateway wallet charges; unknown usage and non-model costs remain unknown.',
                   'Total input token counts include cache creation, cache reads and uncached input.']}
if __name__=='__main__':
 out=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else P/'autonomy-aggregate.json'
 result=aggregate();out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:{x:v for x,v in value.items() if x not in ('tasks','rawConsistencyProblems')} for k,value in result.items() if k in ('original','supplement')},ensure_ascii=False))
 if result['original'].get('rawConsistencyProblems') or result['supplement'].get('rawConsistencyProblems'):raise SystemExit('raw consistency problems; inspect aggregate')
