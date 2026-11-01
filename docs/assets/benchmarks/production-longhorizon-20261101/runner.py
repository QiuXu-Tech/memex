"""Three-session randomized Codex replay of registered public issues."""
import concurrent.futures, datetime, difflib, hashlib, json, os, pathlib, select, signal, subprocess, sys, time

os.umask(0o077)
BASE = pathlib.Path(__file__).resolve().parent
ROOT = pathlib.Path('/tmp/memex-pilot-publication-20261031')
VM = 'memex-prospective-pilot-20261031'
VMBASE = '/opt/memex-pilot'
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p): return json.loads(p.read_text())
def save(p, x):
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f: json.dump(x, f, ensure_ascii=False, indent=2); f.write('\n')
reg = load(BASE / 'registration.json')
allocation = load(BASE / 'allocation-private.json')
assert sha(BASE / 'allocation-private.json') == reg['allocationCommitmentSha256']
assert sha(pathlib.Path(__file__)) == reg['runnerSha256']
assert sha(ROOT / 'scripts/prospective-agent-mcp.mjs') == reg['bridgeSha256']
assert subprocess.run(['git','-C',str(ROOT),'diff','--quiet',reg['memexCommit'],'--',
                       'packages/memex-core','packages/memex-mcp','packages/memex-codex']).returncode == 0
for task in reg['tasks']:
    assert sha(BASE / ('issue-' + task['id'] + '.json')) == task['issueSnapshotSha256']
    assert sha(BASE / (task['id'] + '-source.tar.gz')) == task['sourceArchiveSha256']
    assert sha(BASE / 'checks' / task['id'] / 'verify.js') == task['verifierSha256']

