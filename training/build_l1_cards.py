#!/usr/bin/env python3
"""Build compact, source-marked cards for L1 archive records (local only)."""
import json,re,pathlib,sys
MEM=pathlib.Path.home()/'.dsh/memories'
OUT=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else pathlib.Path.home()/'.dsh'/'memories'/'replay-eval')
HEADINGS=['Primary Request and Intent','Key Technical Concepts','Files and Code','Errors and fixes','Problem Solving','All user messages','Pending Tasks','Current Work','Optional Next Step']
def parse(f):
 t=f.read_text(); end=t.find('\n---',4); fm=t[3:end]; body=t[end+4:].strip(); d={}
 for line in fm.splitlines():
  m=re.match(r'^([A-Za-z_]+):\s*(.*)$',line.strip())
  if m: d[m.group(1)]=m.group(2).strip().strip('"')
 return d,body
def card_for(f):
 d,body=parse(f)
 sections={}
 for i,h in enumerate(HEADINGS):
  start=body.find('## '+h)
  if start<0: continue
  end=len(body)
  for nh in HEADINGS:
   j=body.find('## '+nh,start+3)
   if j>=0: end=min(end,j)
  sections[h]=body[start:end].strip()
 # If no compacted summary, fall back to first lines.
 if not sections:
  sections['Excerpt']=body[:1200]
 parts=[f'> [L1 archive card; source: {f.stem}; original archive remains intact]',f'# {d.get("title","L1 archive card")}']
 for h in ['Primary Request and Intent','Key Technical Concepts','Files and Code','Errors and fixes','Excerpt','Pending Tasks','Current Work','Optional Next Step']:
  if h in sections:
   text=sections[h]
   # cap each section
   parts.append(text[:1800].rstrip())
 return {'id':f.stem,'title':f'[card] {d.get("title","L1 archive")}','useWhen':d.get('use_when',''),'body':'\n\n'.join(parts),'sourceId':f.stem,'originalTokens':d.get('tokens'),'truncated':True}
cards=[]
for f in sorted(MEM.glob('records/*/l1_*.md'))+sorted(MEM.glob('cold/*/l1_*.md')):
 if f.exists(): cards.append(card_for(f))
# dedupe by id
by={c['id']:c for c in cards}
cards=list(by.values())
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'l1-cards.json').write_text(json.dumps({'format':1,'cards':cards},ensure_ascii=False,indent=2))
print('cards',len(cards),'out',OUT/'l1-cards.json')
for c in cards[:3]: print(c['id'],c['title'],len(c['body']))
