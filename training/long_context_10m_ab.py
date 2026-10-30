#!/usr/bin/env python3
"""Controlled answer A/B for the 10M-token long-context experiment.

Reads probes emitted by scripts/long-context-10m.mjs, asks two models on
baseline / memex / distractor contexts, and writes aggregate + row results.
No 10M raw history is sent; only the emitted evidence contexts are used.
"""
import argparse, json, time, urllib.request, yaml
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--data',required=True); ap.add_argument('--out',default='long-context-10m-quality.json')
    ap.add_argument('--credentials',default=str(Path.home()/'.dsh/.credentials.yaml'))
    ap.add_argument('--models',default='deepseek-flash,claude-haiku-4-5'); ap.add_argument('--max-tokens',type=int,default=200)
    ap.add_argument('--endpoint',default='https://apimaster.ai/v1/chat/completions')
    a=ap.parse_args()
    key=yaml.safe_load(open(a.credentials))['refs']['APIMASTER_API_KEY']
    data=json.loads(Path(a.data).read_text()); probes=data['probes']
    def one(model, context, question):
        body={'model':model,'messages':[{'role':'system','content':'Answer using only the context. Reply with the FACT id only, or UNKNOWN.'},{'role':'user','content':context+'\n\nQuestion: '+question}],'max_tokens':a.max_tokens,'temperature':0}
        for attempt in range(4):
            try:
                req=urllib.request.Request(a.endpoint,data=json.dumps(body).encode(),headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'})
                t=time.perf_counter()
                with urllib.request.urlopen(req,timeout=120) as r: x=json.loads(r.read())
                txt=x['choices'][0]['message']['content'].strip(); usage=x.get('usage',{})
                if txt: return txt,usage,round(time.perf_counter()-t,3)
            except Exception:
                pass
            time.sleep(2+attempt*2)
        return 'ERR',{},0.0
    def job(args):
        model,p,cond=args
        ctx={'baseline':'Recent conversation tail:\n'+(p['tail'] or ''),'memex':'Retrieved archived evidence:\n'+p['targetBody'],'distractor':'Retrieved archived evidence:\n'+p['distractorBody']}[cond]
        txt,usage,lat=one(model,ctx,p['question'])
        return {'model':model,'probe':p['id'],'condition':cond,'answer':txt,'correct':p['expect'] in txt,'prompt_tokens':usage.get('prompt_tokens'),'completion_tokens':usage.get('completion_tokens'),'latencySeconds':lat}
    jobs=[(m,p,c) for m in a.models.split(',') for p in probes for c in ['baseline','memex','distractor']]
    with ThreadPoolExecutor(max_workers=2) as ex: rows=list(ex.map(job,jobs))
    summary={}
    for m in a.models.split(','):
        for c in ['baseline','memex','distractor']:
            sub=[r for r in rows if r['model']==m and r['condition']==c]
            summary[f'{m}|{c}']={'correct':sum(r['correct'] for r in sub),'total':len(sub),'accuracy':sum(r['correct'] for r in sub)/len(sub),'avgPromptTokens':round(sum((r['prompt_tokens'] or 0) for r in sub)/len(sub),1),'avgSeconds':round(sum(r['latencySeconds'] for r in sub)/len(sub),3)}
    Path(a.out).write_text(json.dumps({'summary':summary,'rows':rows},indent=2))
    print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
