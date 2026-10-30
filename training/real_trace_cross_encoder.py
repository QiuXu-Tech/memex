import json, random, torch
from transformers import AutoTokenizer, AutoModel
D='/root/real-trace-dataset.json'; M='/root/models/bge-small'
tok=AutoTokenizer.from_pretrained(M); enc=AutoModel.from_pretrained(M, dtype=torch.float32).cuda()
head=torch.nn.Linear(enc.config.hidden_size,1).cuda()
groups=json.load(open(D))['groups']; random.Random(42).shuffle(groups); cut=int(len(groups)*0.75); train,val=groups[:cut],groups[cut:]
def pairs(gs):
 out=[]
 for g in gs:
  for i,p in enumerate(g['pages']): out.append((g['query'],p.get('title','')+'\n'+p.get('body','')[:2500],1.0 if i==g['positive'] else 0.0))
 return out
tr,va=pairs(train),pairs(val)
opt=torch.optim.AdamW(list(enc.parameters())+list(head.parameters()),lr=1e-5)
for ep in range(8):
 enc.train(); head.train(); random.shuffle(tr); total=0
 for s in range(0,len(tr),16):
  b=tr[s:s+16]; x=tok([q for q,_,_ in b],[p for _,p,_ in b],padding=True,truncation=True,max_length=256,return_tensors='pt').to('cuda')
  y=torch.tensor([l for _,_,l in b]).cuda(); opt.zero_grad(); out=enc(**x).last_hidden_state[:,0]; logits=head(out).squeeze(-1); loss=torch.nn.functional.binary_cross_entropy_with_logits(logits,y); loss.backward(); opt.step(); total+=float(loss.detach())*len(b)
 print('epoch',ep+1,'loss',round(total/len(tr),4),flush=True)
enc.eval(); head.eval(); idx=0; ok=0; rank=0
with torch.no_grad():
 for g in val:
  texts=[(g['query'],p.get('title','')+'\n'+p.get('body','')[:2500]) for p in g['pages']]
  x=tok([a for a,_ in texts],[b for _,b in texts],padding=True,truncation=True,max_length=256,return_tensors='pt').to('cuda')
  scores=head(enc(**x).last_hidden_state[:,0]).squeeze(-1).cpu().tolist(); n=len(scores)
  pred=max(range(n),key=lambda i:scores[i]); ok+=int(pred==g['positive']); pos=scores[g['positive']]; rank+=int(all(pos>x for i,x in enumerate(scores) if i!=g['positive']))
print(json.dumps({'val_groups':len(val),'sample_accuracy':round(ok/len(val),4),'pairwise_ranking':round(rank/len(val),4),'base_bge_bi':0.5926}))
open('/root/real-trace-cross.json','w').write(json.dumps({'val_groups':len(val),'sample_accuracy':ok/len(val),'pairwise_ranking':rank/len(val),'base_bge_bi':0.5926},indent=2))
