#!/usr/bin/env python3
"""Freeze a small, private, multi-session time-cutoff replay before any trial."""
import argparse,hashlib,json,pathlib,random,re,subprocess
p=argparse.ArgumentParser();p.add_argument('--session',action='append',required=True);p.add_argument('--out',required=True);p.add_argument('--repo-commit',required=True);p.add_argument('--plan');p.add_argument('--codex-session',action='append');p.add_argument('--codex-seqs',nargs='+',type=int);p.add_argument('--codex-plan');a=p.parse_args();out=pathlib.Path(a.out)
if out.exists():raise SystemExit('refusing to overwrite frozen pilot')
if len(a.session)!=2:raise SystemExit('two DSH sessions required')
if a.codex_seqs and a.codex_plan:raise SystemExit('choose Codex sequences or plan')
codex_plan=json.loads(pathlib.Path(a.codex_plan).read_text()) if a.codex_plan else ([a.codex_seqs] if a.codex_seqs else [])
if len(a.codex_session or [])!=len(codex_plan) or any(not isinstance(group,list) or not group or any(type(seq) is not int for seq in group) or group!=sorted(set(group)) for group in codex_plan):raise SystemExit('invalid Codex session selection plan')
out.mkdir(mode=0o700,parents=True);sha=lambda b:hashlib.sha256(b).hexdigest()
skip=('[MEMORY','Current runtime','Time sampled','## Memory','Extra-context','[测试]','Background subagent','Agent ','<l1-eviction>','background job','Reply with exactly','You are running','Your parent agent','This is an automatically','The available skill catalog','[visual:')
secret=re.compile(r'(?i)(sk-(?:proj-)?[a-z0-9_-]{16,}|bearer\s+[a-z0-9._-]{16,}|(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*["\']?[a-z0-9._-]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)')
redactions=0
def clean(value):
 global redactions
 text=str(value or '');text,n=secret.subn('[REDACTED_CREDENTIAL]',text);redactions+=n;return text
selected=json.loads(pathlib.Path(a.plan).read_text()) if a.plan else [[12728,19372,20693],[4355]]
if not isinstance(selected,list) or len(selected)!=len(a.session) or any(not isinstance(group,list) or any(type(seq) is not int for seq in group) or group!=sorted(set(group)) for group in selected):raise SystemExit('invalid selection plan')
episodes=[];sources=[]
for project,(path,seqs) in enumerate(zip(a.session,selected),1):
 path=pathlib.Path(path);source_hash=sha(path.read_bytes());proc=subprocess.Popen(['zstd','-dc',str(path)],stdout=subprocess.PIPE,text=True);chat=[];summaries=[];found=[];malformed=0
 for line in proc.stdout:
  try:e=json.loads(line)
  except json.JSONDecodeError:malformed+=1;continue
  typ=e.get('type');d=e.get('data',{});seq=e.get('seq',0)
  if typ=='compaction/summary':
   blocks=d.get('summary',[]);text='\n'.join(x.get('text','') for x in blocks if isinstance(x,dict) and x.get('type')=='text');summaries.append((seq,text))
  if typ not in ('user/message','assistant/message'):continue
  blocks=d.get('content');text=' '.join(x.get('text','') for x in blocks if isinstance(x,dict) and x.get('type')=='text') if isinstance(blocks,list) else '';text=' '.join(text.split())
  if not text or text.startswith(skip):continue
  if seq in seqs:
   if typ!='user/message' or len(chat)<12:raise SystemExit('invalid selected question')
   eligible=[(s,t) for s,t in summaries if s<seq and t];last=eligible[-1] if eligible else (None,'');earlier=chat[-44:-4];tail=chat[-4:]
   if not earlier:raise SystemExit('insufficient prior archive')
   pages=[];full=[]
   for turn in earlier:
    if turn['seq']>=seq:raise SystemExit('future data in archive')
    content=clean(turn['text']);id=f"history-{turn['seq']}";title=f"Historical {turn['role']} message {turn['seq']}";summary=content[:120]
    pages.append({'id':id,'kind':'episode','title':title,'summary':summary,'useWhen':'','body':content[:1800]});full.append({'id':id,'title':title,'summary':summary,'body':content,'availableAfter':turn['seq']})
   episode={'id':f'project-{project}-task-{len(found)+1}','project':f'project-{project}','querySeq':seq,'question':clean(text),'tail':[{'seq':t['seq'],'role':t['role'],'text':clean(t['text'])[:1200]} for t in tail],'summary':clean(last[1])[:6000],'summarySeq':last[0],'pages':pages,'fullReferencePages':full}
   episodes.append(episode);found.append(seq)
  if len(text)<=12000:chat.append({'role':'user' if typ=='user/message' else 'assistant','seq':seq,'text':text})
 if proc.wait()!=0 or sha(path.read_bytes())!=source_hash:raise SystemExit('source changed or decompression failed')
 if found!=seqs:raise SystemExit('selected questions not found')
 sources.append({'project':f'project-{project}','sha256':source_hash,'malformedLinesSkipped':malformed,'selectedSeqs':found})
