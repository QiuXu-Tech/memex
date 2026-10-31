#!/usr/bin/env python3
"""Do not start further tasks after a shard reports failure."""
import threading,time
from pilot_batch import run_bounded
started=[];lock=threading.Lock()
def shard(task):
 with lock:started.append(task)
 if task=='first':return {'task':task,'exitCode':1}
 time.sleep(.05);return {'task':task,'exitCode':0}
rows=run_bounded(['first','second','third','fourth'],2,shard,lambda _:None)
assert any(x['exitCode']==1 for x in rows) and set(started)<={'first','second'} and len(rows)==len(started)
print('Pilot batch stops scheduling after shard failure')
