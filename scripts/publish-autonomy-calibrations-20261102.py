#!/usr/bin/env python3
"""Publish redacted synthetic and failed-calibration accounting without raw prompts."""
import json,pathlib
ROOT=pathlib.Path(__file__).resolve().parent.parent
BASE=pathlib.Path('/Users/mk-q/.local/share/memex-forward-20261102')
DEST=ROOT/'docs/assets/benchmarks/production-autonomy-20261102/calibrations.json'
def load(p):return json.loads(p.read_text())
def stage(x):
 keep=('stage','completed','responseCompleted','timeout','elapsedSeconds','usage','clientListPriceUsd','resultSubtype','subtype','exitCode','normalExit','shutdownTimeoutAfterResult','unexpectedTools','tools','mcpResultHasUnverified','hookHasUnverified')
 return {k:x[k] for k in keep if k in x}
out={'kind':'redacted-calibration-ledger','note':'Synthetic prompts, identifiers, local paths and raw answers are excluded; missing usage remains unknown. The forced-final resumed client price was cumulative in that probe, so do not add its two listed prices.','hookSmokes':[]}
for name in ('hook-smoke','hook-smoke-retry','hook-smoke-clarified','mcp-trust-smoke','forced-final-smoke'):
 path=BASE/name/'summary.json'
 if not path.exists():out['hookSmokes'].append({'name':name,'status':'MISSING'});continue
 x=load(path);out['hookSmokes'].append({'name':name,'kind':x.get('kind'),'distinctSessions':x.get('distinctSessions'),
   'sameSession':len(x.get('stages',[]))==2 and x['stages'][0].get('sessionId')==x['stages'][1].get('sessionId') if name=='forced-final-smoke' else None,
   'answerMatches':x.get('answerMatches'),'stages':[stage(y) for y in x.get('stages',[])]})
out['axiosCalibrations']=[]
for name in ('axios-6690-pilot','axios-6690-retry'):
 folder=BASE/name;row={'name':name,'arms':{}}
 for arm in ('baseline','memex'):
  p=folder/'results'/f'{arm}-s1.json';checks=folder/'results'/f'{arm}-checks.json'
  row['arms'][arm]={'session':stage(load(p)) if p.exists() else None,'checks':load(checks) if checks.exists() else None}
 out['axiosCalibrations'].append(row)
folder=BASE/'triage06-blind-canary/reviews/06'
if folder.exists():
 out['reviewCanary']={'limitation':'Packet omitted author/time metadata that agents had seen; these opinions are retained as flawed-input calibration, not cohort ratings.',
  'initialReviews':[{k:load(folder/f'{model}.json').get(k) for k in ('model','status','rating','error')} for model in ('gpt-6.1-sol','deepseek-flash')],
  'initialAdjudication':load(folder/'adjudication.json'),'posthocAdjudication':load(folder/'adjudication-recovery.json') if (folder/'adjudication-recovery.json').exists() else None}
DEST.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print('wrote',DEST)
