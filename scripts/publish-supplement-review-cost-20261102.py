#!/usr/bin/env python3
"""Publish a redacted, heuristic match of successful reviewer calls to UI wallet rows."""
import collections,datetime,json,pathlib
from decimal import Decimal
ROOT=pathlib.Path(__file__).resolve().parent.parent
PRIVATE=pathlib.Path('/Users/mk-q/.local/share/memex-forward-20261102')
BASE=PRIVATE/'supplement-triage/reviews'
DEST=ROOT/'docs/assets/benchmarks/production-autonomy-20261102/supplement-review-cost-reconciliation.json'
NAMES={'s':'gpt-6.1-sol','t':'gpt-6.1-terra','d':'deepseek-flash','g':'gemini-3.8-flash'}
rows={}
for field in (PRIVATE/'supplement-review-ui-matches.txt').read_text().strip().split(';'):
 task,code,amount,delta=field.split('|');key=(task,NAMES[code]);assert key not in rows
 rows[key]=(Decimal(amount),int(delta))
events={};failed=[]
for file in sorted(list(BASE.glob('[0-9][0-9]/gateway.jsonl'))+list((BASE/'posthoc-rescue').glob('[0-9][0-9]-gateway.jsonl'))):
 task=file.parent.name if file.name=='gateway.jsonl' else file.name[:2]
 for line in file.read_text().splitlines():
  event=json.loads(line)
  if event.get('status')=='started':continue
  if event.get('status')!='ok':
   failed.append({'task':task,'model':event.get('model'),'status':event.get('status'),'errorType':event.get('errorType')});continue
  key=(task,event['model']);assert key not in events;events[key]=event
assert len(rows)==90 and set(rows)==set(events) and len(failed)==2
receipts=[];models=collections.defaultdict(lambda:{'calls':0,'usd':Decimal(0)})
for key,(amount,delta) in rows.items():
 assert abs(delta)<=3000 and amount>=0
 event=events[key];usage=event['usage'];finish=datetime.datetime.fromisoformat(event['at'])+datetime.timedelta(seconds=event['elapsedSeconds'])
 assert type(usage['prompt_tokens']) is int and type(usage['completion_tokens']) is int
 models[key[1]]['calls']+=1;models[key[1]]['usd']+=amount
 receipts.append({'task':key[0],'model':key[1],'inputTokens':usage['prompt_tokens'],'outputTokens':usage['completion_tokens'],
  'responseFinishedAt':finish.isoformat(),'uiTimeDeltaMs':delta,'displayedWalletUsd':float(amount)})
total=sum((x['usd'] for x in models.values()),Decimal(0));assert total==Decimal('0.353598')
result={'observedAt':'2026-11-01T18:45:36+00:00','method':'One-to-one match of visible wallet rows by model, reported input/output tokens, and finish time within 3 seconds; earliest visible row precedes the earliest matching review by more than a minute. Response IDs did not match the UI request-ID filter.',
 'scope':'Supplemental review and post-hoc rescue only; not solver calls or the entire study. Matching is heuristic, not cryptographic request-ID attribution.',
 'successfulCalls':len(receipts),'matchedCalls':len(receipts),'displayedWalletUsd':float(total),
 'models':{k:{'calls':v['calls'],'displayedWalletUsd':float(v['usd'])} for k,v in models.items()},
 'unmatchedFailedAttempts':failed,'receipts':receipts}
DEST.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('published review-cost evidence',len(receipts),'rows, USD',total)
