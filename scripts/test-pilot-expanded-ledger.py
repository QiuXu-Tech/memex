#!/usr/bin/env python3
"""Ledger includes failures and does not invent missing usage or prices."""
import json,pathlib,subprocess,tempfile
with tempfile.TemporaryDirectory() as directory:
 root=pathlib.Path(directory);trials=root/'trials';trials.mkdir();reviews=root/'reviews';reviews.mkdir();audit=root/'audit';audit.mkdir()
 usage={'prompt_tokens':10,'completion_tokens':3,'prompt_tokens_details':{'cached_tokens':4}}
 (trials/'pilot-01.json').write_text(json.dumps({'trace':[{'kind':'model','status':'ok','usage':usage,'requestBytes':15},{'kind':'model','status':'http_error'}]}))
 (reviews/'judgements.jsonl').write_text(json.dumps({'status':'empty_response','usage':usage})+'\n');(audit/'autonomy-judgements.jsonl').write_text(json.dumps({'status':'ok','usage':usage})+'\n')
 for n in ('synthetic','real'):(root/(n+'.jsonl')).write_text(json.dumps({'status':'ok','usage':usage})+'\n')
 out=root/'ledger.json';subprocess.run(['python3','scripts/production-pilot-expanded-ledger.py','--trials',str(trials),'--reviews',str(reviews),'--autonomy',str(audit),'--synthetic-probes',str(root/'synthetic.jsonl'),'--real-probes',str(root/'real.jsonl'),'--out',str(out)],check=True,capture_output=True)
 ledger=json.loads(out.read_text());totals=ledger['totals'];assert totals['calls']==6 and totals['promptTokensReported']==50 and totals['completionTokensReported']==15 and totals['cachedPromptTokensReported']==20
 assert totals['callsMissingPromptTokens']==1 and totals['callsMissingCachedTokens']==1 and ledger['billing']['gatewayInvoice']=='UNKNOWN'
print('Expanded pilot ledger inclusion and missing-usage test passed')
