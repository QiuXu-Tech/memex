#!/usr/bin/env python3
"""Exercise tool boundaries inside the disposable pilot VM."""
import json,os,pathlib,subprocess,sys,tempfile
root=pathlib.Path(tempfile.mkdtemp(prefix='case-',dir='/opt/memex-pilot/workspaces/worker-smoke'));checks=pathlib.Path(tempfile.mkdtemp(prefix='case-',dir='/opt/memex-pilot/checks/worker-smoke'))
root.chmod(0o755);checks.chmod(0o755)
(root/'sample.js').write_text('const VALUE = 1;\n');os.link(root/'sample.js',root/'mirror.js');(root/'package.json').write_text('{"name":"fixture"}\n');(root/'link.js').symlink_to('/etc/passwd');(root/'nested').symlink_to('/etc',target_is_directory=True)
(checks/'verify.js').write_text("const fs=require('node:fs');if(!fs.readFileSync('/work/sample.js','utf8').includes('VALUE = 2'))process.exit(1);console.log('fixture pass');\n")
worker=subprocess.Popen([sys.executable,sys.argv[1],'--workspace',str(root),'--checks',str(checks)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
def rpc(op,**kw):
 worker.stdin.write(json.dumps({'op':op,**kw})+'\n');worker.stdin.flush();return json.loads(worker.stdout.readline())
assert rpc('read',path='sample.js')['ok'];assert rpc('search',query='VALUE')['result']['matches']
for path in ('../sentinel','/etc/passwd','link.js','nested/passwd','node_modules/debug/index.js'):
 assert not rpc('read',path=path)['ok'],path
assert not rpc('edit',path='package.json',old='fixture',new='mutated')['ok']
assert not rpc('edit',path='sample.js',old='missing',new='x')['ok']
assert not rpc('shell',command='id')['ok']
assert rpc('edit',path='sample.js',old='VALUE = 1',new='VALUE = 2')['ok']
assert (root/'mirror.js').read_text()=='const VALUE = 1;\n'
result=rpc('public_test');assert result['ok'] and result['result']['status']=='passed',result
worker.stdin.close();assert worker.wait(timeout=5)==0
print('agent read/search/edit/test boundaries passed')
