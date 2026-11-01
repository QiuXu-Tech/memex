#!/usr/bin/env python3
import json
import os
from pathlib import Path
import select
import subprocess
import tempfile
import unittest

SERVER = Path(__file__).with_name('prospective-agent-mcp-v4.mjs')


class BridgeTest(unittest.TestCase):
 def test_stdio_tools_dispatch_limits_and_archive(self):
  with tempfile.TemporaryDirectory() as directory:
   root = Path(directory)
   worker = root / 'worker.py'
   worker.write_text("import json,sys\nfor line in sys.stdin:\n r=json.loads(line)\n print(json.dumps({'ok':True,'result':{'op':r['op'],'status':'failed' if r['op']=='public_test' else 'ok'}}),flush=True)\n")
   archive = root / 'archive.json'
   archive.write_text(json.dumps([{'id':'H1','text':'The prior project decision was to keep the callback.'}]))
   trace = root / 'trace.jsonl'
   p = subprocess.Popen(['node',str(SERVER),'--archive',str(archive),'--trace',str(trace),'--','python3',str(worker)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
   counter = 0
   def rpc(method, params=None):
    nonlocal counter
    counter += 1
    p.stdin.write(json.dumps({'jsonrpc':'2.0','id':counter,'method':method,'params':params or {}})+'\n');p.stdin.flush()
    response = json.loads(p.stdout.readline())
    self.assertEqual(response['id'],counter)
    return response
   def call(name, arguments=None):
    return rpc('tools/call',{'name':name,'arguments':arguments or {}})['result']
   try:
    self.assertEqual(rpc('initialize')['result']['protocolVersion'],'2024-11-05')
    definitions=rpc('tools/list')['result']['tools'];self.assertEqual(len(definitions),6)
    schemas={x['name']:x['inputSchema'] for x in definitions}
    self.assertEqual(schemas['repo_read']['properties']['count']['maximum'],250)
    self.assertEqual(schemas['repo_search']['properties']['limit']['maximum'],30)
    self.assertEqual(json.loads(call('repo_read',{'path':'a.js'})['content'][0]['text'])['op'],'read')
    self.assertTrue(call('repo_edit',{'path':'a.js','old':'a','new':'b','command':'ignored'})['isError'])
    self.assertEqual(json.loads(call('archive_search',{'query':'callback'})['content'][0]['text'])['matches'][0]['id'],'H1')
    self.assertIn('decision',json.loads(call('archive_open',{'id':'H1'})['content'][0]['text'])['text'])
    for _ in range(8):self.assertFalse(call('repo_test')['isError'])
    self.assertEqual(rpc('unsupported')['error']['code'],-32601)
   finally:
    p.stdin.close();p.wait(timeout=10)
    p.stdout.close();p.stderr.close()
   events = [json.loads(line) for line in trace.read_text().splitlines()]
   self.assertEqual(len(events),12)
   self.assertEqual(sum(x['status']=='error' for x in events),1)
   self.assertEqual(os.stat(trace).st_mode & 0o777,0o600)

 def test_repeated_reads_and_searches_are_compact_but_recoverable(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);worker=root/'worker.py';archive=root/'archive.json'
   worker.write_text("import json,sys\nfor line in sys.stdin:\n r=json.loads(line); op=r['op']\n print(json.dumps({'ok':True,'result':{'path':r.get('path'),'start':1,'totalLines':40,'text':'1: original code'} if op=='read' else {'op':op}}),flush=True)\n")
   archive.write_text(json.dumps([{'id':'C1','text':'The alpha callback needs a fix.'}]))
   p=subprocess.Popen(['node',str(SERVER),'--archive',str(archive),'--','python3',str(worker)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
   def call(i,name,args):
    p.stdin.write(json.dumps({'jsonrpc':'2.0','id':i,'method':'tools/call','params':{'name':name,'arguments':args}})+'\n');p.stdin.flush()
    result=json.loads(p.stdout.readline())['result'];self.assertFalse(result['isError']);return json.loads(result['content'][0]['text'])
   try:
    self.assertIn('original code',call(1,'repo_read',{'path':'a.js','start':1,'count':30})['text'])
    self.assertTrue(call(2,'repo_read',{'path':'a.js','start':1,'count':20})['alreadyRead'])
    self.assertIn('original code',call(3,'repo_read',{'path':'a.js','start':1,'count':20,'refresh':True})['text'])
    first=call(4,'archive_search',{'query':'alpha'});self.assertIn('excerpt',first['matches'][0])
    repeat=call(5,'archive_search',{'query':'alpha callback'});self.assertTrue(repeat['matches'][0]['previouslyReturned']);self.assertNotIn('excerpt',repeat['matches'][0])
    self.assertIn('callback',call(6,'archive_open',{'id':'C1'})['text'])
    call(7,'repo_edit',{'path':'a.js','old':'a','new':'b'})
    self.assertIn('original code',call(8,'repo_read',{'path':'a.js','start':1,'count':20})['text'])
   finally:
    p.stdin.close();p.wait(timeout=10);p.stdout.close();p.stderr.close()

 def test_timeout_records_unknown_and_does_not_repeat_edit(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);worker=root/'worker.py';attempts=root/'attempts';trace=root/'trace.jsonl'
   worker.write_text("import json,sys,time\nfrom pathlib import Path\nfor line in sys.stdin:\n r=json.loads(line)\n if r['op']=='edit':\n  with Path(sys.argv[1]).open('a') as f: f.write('edit\\n'); f.flush()\n  time.sleep(10)\n print(json.dumps({'ok':True,'result':{'op':r['op']}}),flush=True)\n")
   p=subprocess.Popen(['node',str(SERVER),'--trace',str(trace),'--worker-timeout-ms','1000','--','python3',str(worker),str(attempts)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
   def call(identifier,name,args):
    p.stdin.write(json.dumps({'jsonrpc':'2.0','id':identifier,'method':'tools/call','params':{'name':name,'arguments':args}})+'\n');p.stdin.flush()
    self.assertTrue(select.select([p.stdout],[],[],5)[0], 'bridge did not reply')
    return json.loads(p.stdout.readline())['result']
   try:
    first=call(1,'repo_read',{'path':'sample.js'});self.assertFalse(first['isError'])
    timed=call(2,'repo_edit',{'path':'sample.js','old':'a','new':'b'});self.assertTrue(timed['isError'])
    self.assertIn('timed out',timed['content'][0]['text'])
    self.assertTrue(call(3,'repo_read',{'path':'sample.js'})['isError'])
   finally:
    p.stdin.close();p.wait(timeout=10);p.stdout.close();p.stderr.close()
   self.assertEqual(attempts.read_text().splitlines(),['edit'])
   rows=[json.loads(line) for line in trace.read_text().splitlines()]
   self.assertEqual([x['status'] for x in rows],['ok','error','error'])


if __name__ == '__main__':unittest.main()
