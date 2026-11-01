#!/usr/bin/env python3
"""Build a public, redacted projection of the local experiment evidence."""
import json,pathlib,re,sys,urllib.parse
ROOT=pathlib.Path(__file__).resolve().parent.parent
PRIVATE=pathlib.Path('/Users/mk-q/.local/share/memex-forward-20261102')
source=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else PRIVATE/'autonomy-aggregate.json'
target=ROOT/'docs/assets/benchmarks/production-autonomy-20261102/results.json'
data=json.loads(source.read_text())
def scrub(s):
 s=re.sub(r'/Users/mk-q/[^\s\'"\]]+','[local-path]',s)
 s=re.sub(r'\bmem_[a-z0-9]{10}\b','[memory-id]',s,flags=re.I)
 s=re.sub(r'\b(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b','[redacted]',s)
 return s
def clean(x):
 if isinstance(x,str):return scrub(x)
 if isinstance(x,list):return [clean(z) for z in x]
 if isinstance(x,dict):return {k:clean(v) for k,v in x.items() if k not in ('sessionId','successfulWriteIds','automaticCheckpointIds')}
 return x
def source_links(folder,arm,repo,commit):
 found=[];seen=set()
 for f in sorted((folder/'traces').glob(f'{arm}-s*-tools.jsonl')):
  for line in f.read_text().splitlines():
   try:e=json.loads(line)
   except ValueError:continue
   if e.get('status')!='ok':continue
   results=[]
   if e.get('name')=='repo_read':results=[e.get('result') or {}]
   if e.get('name')=='repo_search':results=(e.get('result') or {}).get('matches',[])
   for item in results:
    path=item.get('path');num=item.get('line',item.get('start',1))
    if not isinstance(path,str) or pathlib.PurePosixPath(path).is_absolute() or '..' in pathlib.PurePosixPath(path).parts or not isinstance(num,int):continue
    key=(path,num)
    if key in seen:continue
    seen.add(key);found.append({'path':path,'line':num,'url':f'https://github.com/{repo}/blob/{commit}/{urllib.parse.quote(path)}#L{num}'})
    if len(found)>=20:return found
 return found
for name,foldername in (('original','cohort30-triage'),('supplement','supplement-triage')):
 c=data[name];base=PRIVATE/foldername
 for t in c.get('tasks',[]):
  t['finalAnswers']={}
  t['sourceReferences']={}
  for arm in ('baseline','memex'):
   result=base/t['id']/'results'/f'{arm}-s2.json'
   if result.exists():
    r=json.loads(result.read_text());answer=r.get('final','')
    if answer:t['finalAnswers'][arm]={'text':scrub(answer[:12000]),'truncated':len(answer)>12000}
   t['sourceReferences'][arm]=source_links(base/t['id'],arm,t['repo'],t['sourceCommit'])
  packet=base/'reviews'/t['id']/'packet-registration.json'
  if packet.exists():t['blindPacketSha256']=json.loads(packet.read_text())['packetSha256']
  if t.get('runnerError'):t['runnerError']={'type':t['runnerError'].get('type','UNKNOWN')}
  if t.get('memoryChain'):
   t['memoryChain']['successfulWriteCount']=len(t['memoryChain']['successfulWriteIds'])
   t['memoryChain']['automaticCheckpointCount']=len(t['memoryChain']['automaticCheckpointIds'])
cleaned=clean(data)
text=json.dumps(cleaned,ensure_ascii=False,indent=2)+'\n'
if re.search(r'\b(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b',text):raise SystemExit('credential-like text in public output')
target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text)
print(f'published projection {target} ({len(text)} chars)')
