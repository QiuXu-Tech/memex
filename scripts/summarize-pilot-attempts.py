#!/usr/bin/env python3
"""Account for completed files from complete or safely stopped pilot shards."""
import argparse,collections,json,pathlib
p=argparse.ArgumentParser();p.add_argument('--shards',required=True);p.add_argument('--out',required=True);p.add_argument('--planned',type=int,required=True);a=p.parse_args();out=pathlib.Path(a.out)
if out.exists():raise SystemExit('refusing to overwrite attempts summary')
runs=[json.loads(p.read_text()) for p in pathlib.Path(a.shards).glob('*/pilot-*.json')];assert len({r['trial'] for r in runs})==len(runs);models=[e for r in runs for e in r['trace'] if e.get('kind')=='model'];u=collections.Counter();errors=collections.Counter()
for e in models:
 v=e.get('usage') or {};details=v.get('prompt_tokens_details') or {}
 for key,field in [('prompt_tokens','promptTokensReported'),('completion_tokens','completionTokensReported')]:u[field]+=v.get(key) or 0;u[field+'MissingCalls']+=int(v.get(key) is None)
 u['cachedPromptTokensReported']+=details.get('cached_tokens') or 0;u['cachedPromptTokensMissingCalls']+=int(details.get('cached_tokens') is None)
 u['requestBytesReported']+=e.get('requestBytes') or 0;u['responseBytesReported']+=e.get('responseBytes') or 0
 if e.get('status')!='ok':errors[str(e.get('httpStatus') or e.get('errorType') or e.get('status'))]+=1
result={'plannedTrials':a.planned,'recordedTrials':len(runs),'unrecordedTrials':a.planned-len(runs),'trialStatuses':dict(collections.Counter(r['status'] for r in runs)),'modelCalls':len(models),'modelCallStatuses':dict(collections.Counter(e.get('status','UNKNOWN') for e in models)),'failedModelTypes':dict(errors),'modelUsage':dict(u),'continuationCalls':sum(e.get('kind')=='answer_continuation' for r in runs for e in r['trace']),'billing':'UNKNOWN','limitations':['Unrecorded trials were not necessarily started.','Failed calls may have unreported gateway usage or fees.','This summary excludes reviewer and audit calls.']}
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
