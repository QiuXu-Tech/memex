#!/usr/bin/env python3
"""Exercise the pilot worker's real scoped Memex tools and independent baseline."""
import json,pathlib,subprocess,tempfile

def session(root,records,seed_to_store):
 p=subprocess.Popen(['node','--import','./test/register.mjs','scripts/production-pilot-store.mjs'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 def rpc(body):
  p.stdin.write(json.dumps(body)+'\n');p.stdin.flush();r=json.loads(p.stdout.readline());assert r['ok'],r;return r['result']
 info=rpc({'op':'init','root':str(root),'cwd':'/isolated-pilot/contract','sessionId':'s','records':records,'seedToStore':seed_to_store})
 return p,rpc,info
records=[{'id':'history-1','kind':'fact','title':'solar telescope','summary':'mirror focal length','useWhen':'','body':'The focal length is seven metres.'}]
with tempfile.TemporaryDirectory(prefix='memex-pilot-contract-') as d:
 p,rpc,info=session(pathlib.Path(d)/'memex',records,True);assert info['seededInStore']==1
 result=rpc({'op':'tool','name':'memory_search','args':{'query':'solar telescope'}});assert 'history-1' in result['text']
 opened=rpc({'op':'tool','name':'memory_open','args':{'id':'history-1'}});assert 'seven metres' in opened['text'] and 'file:' not in opened['text']
 written=rpc({'op':'tool','name':'memory_write','args':{'kind':'fact','title':'synthetic radio','body':'SYNTHETIC_RADIO_FACT'}});assert 'Saved mem_' in written['text']
 materialized=rpc({'op':'pager','query':'solar telescope'});assert 'history-1' in materialized['ids'] and materialized['tokens']<=1800
 rpc({'op':'close'});p.stdin.close();assert p.wait(timeout=10)==0
 p,rpc,info=session(pathlib.Path(d)/'keyword',records,False);assert info['archiveRecords']==1 and info['seededInStore']==0
 result=rpc({'op':'tool','name':'archive_search','args':{'query':'solar telescope'}});assert 'history-1' in result['text'];assert 'seven metres' in rpc({'op':'tool','name':'archive_open','args':{'id':'history-1'}})['text'];assert rpc({'op':'stats'})['records']==0
 rpc({'op':'close'});p.stdin.close();assert p.wait(timeout=10)==0
print('pilot worker contract passed: real scoped tools, independent keyword path, budget, write and path privacy')
