#!/usr/bin/env python3
"""Sanitize registered pilot results without treating missing records as successes."""
import argparse,collections,json,pathlib

BATCHES=[('eslint-1','20261031-eslint-batch1','upstreamRegression'),('lodash-interrupted','20261031-lodash-batch2','regressionControls'),('lodash-repair','20261031-lodash-batch3','regressionControls'),('eslint-2','20261031-eslint-batch4','regressionControls'),('lodash-model-check','20261031-lodash-batch5','regressionControls'),('mixed-3','20261031-mixed-batch6','regressionControls'),('prettier-4','20261031-prettier-batch7','regressionControls'),('eslint-3','20261031-eslint-batch8','regressionControls'),('mixed-4','20261031-mixed-batch9','regressionControls'),('prettier-interrupted','20261031-prettier-batch10','regressionControls'),('prettier-route','20261031-prettier-batch11','regressionControls')]

def outcome(result,exists):
 if result is None:return 'INTERRUPTED' if exists else 'NOT_RUN'
 state=result.get('status')
 if state=='NOT_RUN_AFTER_STOP':return 'NOT_RUN'
 if state in ('model_failure','setup_failure','started') or result.get('checkError'):return 'UNKNOWN'
 if state!='completed':return 'INCOMPLETE'
 acceptance=result.get('acceptance');regression=result.get('_regression')
 if not isinstance(acceptance,dict) or not isinstance(regression,dict):return 'UNKNOWN'
 if acceptance.get('exitCode') is None or regression.get('exitCode') is None:return 'UNKNOWN'
 return 'PASS' if acceptance['exitCode']==0 and regression['exitCode']==0 else 'CHECKS_NONZERO'


def usage(root):
 totals=collections.defaultdict(lambda:{'started':0,'completed':0,'reportedPromptTokens':0,'reportedCompletionTokens':0,'missingUsage':0,'failedResponses':0,'unmatchedStarted':0,'requestBytes':0,'responseBytes':0})
 for rel in ('solver-calls.jsonl','review-calls.jsonl','adjudication-calls.jsonl','posthoc-reference-normalization/adjudication-calls.jsonl','calls.jsonl'):
  path=root/rel
  if not path.exists():continue
  starts=collections.Counter();ends=collections.Counter()
  for line in path.read_text().splitlines():
   row=json.loads(line);model=row['model'];t=totals[model];label=row.get('label')
   if row['status']=='started':starts[(model,label)]+=1;t['started']+=1;t['requestBytes']+=row.get('requestBytes',0);continue
   ends[(model,label)]+=1;t['completed']+=1;t['failedResponses']+=row['status']!='ok';t['responseBytes']+=row.get('responseBytes',0);v=row.get('usage',{})
   if isinstance(v.get('prompt_tokens'),int) and isinstance(v.get('completion_tokens'),int):t['reportedPromptTokens']+=v['prompt_tokens'];t['reportedCompletionTokens']+=v['completion_tokens']
   else:t['missingUsage']+=1
  for (model,label),n in (starts-ends).items():totals[model]['unmatchedStarted']+=n
 return dict(totals)


def reviews(root, models):
 result=[];mapping_file=root/'blind-key.json'
 if not mapping_file.exists():return result
 mapping=json.loads(mapping_file.read_text())
 for blind,slot in mapping.items():
  ratings=[]
  for model in models:
   path=root/'reviews'/f'{blind}-{model}.json'
   if not path.exists():ratings.append({'model':model,'status':'MISSING'});continue
   data=json.loads(path.read_text());parsed=data.get('parsed',{});value=parsed.get('rating',{})
   ratings.append({'model':model,'status':'VALID' if parsed.get('valid') else 'INVALID','correctness':value.get('correctness'),'sideEffects':value.get('side_effects')})
  adj=root/'adjudications'/f'{blind}.json';a=None
  if adj.exists():
   z=json.loads(adj.read_text())['parsed'];v=z.get('rating',{});a={'status':'VALID' if z.get('valid') else 'INVALID','correctness':v.get('correctness'),'sideEffects':v.get('side_effects')}
  result.append({'blind':blind,'slot':slot,'ratings':ratings,'registeredAdjudication':a})
 return result


def posthoc_review(root):
 if not (root/'manifest.json').exists():return None
 manifest=json.loads((root/'manifest.json').read_text());mapping=json.loads((root/'blind-key.json').read_text());candidates=[]
 for entry in manifest['candidates']:
  blind=entry['blind'];source=mapping[blind];ratings=[]
  for model in entry['reviewers']:
   path=root/'reviews'/f'{blind}-{model}.json'
   if not path.exists():ratings.append({'model':model,'status':'MISSING'});continue
   parsed=json.loads(path.read_text()).get('parsed',{});value=parsed.get('rating',{})
   ratings.append({'model':model,'status':'VALID' if parsed.get('valid') else 'INVALID','correctness':value.get('correctness'),'sideEffects':value.get('side_effects')})
  path=root/'adjudications'/f'{blind}.json';adjudication=None
  if path.exists():
   parsed=json.loads(path.read_text()).get('parsed',{});value=parsed.get('rating',{})
   adjudication={'status':'VALID' if parsed.get('valid') else 'INVALID','correctness':value.get('correctness'),'sideEffects':value.get('side_effects')}
  candidates.append({'blind':blind,'batch':source['batch'],'slot':source['slot'],'issue':source['issue'],'arm':source['arm'],'ratings':ratings,'adjudication':adjudication})
 return {'kind':manifest['kind'],'selection':manifest['selection'],'candidates':candidates,'usage':usage(root),'limitations':manifest['limitations']}