for codex_path,codex_seqs in zip(a.codex_session or [],codex_plan):
 path=pathlib.Path(codex_path);source_hash=sha(path.read_bytes());project=len(sources)+1;chat=[];found=[];malformed=0
 with path.open() as stream:
  for seq,line in enumerate(stream,1):
   try:e=json.loads(line)
   except json.JSONDecodeError:malformed+=1;continue
   d=e.get('payload',{});role=d.get('role');blocks=d.get('content')
   if e.get('type')!='response_item' or d.get('type')!='message' or role not in ('user','assistant') or not isinstance(blocks,list):continue
   text=' '.join(' '.join(x.get('text','') for x in blocks if isinstance(x,dict) and x.get('type') in ('input_text','output_text')).split())
   if not text or text.startswith(skip) or (role=='user' and text.startswith(('<','[','You are','The user','AGENTS.md','# AGENTS'))):continue
   if seq in codex_seqs:
    if role!='user' or len(chat)<12:raise SystemExit('invalid selected Codex question')
    earlier=chat[-44:-4];tail=chat[-4:];pages=[];full=[]
    if not earlier:raise SystemExit('insufficient prior Codex archive')
    for turn in earlier:
     if turn['seq']>=seq:raise SystemExit('future data in archive')
     content=clean(turn['text']);id=f"history-{turn['seq']}";title=f"Historical {turn['role']} message {turn['seq']}";summary=content[:120]
     pages.append({'id':id,'kind':'episode','title':title,'summary':summary,'useWhen':'','body':content[:1800]});full.append({'id':id,'title':title,'summary':summary,'body':content,'availableAfter':turn['seq']})
    episodes.append({'id':f'project-{project}-task-{len(found)+1}','project':f'project-{project}','querySeq':seq,'question':clean(text),'tail':[{'seq':t['seq'],'role':t['role'],'text':clean(t['text'])[:1200]} for t in tail],'summary':'','summarySeq':None,'pages':pages,'fullReferencePages':full});found.append(seq)
   if len(text)<=12000:chat.append({'role':role,'seq':seq,'text':text})
 if sha(path.read_bytes())!=source_hash:raise SystemExit('Codex snapshot changed')
 if found!=codex_seqs:raise SystemExit('selected Codex questions not found')
 sources.append({'project':f'project-{project}','sha256':source_hash,'malformedLinesSkipped':malformed,'selectedSeqs':found,'format':'codex-jsonl-snapshot'})
private={'sources':sources,'episodes':episodes,'redactionCount':redactions};(out/'episodes.json').write_text(json.dumps(private,ensure_ascii=False,indent=2));(out/'episodes.json').chmod(0o600)
rng=random.Random(20261031);arms=['recent_summary','keyword_archive','pager_only','pager_tools_readonly','pager_tools_write'];assignments=[]
for e in episodes:
 order=arms.copy();rng.shuffle(order);assignments.append({'episode':e['id'],'order':order})
task_order=[e['id'] for e in episodes];random.Random(20261032).shuffle(task_order)
manifest={'kind':'exploratory-multi-session-tool-replay-preregistration','repoCommit':a.repo_commit,'sources':sources,'selectedIds':[e['id'] for e in episodes],'sessionCount':len(sources),'taskCount':len(episodes),'randomSeed':20261031,'assignments':assignments,'taskExecutionOrder':task_order,'maxConcurrentTasks':2,'failurePolicy':'stop failing shard on a model or runner failure; stop scheduling new shards after any shard fails; do not retry', 'arms':arms,'toolLimitFallback':'denied tools receive explicit not-executed result; one tool-free model response; repeated exact searches reused; identical writes never automatically retried within a phase','reviewerThinking':'DeepSeek thinking disabled, explicit JSON and anchored rubric','autonomyAudit':'separate planned unblinded AI review of each write-enabled run; not human review','model':'claude-haiku-4-5 via APIMaster','temperature':0,'answerMaxTokens':2500,'answerMaxContinuations':2,'autonomyCitationSchema':'separate-history-and-memory','intakeMaxTokens':1000,'maxAnswerToolRounds':5,'maxIntakeToolRoundsPerBatch':3,'maxWritesPerTrial':12,'archive':'up to 40 previous actual user/assistant messages; body clipped at 1800 characters per message; identical archive source per arm','summary':'latest historical compaction summary if available plus four preceding chat messages, fixed across arms','summaryChars':6000,'pagerBudgetEstimate':1800,'pageTokenCap':400,'machineReview':'two blind machine judges, GPT-6 Astra and DeepSeek Flash; no human labels','rubric':'correctness, coverage and evidence support with explicit 0/1/2 anchors or UNKNOWN against time-prior evidence; separate model calls; abstention when evidence insufficient','cost':'capture all gateway usage including cached tokens and local compute/storage/network measures; actual invoice and upstream historical ingestion UNKNOWN','autonomy':'write-capable arm sees only time-prior conversation messages in chronological batches, without the future question, then chooses memory tools; an isolated replay, not a live production lifecycle','limits':['prior sessions and previously examined questions are not held-out or representative','history truncated; actual task execution and future actions are not reproduced','machine-written memory begins empty; readonly arms index the same historical chat','human labels and actual invoices unavailable','no claims about significance, production improvement, or cost savings'],'credentialRedactions':redactions}
raw=json.dumps(manifest,ensure_ascii=False,indent=2)+'\n';(out/'preregistered.json').write_text(raw);(out/'preregistered.sha256').write_text(sha(raw.encode())+'  preregistered.json\n');print(json.dumps({'sessions':len(sources),'tasks':len(episodes),'arms':len(arms),'runs':len(episodes)*len(arms),'hasHistoricalSummary':sum(bool(e['summary']) for e in episodes),'archiveMessages':sum(len(e['pages']) for e in episodes),'credentialRedactions':redactions,'manifestSha256':sha(raw.encode())}))
