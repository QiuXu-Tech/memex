#!/usr/bin/env python3
"""An answer-stage write is still a write for the unblinded audit schema."""
import json,pathlib,subprocess,tempfile
with tempfile.TemporaryDirectory() as d:
 root=pathlib.Path(d);f=root/'f';t=root/'t';r=root/'r';a=root/'a'
 for p in (f,t,r,a):p.mkdir()
 manifest={'arms':['pager_tools_write'],'assignments':[{'episode':'e','order':['pager_tools_write']}],'repoCommit':'test','sessionCount':1,'taskCount':1,'randomSeed':1,'limits':[],'autonomyAudit':'planned','autonomyCitationSchema':'separate-history-and-memory'}
 (f/'preregistered.json').write_text(json.dumps(manifest));(f/'preregistered.sha256').write_text('hash  preregistered.json\n')
 episode={'id':'e','querySeq':5,'summarySeq':None,'tail':[{'seq':4}],'pages':[{'id':'history-1','body':'example'}],'fullReferencePages':[{'availableAfter':1}]}
 (f/'episodes.json').write_text(json.dumps({'episodes':[episode]}))
 run={'trial':'pilot-01','episode':'e','arm':'pager_tools_write','status':'ok','answer':'example','elapsedSeconds':1,'parentCpuSeconds':0,'childCpuUserSeconds':0,'childCpuSystemSeconds':0,'storeBytes':1,'trace':[{'kind':'tool','stage':'answer','name':'memory_write','status':'ok','arguments':{'body':'example'},'result':'Saved mem_abc'}]}
 (t/'pilot-01.json').write_text(json.dumps(run));(r/'private-blind-key.json').write_text('{}');(r/'judgements.jsonl').write_text('')
 grade={'memory_needed':'unknown','writes_faithful':'yes','answer_used_prior_write':'no','supportingSourceIds':['history-1'],'supportingMemoryIds':['mem_abc'],'reason':'example'}
 bad={**grade,'supportingMemoryIds':['mem_fake']};(a/'autonomy-judgements.jsonl').write_text(json.dumps({'trial':'pilot-01','reviewerModel':'deepseek-flash','status':'ok','raw':json.dumps(grade)})+'\n'+json.dumps({'trial':'pilot-01','reviewerModel':'gpt-6-astra','status':'ok','raw':json.dumps(bad)})+'\n')
 out=root/'out.json';subprocess.run(['python3','scripts/production-pilot-analyze.py','--frozen',str(f),'--trials',str(t),'--reviews',str(r),'--autonomy-reviews',str(a),'--out',str(out)],check=True,capture_output=True)
 data=json.loads(out.read_text());assert data['autonomyObserved'][0]['preQuestionWrites']==0 and data['autonomyObserved'][0]['answerWrites']==1 and data['autonomyMachineAudit']['valid']==1 and data['autonomyMachineAudit']['problems']=={'memory_ids':1}
print('Answer-stage write is counted in autonomy audit validation')
