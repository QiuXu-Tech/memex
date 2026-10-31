#!/usr/bin/env python3
"""Bounded repository worker for a single disposable Linux VM workspace.

The model supplies data only; there is no arbitrary shell, network or path tool.
A trusted dispatcher starts the worker with a preassigned workspace and check set.
"""
import argparse,json,os,pathlib,stat,subprocess,sys,tempfile,time

ROOT=pathlib.Path('/opt/memex-pilot')
SOURCE_EXT={'.js','.mjs','.cjs','.ts','.mts','.cts','.json'}
EDIT_EXT=SOURCE_EXT-{'.json'}
SKIP={'.git','node_modules','.cache','coverage','dist','build','test','tests','__tests__','__snapshots__'}
p=argparse.ArgumentParser();p.add_argument('--workspace',required=True);p.add_argument('--checks',required=True);p.add_argument('--sandbox',default='/opt/memex-pilot/prospective-vm-sandbox.sh');p.add_argument('--self-test-mode',action='store_true');args=p.parse_args()
root=pathlib.Path(args.workspace).resolve(strict=True);checks=pathlib.Path(args.checks).resolve(strict=True)
if not root.is_relative_to(ROOT/'workspaces') or not checks.is_relative_to(ROOT/'checks') or root == ROOT/'workspaces' or checks == ROOT/'checks':raise SystemExit('invalid assigned root')
if not args.self_test_mode and pathlib.Path(args.sandbox).resolve()!=ROOT/'prospective-vm-sandbox.sh':raise SystemExit('untrusted sandbox path')
changes=0

def safe_path(name,edit=False):
 if not isinstance(name,str) or len(name)>500 or not name or '\x00' in name:raise ValueError('invalid path')
 p=pathlib.PurePosixPath(name)
 if p.is_absolute() or any(part in ('.','..') for part in p.parts) or any(part in SKIP for part in p.parts):raise ValueError('path denied')
 candidate=root.joinpath(*p.parts)
 if any(pathlib.Path(*candidate.parts[:i]).is_symlink() for i in range(len(root.parts)+1,len(candidate.parts)+1)):raise ValueError('symlink denied')
 resolved=candidate.resolve(strict=True)
 if not resolved.is_relative_to(root) or not resolved.is_file():raise ValueError('not an allowed file')
 if edit and resolved.suffix not in EDIT_EXT:raise ValueError('file type denied')
 if resolved.stat().st_size>1500000:raise ValueError('file too large')
 return resolved

def text_file(p):
 fd=os.open(p,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
 with os.fdopen(fd,'r',encoding='utf8') as f:return f.read()

def action(req):
 global changes
 op=req.get('op')
 if op=='read':
  path=safe_path(req.get('path'));lines=text_file(path).splitlines();start=req.get('start',1);count=req.get('count',100)
  if not isinstance(start,int) or not isinstance(count,int) or start<1 or count<1 or count>150:raise ValueError('invalid line window')
  return {'path':str(path.relative_to(root)),'start':start,'totalLines':len(lines),'text':'\n'.join(f'{i+1}: {line[:500]}' for i,line in enumerate(lines[start-1:start-1+count],start-1))[:18000]}
 if op=='search':
  query=req.get('query');limit=req.get('limit',20)
  if not isinstance(query,str) or not 2<=len(query)<=100 or '\n' in query or not isinstance(limit,int) or not 1<=limit<=30:raise ValueError('invalid query')
  result=[];visited=0
  for dirname,dirs,files in os.walk(root,followlinks=False):
   dirs[:]=sorted(d for d in dirs if d not in SKIP and not (pathlib.Path(dirname)/d).is_symlink())
   for name in sorted(files):
    path=pathlib.Path(dirname)/name
    if path.suffix not in SOURCE_EXT or path.is_symlink():continue
    visited+=1
    if visited>15000:break
    try:
     if path.stat().st_size>300000:continue
     for i,line in enumerate(text_file(path).splitlines(),1):
      if query.lower() in line.lower():
       result.append({'path':str(path.relative_to(root)),'line':i,'text':line[:350]})
       if len(result)>=limit:return {'matches':result,'truncated':True}
    except (OSError,UnicodeError):continue
   if visited>15000:break
  return {'matches':result,'truncated':visited>15000}
 if op=='edit':
  if changes>=12:raise ValueError('edit limit reached')
  path=safe_path(req.get('path'),True);old=req.get('old');new=req.get('new')
  if not isinstance(old,str) or not isinstance(new,str) or not 1<=len(old)<=12000 or len(new)>16000 or '\x00' in new:raise ValueError('invalid edit')
  before=text_file(path)
  if before.count(old)!=1:raise ValueError('old text must occur exactly once')
  after=before.replace(old,new,1)
  if len(after)>1500000:raise ValueError('result too large')
  mode=stat.S_IMODE(path.stat().st_mode)
  fd,tmp=tempfile.mkstemp(prefix='.agent-edit-',dir=path.parent)
  try:
   with os.fdopen(fd,'w',encoding='utf8') as f:f.write(after);f.flush();os.fsync(f.fileno())
   os.chmod(tmp,mode);os.replace(tmp,path)
  except Exception:
   try:os.unlink(tmp)
   except FileNotFoundError:pass
   raise
  changes+=1;return {'path':str(path.relative_to(root)),'editCount':changes}
 if op=='public_test':
  if args.self_test_mode:raise ValueError('tests disabled in self-test mode')
  start=time.monotonic();result=subprocess.run(['sudo','-n',args.sandbox,str(root),str(checks),'30'],capture_output=True,text=True,timeout=36,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'});return {'status':'passed' if result.returncode==0 else 'failed','exitCode':result.returncode,'output':(result.stdout+result.stderr)[:5000],'elapsedSeconds':round(time.monotonic()-start,3)}
 if op=='status':return {'editCount':changes}
 raise ValueError('unsupported operation')

for line in sys.stdin:
 try:
  req=json.loads(line);result=action(req);print(json.dumps({'ok':True,'result':result},ensure_ascii=False),flush=True)
 except Exception as e:print(json.dumps({'ok':False,'errorType':type(e).__name__,'error':str(e)[:300]}),flush=True)
