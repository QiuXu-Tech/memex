#!/usr/bin/env python3
"""Sanitize registered pilot results without treating missing records as successes."""
import argparse,collections,hashlib,json,pathlib

BATCHES=[('eslint-1','20261031-eslint-batch1','upstreamRegression'),('lodash-interrupted','20261031-lodash-batch2','regressionControls'),('lodash-repair','20261031-lodash-batch3','regressionControls'),('eslint-2','20261031-eslint-batch4','regressionControls'),('lodash-model-check','20261031-lodash-batch5','regressionControls'),('mixed-3','20261031-mixed-batch6','regressionControls'),('prettier-4','20261031-prettier-batch7','regressionControls'),('eslint-3','20261031-eslint-batch8','regressionControls'),('mixed-4','20261031-mixed-batch9','regressionControls'),('prettier-interrupted','20261031-prettier-batch10','regressionControls'),('prettier-route','20261031-prettier-batch11','regressionControls'),('prettier-six','20261031-prettier-batch12','regressionControls'),('prettier-unstarted','20261031-prettier-batch13','regressionControls'),('prettier-lowcost','20261031-prettier-batch14','regressionControls'),('prettier-gateway','20261031-prettier-batch15','regressionControls'),('dayjs-gateway','20261031-dayjs-batch16','regressionControls'),('moment-mathjs','20261031-mixed-batch17','regressionControls')]
BATCHES.append(('dayjs-mathjs','20261031-mixed-batch18','regressionControls'))
BATCHES.append(('prettier-late','20261031-prettier-batch19','regressionControls'))
BATCHES.append(('mathjs-late','20261031-mathjs-batch20','regressionControls'))
BATCHES.append(('validator-new','20261031-validator-batch21','regressionControls'))
BATCHES.append(('luxon-new','20261031-luxon-batch22','regressionControls'))
BATCHES.extend([('lodash-new','20261031-lodash-batch23','regressionControls'),('yup-new','20261031-yup-batch24','regressionControls'),('validator-chartjs','20261031-mixed-batch25','regressionControls')])
BATCHES.append(('chartjs-unstarted','20261031-chartjs-batch26','regressionControls'))
NEW_LABELS={'prettier-gateway','dayjs-gateway','moment-mathjs','dayjs-mathjs','prettier-late','mathjs-late','validator-new','luxon-new','lodash-new','yup-new','validator-chartjs','chartjs-unstarted'}

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


def usage(root, files=None):
 totals=collections.defaultdict(lambda:{'started':0,'completed':0,'reportedPromptTokens':0,'reportedCompletionTokens':0,'missingUsage':0,'failedResponses':0,'unmatchedStarted':0,'requestBytes':0,'responseBytes':0})
 for rel in (files or ('solver-calls.jsonl','review-calls.jsonl','adjudication-calls.jsonl','posthoc-reference-normalization/adjudication-calls.jsonl','calls.jsonl')):
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


def failures(root, files):
 rows=[]
 for name in files:
  path=root/name
  if not path.exists():continue
  digest=hashlib.sha256(path.read_bytes()).hexdigest()
  for line in path.read_text().splitlines():
   event=json.loads(line)
   if event.get('status') in ('started','ok'):continue
   rows.append({'log':name,'logSha256':digest,**{key:event.get(key) for key in ('at','label','model','status','httpStatus','errorType','errorCode','elapsedSeconds')}})
 return rows


