import json, random, torch, time
from transformers import AutoTokenizer, AutoModel
D='/root/real-trace-dataset.json'; M='/root/models/bge-small'; RULE='/root/rule-selection.json'
tok=AutoTokenizer.from_pretrained(M); enc=AutoModel.from_pretrained(M,dtype=torch.float32).cuda(); head=torch.nn.Linear(enc.config.hidden_size,1).cuda()
groups=json.load(open(D))['groups']; rule={x['group']:x for x in json.load(open(RULE))}
idxs=list(range(len(groups))); random.Random(42).shuffle(idxs); cut=int(len(idxs)*0.75); tr_idx,va_idx=idxs[:cut],idxs[cut:]
def pair(g):
 return (g['query'],None)
def text(p): return p.get('title','')+'\n'+p.get('body','')[:2500]
tr=[]
for i in tr_idx:
 g=groups[i]
 for j,p in enumerate(g['pages']): tr.append((g['query'],text(p),1.0 if j==g['positive'] else 0.0))
opt=torch.optim.AdamW(list(enc.parameters())+list(head.parameters()),lr=1e-5)
for ep in range(6):
 enc.train(); head.train(); random.shuffle(tr); total=0
 for s in range(0,len(tr),16):
  b=tr[s:s+16]; x=tok([q for q,_,_ in b],[p for _,p,_ in b],padding=True,truncation=True,max_length=256,return_tensors='pt').to('cuda')
  y=torch.tensor([l for _,_,l in b]).cuda(); opt.zero_grad(); out=head(enc(**x).last_hidden_state[:,0]).squeeze(-1); loss=torch.nn.functional.binary_cross_entropy_with_logits(out,y); loss.backward(); opt.step(); total+=float(loss.detach())*len(b)
 print('epoch',ep+1,'loss',round(total/len(tr),4),flush=True)
enc.eval(); head.eval()
BUDGET=500
learn_ok=0; rule_ok=0; learn_tokens=0; rule_tokens=0; learn_time=0
for gi in va_idx:
 g=groups[gi]; texts=[text(p) for p in g['pages']]
 t0=time.perf_counter()
 with torch.no_grad():
  x=tok([g['query']]*len(texts),texts,padding=True,truncation=True,max_length=256,return_tensors='pt').to('cuda'); scores=head(enc(**x).last_hidden_state[:,0]).squeeze(-1).cpu().tolist()
 learn_time+=time.perf_counter()-t0
 order=sorted(range(len(texts)),key=lambda i:scores[i],reverse=True)
 selected=[]; used=0
 for i in order:
  est=len(texts[i])//4
  if used+est>BUDGET and selected: continue
  selected.append(i); used+=est
  if used>=BUDGET: break
 learn_ok+=int(g['positive'] in selected); learn_tokens+=used
 r=rule.get(gi,{'included':[],'tokens':0}); rule_ok+=int(g['positive'] in r['included']); rule_tokens+=r['tokens']
n=len(va_idx)
print(json.dumps({'val_groups':n,'budget_tokens':BUDGET,'learned_materializer':{'positive_recall':round(learn_ok/n,4),'avg_selected_tokens':round(learn_tokens/n,1),'avg_score_ms':round(learn_time/n*1000,2)},'rule_materializer':{'positive_recall':round(rule_ok/n,4),'avg_selected_tokens':round(rule_tokens/n,1)}}))
open('/root/learned-materializer.json','w').write(json.dumps({'val_groups':n,'budget_tokens':BUDGET,'learned_materializer':{'positive_recall':learn_ok/n,'avg_selected_tokens':learn_tokens/n,'avg_score_ms':learn_time/n*1000},'rule_materializer':{'positive_recall':rule_ok/n,'avg_selected_tokens':rule_tokens/n}},indent=2))
