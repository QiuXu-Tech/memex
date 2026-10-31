#!/usr/bin/env python3
"""Sanitize registered pilot results without treating missing records as successes."""
import argparse,collections,copy,hashlib,json,pathlib

BATCHES=[('eslint-1','20261031-eslint-batch1','upstreamRegression'),('lodash-interrupted','20261031-lodash-batch2','regressionControls'),('lodash-repair','20261031-lodash-batch3','regressionControls'),('eslint-2','20261031-eslint-batch4','regressionControls'),('lodash-model-check','20261031-lodash-batch5','regressionControls'),('mixed-3','20261031-mixed-batch6','regressionControls'),('prettier-4','20261031-prettier-batch7','regressionControls'),('eslint-3','20261031-eslint-batch8','regressionControls'),('mixed-4','20261031-mixed-batch9','regressionControls'),('prettier-interrupted','20261031-prettier-batch10','regressionControls'),('prettier-route','20261031-prettier-batch11','regressionControls'),('prettier-six','20261031-prettier-batch12','regressionControls'),('prettier-unstarted','20261031-prettier-batch13','regressionControls'),('prettier-lowcost','20261031-prettier-batch14','regressionControls'),('prettier-gateway','20261031-prettier-batch15','regressionControls'),('dayjs-gateway','20261031-dayjs-batch16','regressionControls'),('moment-mathjs','20261031-mixed-batch17','regressionControls')]
BATCHES.append(('dayjs-mathjs','20261031-mixed-batch18','regressionControls'))
BATCHES.append(('prettier-late','20261031-prettier-batch19','regressionControls'))
BATCHES.append(('mathjs-late','20261031-mathjs-batch20','regressionControls'))
BATCHES.append(('validator-new','20261031-validator-batch21','regressionControls'))
BATCHES.append(('luxon-new','20261031-luxon-batch22','regressionControls'))
BATCHES.extend([('lodash-new','20261031-lodash-batch23','regressionControls'),('yup-new','20261031-yup-batch24','regressionControls'),('validator-chartjs','20261031-mixed-batch25','regressionControls')])
BATCHES.append(('chartjs-unstarted','20261031-chartjs-batch26','regressionControls'))
BATCHES.extend([('independent-27','20261031-independent-batch27','regressionControls'),('independent-28','20261031-independent-batch28','regressionControls'),('setup-stop-29','20261031-independent-batch29','regressionControls'),('independent-30','20261031-independent-batch30','regressionControls'),('independent-31','20261031-independent-batch31','regressionControls'),('independent-32','20261031-independent-batch32','regressionControls'),('independent-35','20261031-independent-batch35','regressionControls')])
NEW_LABELS={'prettier-gateway','dayjs-gateway','moment-mathjs','dayjs-mathjs','prettier-late','mathjs-late','validator-new','luxon-new','lodash-new','yup-new','validator-chartjs','chartjs-unstarted'}
FOLLOWUP_LABELS={'independent-27','independent-28','independent-30','independent-31','independent-32','independent-35'}

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


def solver_limit_observations(root, manifest):
 path=root/'solver-calls.jsonl';normal=manifest.get('maxOutputTokens');forced=manifest.get('maxForcedFinalTokens')
 if not path.exists() or not isinstance(normal,int) or not isinstance(forced,int):return []
 digest=hashlib.sha256(path.read_bytes()).hexdigest();rows=[]
 for line in path.read_text().splitlines():
  event=json.loads(line);value=event.get('usage',{}).get('completion_tokens')
  limit=forced if ':final' in event.get('operationLabel','') else normal
  if event.get('status')=='ok' and isinstance(value,int) and value>limit:
   rows.append({'at':event.get('at'),'label':event.get('label'),'model':event.get('model'),'requestedMaxTokens':limit,'reportedCompletionTokens':value,'logSha256':digest})
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


