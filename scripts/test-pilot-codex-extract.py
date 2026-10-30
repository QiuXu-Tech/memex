#!/usr/bin/env python3
"""Time-cutoff regression for the three-session pilot intake."""
import json, pathlib, subprocess, tempfile

with tempfile.TemporaryDirectory() as directory:
 root=pathlib.Path(directory);sessions=[]
 for number in range(2):
  lines=[json.dumps({'type':'user/message' if i%2 else 'assistant/message','seq':i,'time':1000*i,'data':{'content':[{'type':'text','text':f'message {i}'}]}}) for i in range(1,14)]
  raw=root/f'dsh{number}.jsonl';raw.write_text('\n'.join(lines)+'\n');compressed=raw.with_suffix('.zstd')
  with compressed.open('wb') as output:subprocess.run(['zstd','-q','-c',str(raw)],stdout=output,check=True)
  sessions.append(compressed)
 codex=root/'codex.jsonl';events=[{'type':'session_meta','timestamp':'2026-01-01T00:00:00Z'}]
 for i in range(1,15):
  events.append({'type':'response_item','timestamp':f'2026-01-01T00:00:{i:02d}Z','payload':{'type':'message','role':'user' if i%2 else 'assistant','content':[{'type':'input_text','text':f'Codex message {i}'+ ('\u2028separator' if i==3 else '')}]}})
 codex.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in events));plan=root/'plan.json';plan.write_text('[[13],[13]]');frozen=root/'frozen'
 cmd=['python3','scripts/production-pilot-prepare.py','--session',str(sessions[0]),'--session',str(sessions[1]),'--plan',str(plan),'--codex-session',str(codex),'--codex-seqs','14','--repo-commit','test','--out',str(frozen)]
 subprocess.run(cmd,check=True,capture_output=True,text=True)
 data=json.loads((frozen/'episodes.json').read_text());manifest=json.loads((frozen/'preregistered.json').read_text());episode=data['episodes'][-1]
 assert manifest['sessionCount']==3 and manifest['taskCount']==3 and episode['querySeq']==14
 assert episode['summarySeq'] is None and all(p['availableAfter']<14 for p in episode['fullReferencePages']) and all(t['seq']<14 for t in episode['tail'])
 assert any('separator' in p['body'] for p in episode['fullReferencePages'])
 subprocess.run(['python3','scripts/verify-pilot-temporal.py','--session',str(sessions[0]),'--session',str(sessions[1]),'--session',str(codex),'--frozen',str(frozen),'--out',str(root/'temporal.json')],check=True,capture_output=True,text=True)
print('Codex snapshot extraction and temporal cutoff: PASS')