def session(task, arm, stage, prompt):
    name = task['id']; prefix = f'{name}-{arm}-s{stage}'
    host = BASE / 'host' / name / arm
    archive = BASE / 'archives' / f'{name}-{arm}.json'
    trace = BASE / 'traces' / (prefix + '-pilot.jsonl')
    worker = ['--archive',str(archive),'--trace',str(trace),'--','/opt/homebrew/bin/limactl','shell',VM,'--',
              'python3',VMBASE + '/prospective-agent-worker-v4.py',
              '--workspace',VMBASE + f'/workspaces/longpilot-20261101/{name}/{arm}',
              '--checks',VMBASE + f'/checks/longpilot-20261101/{name}']
    pilot_tools = ['repo_read','repo_search','archive_search','archive_open']
    if stage > 1: pilot_tools += ['repo_edit','repo_test']
    args = ['codex','exec','--ignore-user-config','--strict-config','--disable','shell_tool',
            '--disable','unified_exec','--disable','apps','--disable','plugins','--disable','remote_plugin',
            '--disable','tool_suggest','--ephemeral','--skip-git-repo-check','--sandbox','workspace-write',
            '--model','gpt-6.1-sol','--json','--cd',str(host),'-c','approval_policy="never"',
            '-c','model_reasoning_effort="low"','-c','web_search="disabled"',
            '-c','mcp_servers.pilot.command="/opt/homebrew/bin/node"',
            '-c','mcp_servers.pilot.args='+json.dumps([str(ROOT/'scripts/prospective-agent-mcp.mjs')]+worker),
            '-c','mcp_servers.pilot.required=true','-c','mcp_servers.pilot.default_tools_approval_mode="approve"',
            '-c','mcp_servers.pilot.enabled_tools='+json.dumps(pilot_tools)]
    if arm == 'memex':
        argv = ['--import',str(ROOT/'test/register.mjs'),str(ROOT/'packages/memex-mcp/bin/server.mjs'),
                '--root',str(BASE/'memory'/name),'--cwd',str(host),'--agent','codex','--model','gpt-6.1-sol','--levels','l3']
        args += ['-c','mcp_servers.memex.command="/opt/homebrew/bin/node"',
                 '-c','mcp_servers.memex.args='+json.dumps(argv),'-c','mcp_servers.memex.required=true',
                 '-c','mcp_servers.memex.default_tools_approval_mode="approve"',
                 '-c','mcp_servers.memex.enabled_tools='+json.dumps(['memory_write','memory_search','memory_open','memory_grep','memory_index','memory_list','memory_set_status','memory_forget'])]
    args.append(prompt)
    outpath = BASE/'traces'/(prefix+'-events.jsonl'); errpath = BASE/'traces'/(prefix+'-stderr.txt')
    started, tick, timedout, violation, buf = now(), time.monotonic(), False, None, b''
    with outpath.open('xb') as output, errpath.open('xb') as errors:
        proc = subprocess.Popen(args,stdout=subprocess.PIPE,stderr=errors,start_new_session=True)
        fd = proc.stdout.fileno(); os.set_blocking(fd,False)
        while True:
            if time.monotonic()-tick >= reg['sessionTimeoutSeconds']: timedout=True; break
            ready,_,_=select.select([fd],[],[],1)
            if not ready: continue
            chunk=os.read(fd,65536)
            if not chunk: break
            output.write(chunk); output.flush(); buf += chunk
            while b'\n' in buf:
                line,buf=buf.split(b'\n',1)
                try: event=json.loads(line)
                except ValueError: continue
                item=event.get('item') or {}
                allowed={'pilot','memex'} if arm=='memex' else {'pilot'}
                if event.get('type')=='item.started' and ((item.get('type')=='mcp_tool_call' and item.get('server') not in allowed)
                       or item.get('type') in ('command_execution','web_search')):
                    violation={'type':item.get('type'),'server':item.get('server'),'tool':item.get('tool')}; break
            if violation: break
        if timedout or violation:
            try: os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: os.killpg(proc.pid,signal.SIGKILL); proc.wait()
            while select.select([fd],[],[],0)[0]:
                chunk=os.read(fd,65536)
                if not chunk: break
                output.write(chunk)
        else: proc.wait(timeout=10)
    events=[]
    for line in outpath.read_text(errors='replace').splitlines():
        try: events.append(json.loads(line))
        except ValueError: pass
    messages=[e['item'].get('text','') for e in events if e.get('type')=='item.completed' and (e.get('item') or {}).get('type')=='agent_message']
    calls=[e['item'] for e in events if e.get('type')=='item.completed' and (e.get('item') or {}).get('type')=='mcp_tool_call']
    result={'task':name,'arm':arm,'stage':stage,'exitCode':proc.returncode,'timeout':timedout,
            'unexpectedTool':violation,'startedAt':started,'finishedAt':now(),'elapsedSeconds':round(time.monotonic()-tick,2),
            'archiveSha256':sha(archive),'threadIds':[e.get('thread_id') for e in events if e.get('type')=='thread.started'],
            'usage':[e.get('usage') for e in events if e.get('type')=='turn.completed'],
            'final':messages[-1] if messages else '',
            'calls':[{'server':c.get('server'),'tool':c.get('tool'),'status':c.get('status'),'error':c.get('error')} for c in calls],
            'failures':[e.get('type') for e in events if e.get('type') in ('turn.failed','error')]}
    save(BASE/'results'/(prefix+'.json'),result)
    print(json.dumps({'task':name,'arm':arm,'stage':stage,'exit':proc.returncode,'timeout':timedout,
                      'final':bool(result['final']),'calls':len(calls),'usage':result['usage']}),flush=True)
    return result