def qwen_limit_observations(root, manifest):
 path=root/'review-calls.jsonl';limits=manifest.get('reviewOutputTokenLimits',{})
 limit=limits.get('qwen3.8-flash',manifest.get('maxReviewTokens'))
 if not path.exists() or not isinstance(limit,int) or 'qwen3.8-flash' not in manifest.get('reviewers',[]):return []
 digest=hashlib.sha256(path.read_bytes()).hexdigest();rows=[]
 for line in path.read_text().splitlines():
  event=json.loads(line);usage=event.get('usage',{});value=usage.get('completion_tokens')
  if event.get('model')=='qwen3.8-flash' and event.get('status')=='ok' and isinstance(value,int) and value>limit:
   rows.append({'at':event.get('at'),'label':event.get('label'),'requestedMaxTokens':limit,'reportedCompletionTokens':value,'reportedReasoningTokens':usage.get('completion_tokens_details',{}).get('reasoning_tokens'),'logSha256':digest})
 return rows


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
   ratings.append({'model':model,'status':'VALID' if parsed.get('valid') else 'INVALID','eventStatus':data.get('eventStatus'),'correctness':value.get('correctness'),'sideEffects':value.get('side_effects')})
  adj=root/'adjudications'/f'{blind}.json';a=None
  if adj.exists():
   data=json.loads(adj.read_text());z=data['parsed'];v=z.get('rating',{});a={'status':'VALID' if z.get('valid') else 'INVALID','eventStatus':data.get('eventStatus'),'correctness':v.get('correctness'),'sideEffects':v.get('side_effects')}
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
   data=json.loads(path.read_text());parsed=data.get('parsed',{});value=parsed.get('rating',{})
   ratings.append({'model':model,'status':'VALID' if parsed.get('valid') else 'INVALID','eventStatus':data.get('eventStatus'),'correctness':value.get('correctness'),'sideEffects':value.get('side_effects')})
  path=root/'adjudications'/f'{blind}.json';adjudication=None
  if path.exists():
   data=json.loads(path.read_text());parsed=data.get('parsed',{});value=parsed.get('rating',{})
   adjudication={'status':'VALID' if parsed.get('valid') else 'INVALID','eventStatus':data.get('eventStatus'),'correctness':value.get('correctness'),'sideEffects':value.get('side_effects')}
  candidates.append({'blind':blind,'batch':source['batch'],'slot':source['slot'],'issue':source['issue'],'arm':source['arm'],'ratings':ratings,'adjudication':adjudication})
 return {'kind':manifest['kind'],'selection':manifest['selection'],'candidates':candidates,'usage':usage(root),'limitations':manifest['limitations']}


def synthetic_smoke(root,model):
 path=root/'trace.jsonl'
 if not path.exists():return None
 rows=[json.loads(line) for line in path.read_text().splitlines() if line.strip()];calls=[x for x in rows if x.get('kind')=='model'];started=sum(x.get('phase')=='started' for x in calls);ends=[x for x in calls if x.get('phase')=='completed'];with_usage=[x for x in ends if isinstance(x.get('usage',{}).get('prompt_tokens'),int) and isinstance(x.get('usage',{}).get('completion_tokens'),int)]
 result=json.loads((root/'result.json').read_text()) if (root/'result.json').exists() else {}
 return {'model':model,'status':result.get('status','UNKNOWN'),'started':started,'completed':len(ends),'unmatchedStarted':max(0,started-len(ends)),'missingUsage':len(ends)-len(with_usage),'reportedPromptTokens':sum(x['usage']['prompt_tokens'] for x in with_usage),'reportedCompletionTokens':sum(x['usage']['completion_tokens'] for x in with_usage),'toolCalls':result.get('toolCalls'),'testsPassed':result.get('testsPassed')}


def unstarted_adjudications(root):
 if not (root/'manifest.json').exists():return None
 manifest=json.loads((root/'manifest.json').read_text());mapping=json.loads((root/'blind-key.json').read_text());items=[]
 for entry in manifest['candidates']:
  blind=entry['blind'];path=root/'adjudications'/f'{blind}.json';result={'status':'MISSING'}
  if path.exists():
   data=json.loads(path.read_text());parsed=data.get('parsed',{});value=parsed.get('rating',{})
   result={'status':'VALID' if parsed.get('valid') else 'INVALID','eventStatus':data.get('eventStatus'),'correctness':value.get('correctness'),'sideEffects':value.get('side_effects')}
  items.append({'blind':blind,**mapping[blind],'result':result})
 return {'kind':manifest['kind'],'selection':manifest['selection'],'model':manifest['model'],'candidates':items,'usage':usage(root),'limitations':manifest['limitations']}


