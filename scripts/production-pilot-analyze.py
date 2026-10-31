#!/usr/bin/env python3
"""Aggregate a private pilot without publishing tasks, answers, or tool content."""
import argparse,collections,json,pathlib,re,statistics
from pilot_citations import validate_autonomy_citations
p=argparse.ArgumentParser();p.add_argument('--frozen',required=True);p.add_argument('--trials',required=True);p.add_argument('--reviews',required=True);p.add_argument('--replacement-reviews');p.add_argument('--autonomy-reviews');p.add_argument('--replacement-autonomy-reviews');p.add_argument('--out',required=True);a=p.parse_args();frozen=pathlib.Path(a.frozen);trials=pathlib.Path(a.trials);reviews=pathlib.Path(a.reviews);out=pathlib.Path(a.out)
if out.exists():raise SystemExit('refusing to overwrite aggregate')
manifest=json.loads((frozen/'preregistered.json').read_text());episodes={e['id']:e for e in json.loads((frozen/'episodes.json').read_text())['episodes']};runs=[json.loads(x.read_text()) for x in sorted(trials.glob('pilot-*.json'))];key=json.loads((reviews/'private-blind-key.json').read_text());judgements=[json.loads(x) for x in (reviews/'judgements.jsonl').read_text().splitlines()] if (reviews/'judgements.jsonl').exists() else []
expected=[(a['episode'],arm) for a in manifest['assignments'] for arm in a['order']];assert [(r['episode'],r['arm']) for r in runs]==expected and len(runs)==len(expected) and len({r['trial'] for r in runs})==len(runs)
registered_judgements=list(judgements);replacement_judgements=[]
if a.replacement_reviews:
 replacement=pathlib.Path(a.replacement_reviews);assert json.loads((replacement/'private-blind-key.json').read_text())==key
 replacement_judgements=[json.loads(x) for x in (replacement/'judgements.jsonl').read_text().splitlines()] if (replacement/'judgements.jsonl').exists() else [];judgements+=replacement_judgements
reviewed=collections.defaultdict(dict);judge_problems=collections.Counter();judge_problems_by_model=collections.defaultdict(collections.Counter);review_usage=collections.defaultdict(lambda:collections.Counter())
for j in judgements:
 sent=j.get('requestSent',True);u=j.get('usage') or {};c=review_usage[j['reviewerModel']];c['plannedJobs']+=1;c['calls']+=int(sent);c['callsNotSent']+=int(not sent);c['promptTokens']+=u.get('prompt_tokens') or 0;c['completionTokens']+=u.get('completion_tokens') or 0;c['missingPromptFields']+=int(sent and u.get('prompt_tokens') is None);c['missingCompletionFields']+=int(sent and u.get('completion_tokens') is None);c['cachedPromptTokens']+=((u.get('prompt_tokens_details') or {}).get('cached_tokens') or 0);c['cacheCreation5mTokens']+=(u.get('claude_cache_creation_5_m_tokens') or 0);c['cacheCreation1hTokens']+=(u.get('claude_cache_creation_1_h_tokens') or 0);c['callsWithoutUsage']+=int(sent and not bool(u));c['requestBytes']+=j.get('requestBytes',0);c['responseBytes']+=j.get('responseBytes',0)
 try:
  if j['status']!='ok':raise ValueError(j['status'])
  obj=json.loads(j['raw']);blind=key[j['blindId']];e=episodes[blind['episode']];sourceids={x['id'] for x in e['pages']}
  for field in ['correctness','coverage','evidence_support']:
   if obj.get(field) is not None and (type(obj[field]) is not int or obj[field] not in (0,1,2)):raise ValueError('score')
  if not isinstance(obj.get('relevantSourceIds'),list) or any(x not in sourceids for x in obj['relevantSourceIds']):raise ValueError('source_ids')
  if obj.get('unsupported_claims') is not None and (type(obj['unsupported_claims']) is not int or obj['unsupported_claims']<0):raise ValueError('unsupported')
  if j['reviewerModel'] in reviewed[blind['trial']]:raise ValueError('duplicate')
  reviewed[blind['trial']][j['reviewerModel']]=obj
 except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e:judge_problems[str(e) or type(e).__name__]+=1;judge_problems_by_model[j['reviewerModel']][str(e) or type(e).__name__]+=1
