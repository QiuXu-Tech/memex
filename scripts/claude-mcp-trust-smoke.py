#!/usr/bin/env python3
"""Synthetic real-client smoke for MCP-written unverified memories and recall."""
import argparse,json,os,pathlib,re,secrets,shlex,subprocess,time
ROOT=pathlib.Path(__file__).resolve().parent.parent
p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=pathlib.Path);a=p.parse_args()
out=a.out.resolve();out.mkdir(parents=True,mode=0o700,exist_ok=False);project=out/'project';project.mkdir(mode=0o700)
mem=out/'memory';config=out/'claude-config';config.mkdir(mode=0o700);loader=ROOT/'test/register.mjs'
env={k:v for k,v in os.environ.items() if k in ('HOME','PATH','TMPDIR','LANG','SHELL','ANTHROPIC_API_KEY','ANTHROPIC_BASE_URL')}
env.update(CLAUDE_CONFIG_DIR=str(config),CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',DISABLE_AUTOUPDATER='1')
if not env.get('ANTHROPIC_API_KEY') or not env.get('ANTHROPIC_BASE_URL'):raise SystemExit('configured gateway required')
r=subprocess.run(['node','--import',str(loader),str(ROOT/'packages/memex-claude/bin/cli.mjs'),'init','--project',str(project),'--root',str(mem),'--levels','l3','--model','claude-haiku-4-5'],capture_output=True,text=True,timeout=60,env=env,stdin=subprocess.DEVNULL)
if r.returncode:raise SystemExit('adapter init failed: '+r.stderr[:300])
settings=project/'.claude/settings.json';obj=json.loads(settings.read_text())
for groups in obj['hooks'].values():
 for group in groups:
  for hook in group['hooks']:hook['command']='env NODE_OPTIONS='+shlex.quote(f'--import={loader}')+' '+hook['command']
settings.write_text(json.dumps(obj,indent=2)+'\n')
mcp=out/'mcp.json';mcp.write_text(json.dumps({'mcpServers':{'memex':{'command':'/opt/homebrew/bin/node','args':['--import',str(loader),str(ROOT/'packages/memex-mcp/bin/server.mjs'),'--root',str(mem),'--cwd',str(project),'--agent','claude-code','--model','claude-haiku-4-5','--levels','l3']}}})+'\n')
marker='Q'+secrets.token_hex(5).upper()
prompts=[f'The Quartz release plan identifier is {marker}. Use memory_write to save this synthetic decision for the next session, then repeat the identifier in one complete sentence.',
         'Search your memory for the Quartz release plan identifier and reply with the identifier.']
allowed='mcp__memex__memory_write,mcp__memex__memory_search,mcp__memex__memory_open'
rows=[]
for stage,prompt in enumerate(prompts,1):
 cmd=['claude','-p',prompt,'--restricted','--effort','low','--strict-mcp-config','--mcp-config',str(mcp),'--settings',str(settings),'--tools','','--allowedTools',allowed,'--no-session-persistence','--model','claude-haiku-4-5','--max-budget-usd','0.05','--output-format','stream-json','--verbose','--include-hook-events']
 start=time.monotonic()
 try:
  r=subprocess.run(cmd,cwd=project,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=240);stdout,stderr,code,timed=r.stdout,r.stderr,r.returncode,False
 except subprocess.TimeoutExpired as e:
  stdout=e.stdout.decode(errors='replace') if isinstance(e.stdout,bytes) else e.stdout or ''
  stderr=e.stderr.decode(errors='replace') if isinstance(e.stderr,bytes) else e.stderr or '';code,timed=None,True
 (out/f'stage-{stage}.jsonl').write_text(stdout);(out/f'stage-{stage}.stderr').write_text(stderr)
 events=[]
 for line in stdout.splitlines():
  try:events.append(json.loads(line))
  except ValueError:pass
 result=next((e for e in reversed(events) if e.get('type')=='result'),None) or {}
 calls=[x for e in events if e.get('type')=='assistant' for x in (e.get('message')or{}).get('content',[]) if x.get('type')=='tool_use']
 results=[x for e in events if e.get('type')=='user' for x in (e.get('message')or{}).get('content',[]) if x.get('type')=='tool_result']
 hooks=[e.get('stdout','') for e in events if e.get('subtype')=='hook_response' and e.get('hook_name')=='UserPromptSubmit']
 rows.append({'stage':stage,'completed':result.get('subtype')=='success' and bool(result.get('result')) and not timed,'exitCode':code,'timeout':timed,
  'elapsedSeconds':round(time.monotonic()-start,2),'sessionId':result.get('session_id'),'answer':result.get('result',''),
  'usage':result.get('usage'),'clientListPriceUsd':result.get('total_cost_usd'),'tools':[x.get('name') for x in calls],
  'mcpResultHasUnverified':'[unverified]' in json.dumps(results,ensure_ascii=False),'hookHasUnverified':'[unverified]' in ''.join(hooks),
  'writtenIds':re.findall(r'Stored (mem_[0-9a-f]{10})',json.dumps(results))})
 print(json.dumps({k:rows[-1][k] for k in ('stage','completed','timeout','clientListPriceUsd','tools','mcpResultHasUnverified','hookHasUnverified')}),flush=True)
 if not rows[-1]['completed']:break
summary={'kind':'synthetic-explicit-mcp-write-and-cross-session-recall','marker':marker,'stages':rows,
 'distinctSessions':len({r['sessionId'] for r in rows if r.get('sessionId')}),
 'answerMatches':len(rows)==2 and marker in rows[1]['answer'],
 'limits':['Synthetic prompted write and read, not autonomous behavior or a production A/B effect.','Client list budget is not a gateway invoice.']}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({'distinctSessions':summary['distinctSessions'],'answerMatches':summary['answerMatches']}),flush=True)