def budgeted_posthoc(root, batch):
 if not (root/'manifest.json').exists():return None
 manifest=json.loads((root/'manifest.json').read_text());items=[]
 def rating(path):
  if not path.exists():return {'status':'MISSING'}
  data=json.loads(path.read_text());parsed=data.get('parsed',{});value=parsed.get('rating',{})
  return {'status':'VALID' if parsed.get('valid') else 'INVALID','eventStatus':data.get('eventStatus'),'correctness':value.get('correctness'),'sideEffects':value.get('side_effects')}
 if batch==15:
  for row in reviews(root,manifest['reviewers']):
   assignment=manifest['schedule'][row['slot']-1];items.append({**row,'issue':assignment['issue'],'arm':assignment['arm']})
  costs=usage(root,('review-calls.jsonl','adjudication-calls.jsonl'))
 else:
  mapping=json.loads((root/'posthoc-key.json').read_text())
  for blind,item in mapping.items():
   old=item['originalBlind'];slot=item['slot'];assignment=manifest['schedule'][slot-1]
   first=rating(root/'reviews'/f'{old}-deepseek-flash.json');second=rating(root/'reviews'/f'{old}-qwen3.8-flash.json')
   replacement=rating(root/'posthoc-reviews'/f'{blind}.json') if second['status']!='VALID' else {'status':'NOT_APPLICABLE'}
   adjudication=rating(root/'posthoc-adjudications'/f'{blind}.json')
   items.append({'blind':blind,'slot':slot,'issue':assignment['issue'],'arm':assignment['arm'],'originalDeepseek':first,'originalQwen':second,'posthocQwen':replacement,'posthocAdjudication':adjudication})
  costs=usage(root,('posthoc-review-calls.jsonl','posthoc-adjudication-calls.jsonl'))
 result={'kind':manifest['kind'],'selection':manifest['selection'],'candidates':items,'usage':costs,'limitations':manifest['limitations']}
 normal=root/'adjudication-reference-normalization.json'
 if batch==15 and normal.exists():
  data=json.loads(normal.read_text());result['posthocReferenceNormalization']={'inputSha256':data['inputSha256'],'scriptSha256':data['scriptSha256'],'rows':{k:{'status':v['status'],'correctness':v.get('parsed',{}).get('rating',{}).get('correctness'),'sideEffects':v.get('parsed',{}).get('rating',{}).get('side_effects'),'changes':v.get('changes',[])} for k,v in data['rows'].items()}}
 return result


def fallback_adjudications(root):
 if not (root/'manifest.json').exists():return None
 manifest=json.loads((root/'manifest.json').read_text());items=[]
 for item in manifest['candidates']:
  path=root/'adjudications'/f"{item['blind']}.json";result={'status':'MISSING'}
  if path.exists():
   data=json.loads(path.read_text());parsed=data.get('parsed',{});value=parsed.get('rating',{})
   result={'status':'VALID' if parsed.get('valid') else 'INVALID','eventStatus':data.get('eventStatus'),'correctness':value.get('correctness'),'sideEffects':value.get('side_effects')}
  items.append({'blind':item['blind'],'batch':item.get('batch'),'slot':item['slot'],'result':result})
 return {'kind':manifest['kind'],'selection':manifest['selection'],'model':manifest['model'],'candidates':items,'usage':usage(root,('calls.jsonl',)),'limitations':manifest['limitations']}


def batch17_unstarted_reviews(root, source):
 if not (root/'manifest.json').exists():return None
 manifest=json.loads((root/'manifest.json').read_text());schedule=json.loads((source/'manifest.json').read_text())['schedule'];items=[]
 def rating(path,model):
  if not path.exists():return {'model':model,'status':'MISSING'}
  data=json.loads(path.read_text());parsed=data.get('parsed',{});value=parsed.get('rating',{})
  return {'model':model,'status':'VALID' if parsed.get('valid') else 'INVALID','eventStatus':data.get('eventStatus'),'correctness':value.get('correctness'),'sideEffects':value.get('side_effects')}
 for item in manifest['candidates']:
  blind=item['blind'];assignment=schedule[item['slot']-1]
  ratings=[rating(root/'reviews'/f'{blind}-{model}.json',model) for model in manifest['reviewers']]
  model=manifest['adjudicator'];adj=rating(root/'adjudications'/f'{blind}-{model}.json',model)
  items.append({'blind':blind,'originalBlind':item['originalBlind'],'slot':item['slot'],'issue':assignment['issue'],'arm':assignment['arm'],'ratings':ratings,'adjudication':adj})
 return {'kind':manifest['kind'],'selection':manifest['selection'],'candidates':items,'usage':usage(root,('review-calls.jsonl','adjudication-calls.jsonl')),'failures':failures(root,('review-calls.jsonl','adjudication-calls.jsonl')),'limitations':manifest['limitations']}


