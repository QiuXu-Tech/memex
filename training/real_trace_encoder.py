#!/usr/bin/env python3
"""Train/evaluate the 2-layer context encoder on real memex archive records.

Dataset format: groups of (query, pages, positive index), built from the user's
own archive. The file and weights stay on the training host; only aggregate
metrics are reported.
"""
import json, math, random, sys
from pathlib import Path
import torch
from torch import nn
import torch.nn.functional as F

VOCAB=2048; DIM=128; HEADS=4; MAX_LEN=128; DEVICE='cuda' if torch.cuda.is_available() else 'cpu'
TOKEN_RE=__import__('re').compile(r'[a-z0-9]+')
def tokenize(text): return [((lambda h: (h*16777619)&0xFFFFFFFF)(sum((h*16777619)^ord(c) for c in []) or 2166136261))%(VOCAB) for _ in []] or [((2166136261 ^ b) * 16777619) & 0xFFFFFFFF % VOCAB for b in []]
# Correct FNV-1a
def fnv(text):
    h=2166136261
    for b in text.encode('utf-8'):
        h^=b; h=(h*16777619)&0xFFFFFFFF
    return h
def ids(text): return [fnv(t)%VOCAB for t in TOKEN_RE.findall(text.lower())]
def encode(query,page):
    t=(ids(query)+ids(page.get('title',''))+ids(page.get('body','')))[:MAX_LEN]
    m=[1]*len(t)
    while len(t)<MAX_LEN: t.append(0); m.append(0)
    return t,m
class Layer(nn.Module):
    def __init__(self):
        super().__init__(); self.qkv=nn.Linear(DIM,DIM*3); self.out=nn.Linear(DIM,DIM); self.ff1=nn.Linear(DIM,DIM*4); self.ff2=nn.Linear(DIM*4,DIM); self.ln1=nn.LayerNorm(DIM); self.ln2=nn.LayerNorm(DIM)
    def forward(self,h,mask):
        qkv=self.qkv(h).reshape(h.shape[0],h.shape[1],3,HEADS,DIM//HEADS).permute(2,0,3,1,4); q,k,v=qkv[0],qkv[1],qkv[2]
        scores=(q@k.transpose(-2,-1))/math.sqrt(DIM//HEADS); scores=scores.masked_fill(mask[:,None,None,:]==0,-1e9); attn=torch.softmax(scores,-1)
        ctx=(attn@v).transpose(1,2).reshape(h.shape[0],h.shape[1],DIM); h=self.ln1(h+self.out(ctx)); return self.ln2(h+self.ff2(F.gelu(self.ff1(h))))
class Encoder(nn.Module):
    def __init__(self):
        super().__init__(); self.token_emb=nn.Embedding(VOCAB,DIM); self.pos_emb=nn.Embedding(MAX_LEN,DIM); self.layers=nn.ModuleList([Layer(),Layer()]); self.head=nn.Linear(DIM,1)
    def forward(self,tokens,mask):
        pos=torch.arange(tokens.shape[1],device=tokens.device).unsqueeze(0); h=self.token_emb(tokens)+self.pos_emb(pos)
        for l in self.layers: h=l(h,mask)
        pooled=(h*mask.unsqueeze(-1)).sum(1)/mask.sum(1,keepdim=True).clamp(min=1); return self.head(pooled).squeeze(-1)

data=json.load(open('/root/real-trace-dataset.json'))
groups=data['groups']; random.Random(42).shuffle(groups)
cut=int(len(groups)*0.75); train,val=groups[:cut],groups[cut:]
def samples(gs):
    rows=[]
    for g in gs:
        for i,p in enumerate(g['pages']): rows.append((*encode(g['query'],p),1.0 if i==g['positive'] else 0.0))
    return rows
tr,va=samples(train),samples(val)
print('device',DEVICE,'train',len(tr),'val',len(va),flush=True)
model=Encoder().to(DEVICE); opt=torch.optim.AdamW(model.parameters(),lr=2e-3,weight_decay=.01)
for epoch in range(20):
    model.train(); random.shuffle(tr); total=0
    for start in range(0,len(tr),32):
        b=tr[start:start+32]; t=torch.tensor([r[0] for r in b]).to(DEVICE); m=torch.tensor([r[1] for r in b],dtype=torch.float32).to(DEVICE); y=torch.tensor([r[2] for r in b]).to(DEVICE)
        opt.zero_grad(); loss=F.binary_cross_entropy_with_logits(model(t,m),y); loss.backward(); opt.step(); total+=float(loss.detach())*len(b)
    if (epoch+1)%5==0: print('epoch',epoch+1,'loss',round(total/len(tr),4),flush=True)
model.eval(); correct=0; rank_ok=0; pairs=0
with torch.no_grad():
    for g in val:
        logits=[]
        for p in g['pages']:
            t,m=encode(g['query'],p); logits.append(float(model(torch.tensor([t]).to(DEVICE),torch.tensor([m],dtype=torch.float32).to(DEVICE))[0]))
        pred=max(range(len(logits)),key=lambda i:logits[i]); correct+=int(pred==g['positive'])
        pos=logits[g['positive']]; negs=[x for i,x in enumerate(logits) if i!=g['positive']]; pairs+=1; rank_ok+=int(all(pos>x for x in negs))
print(json.dumps({'train_groups':len(train),'val_groups':len(val),'sample_accuracy':correct/len(val),'pairwise_ranking':rank_ok/max(1,pairs),'val_samples':len(va)}))
open('/root/real-trace-encoder.json','w').write(json.dumps({'train_groups':len(train),'val_groups':len(val),'sample_accuracy':correct/len(val),'pairwise_ranking':rank_ok/max(1,pairs),'val_samples':len(va),'dataset_records':data['records']},indent=2))
