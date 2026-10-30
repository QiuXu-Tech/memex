#!/usr/bin/env python3
"""Record/session-isolated quality A/B protocol.

Input JSON schema (required unless --exploratory):
{
  "dataset": "name", "realMemory": false,
  "splitKey": "sessionId", "trainKeys": [...], "testKeys": [...],
  "costModel": {"answerInputPer1k":0.0,"answerOutputPer1k":0.0,"judgeInputPer1k":0.0,"judgeOutputPer1k":0.0},
  "queries": [{
    "id":"q1","sessionId":"s1","recordIds":["..."], "humanRelevance":{"mem_x":1},
    "verified":true,"question":"...","referenceFacts":"...",
    "ruleContext":"...","hybridContext":"...",
    "ruleIds":["..."],"hybridIds":["..."]
  }]
}
Checks: verified labels, disjoint train/test keys, authorization for real memory,
cost model present. Saves both answer orders, mapping, raw answers, judge
rationale, recall, timings, tokens and separate answer/judge cost.
"""
import argparse,json,random,re,sys,time,urllib.request
from pathlib import Path

def call(url,key,model,messages,max_tokens=700):
    body={'model':model,'messages':messages,'max_tokens':max_tokens,'temperature':0}
    req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'})
    start=time.perf_counter()
    with urllib.request.urlopen(req,timeout=120) as r: data=json.loads(r.read())
    return data, time.perf_counter()-start

def cost(usage, i, o):
    usage=usage or {}; return round((usage.get('prompt_tokens',0)*i + usage.get('completion_tokens',0)*o)/1000,6)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('dataset'); ap.add_argument('--out',default='quality-ab-protocol.json')
    ap.add_argument('--config',default=str(Path.home()/'.config/apimaster.json'))
    ap.add_argument('--answer-models',default='deepseek-flash,claude-haiku-4-5')
    ap.add_argument('--judge',default='gpt-6-astra')
    ap.add_argument('--endpoint',default='https://apimaster.ai/v1/chat/completions')
    ap.add_argument('--authorize-real-memory',action='store_true')
    ap.add_argument('--exploratory',action='store_true')
    a=ap.parse_args(); data=json.loads(Path(a.dataset).read_text())
    if data.get('realMemory') and not a.authorize_real_memory:
        sys.exit('realMemory dataset requires --authorize-real-memory')
    cm=data.get('costModel') or {}
    if not a.exploratory:
        if not cm.get('answer') or not cm.get('judge'):
            sys.exit('costModel.answer (per model) and costModel.judge are required unless --exploratory')
        for model in a.answer_models.split(','):
            model=model.strip()
            if not cm['answer'].get(model):
                sys.exit(f'costModel.answer missing {model}')
        if not cm['judge'].get(a.judge):
            sys.exit(f'costModel.judge missing {a.judge}')
    train=set(data.get('trainKeys',[])); test=set(data.get('testKeys',[]))
    splitKey=data.get('splitKey','sessionId')
    if train and test and train & test:
        sys.exit('trainKeys and testKeys must be disjoint')
    for q in data['queries']:
        if not a.exploratory and not q.get('verified'):
            sys.exit(f"query {q.get('id')} is not human-verified")
        if train and test and q.get(splitKey) not in test:
            sys.exit(f"query {q.get('id')} is not in testKeys")
    cfg=json.loads(Path(a.config).read_text()); key=cfg.get('apiKey') or cfg.get('key')
    if not key: sys.exit('config must contain apiKey')
    def rate(model, table):
        row=(table or {}).get(model)
        return (row['inputPer1M'],row['outputPer1M']) if row else None
    system='Answer using ONLY the provided context. Cite record ids for major claims. If absent, say "not in context". Be concise.'
    out={'dataset':data.get('dataset'),'judge':a.judge,'exploratory':a.exploratory,'queries':[],'totals':{}}
    total_answer_cost=0.0; total_judge_cost=0.0
    for q in data['queries']:
        item={'id':q.get('id'),'question':q.get('question'),'sessionId':q.get(splitKey),'recordIds':q.get('recordIds'),'verified':q.get('verified',False),'conditions':{}}
        contexts={'rule':q['ruleContext'],'hybrid':q['hybridContext']}
        ids={'rule':q.get('ruleIds',[]),'hybrid':q.get('hybridIds',[])}
        rel={k for k,v in (q.get('humanRelevance') or {}).items() if v}
        item['selectionRecall']={c:{'selected':len(ids[c]),'relevantSelected':len(rel & set(ids[c])),'relevantTotal':len(rel),'recall': (len(rel & set(ids[c]))/len(rel)) if rel else None} for c in ids}
        for model in a.answer_models.split(','):
            model=model.strip(); answers={}
            for cond,ctx in contexts.items():
                resp,lat=call(a.endpoint,key,model,[{'role':'system','content':system},{'role':'user','content':ctx+'\n\nQuestion: '+q['question']}],max_tokens=700)
                answer_rate=rate(model,cm.get('answer'))
                answer_cost=None if answer_rate is None else cost(resp.get('usage'),*answer_rate)
                answers[cond]={'text':resp['choices'][0]['message']['content'],'usage':resp.get('usage',{}),'latencySeconds':round(lat,3),'cost':answer_cost}
                if answer_cost is not None: total_answer_cost += answer_cost
            judged={}
            for order in [('rule','hybrid'),('hybrid','rule')]:
                mapping={'A':order[0],'B':order[1]}
                prompt=f'''Question:\n{q['question']}\n\nReference facts:\n{q.get('referenceFacts','')}\n\nAnswer A:\n{answers[mapping['A']]['text']}\n\nAnswer B:\n{answers[mapping['B']]['text']}\n\nReturn ONLY JSON {{"A":{{"coverage":0-10,"correctness":0-10,"focus":0-10}},"B":{{...}},"winner":"A|B|tie","reason":"<=120 chars"}}. Judge only against reference facts; penalize missing key facts and unsupported claims.'''
                resp,lat=call(a.endpoint,key,a.judge,[{'role':'user','content':prompt}],max_tokens=400)
                text=resp['choices'][0]['message']['content']; m=re.search(r'\{.*\}',text,re.S)
                judge_rate=rate(a.judge,cm.get('judge'))
                judge_cost=None if judge_rate is None else cost(resp.get('usage'),*judge_rate)
                judged[f"{order[0]}-first"]={'mapping':mapping,'latencySeconds':round(lat,3),'usage':resp.get('usage',{}),'cost':judge_cost,'result':json.loads(m.group(0)) if m else {'raw':text}}
                if judge_cost is not None: total_judge_cost += judge_cost
            item['conditions'][model]={'answers':answers,'judgeOrders':judged}
        out['queries'].append(item)
    out['totals']={'answerCost':round(total_answer_cost,6) if not a.exploratory else None,'judgeCost':round(total_judge_cost,6) if not a.exploratory else None,'totalCost':round(total_answer_cost+total_judge_cost,6) if not a.exploratory else None,'currency':cm.get('currency')}
    Path(a.out).write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print('wrote',a.out,'queries',len(out['queries']),'totalCost',out['totals']['totalCost'])

if __name__=='__main__': main()