def new_pilot_summary(batches):
 pairs={};rating_status=collections.Counter();adjudications=collections.Counter();comparable=0;disagreements=0
 for batch in batches:
  if batch['batch'] not in NEW_LABELS:continue
  indexed={r['slot']:r for r in batch['reviews']}
  for r in batch['reviews']:
   rating_status.update(v['status'] for v in r['ratings'])
   if len(r['ratings'])==2 and all(v['status']=='VALID' for v in r['ratings']):
    comparable+=1
    a,b=r['ratings'];different=(a['correctness'],a['sideEffects'])!=(b['correctness'],b['sideEffects'])
    if different:
     disagreements+=1;adjudications[(r['registeredAdjudication'] or {}).get('status','MISSING')]+=1
  for run in batch['runs']:
   key=(run['project'],run['issue']);entry=pairs.setdefault(key,{})
   old=entry.get(run['arm'])
   if old and old['run']['attemptOutcome']!='NOT_RUN' and run['attemptOutcome']!='NOT_RUN':
    raise ValueError('multiple started assignments for same new issue and arm')
   if old is None or old['run']['attemptOutcome']=='NOT_RUN':entry[run['arm']]={'run':run,'review':indexed.get(run['slot'])}
 counts=collections.Counter();both_checks=0;full_scored=0;negative=[];started_issues=0
 for (project,issue),arms in pairs.items():
  if any(value['run']['attemptOutcome']!='NOT_RUN' for value in arms.values()):started_issues+=1
  if any(value['run'].get('historyRecords')==0 for value in arms.values()):negative.append(f'{project}#{issue}')
  for arm in ('keyword','memex'):counts[(arms.get(arm) or {'run':{'attemptOutcome':'NOT_RUN'}})['run']['attemptOutcome']]+=1
  if len(arms)==2 and all(value['run']['attemptOutcome']=='PASS' for value in arms.values()):both_checks+=1
  if len(arms)==2 and all(value['run'].get('status')=='completed' and value['review'] and len(value['review']['ratings'])==2 and all(r['status']=='VALID' for r in value['review']['ratings']) for value in arms.values()):full_scored+=1
 return {'distinctIssues':len(pairs),'issuesWithAnyStartedArm':started_issues,'assignmentOutcomes':dict(counts),
         'bothArmsCompleteAndChecksPass':both_checks,'bothArmsCompleteWithTwoOriginalFormatValidReviews':full_scored,
         'originalReviewStatuses':dict(rating_status),'originalComparableCandidateReviewPairs':comparable,
         'originalScoreDisagreements':disagreements,'originalDisagreementAdjudications':dict(adjudications),
         'noHistoryControls':sorted(negative)}