def check_and_patch(task,arm):
    name=task['id']; work=VMBASE+f'/workspaces/longpilot-20261101/{name}/{arm}'
    check=VMBASE+f'/checks/longpilot-20261101/{name}'
    p=subprocess.run(['limactl','shell',VM,'--','sudo','-n',VMBASE+'/prospective-vm-sandbox.sh',work,check,'30'],
                     capture_output=True,text=True,timeout=45)
    paths=task['sourcePaths']; patches=[]
    target=BASE/'patched'/name/arm; target.mkdir(parents=True,exist_ok=True)
    for path in paths:
        dest=target/path; dest.parent.mkdir(parents=True,exist_ok=True)
        subprocess.run(['limactl','copy',f'{VM}:{work}/{path}',str(dest)],check=True,timeout=60,capture_output=True)
        before=(BASE/name/path).read_text(); after=dest.read_text()
        patches.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+path,tofile='b/'+path))
    patch=BASE/'patches'/f'{name}-{arm}.diff'; patch.parent.mkdir(exist_ok=True); patch.write_text(''.join(patches))
    return {'testExitCode':p.returncode,'testOutput':(p.stdout+p.stderr)[:3000],
            'patchSha256':sha(patch),'patchBytes':patch.stat().st_size}

def run_pair(task):
    name=task['id']; data=load(BASE/('issue-'+name+'.json')); comments=data['comments']
    comments=[{'id':'C'+str(i+1),'text':c['createdAt']+' '+((c.get('author') or {}).get('login') or 'unknown')+': '+c['body'],'url':c['url']} for i,c in enumerate(comments)]
    split=task['commentSplit']; summary={}
    subject=f"{task['repo']} issue #{task['issueNumber']}: {data['title']}\nIssue: {data['url']}\nPinned source files: {', '.join(task['sourcePaths'])}\n\n"
    for arm in allocation['tasks'][name]['armOrder']:
        host=BASE/'host'/name/arm; host.mkdir(parents=True,exist_ok=False)
        if arm=='memex':
            subprocess.run(['/opt/homebrew/bin/node','--import',str(ROOT/'test/register.mjs'),
              str(ROOT/'packages/memex-codex/bin/cli.mjs'),'init','--project',str(host),'--root',str(BASE/'memory'/name),
              '--model','gpt-6.1-sol','--levels','l3'],capture_output=True,text=True,check=True)
        archive=BASE/'archives'/f'{name}-{arm}.json'
        records=[{'id':'ISSUE','text':data['title']+'\n\n'+data['body'],'url':data['url']}]+comments[:split[0]]
        archive.write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
        stages=[]
        for n in (1,2,3):
            if n>1:
                records += comments[split[n-2]:split[n-1]]
                records.append({'id':f'HANDOFF{n-1}','text':f'Earlier session {n-1} handoff: '+stages[-1]['final']})
                archive.write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
            result=session(task,arm,n,subject+reg['prompts'][str(n)])
            stages.append(result)
            if result['exitCode']!=0 or result['timeout'] or result['unexpectedTool'] or not result['final']: break
        outcome={'sessionsCompleted':sum(x['exitCode']==0 and not x['timeout'] and bool(x['final']) for x in stages),
                 'threadIds':[x['threadIds'][0] for x in stages if len(x['threadIds'])==1],
                 'final':stages[-1]['final'] if stages else '',**check_and_patch(task,arm)}
        save(BASE/'results'/f'{name}-{arm}-outcome.json',outcome)
        summary[arm]={k:v for k,v in outcome.items() if k!='final'}
        if any(x['unexpectedTool'] for x in stages): break
    save(BASE/'results'/f'{name}-summary.json',{'task':name,'arms':summary,'completedAt':now()})
    return {'task':name,'arms':{a:{'sessions':v['sessionsCompleted'],'testExitCode':v['testExitCode']} for a,v in summary.items()}}

if __name__=='__main__':
    (BASE/'traces').mkdir(exist_ok=True);(BASE/'archives').mkdir(exist_ok=True);(BASE/'results').mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(run_pair,t):t['id'] for t in reg['tasks']}
        for future in concurrent.futures.as_completed(futures):
            try: print(json.dumps(future.result()),flush=True)
            except Exception as e:
                task=futures[future];save(BASE/'results'/f'{task}-runner-error.json',{'task':task,'errorType':type(e).__name__,'error':str(e),'at':now()})
                print(json.dumps({'task':task,'runnerError':type(e).__name__,'error':str(e)}),flush=True)