def posthoc_invalid_adjudications(root):
 if not (root/'manifest.json').exists():return None
 manifest=json.loads((root/'manifest.json').read_text());items=[]
 for item in manifest['candidates']:
  path=root/'adjudications'/f"{item['blind']}.json";result={'status':'MISSING'}
  if path.exists():
   data=json.loads(path.read_text());parsed=data.get('parsed',{});rating=parsed.get('rating',{})
   result={'status':'VALID' if parsed.get('valid') else 'INVALID','eventStatus':data.get('eventStatus'),'correctness':rating.get('correctness'),'sideEffects':rating.get('side_effects')}
  items.append({**{k:item[k] for k in ('blind','source','sourceBlind','slot','issue','arm')},'result':result})
 return {'kind':manifest['kind'],'selection':manifest['selection'],'model':manifest['model'],'candidates':items,'usage':usage(root,('calls.jsonl',)),'failures':failures(root,('calls.jsonl',)),'limitations':manifest['limitations']}


def posthoc_alternate_reviews(root,base):
 if not (root/'manifest.json').exists():return None
 manifest=json.loads((root/'manifest.json').read_text());items=[]
 def rating(path):
  if not path.exists():return {'status':'MISSING'}
  data=json.loads(path.read_text());parsed=data.get('parsed',{});value=parsed.get('rating',{})
  return {'status':'VALID' if parsed.get('valid') else 'INVALID','eventStatus':data.get('eventStatus'),'correctness':value.get('correctness'),'sideEffects':value.get('side_effects')}
 for item in manifest['candidates']:
  blind=item['blind'];items.append({**{k:item[k] for k in ('blind','source','sourceBlind','slot','issue','arm')},
   'firstReview':rating(base/item['firstReviewPath']),'supplementaryReview':rating(root/'reviews'/f'{blind}.json'),
   'supplementaryAdjudication':rating(root/'adjudications'/f'{blind}.json')})
 return {'kind':manifest['kind'],'selection':manifest['selection'],'reviewer':manifest['reviewer'],'adjudicator':manifest['adjudicator'],
         'candidates':items,'usage':usage(root,('review-calls.jsonl','adjudication-calls.jsonl')),
         'failures':failures(root,('review-calls.jsonl','adjudication-calls.jsonl')),'limitations':manifest['limitations']}


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


def supplemental_coverage(batches, batch15, batch16, batch17):
 pairs={}
 for batch in batches:
  if batch['batch'] not in NEW_LABELS:continue
  indexed={r['slot']:r for r in batch['reviews']}
  for run in batch['runs']:
   arms=pairs.setdefault((run['project'],run['issue']),{});old=arms.get(run['arm'])
   if old and old['run']['attemptOutcome']!='NOT_RUN':continue
   review=indexed.get(run['slot']);arms[run['arm']]={'run':run,'ratings':[r['status'] for r in review['ratings']] if review else []}
 def covered():
  return {k for k,arms in pairs.items() if len(arms)==2 and all(a['run'].get('status')=='completed' and a['ratings']==['VALID','VALID'] for a in arms.values())}
 original=covered()
 for c in (batch15 or {}).get('candidates',[]):
  arm=pairs[('prettier',c['issue'])][c['arm']]
  if len(c['ratings'])==2 and all(r['status']=='VALID' for r in c['ratings']):arm['ratings']=['VALID','VALID']
 for c in (batch16 or {}).get('candidates',[]):
  if c['posthocQwen']['status']=='VALID':pairs[('dayjs',c['issue'])][c['arm']]['ratings']=[c['originalDeepseek']['status'],'VALID']
 for c in (batch17 or {}).get('candidates',[]):
  arm=pairs[('mathjs',c['issue'])][c['arm']]
  if arm['ratings']==['MISSING','MISSING']:arm['ratings']=[r['status'] for r in c['ratings']]
 combined=covered();controls={k for k,arms in pairs.items() if any(a['run'].get('historyRecords')==0 for a in arms.values())}
 return {'issuePairsWithOriginalOrSupplementaryRatings':len(combined),'noHistoryControlsIncluded':len(combined & controls),
         'issuePairsExcludingNoHistoryControls':len(combined-controls),'additionalIssuesAfterSupplementaryReviews':sorted(f'{p}#{n}' for p,n in combined-original)}