def summarize(base):
 all_batches=[]
 for label,name,regression in BATCHES:
  root=base/name
  if not (root/'manifest.json').exists():continue
  manifest=json.loads((root/'manifest.json').read_text());runs=[];context_path=root/'contexts.json';contexts=json.loads(context_path.read_text()) if context_path.exists() else {}
  for i,assignment in enumerate(manifest['schedule'],1):
   directory=root/'runs'/f'{i:02d}';path=directory/'result.json';x=json.loads(path.read_text()) if path.exists() else None
   projects=manifest.get('tasks',{});project=projects.get(assignment['issue']) if isinstance(projects,dict) else None
   if not project and len(manifest.get('sourceCommit',{}))==1:project=next(iter(manifest['sourceCommit']))
   item={'slot':i,'issue':assignment['issue'],'project':project,'arm':assignment['arm'],'historyRecords':contexts.get(assignment['issue'],{}).get('memoryRecordCount'),'attemptOutcome':outcome({**x,'_regression':x.get(regression)} if x else None,directory.exists()),'status':x.get('status') if x else None}
   if x:
    item.update({'changedFileCount':len(x.get('changed',[])),'modelCalls':x.get('modelCalls'),'toolCalls':x.get('toolCalls'),'publicTestCalls':x.get('publicTestCalls'),'forcedFinal':x.get('forcedFinal',False),'acceptanceExit':(x.get('acceptance') or {}).get('exitCode'),'regressionExit':(x.get(regression) or {}).get('exitCode'),'checkErrorPresent':bool(x.get('checkError'))})
   runs.append(item)
  posthoc=None
  normalized=root/'posthoc-reference-normalization/normalized.json'
  if normalized.exists():
   original=json.loads(normalized.read_text());posthoc={'normalizationStatuses':dict(collections.Counter(x.get('status') for x in original.values())),'ratings':{key:{'status':value.get('status'),'correctness':value.get('parsed',{}).get('rating',{}).get('correctness'),'sideEffects':value.get('parsed',{}).get('rating',{}).get('side_effects')} for key,value in original.items()},'adjudications':{}}
   for path in sorted((root/'posthoc-reference-normalization').glob('B*.json')):
    data=json.loads(path.read_text());parsed=data.get('parsed',{});rating=parsed.get('rating',{});posthoc['adjudications'][path.stem]={'status':'VALID' if parsed.get('valid') else 'INVALID','correctness':rating.get('correctness'),'sideEffects':rating.get('side_effects')}
  all_batches.append({'batch':label,'scoreDirectionExplicit':label in ('mixed-3','prettier-4','eslint-3','mixed-4','prettier-interrupted','prettier-route','prettier-six','prettier-unstarted','prettier-lowcost','prettier-gateway','dayjs-gateway','moment-mathjs','dayjs-mathjs','prettier-late','mathjs-late','validator-new','luxon-new','lodash-new','yup-new','validator-chartjs','chartjs-unstarted'),'sourceCommit':manifest['sourceCommit'],'plannedAssignments':len(runs),'runs':runs,'outcomes':dict(collections.Counter(x['attemptOutcome'] for x in runs)),'reviews':reviews(root,manifest.get('reviewers',[])),'posthocNormalization':posthoc,'usage':usage(root),'failures':failures(root,('solver-calls.jsonl','review-calls.jsonl','adjudication-calls.jsonl')),'qwenReportedOverLimit':qwen_limit_observations(root,manifest)})
 return {'kind':'separate-prospective-open-source-instrumentation-batches','batches':all_batches,'newPilotSummary':new_pilot_summary(all_batches),'posthocExplicitRubric':posthoc_review(base/'posthoc-explicit-rubric'),'posthocUnstartedAdjudication':unstarted_adjudications(base/'posthoc-unstarted-adjudication'),'budgetedPosthocBatch15':budgeted_posthoc(base/'20261031-batch15-posthoc-budgeted',15),'budgetedPosthocBatch16':budgeted_posthoc(base/'20261031-batch16-posthoc-budgeted',16),'fallbackAdjudicationsBatch16':fallback_adjudications(base/'20261031-batch16-fallback-adjudication'),'fallbackAdjudicationsBatches17to20':fallback_adjudications(base/'20261031-batches17-20-fallback'),'unstartedReviewsBatch17':batch17_unstarted_reviews(base/'20261031-batch17-unstarted-reviews',base/'20261031-mixed-batch17'),'diagnostics':{'reviewerRouteProbe':usage(base/'20261031-reviewer-route-probe'),'alternateSolverToolProbe':usage(base/'20261031-sol-tool-probe'),'post503HealthProbe':usage(base/'20261031-post503-route-probe'),'alternateSolverSyntheticSmoke':synthetic_smoke(base/'20261031-sol-agent-smoke','gpt-6.1-sol'),'deepseekSyntheticSmoke':synthetic_smoke(base/'20261031-deepseek-agent-smoke','deepseek-flash'),'gatewayTriage':usage(base/'20261031-1809-gateway-triage'),'gatewayTriageFailures':failures(base/'20261031-1809-gateway-triage',('calls.jsonl',)),'qwenNoThinkingProbe':usage(base/'20261031-qwen-no-thinking-probe'),'qwenReviewRouteProbe':usage(base/'20261031-qwen-review-route-probe'),'geminiReviewRouteProbe':usage(base/'20261031-gemini-review-route-probe'),'reviewBudgetProbe':usage(base/'20261031-review-budget-probe'),'timeoutHealthProbe':usage(base/'20261031-1940-timeout-health'),'transportHealthProbe':usage(base/'20261031-2055-transport-health')},'limitations':['Different batches were selected or revised after prior results and are not one pre-registered cohort.','The pre-seeded public issue discussions are not long production sessions.','Tests are partial and reviewers are AI; label validity does not prove factual support.','The numeric review direction was not specified in batches 1–5; their raw scores cannot be treated as a common scale.','Unmatched started and failed requests may have unreported tokens or fees; only explicitly registered later batches retry explicit HTTP 503, not timeouts.','Source exposure to public PRs or model pretraining cannot be excluded.']}


def main():
 p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--out',required=True);a=p.parse_args();result=summarize(pathlib.Path(a.base));pathlib.Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps([{'batch':x['batch'],'outcomes':x['outcomes'],'usage':x['usage']} for x in result['batches']]))
if __name__=='__main__':main()