arms={};autonomy=[]
for arm in manifest['arms']:
 rs=[r for r in runs if r['arm']==arm];events=[e for r in rs for e in r['trace']];models=[x for x in events if x['kind']=='model'];tools=[x for x in events if x['kind']=='tool'];u=collections.Counter()
 for x in models:
  usage=x.get('usage') or {};u['promptTokens']+=usage.get('prompt_tokens') or 0;u['completionTokens']+=usage.get('completion_tokens') or 0;u['missingPromptFields']+=int(usage.get('prompt_tokens') is None);u['missingCompletionFields']+=int(usage.get('completion_tokens') is None);u['cachedPromptTokens']+=((usage.get('prompt_tokens_details') or {}).get('cached_tokens') or 0);u['cacheCreation5mTokens']+=(usage.get('claude_cache_creation_5_m_tokens') or 0);u['cacheCreation1hTokens']+=(usage.get('claude_cache_creation_1_h_tokens') or 0);u['callsWithoutUsage']+=int(not bool(usage));u['requestBytes']+=x.get('requestBytes',0);u['responseBytes']+=x.get('responseBytes',0)
 scores={}
 for reviewer in ['gpt-6-astra','deepseek-flash','gpt-6.1-sol']:
  vals=[]
  for r in rs:
   obj=reviewed[r['trial']].get(reviewer);vals.append('UNKNOWN' if obj is None or obj.get('correctness') is None else str(obj['correctness']))
  scores[reviewer]=dict(collections.Counter(vals))
 dimensions={}
 for reviewer in ['gpt-6-astra','deepseek-flash','gpt-6.1-sol']:
  dimensions[reviewer]={}
  for field in ['correctness','coverage','evidence_support','unsupported_claims']:
   vals=[]
   for r in rs:
    obj=reviewed[r['trial']].get(reviewer);value=None if obj is None else obj.get(field);vals.append('UNKNOWN' if value is None else str(value))
   dimensions[reviewer][field]=dict(collections.Counter(vals))
 both=[reviewed[r['trial']] for r in rs if all(x in reviewed[r['trial']] for x in ['gpt-6-astra','deepseek-flash'])];agree=sum(x['gpt-6-astra'].get('correctness')==x['deepseek-flash'].get('correctness') and x['gpt-6-astra'].get('correctness') is not None for x in both)
 arms[arm]={'attempts':len(rs),'statusCounts':dict(collections.Counter(r['status'] for r in rs)),'nonemptyAnswers':sum(bool(r.get('answer','').strip()) for r in rs),'answerFinishLength':sum(any(x['kind']=='model' and x.get('stage')=='answer' and x.get('finishReason')=='length' for x in r['trace']) for r in rs),'intakeFinishLengthCalls':sum(x.get('stage')=='intake' and x.get('finishReason')=='length' for x in models),'intakeProblemRuns':sum(bool(r.get('intakeProblems')) for r in rs),'modelCalls':len(models),'failedModelCalls':sum(x['status']!='ok' for x in models),'gatewayUsage':dict(u),'toolCalls':dict(collections.Counter(x['name'] for x in tools)),'executedToolCalls':sum(x['status']=='ok' for x in tools),'duplicateReadsAvoided':sum(x['status']=='duplicate_reused' for x in tools),'duplicateWritesBlocked':sum(x['status']=='duplicate_write_blocked' for x in tools),'failedToolCalls':sum(x['status']=='error' for x in tools),'toolRoundLimits':sum(x['kind']=='tool_limit' for x in events),'finalizationStatusCounts':dict(collections.Counter(x['status'] for x in events if x['kind']=='tool_finalization')),'elapsedSecondsMedian':statistics.median(r['elapsedSeconds'] for r in rs),'elapsedSecondsMax':max(r['elapsedSeconds'] for r in rs),'parentCpuSeconds':sum(r['parentCpuSeconds'] for r in rs),'childCpuUserSeconds':sum(r['childCpuUserSeconds'] for r in rs),'childCpuSystemSeconds':sum(r['childCpuSystemSeconds'] for r in rs),'storeBytesTotal':sum(r['storeBytes'] for r in rs),'machineCorrectnessScores':scores,'machineScoresByDimension':dimensions,'bothRegisteredJudgesValid':len(both),'bothRegisteredNonNullCorrectness':sum(all(x[m].get('correctness') is not None for m in ['gpt-6-astra','deepseek-flash']) for x in both),'bothRegisteredSameNonNullCorrectness':agree,'primaryAndReplacementValid':sum(all(x in reviewed[r['trial']] for x in ['gpt-6-astra','gpt-6.1-sol']) for r in rs),'primaryAndReplacementSameNonNullCorrectness':sum(all(x in reviewed[r['trial']] for x in ['gpt-6-astra','gpt-6.1-sol']) and reviewed[r['trial']]['gpt-6-astra'].get('correctness') is not None and reviewed[r['trial']]['gpt-6-astra'].get('correctness')==reviewed[r['trial']]['gpt-6.1-sol'].get('correctness') for r in rs)}
 arms[arm]['answerContinuationRuns']=sum(any(e.get('kind')=='answer_continuation' for e in r['trace']) for r in rs)
 arms[arm]['answerContinuationCalls']=sum(e.get('kind')=='answer_continuation' for e in events)
 arms[arm]['answerContinuationCompletedRuns']=sum(r['status']=='ok' and any(e.get('kind')=='answer_continuation' for e in r['trace']) for r in rs)
 if arm=='pager_tools_write':
  for r in rs:
   ts=[x for x in r['trace'] if x['kind']=='tool'];saved=[];written_bodies=[]
   for x in ts:
    if x['name']=='memory_write' and x['stage']=='intake' and x['status']=='ok':
     m=re.search(r'Saved (mem_[a-z0-9]+)',x.get('result',''))
     if m:saved.append(m.group(1));written_bodies.append(str(x.get('arguments',{}).get('body','')))
   opened=[x.get('arguments',{}).get('id') for x in ts if x['name']=='memory_open' and x['stage']=='answer' and x['status']=='ok'];searches=[x for x in ts if x['name']=='memory_search' and x['stage']=='answer' and x['status']=='ok'];matched=[v for v in opened if v in saved]
   pager_ids=[id for event in r['trace'] if event['kind']=='pager' for id in event.get('ids',[]) if id in saved]
   answer_writes=[x for x in ts if x['name']=='memory_write' and x['stage']=='answer' and x['status']=='ok']
   prior=episodes[r['episode']]['pages'];exact=sum(bool(body.strip()) and any(body in p['body'] for p in prior) for body in written_bodies)
   autonomy.append({'trial':r['trial'],'preQuestionWrites':len(saved),'writeBodiesExactlyPresentInEarlierArchive':exact,'otherWriteFidelity':'UNKNOWN','answerWrites':len(answer_writes),'answerSearchCalls':len(searches),'searchReturnedOwnWrittenRecord':any(id in x.get('result','') for x in searches for id in saved),'answerOpens':len(opened),'pagerIncludedOwnWrittenRecord':bool(pager_ids),'citedPagerOwnRecord':any(v in r.get('answer','') for v in pager_ids),'openedOwnWrittenRecord':bool(matched),'citedOpenedOwnRecord':any(v in r.get('answer','') for v in matched)})
