#!/usr/bin/env python3
"""Run a tiny synthetic Claude Code hook smoke in an isolated temporary project."""
import argparse, json, os, pathlib, secrets, shlex, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser()
parser.add_argument('--out', required=True, type=pathlib.Path)
args = parser.parse_args()
out = args.out.resolve()
out.mkdir(mode=0o700, parents=True, exist_ok=False)
project = out / 'project'; project.mkdir(mode=0o700)
mem = out / 'memory'; config_dir = out / 'claude-config'; config_dir.mkdir(mode=0o700)
loader = ROOT / 'test/register.mjs'
env = {k: v for k, v in os.environ.items() if k in ('HOME', 'PATH', 'TMPDIR', 'LANG', 'SHELL', 'ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL')}
env.update(CLAUDE_CONFIG_DIR=str(config_dir), CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',
           DISABLE_AUTOUPDATER='1')
if not env.get('ANTHROPIC_API_KEY') or not env.get('ANTHROPIC_BASE_URL'):
    raise SystemExit('ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL are required in the environment')
init = subprocess.run(['node', '--import', str(loader), str(ROOT/'packages/memex-claude/bin/cli.mjs'),
                       'init', '--project', str(project), '--root', str(mem), '--levels', 'l3', '--model', 'claude-haiku-4-5'],
                      cwd=ROOT, capture_output=True, text=True, timeout=60, env=env)
if init.returncode != 0: raise SystemExit('adapter init failed: ' + init.stderr[:300])
mcp = out/'empty-mcp.json'; mcp.write_text('{"mcpServers":{}}\n')
settings = project/'.claude/settings.json'
generated_settings = json.loads(settings.read_text())
marker = 'Q' + secrets.token_hex(5).upper()
prompts = [f'This synthetic release note says the Quartz release plan identifier is {marker}. Summarize that decision in one complete sentence.',
           'What identifier did the Quartz release plan use? Reply with the identifier and no extra explanation.']
rows = []
for stage, prompt in enumerate(prompts, 1):
    # Capture only the synthetic prompt hook input and keep the test loader
    # confined to hook processes, not the Claude Code client itself.
    stage_settings = json.loads(json.dumps(generated_settings))
    for event, groups in stage_settings['hooks'].items():
        for group in groups:
            for hook in group['hooks']:
                command = 'env NODE_OPTIONS=' + shlex.quote(f'--import={loader}') + ' ' + hook['command']
                if event == 'UserPromptSubmit':
                    command = 'tee ' + shlex.quote(str(out / f'stage-{stage}-prompt-hook.json')) + ' | ' + command
                hook['command'] = command
    settings.write_text(json.dumps(stage_settings, indent=2) + '\n')
    cmd = ['claude', '-p', prompt, '--restricted', '--strict-mcp-config', '--mcp-config', str(mcp),
           '--settings', str(settings), '--tools', '', '--no-session-persistence', '--model', 'claude-haiku-4-5',
           '--max-budget-usd', '0.02', '--output-format', 'stream-json', '--verbose', '--include-hook-events']
    started=time.time()
    try:
        p=subprocess.run(cmd,cwd=project,env=env,stdin=subprocess.DEVNULL,text=True,capture_output=True,timeout=300)
        stdout, stderr, code, timeout = p.stdout, p.stderr, p.returncode, False
    except subprocess.TimeoutExpired as exc:
        stdout=exc.stdout.decode() if isinstance(exc.stdout,bytes) else exc.stdout or ''
        stderr=exc.stderr.decode() if isinstance(exc.stderr,bytes) else exc.stderr or ''
        code,timeout=None,True
    (out/f'stage-{stage}.jsonl').write_text(stdout)
    (out/f'stage-{stage}.stderr').write_text(stderr)
    events=[]
    for line in stdout.splitlines():
        try: events.append(json.loads(line))
        except ValueError: pass
    result=next((e for e in reversed(events) if e.get('type')=='result'),None)
    rows.append({'stage':stage,'exitCode':code,'timeout':timeout,'elapsedSeconds':round(time.time()-started,2),
                 'completed':bool(result and result.get('subtype')=='success' and result.get('result')),
                 'sessionId':(result or {}).get('session_id'),'answer':(result or {}).get('result',''),
                 'usage':(result or {}).get('usage'),'clientListPriceUsd':(result or {}).get('total_cost_usd'),
                 'hookEventTypes':[e.get('subtype') for e in events if e.get('type')=='system' and str(e.get('subtype','')).startswith('hook_')]})
    print(json.dumps({'stage':stage,'completed':rows[-1]['completed'],'timeout':timeout,'elapsedSeconds':rows[-1]['elapsedSeconds']}),flush=True)
    if not rows[-1]['completed']: break
summary={'kind':'synthetic-two-session-claude-hook-smoke','marker':marker,'stages':rows,
         'distinctSessions':len({x['sessionId'] for x in rows if x['sessionId']}),
         'answerMatches':len(rows)==2 and marker in rows[1]['answer'],
         'limitations':['Synthetic mechanism check; not a production task or an A/B effect.',
                        'No ordinary prior handoff is supplied to the second process.']}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({'distinctSessions':summary['distinctSessions'],'answerMatches':summary['answerMatches']}),flush=True)