def synthetic_smoke(root):
 path=root/'trace.jsonl'
 if not path.exists():return None
 rows=[json.loads(line) for line in path.read_text().splitlines() if line.strip()];calls=[x for x in rows if x.get('kind')=='model'];started=sum(x.get('phase')=='started' for x in calls);ends=[x for x in calls if x.get('phase')=='completed'];with_usage=[x for x in ends if isinstance(x.get('usage',{}).get('prompt_tokens'),int) and isinstance(x.get('usage',{}).get('completion_tokens'),int)]
 result=json.loads((root/'result.json').read_text()) if (root/'result.json').exists() else {}
 return {'model':'gpt-6.1-sol','status':result.get('status','UNKNOWN'),'started':started,'completed':len(ends),'unmatchedStarted':max(0,started-len(ends)),'missingUsage':len(ends)-len(with_usage),'reportedPromptTokens':sum(x['usage']['prompt_tokens'] for x in with_usage),'reportedCompletionTokens':sum(x['usage']['completion_tokens'] for x in with_usage),'toolCalls':result.get('toolCalls'),'testsPassed':result.get('testsPassed')}


def summarize(base):
 all_batches=[]
 for label,name,regression in BATCHES:
  root=base/name
  if not (root/'manifest.json').exists():continue
  manifest=json.loads((root/'manifest.json').read_text());runs=[]
  for i,assignment in enumerate(manifest['schedule'],1):
   directory=root/'runs'/f'{i:02d}';path=directory/'result.json';x=json.loads(path.read_text()) if path.exists() else None
   item={'slot':i,'issue':assignment['issue'],'arm':assignment['arm'],'attemptOutcome':outcome({**x,'_regression':x.get(regression)} if x else None,directory.exists()),'status':x.get('status') if x else None}
   if x:
    item.update({'changedFileCount':len(x.get('changed',[])),'modelCalls':x.get('modelCalls'),'toolCalls':x.get('toolCalls'),'publicTestCalls':x.get('publicTestCalls'),'forcedFinal':x.get('forcedFinal',False),'acceptanceExit':(x.get('acceptance') or {}).get('exitCode'),'regressionExit':(x.get(regression) or {}).get('exitCode'),'checkErrorPresent':bool(x.get('checkError'))})
   runs.append(item)
  posthoc=None
  normalized=root/'posthoc-reference-normalization/normalized.json'
  if normalized.exists():
   original=json.loads(normalized.read_text());posthoc={'normalizationStatuses':dict(collections.Counter(x.get('status') for x in original.values())),'ratings':{key:{'status':value.get('status'),'correctness':value.get('parsed',{}).get('rating',{}).get('correctness'),'sideEffects':value.get('parsed',{}).get('rating',{}).get('side_effects')} for key,value in original.items()},'adjudications':{}}
   for path in sorted((root/'posthoc-reference-normalization').glob('B*.json')):
    data=json.loads(path.read_text());parsed=data.get('parsed',{});rating=parsed.get('rating',{});posthoc['adjudications'][path.stem]={'status':'VALID' if parsed.get('valid') else 'INVALID','correctness':rating.get('correctness'),'sideEffects':rating.get('side_effects')}
  all_batches.append({'batch':label,'scoreDirectionExplicit':label in ('mixed-3','prettier-4','eslint-3','mixed-4','prettier-interrupted','prettier-route'),'sourceCommit':manifest['sourceCommit'],'plannedAssignments':len(runs),'runs':runs,'outcomes':dict(collections.Counter(x['attemptOutcome'] for x in runs)),'reviews':reviews(root,manifest.get('reviewers',[])),'posthocNormalization':posthoc,'usage':usage(root)})
 return {'kind':'separate-prospective-open-source-instrumentation-batches','batches':all_batches,'posthocExplicitRubric':posthoc_review(base/'posthoc-explicit-rubric'),'diagnostics':{'reviewerRouteProbe':usage(base/'20261031-reviewer-route-probe'),'alternateSolverToolProbe':usage(base/'20261031-sol-tool-probe'),'alternateSolverSyntheticSmoke':synthetic_smoke(base/'20261031-sol-agent-smoke')},'limitations':['Different batches were selected or revised after prior results and are not one pre-registered cohort.','The pre-seeded public issue discussions are not long production sessions.','Tests are partial and reviewers are AI; label validity does not prove factual support.','The numeric review direction was not specified in batches 1–5; their raw scores cannot be treated as a common scale.','Unmatched started and failed requests may have unreported tokens or fees; no failed request is automatically retried.','Source exposure to public PRs or model pretraining cannot be excluded.']}


def main():
 p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--out',required=True);a=p.parse_args();result=summarize(pathlib.Path(a.base));pathlib.Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps([{'batch':x['batch'],'outcomes':x['outcomes'],'usage':x['usage']} for x in result['batches']]))
if __name__=='__main__':main()