assert all(len(e['pages'])>0 and all(x['availableAfter']<e['querySeq'] for x in e['fullReferencePages']) and (e['summarySeq'] is None or e['summarySeq']<e['querySeq']) and all(x['seq']<e['querySeq'] for x in e['tail']) for e in episodes.values())
result={'kind':'exploratory-pilot-aggregate','registrationManifestSha256':(frozen/'preregistered.sha256').read_text().split()[0],'sourceBase':manifest['repoCommit'],'sessions':manifest['sessionCount'],'tasks':manifest['taskCount'],'attempts':len(runs),'randomSeed':manifest['randomSeed'],'arms':arms,'autonomyObserved':autonomy,'reviews':{'plannedRegisteredReviews':sum(bool(r.get('answer','').strip()) and r['status']=='ok' for r in runs)*2,'plannedReplacementReviews':sum(bool(r.get('answer','').strip()) and r['status']=='ok' for r in runs) if a.replacement_reviews else 0,'registeredReceived':len(registered_judgements),'replacementReceived':len(replacement_judgements),'received':len(judgements),'valid':sum(len(v) for v in reviewed.values()),'validByModel':dict(collections.Counter(model for per_trial in reviewed.values() for model in per_trial)),'problems':dict(judge_problems),'problemsByModel':{k:dict(v) for k,v in judge_problems_by_model.items()},'usageByModel':{k:dict(v) for k,v in review_usage.items()},'humanLabels':0},'billing':{'actualInvoice':'UNKNOWN','historicalIngestion':'UNKNOWN','providerDiscounts':'UNKNOWN','localComputePricing':'UNKNOWN','storagePricing':'UNKNOWN','humanReviewCost':'UNKNOWN','costPerAttempt':'UNKNOWN','costPerVerifiedSuccess':'UNKNOWN'},'limitations':manifest['limits']+['reviewer references clipped to 1000 characters per earlier message','two model judges are not independent human annotators','model scores are not factual ground truth','concurrent task execution means elapsed times are not low-load benchmarks']}
if a.autonomy_reviews:
 ap=pathlib.Path(a.autonomy_reviews)/'autonomy-judgements.jsonl';rr=[json.loads(x) for x in ap.read_text().splitlines()] if ap.exists() else [];registered_count=len(rr);replacement_count=0
 if a.replacement_autonomy_reviews:
  rp=pathlib.Path(a.replacement_autonomy_reviews)/'autonomy-judgements.jsonl';extra=[json.loads(x) for x in rp.read_text().splitlines()] if rp.exists() else [];replacement_count=len(extra);rr+=extra
 valid=[];issues=collections.Counter();au=collections.defaultdict(lambda:collections.Counter());runmap={r['trial']:r for r in runs}
 for x in rr:
  sent=x.get('requestSent',True);usage=x.get('usage') or {};c=au[x['reviewerModel']];c['plannedJobs']+=1;c['calls']+=int(sent);c['callsNotSent']+=int(not sent);c['promptTokens']+=usage.get('prompt_tokens') or 0;c['completionTokens']+=usage.get('completion_tokens') or 0;c['cachedPromptTokens']+=((usage.get('prompt_tokens_details') or {}).get('cached_tokens') or 0);c['cacheCreation5mTokens']+=(usage.get('claude_cache_creation_5_m_tokens') or 0);c['cacheCreation1hTokens']+=(usage.get('claude_cache_creation_1_h_tokens') or 0);c['missingPromptFields']+=int(sent and usage.get('prompt_tokens') is None);c['missingCompletionFields']+=int(sent and usage.get('completion_tokens') is None);c['callsWithoutUsage']+=int(sent and not bool(usage));c['requestBytes']+=x.get('requestBytes',0);c['responseBytes']+=x.get('responseBytes',0)
  try:
   if x['status']!='ok':raise ValueError(x['status'])
   obj=json.loads(x['raw']);run=runmap[x['trial']];ids={z['id'] for z in episodes[run['episode']]['pages']}
   if run['arm']!='pager_tools_write':raise ValueError('arm')
   for field in ['memory_needed','writes_faithful','answer_used_prior_write']:
    if obj.get(field) not in ('yes','no','unknown',None):raise ValueError('score')
   citation_problem=validate_autonomy_citations(obj,episodes[run['episode']],run,manifest.get('autonomyCitationSchema')=='separate-history-and-memory')
   if citation_problem:raise ValueError(citation_problem)
   observed=next(z for z in autonomy if z['trial']==x['trial'])
   if not (observed['preQuestionWrites'] or observed['answerWrites']) and obj.get('writes_faithful') is not None:raise ValueError('no_writes')
   valid.append((x,obj))
  except (ValueError,KeyError,TypeError,json.JSONDecodeError) as e:issues[str(e) or type(e).__name__]+=1
 fields={}
 for model in ['gpt-6-astra','deepseek-flash','gpt-6.1-sol']:
  fields[model]={field:dict(collections.Counter(str(obj.get(field)) if obj.get(field) is not None else 'UNKNOWN' for x,obj in valid if x['reviewerModel']==model)) for field in ['memory_needed','writes_faithful','answer_used_prior_write']}
 audit_key='autonomyMachineAudit' if manifest.get('autonomyAudit') else 'postHocAutonomyMachineAudit'
 result[audit_key]={'plannedInitial':len(autonomy)*2,'initialReceived':registered_count,'replacementReceived':replacement_count,'received':len(rr),'valid':len(valid),'validByModel':dict(collections.Counter(x['reviewerModel'] for x,_ in valid)),'problems':dict(issues),'scoresByModel':fields,'usageByModel':{k:dict(v) for k,v in au.items()},'limitations':['planned and unblinded' if manifest.get('autonomyAudit') else 'post hoc and unblinded','model opinions, not human labels or proof of fidelity','same historical tasks and clipped evidence']}
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'attempts':result['attempts'],'reviewReceived':len(judgements),'reviewValid':result['reviews']['valid'],'problems':dict(judge_problems),'arms':{k:{'status':v['statusCounts'],'tools':v['toolCalls']} for k,v in arms.items()},'autonomy':autonomy}))
