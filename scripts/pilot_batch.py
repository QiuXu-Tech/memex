"""Bounded shard scheduling that stops starting new work after failure."""
import concurrent.futures

def run_bounded(tasks,workers,runner,on_result):
 remaining=iter(tasks);rows=[];failed=False
 with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
  pending={}
  for _ in range(workers):
   task=next(remaining,None)
   if task is not None:pending[pool.submit(runner,task)]=task
  while pending:
   done,_=concurrent.futures.wait(pending,return_when=concurrent.futures.FIRST_COMPLETED)
   for future in done:
    task=pending.pop(future)
    try:row=future.result()
    except Exception as e:row={'task':task,'exitCode':-1,'errorType':type(e).__name__}
    rows.append(row);on_result(row);failed=failed or row['exitCode']!=0
   if not failed:
    while len(pending)<workers:
     task=next(remaining,None)
     if task is None:break
     pending[pool.submit(runner,task)]=task
 return rows
