#!/usr/bin/env python3
"""Extract local replay episodes from a DSH session + memex records.

No network calls. Outputs JSON + human-review markdown. Labels are provisional.
"""
import json,re,subprocess,pathlib,datetime,sys

SESSION_ROOT=pathlib.Path.home()/'.dsh/sessions'
MEM=pathlib.Path.home()/'.dsh/memories'
OUT=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else pathlib.Path.home()/'.dsh'/'memories'/'replay-eval')
OUT.mkdir(parents=True,exist_ok=True)

def parse_record(f):
 t=f.read_text(); end=t.find('\n---',4); fm=t[3:end] if t.startswith('---') else ''; body=t[end+4:].strip() if end>0 else t
 d={}
 for line in fm.splitlines():
  m=re.match(r'^([A-Za-z_]+):\s*(.*)$',line.strip())
  if m: d[m.group(1)]=m.group(2).strip().strip('"')
 return {'id':f.stem,'title':d.get('title',''),'useWhen':d.get('use_when',''),'summary':d.get('summary',''),'body':body,'sessionId':d.get('session_id'),'createdAt':int(d.get('created_at','0') or 0),'kind':d.get('kind','artifact')}

records=[parse_record(f) for f in list(MEM.glob('records/*/*.md'))+list(MEM.glob('cold/*/*.md'))]
by_id={r['id']:r for r in records}
# find the most recent session in the workspace
files=sorted(SESSION_ROOT.glob('--Users-mk-q-Documents-deepseek-harness-default-workspace--/*/session.v4.jsonl.zstd'),key=lambda p:p.stat().st_mtime,reverse=True)
if not files: sys.exit('no session file')
session_file=files[0]
raw=subprocess.run(['zstd','-dc',str(session_file)],capture_output=True,text=True).stdout
events=[]
for line in raw.splitlines():
 try: o=json.loads(line)
 except: continue
 if o.get('type')=='user/message':
  d=o.get('data',{}); c=d.get('content')
  if isinstance(c,list):
   text=' '.join(b.get('text','') for b in c if isinstance(b,dict) and b.get('type')=='text'); text=' '.join(text.split())
   if text: events.append({'kind':'user','time':o.get('time',0),'seq':o.get('seq'),'text':text})
 elif o.get('type')=='assistant/message':
  d=o.get('data',{}); c=d.get('content')
  if isinstance(c,list):
   text=' '.join(b.get('text','') for b in c if isinstance(b,dict) and b.get('type')=='text'); text=' '.join(text.split())
   if text: events.append({'kind':'assistant','time':o.get('time',0),'seq':o.get('seq'),'text':text})
skip=('[MEMORY','Current runtime','Time sampled','## Memory','Extra-context','[测试]','Background subagent','Agent ','<l1-eviction>','<model changed','background job','Reply with exactly','You are running a controlled','Your parent agent id','You are repeating','This is an automatically','The available skill catalog','[visual:')
trivial={'重启完成','重启好了','测试一下','你去更新吧','继续','继续推进','好','好的','OK','ok','去做','可以'}
def real_user(e):
 t=e.get('text',''); low=t.strip().lower()
 if e['kind']!='user': return False
 if any(t.startswith(s) for s in skip): return False
 if len(t)<8 or len(t)>500: return False
 if low in trivial: return False
 if re.match(r'^(ssh|cd|ls|curl|git|npm|python|kill|ps|tail|cat|grep|sed|find|scp|head|wc)\b',t): return False
 return True
users=[e for e in events if real_user(e)]
l1=[e for e in events if e['kind']=='user' and '<l1-eviction>' in e['text']]
writes=[]
for line in raw.splitlines():
 try: o=json.loads(line)
 except: continue
 if o.get('type')!='tool/call': continue
 d=o.get('data',{})
 if d.get('name')!='memory_write': continue
 try: args=json.loads(d.get('arguments','{}'))
 except: args={}
 title=args.get('title','')
 if title: writes.append({'time':o.get('time',0),'seq':o.get('seq'),'title':title})
print('memory_write tool calls',len(writes))
def prev_user(t,min_time=0):
 cand=[u for u in users if u['time']<t and u['time']>=min_time]
 return cand[-1] if cand else None
