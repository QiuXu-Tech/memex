import json,yaml,urllib.request,time,concurrent.futures
from pathlib import Path
key=yaml.safe_load(open(Path.home()/'.dsh/.credentials.yaml'))['refs']['APIMASTER_API_KEY']
d=json.load(open('/tmp/ab-dataset.json')); tr={x['item']:x for x in json.load(open('/tmp/ab-treatments.json'))}
SYSTEM='You are answering a long-horizon project question. Use ONLY the context provided. If the answer is not present, reply exactly UNKNOWN.'
def call(model,context,question):
 body={'model':model,'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':context+'\n\nQuestion: '+question}],'max_tokens':20,'temperature':0}
 req=urllib.request.Request('https://apimaster.ai/v1/chat/completions',data=json.dumps(body).encode(),headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'})
 t=time.perf_counter()
 with urllib.request.urlopen(req,timeout=90) as r: data=json.loads(r.read())
 return data['choices'][0]['message']['content'].strip(), data.get('usage',{}), time.perf_counter()-t
def run(model,probe,condition):
 try:
  if condition=='baseline': ctx=d['tail']
  else: ctx=tr[probe['item']]['treatment']
  ans,usage,lat=call(model,ctx,probe['query'])
  return {'model':model,'condition':condition,'item':probe['item'],'answer':ans,'correct':probe['fact'] in ans,'prompt_tokens':usage.get('prompt_tokens'),'seconds':round(lat,3)}
 except Exception as e:
  return {'model':model,'condition':condition,'item':probe['item'],'answer':'ERR','correct':False,'error':str(e)[:100]}
models=['claude-haiku-4-5','gpt-6-astra']
jobs=[(m,p,c) for m in models for p in d['probes'] for c in ['baseline','memex']]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
 rows=list(ex.map(lambda x:run(*x),jobs))
out=[]
for m in models:
 for c in ['baseline','memex']:
  sub=[r for r in rows if r['model']==m and r['condition']==c]
  out.append({'model':m,'condition':c,'correct':sum(r['correct'] for r in sub),'total':len(sub),'accuracy':round(sum(r['correct'] for r in sub)/len(sub),3),'avg_prompt_tokens':round(sum(r.get('prompt_tokens') or 0 for r in sub)/len(sub),1),'avg_seconds':round(sum(r.get('seconds',0) for r in sub)/len(sub),3)})
json.dump({'summary':out,'rows':rows},open('/tmp/memex-longhorizon-ab.json','w'),indent=2)
print(json.dumps(out,indent=2))