def historical_resolution_coverage(batches,batch15,batch16,batch17,fallback16,fallback17to20,posthoc33):
 pairs={}
 for batch in batches:
  if batch['batch'] not in NEW_LABELS:continue
  indexed={r['slot']:copy.deepcopy(r) for r in batch['reviews']}
  for run in batch['runs']:
   arms=pairs.setdefault((run['project'],run['issue']),{});old=arms.get(run['arm'])
   if old and old['run']['attemptOutcome']!='NOT_RUN':continue
   arms[run['arm']]={'run':run,'review':indexed.get(run['slot']),'batch':batch['batch']}
 for c in (batch15 or {}).get('candidates',[]):
  pairs[('prettier',c['issue'])][c['arm']]['review']=copy.deepcopy(c)
 for c in (batch16 or {}).get('candidates',[]):
  arm=pairs[('dayjs',c['issue'])][c['arm']];second=c['originalQwen'] if c['originalQwen']['status']=='VALID' else c['posthocQwen']
  arm['review']={'slot':c['slot'],'ratings':[c['originalDeepseek'],second],'registeredAdjudication':c['posthocAdjudication']};arm['source']='batch16-posthoc'
 for c in (batch17 or {}).get('candidates',[]):
  arm=pairs[('mathjs',c['issue'])][c['arm']]
  if not arm['review'] or all(r['status']=='MISSING' for r in arm['review']['ratings']):
   arm['review']={'slot':c['slot'],'ratings':c['ratings'],'registeredAdjudication':c['adjudication']}
 for c in (fallback16 or {}).get('candidates',[]):
  if c['result']['status']!='VALID':continue
  for arms in pairs.values():
   for arm in arms.values():
    if arm.get('source')=='batch16-posthoc' and arm['run']['slot']==c['slot']:arm['review']['registeredAdjudication']=c['result']
 names={'17':'moment-mathjs','18':'dayjs-mathjs','19':'prettier-late','20':'mathjs-late'}
 for c in (fallback17to20 or {}).get('candidates',[]):
  if c['result']['status']!='VALID':continue
  for arms in pairs.values():
   for arm in arms.values():
    if arm['batch']==names.get(c['batch']) and arm['run']['slot']==c['slot']:arm['review']['registeredAdjudication']=c['result']
 def counts():
  scored=[];resolved=[];unresolved=[];comparisons=collections.Counter()
  for key,arms in pairs.items():
   if set(arms)!={'keyword','memex'} or any(a['run'].get('historyRecords')==0 for a in arms.values()):continue
   if not all(a['run'].get('status')=='completed' and a['review'] and len(a['review']['ratings'])==2 and all(r['status']=='VALID' for r in a['review']['ratings']) for a in arms.values()):continue
   scored.append(key);ok=True
   for arm,a in arms.items():
    review=a['review'];first,second=review['ratings']
    if (first['correctness'],first['sideEffects'])!=(second['correctness'],second['sideEffects']) and (review.get('registeredAdjudication') or {}).get('status')!='VALID':
     ok=False;unresolved.append({'project':key[0],'issue':key[1],'arm':arm,'batch':a['batch'],'slot':a['run']['slot']})
   if ok:
    resolved.append(key);scores={}
    for arm,a in arms.items():
     review=a['review'];first,second=review['ratings']
     choice=first if (first['correctness'],first['sideEffects'])==(second['correctness'],second['sideEffects']) else review['registeredAdjudication']
     scores[arm]=choice.get('correctness')
    k,v=scores['keyword'],scores['memex']
    comparisons['UNKNOWN' if k is None or v is None else 'MEMEX_HIGHER' if v>k else 'KEYWORD_HIGHER' if k>v else 'EQUAL']+=1
  return {'pairsWithTwoValidRatingsPerArm':len(scored),'pairsWithValidDisagreementAdjudications':len(resolved),
          'resolvedIssueIds':sorted(f'{project}#{issue}' for project,issue in resolved),
          'resolvedCorrectnessComparisons':dict(comparisons),'unresolvedCandidates':unresolved}
 before=counts()
 lookup={'20261031-batch15-posthoc-budgeted':'prettier-gateway','20261031-prettier-batch19':'prettier-late',
         '20261031-luxon-batch22':'luxon-new','20261031-lodash-batch23':'lodash-new'}
 for c in (posthoc33 or {}).get('candidates',[]):
  if c['result']['status']!='VALID':continue
  for arms in pairs.values():
   for arm in arms.values():
    if arm['batch']==lookup.get(c['source']) and arm['run']['slot']==c['slot'] and arm['run']['arm']==c['arm']:
     arm['review']['registeredAdjudication']=c['result']
 return {'excludesNoHistoryControls':True,'beforeV33':before,'includingV33':counts(),
         'note':'Supplementary post-hoc ratings and adjudications are included where identified; format validity does not establish correctness.'}


