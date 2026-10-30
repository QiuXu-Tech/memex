#!/usr/bin/env python3
"""Validate pilot aggregate accounting, missing scores and private-data exclusion."""
import json,pathlib,subprocess,tempfile
with tempfile.TemporaryDirectory(prefix='pilot-aggregate-test-') as d:
 root=pathlib.Path(d);f=root/'frozen';r=root/'trials';j=root/'reviews';f.mkdir();r.mkdir();j.mkdir()
 manifest={'arms':['recent_summary'],'assignments':[{'episode':'e1','order':['recent_summary']}],'repoCommit':'test','sessionCount':1,'taskCount':1,'randomSeed':1,'limits':[]}
 (f/'preregistered.json').write_text(json.dumps(manifest));(f/'preregistered.sha256').write_text('test-hash  preregistered.json\n')
 ep={'id':'e1','question':'PRIVATE_QUESTION','querySeq':5,'summarySeq':1,'tail':[{'seq':2}],'pages':[{'id':'history-1'}],'fullReferencePages':[{'availableAfter':1}]};(f/'episodes.json').write_text(json.dumps({'episodes':[ep]}))
 run={'trial':'pilot-01','episode':'e1','arm':'recent_summary','status':'ok','answer':'PRIVATE_ANSWER','elapsedSeconds':2,'parentCpuSeconds':.1,'childCpuUserSeconds':.2,'childCpuSystemSeconds':.1,'storeBytes':123,'trace':[{'kind':'model','status':'ok','usage':{'prompt_tokens':100,'completion_tokens':25,'prompt_tokens_details':{'cached_tokens':10}},'requestBytes':300,'responseBytes':120}]};(r/'pilot-01.json').write_text(json.dumps(run))
 (j/'private-blind-key.json').write_text(json.dumps({'blind-01':{'trial':'pilot-01','episode':'e1','arm':'recent_summary'}}))
 good={'correctness':2,'coverage':1,'evidence_support':2,'unsupported_claims':0,'relevantSourceIds':['history-1']};rows=[{'blindId':'blind-01','reviewerModel':'gpt-6-astra','status':'ok','raw':json.dumps(good),'usage':{'prompt_tokens':20,'completion_tokens':5}},{'blindId':'blind-01','reviewerModel':'deepseek-flash','status':'ok','raw':'not-json','usage':{'prompt_tokens':30,'completion_tokens':0}}];(j/'judgements.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in rows))
 out=root/'aggregate.json';subprocess.run(['python3','scripts/production-pilot-analyze.py','--frozen',str(f),'--trials',str(r),'--reviews',str(j),'--out',str(out)],check=True,capture_output=True,text=True)
 data=json.loads(out.read_text());arm=data['arms']['recent_summary'];assert arm['gatewayUsage']['promptTokens']==100 and arm['gatewayUsage']['cachedPromptTokens']==10;assert data['reviews']['valid']==1 and arm['bothRegisteredNonNullCorrectness']==0;assert arm['machineCorrectnessScores']['deepseek-flash']['UNKNOWN']==1;assert data['billing']['actualInvoice']=='UNKNOWN';assert 'PRIVATE_' not in out.read_text()
print('pilot aggregate contract passed: usage, missing machine review, privacy and UNKNOWN billing')
