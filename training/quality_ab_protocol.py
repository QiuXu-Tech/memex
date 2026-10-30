#!/usr/bin/env python3
"""Record/session-isolated quality A/B protocol.

Input JSON:
{
  "dataset": "record-session-disjoint-v1",
  "queries": [
    {"id":"q1","recordIds":[...],"sessionId":"...","question":"...","humanRelevance":{"pageId":0|1},"verified":true,
     "ruleContext":"...","hybridContext":"...","referenceFacts":"..."}
  ]
}
It saves, per question: condition order, raw answers, judge scores/rationale,
usage tokens and a caller-supplied cost model. It does not ship real memory
content to third parties unless the caller supplies contexts explicitly.
"""
import argparse,json,random,re,sys,yaml,urllib.request
from pathlib import Path

def api(url,key,model,messages,max_tokens=700):
    body={'model':model,'messages':messages,'max_tokens':max_tokens,'temperature':0}
    req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=120) as r: return json.loads(r.read())

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('dataset'); ap.add_argument('--out',default='quality-ab-protocol.json'); ap.add_argument('--config',default=str(Path.home()/'.config/apimaster.json')); ap.add_argument('--answer-models',default='deepseek-flash,claude-haiku-4-5'); ap.add_argument('--judge',default='gpt-6-astra'); ap.add_argument('--endpoint',default='https://apimaster.ai/v1/chat/completions'); ap.add_argument('--cost-per-1k-input',type=float,default=0); ap.add_argument('--cost-per-1k-output',type=float,default=0)
    a=ap.parse_args(); data=json.loads(Path(a.dataset).read_text())
    cfg=json.loads(Path(a.config).read_text()); key=cfg.get('apiKey') or cfg.get('key')
    if not key: sys.exit('config must contain apiKey')
    out={'dataset':data.get('dataset'),'judge':a.judge,'queries':[]}
    system='Answer using ONLY the provided context. Cite record ids for major claims. If absent, say "not in context". Be concise.'
    for q in data['queries']:
        item={'id':q.get('id'),'question':q.get('question'),'recordIds':q.get('recordIds'),'sessionId':q.get('sessionId'),'verified':q.get('verified',False),'conditions':{}}
        contexts={'rule':q['ruleContext'],'hybrid':q['hybridContext']}
        for model in a.answer_models.split(','):
            model=model.strip(); answers={}
            for cond,ctx in contexts.items():
                r=api(a.endpoint,key,model,[{'role':'system','content':system},{'role':'user','content':ctx+'\n\nQuestion: '+q['question']}],max_tokens=700)
                answers[cond]={'text':r['choices'][0]['message']['content'],'usage':r.get('usage',{})}
            order=['rule','hybrid']; random.shuffle(order)
            mapping={'A':order[0],'B':order[1]}
            prompt=f'''Question:\n{q['question']}\n\nReference facts:\n{q.get('referenceFacts','')}\n\nAnswer A:\n{answers[mapping['A']]['text']}\n\nAnswer B:\n{answers[mapping['B']]['text']}\n\nReturn ONLY JSON {{"A":{{"coverage":0-10,"correctness":0-10,"focus":0-10}},"B":{{...}},"winner":"A|B|tie","reason":"<=120 chars"}}. Judge only against reference facts; penalize missing key facts and unsupported claims.'''
            j=api(a.endpoint,key,a.judge,[{'role':'user','content':prompt}],max_tokens=400)
            text=j['choices'][0]['message']['content']; m=re.search(r'\{.*\}',text,re.S)
            item['conditions'][model]={'mapping':mapping,'answers':answers,'judge':json.loads(m.group(0)) if m else {'raw':text},'usage':j.get('usage',{})}
        for model,row in item['conditions'].items():
            for cond,ans in row['answers'].items():
                u=ans.get('usage',{})
                ans['cost']=round((u.get('prompt_tokens',0)*a.cost_per_1k_input + u.get('completion_tokens',0)*a.cost_per_1k_output)/1000,6)
        out['queries'].append(item)
    Path(a.out).write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print('wrote',a.out,'queries',len(out['queries']))

if __name__=='__main__': main()