def next_user(t):
 cand=[u for u in users if u['time']>t]
 return cand[0] if cand else None
def next_assistant(t):
 cand=[e for e in events if e['kind']=='assistant' and e['time']>t]
 return cand[0] if cand else None
def epoch(ms): return datetime.datetime.fromtimestamp(ms/1000,datetime.timezone.utc).isoformat()

episodes=[]
used_queries=set()
# 1) L1 eviction episodes
for e in l1:
 m=re.search(r'记录 id 为 (l1_[0-9a-f]+)',e['text']); rid=m.group(1) if m else None
 rec=by_id.get(rid)
 q=prev_user(e['time'])
 if not q or not rec: continue
 key=('l1',q['text'],rid)
 if key in used_queries or q['text'] in {x['query'] for x in episodes}: continue
 used_queries.add(key)
 later=next_user(e['time']); ans=next_assistant(e['time'])
 episodes.append({'id':f'ep-l1-{len(episodes)+1:02d}','source':'l1-eviction','seq':e.get('seq'),'time':epoch(e['time']),'query':q['text'],'querySeq':q.get('seq'),'recordIds':[rid] if rid else [],'recordTitles':[rec['title']] if rec else [],'referenceFacts':(rec['title']+'\n'+rec['summary']+'\n'+rec['body'][:600]) if rec else '','availableBefore':[r['id'] for r in records if r['createdAt']<=e['time']][:80],'laterUser':later['text'][:300] if later else None,'laterAssistant':ans['text'][:500] if ans else None,'verified':False})
# 2) memory_write episodes (exact title -> record, nearest user query)
for w in sorted(writes,key=lambda x:x['time']):
 if len(episodes)>=30: break
 rec=next((r for r in records if r['title']==w['title']),None)
 if rec is None: continue
 q=prev_user(w['time'],min_time=w['time']-24*3600*1000)
 if not q: continue
 if q['text'] in {x['query'] for x in episodes}: continue
 if q['text'] in {x['query'] for x in episodes}: continue
 episodes.append({'id':f'ep-mem-{len(episodes)+1:02d}','source':'memory-write','seq':w['seq'],'time':epoch(w['time']),'query':q['text'],'querySeq':q.get('seq'),'recordIds':[rec['id']],'recordTitles':[rec['title']],'referenceFacts':rec['title']+'\n'+rec['summary']+'\n'+rec['body'][:800],'availableBefore':[r['id'] for r in records if r['createdAt']<=w['time']][:80],'laterUser':None,'laterAssistant':None,'verified':False})

episodes=episodes[:30]
# write
(OUT/'replay-episodes.json').write_text(json.dumps({'format':1,'sourceSession':str(session_file),'labels':'provisional; human review required','episodes':episodes},ensure_ascii=False,indent=2))
lines=['# Replay episode review','','Labels are provisional. Confirm relevant records/facts before using for scoring.','']
for ep in episodes:
 lines += [f"## {ep['id']} · {ep['source']} · {ep['time']}",'',f"**Query:** {ep['query']}",'',f"**Relevant records:** "+', '.join(f"{t} ({i})" for t,i in zip(ep['recordTitles'],ep['recordIds'])),'',f"**Reference facts:**",'```',ep['referenceFacts'][:800],'```','',f"**Human label:** [ ] relevant  [ ] partially  [ ] not relevant  **Notes:** ",'']
(OUT/'replay-review.md').write_text('\n'.join(lines))
import csv
with (OUT/'replay-labels.csv').open('w',newline='',encoding='utf-8') as fh:
 w=csv.writer(fh); w.writerow(['episode','source','time','query','record_ids','record_titles','label','notes'])
 for ep in episodes: w.writerow([ep['id'],ep['source'],ep['time'],ep['query'],';'.join(ep['recordIds']),';'.join(ep['recordTitles']),'',''])
print('session',session_file)
print('records',len(records),'l1 events',len(l1),'episodes',len(episodes))
print('out',OUT)
print('sources', {s:sum(1 for e in episodes if e['source']==s) for s in ['l1-eviction','memory-write']})
