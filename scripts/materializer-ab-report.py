#!/usr/bin/env python3
import json, pathlib, statistics, sys
p=pathlib.Path.home()/'.dsh/memories/materializer-trace.jsonl'
rows=[]
for line in p.read_text().splitlines():
 try: o=json.loads(line)
 except: continue
 if o.get('form')=='materializer-ab': rows.append(o)
print('materializer-ab entries:',len(rows))
if not rows: sys.exit(0)
for key in ['ruleTokens','hybridTokens','addedIds','removedIds']:
 vals=[len(r.get(key,[])) if isinstance(r.get(key),list) else r.get(key,0) for r in rows]
 print(key,'mean',round(sum(vals)/len(vals),2),'min',min(vals),'max',max(vals))
print('\nlast 5:')
for r in rows[-5:]:
 print(r.get('at'), 'q=',str(r.get('query'))[:60], 'rule',len(r.get('ruleIds',[])), 'hybrid',len(r.get('hybridIds',[])), 'added',r.get('addedIds',[])[:3], 'removed',r.get('removedIds',[])[:3])
