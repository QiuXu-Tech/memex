#!/usr/bin/env python3
"""Run isolated task shards in preregistered order, with no automatic retries."""
import argparse,concurrent.futures,json,os,pathlib,shutil,subprocess
p=argparse.ArgumentParser();p.add_argument('--frozen',required=True);p.add_argument('--out',required=True);a=p.parse_args();f=pathlib.Path(a.frozen).resolve();out=pathlib.Path(a.out).resolve()
if out.exists():raise SystemExit('refusing to overwrite prior execution')
out.mkdir(parents=True,mode=0o700);shards=out/'shards';shards.mkdir(mode=0o700);manifest=json.loads((f/'preregistered.json').read_text());tasks=manifest['taskExecutionOrder'];assert set(tasks)=={x['episode'] for x in manifest['assignments']} and manifest['maxConcurrentTasks']==2

def run(task):
 root=shards/task;log=out/(task+'.log')
 with log.open('x') as h:
  os.chmod(log,0o600);proc=subprocess.run(['python3','scripts/production-pilot-run.py','--frozen',str(f),'--out',str(root),'--task-id',task],stdout=h,stderr=subprocess.STDOUT)
 return {'task':task,'exitCode':proc.returncode}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 results=[]
 for result in pool.map(run,tasks):
  results.append(result);print(json.dumps({'completedTasks':len(results),'totalTasks':len(tasks),'task':result['task'],'exitCode':result['exitCode']}),flush=True)
(out/'batch-status.json').write_text(json.dumps(results,indent=2)+'\n');(out/'batch-status.json').chmod(0o600)
if any(x['exitCode'] for x in results):raise SystemExit('one or more shards failed; evidence preserved, no retries')
combined=out/'combined';combined.mkdir(mode=0o700);trials=[]
for task in tasks:
 for path in sorted((shards/task).glob('pilot-*.json')):
  dest=combined/path.name
  if dest.exists():raise SystemExit('duplicate trial ID; refusing merge')
  shutil.copyfile(path,dest);dest.chmod(0o600);trials.append(json.loads(dest.read_text()))
expected=[(x['episode'],arm) for x in manifest['assignments'] for arm in x['order']];trials.sort(key=lambda x:x['trial'])
if [(r['episode'],r['arm']) for r in trials]!=expected:raise SystemExit('missing or unexpected trial; refusing aggregate')
with (combined/'execution.jsonl').open('x') as h:
 os.chmod(combined/'execution.jsonl',0o600)
 for r in trials:h.write(json.dumps({k:r.get(k) for k in ('trial','episode','arm','status','writeCount','elapsedSeconds')})+'\n')
print(json.dumps({'trials':len(trials),'taskShards':len(tasks),'allAssignmentsPresent':True}),flush=True)