def followup_summary(batches,supplementary=None):
 pairs={};rating_status=collections.Counter();adjudications=collections.Counter();outcomes=collections.Counter()
 source_labels={'20261031-independent-batch31':'independent-31','20261031-independent-batch32':'independent-32'}
 for batch in batches:
  if batch['batch'] not in FOLLOWUP_LABELS:continue
  indexed={r['slot']:copy.deepcopy(r) for r in batch['reviews']}
  for c in (supplementary or {}).get('candidates',[]):
   if source_labels.get(c['source'])!=batch['batch'] or c['supplementaryReview']['status']!='VALID':continue
   review=indexed.get(c['slot'])
   if not review or len(review['ratings'])!=2 or review['ratings'][0]['status']!='VALID' or review['ratings'][1]['status']=='VALID':raise ValueError('unexpected supplementary review source')
   review['ratings'][1]=c['supplementaryReview'];review['registeredAdjudication']=c['supplementaryAdjudication'];review['usedSupplementary']=True
  for run in batch['runs']:
   key=(run['project'],run['issue']);arms=pairs.setdefault(key,{})
   old=arms.get(run['arm'])
   if old and old['run']['attemptOutcome']!='NOT_RUN' and run['attemptOutcome']!='NOT_RUN':raise ValueError('duplicate started follow-up issue and arm')
   if old is None or old['run']['attemptOutcome']=='NOT_RUN':arms[run['arm']]={'run':run,'review':indexed.get(run['slot'])}
  for review in indexed.values():
   rating_status.update(r['status'] for r in review['ratings'])
   if len(review['ratings'])==2 and all(r['status']=='VALID' for r in review['ratings']):
    a,b=review['ratings']
    if (a['correctness'],a['sideEffects'])!=(b['correctness'],b['sideEffects']):
     adjudications[(review['registeredAdjudication'] or {}).get('status','MISSING')]+=1
 details=[];comparisons=collections.Counter()
 for arms in pairs.values():outcomes.update(x['run']['attemptOutcome'] for x in arms.values())
 for (project,issue),arms in sorted(pairs.items()):
  def scored(x):
   r=x['review']
   return x['run'].get('status')=='completed' and r and len(r['ratings'])==2 and all(v['status']=='VALID' for v in r['ratings'])
  def resolved(x):
   if not scored(x):return False
   r=x['review'];a,b=r['ratings']
   return (a['correctness'],a['sideEffects'])==(b['correctness'],b['sideEffects']) or (r['registeredAdjudication'] or {}).get('status')=='VALID'
  complete=set(arms)=={'keyword','memex'} and all(scored(x) for x in arms.values())
  done=bool(complete and all(resolved(x) for x in arms.values()));scores={}
  if done:
   for arm,x in arms.items():
    review=x['review'];first,second=review['ratings']
    choice=first if (first['correctness'],first['sideEffects'])==(second['correctness'],second['sideEffects']) else review['registeredAdjudication']
    scores[arm]=choice.get('correctness')
   k,v=scores['keyword'],scores['memex'];comparisons['UNKNOWN' if k is None or v is None else 'MEMEX_HIGHER' if v>k else 'KEYWORD_HIGHER' if k>v else 'EQUAL']+=1
  details.append({'project':project,'issue':issue,'arms':{arm:x['run']['attemptOutcome'] for arm,x in arms.items()},
                  'bothArmsCompleteWithTwoFormatValidReviews':bool(complete),
                  'bothArmsCompleteWithDisagreementsResolved':done,'effectiveCorrectness':scores,
                  'usedSupplementaryReviews':any((x['review'] or {}).get('usedSupplementary',False) for x in arms.values())})
 return {'distinctIssues':len(pairs),'assignmentOutcomes':dict(outcomes),
         'bothArmsCompleteWithTwoFormatValidReviews':sum(x['bothArmsCompleteWithTwoFormatValidReviews'] for x in details),
         'bothArmsCompleteWithDisagreementsResolved':sum(x['bothArmsCompleteWithDisagreementsResolved'] for x in details),
         'resolvedCorrectnessComparisons':dict(comparisons),'reviewStatuses':dict(rating_status),'disagreementAdjudications':dict(adjudications),'issues':details}


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
    item.update({'changedFileCount':len(x.get('changed',[])),'modelCalls':x.get('modelCalls'),'toolCalls':x.get('toolCalls'),'deniedToolCalls':x.get('deniedToolCalls'),'publicTestCalls':x.get('publicTestCalls'),'forcedFinal':x.get('forcedFinal',False),'acceptanceExit':(x.get('acceptance') or {}).get('exitCode'),'regressionExit':(x.get(regression) or {}).get('exitCode'),'checkErrorPresent':bool(x.get('checkError'))})
   runs.append(item)
  posthoc=None
  normalized=root/'posthoc-reference-normalization/normalized.json'
  if normalized.exists():
   original=json.loads(normalized.read_text());posthoc={'normalizationStatuses':dict(collections.Counter(x.get('status') for x in original.values())),'ratings':{key:{'status':value.get('status'),'correctness':value.get('parsed',{}).get('rating',{}).get('correctness'),'sideEffects':value.get('parsed',{}).get('rating',{}).get('side_effects')} for key,value in original.items()},'adjudications':{}}
   for path in sorted((root/'posthoc-reference-normalization').glob('B*.json')):
    data=json.loads(path.read_text());parsed=data.get('parsed',{});rating=parsed.get('rating',{});posthoc['adjudications'][path.stem]={'status':'VALID' if parsed.get('valid') else 'INVALID','correctness':rating.get('correctness'),'sideEffects':rating.get('side_effects')}
  all_batches.append({'batch':label,'scoreDirectionExplicit':label in FOLLOWUP_LABELS or label in ('mixed-3','prettier-4','eslint-3','mixed-4','prettier-interrupted','prettier-route','prettier-six','prettier-unstarted','prettier-lowcost','prettier-gateway','dayjs-gateway','moment-mathjs','dayjs-mathjs','prettier-late','mathjs-late','validator-new','luxon-new','lodash-new','yup-new','validator-chartjs','chartjs-unstarted'),'sourceCommit':manifest['sourceCommit'],'plannedAssignments':len(runs),'runs':runs,'outcomes':dict(collections.Counter(x['attemptOutcome'] for x in runs)),'reviews':reviews(root,manifest.get('reviewers',[])),'posthocNormalization':posthoc,'usage':usage(root),'failures':failures(root,('solver-calls.jsonl','review-calls.jsonl','adjudication-calls.jsonl')),'qwenReportedOverLimit':qwen_limit_observations(root,manifest),'solverReportedOverLimit':solver_limit_observations(root,manifest) if label in FOLLOWUP_LABELS else []})
 b15=budgeted_posthoc(base/'20261031-batch15-posthoc-budgeted',15);b16=budgeted_posthoc(base/'20261031-batch16-posthoc-budgeted',16);b17=batch17_unstarted_reviews(base/'20261031-batch17-unstarted-reviews',base/'20261031-mixed-batch17')
 f16=fallback_adjudications(base/'20261031-batch16-fallback-adjudication');f17=fallback_adjudications(base/'20261031-batches17-20-fallback');p33=posthoc_invalid_adjudications(base/'20261031-posthoc-adjudication-v33')
 p34=posthoc_alternate_reviews(base/'20261031-posthoc-review-v34',base)
 return {'kind':'separate-prospective-open-source-instrumentation-batches','batches':all_batches,'newPilotSummary':new_pilot_summary(all_batches),'supplementaryCoverage':supplemental_coverage(all_batches,b15,b16,b17),'distinctIssueFollowupSummary':followup_summary(all_batches),'distinctIssueFollowupSupplementaryCoverage':followup_summary(all_batches,p34),'posthocReviewsV34':p34,'historicalResolutionCoverage':historical_resolution_coverage(all_batches,b15,b16,b17,f16,f17,p33),'posthocAdjudicationsV33':p33,'posthocExplicitRubric':posthoc_review(base/'posthoc-explicit-rubric'),'posthocUnstartedAdjudication':unstarted_adjudications(base/'posthoc-unstarted-adjudication'),'budgetedPosthocBatch15':b15,'budgetedPosthocBatch16':b16,'fallbackAdjudicationsBatch16':f16,'fallbackAdjudicationsBatches17to20':f17,'unstartedReviewsBatch17':b17,'diagnostics':{'reviewerRouteProbe':usage(base/'20261031-reviewer-route-probe'),'alternateSolverToolProbe':usage(base/'20261031-sol-tool-probe'),'post503HealthProbe':usage(base/'20261031-post503-route-probe'),'alternateSolverSyntheticSmoke':synthetic_smoke(base/'20261031-sol-agent-smoke','gpt-6.1-sol'),'deepseekSyntheticSmoke':synthetic_smoke(base/'20261031-deepseek-agent-smoke','deepseek-flash'),'gatewayTriage':usage(base/'20261031-1809-gateway-triage'),'gatewayTriageFailures':failures(base/'20261031-1809-gateway-triage',('calls.jsonl',)),'qwenNoThinkingProbe':usage(base/'20261031-qwen-no-thinking-probe'),'qwenReviewRouteProbe':usage(base/'20261031-qwen-review-route-probe'),'geminiReviewRouteProbe':usage(base/'20261031-gemini-review-route-probe'),'reviewBudgetProbe':usage(base/'20261031-review-budget-probe'),'timeoutHealthProbe':usage(base/'20261031-1940-timeout-health'),'transportHealthProbe':usage(base/'20261031-2055-transport-health'),'v27JudgeRouteProbe':usage(base/'20261031-v27-judge-route-probe')},'limitations':['Different batches were selected or revised after prior results and are not one pre-registered cohort.','The pre-seeded public issue discussions are not long production sessions.','Tests are partial and reviewers are AI; label validity does not prove factual support.','The numeric review direction was not specified in batches 1–5; their raw scores cannot be treated as a common scale.','Unmatched started and failed requests may have unreported tokens or fees; only explicitly registered later batches retry explicit HTTP 503, not timeouts.','Source exposure to public PRs or model pretraining cannot be excluded.']}


def main():
 p=argparse.ArgumentParser();p.add_argument('--base',required=True);p.add_argument('--out',required=True);a=p.parse_args();result=summarize(pathlib.Path(a.base));pathlib.Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps([{'batch':x['batch'],'outcomes':x['outcomes'],'usage':x['usage']} for x in result['batches']]))
if __name__=='__main__':main()
