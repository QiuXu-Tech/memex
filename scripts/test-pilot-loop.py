#!/usr/bin/env python3
"""Regression tests for bounded tool use and final-answer preservation."""
import importlib.util,pathlib
path=pathlib.Path('scripts/pilot_loop.py');spec=importlib.util.spec_from_file_location('pilot_loop',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
def tool(name,args,id):return {'id':id,'type':'function','function':{'name':name,'arguments':args}}
def tools(*names):return [{'function':{'name':n}} for n in names]
class Worker:
 def __init__(self):self.calls=[]
 def rpc(self,x):self.calls.append((x['name'],x['args']));return {'text':'observed result'}
class Model:
 def __init__(self,steps):self.steps=iter(steps);self.seen=[]
 def __call__(self,m,t,cap,trace,stage):
  self.seen.append({'tools':[x['function']['name'] for x in t],'messages':list(m)})
  msg,reason=next(self.steps);trace.append({'kind':'model','stage':stage,'status':'ok','finishReason':reason});return msg

def case_limit():
 w=Worker();trace=[];m=Model([({'tool_calls':[tool('memory_search','{"query":"one"}','a')], 'content':None},'tool_calls'),({'tool_calls':[tool('memory_search','{"query":"two"}','b')], 'content':None},'tool_calls'),({'tool_calls':[tool('memory_write','{"body":"must not write"}','c')], 'content':None},'tool_calls'),({'content':'Evidence is insufficient.'},'stop')]);messages=[]
 r=mod.run_tool_loop(messages,tools('memory_search','memory_write'),w,trace,'answer',100,2,5,m)
 assert r['status']=='ok' and r['text']=='Evidence is insufficient.' and r['finalizedAfterLimit']
 assert [x[0] for x in w.calls]==['memory_search','memory_search'] and m.seen[-1]['tools']==[]
 assert any(x.get('role')=='tool' and x.get('tool_call_id')=='c' and 'not executed' in x.get('content','').lower() for x in m.seen[-1]['messages'])
 assert any(x['kind']=='tool_limit' for x in trace)

def case_duplicate_and_write():
 w=Worker();trace=[];m=Model([({'tool_calls':[tool('memory_search','{"query":"x"}','a')], 'content':None},'tool_calls'),({'tool_calls':[tool('memory_search','{"query":"x"}','b')], 'content':None},'tool_calls'),({'tool_calls':[tool('memory_write','{"body":"new"}','c')], 'content':None},'tool_calls'),({'tool_calls':[tool('memory_search','{"query":"x"}','d')], 'content':None},'tool_calls'),({'content':'done'},'stop')]);r=mod.run_tool_loop([],tools('memory_search','memory_write'),w,trace,'answer',100,5,3,m)
 assert r['status']=='ok' and [x[0] for x in w.calls]==['memory_search','memory_write','memory_search']
 assert sum(x.get('status')=='duplicate_reused' for x in trace)==1

def case_no_answer():
 w=Worker();trace=[];m=Model([({'tool_calls':[tool('memory_search','{"query":"x"}','a')], 'content':None},'tool_calls'),({'content':''},'stop')]);r=mod.run_tool_loop([],tools('memory_search'),w,trace,'answer',100,0,0,m);assert r['status']=='empty_after_limit' and not w.calls
def case_duplicate_write_and_uncertain_failure():
 for fails in (False,True):
  class W(Worker):
   def rpc(self,x):
    self.calls.append((x['name'],x['args']))
    if fails:raise RuntimeError('ambiguous write failure')
    return {'text':'saved'}
  w=W();trace=[];m=Model([({'tool_calls':[tool('memory_write','{"body":"same"}','a')], 'content':None},'tool_calls'),({'tool_calls':[tool('memory_write','{"body":"same"}','b')], 'content':None},'tool_calls'),({'content':'done'},'stop')]);r=mod.run_tool_loop([],tools('memory_write'),w,trace,'intake',100,5,3,m)
  assert len(w.calls)==1 and any(x.get('status')=='duplicate_write_blocked' for x in trace)
  assert r['status']=='ok'

def case_truncated_continuation():
 w=Worker();trace=[];m=Model([({'content':'First part '},'length'),({'content':'second part.'},'stop')]);r=mod.run_tool_loop([],tools(),w,trace,'answer',100,2,0,m)
 assert r['status']=='ok' and r['text']=='First part second part.' and len(m.seen)==2
 assert m.seen[-1]['tools']==[] and any(x['kind']=='answer_continuation' for x in trace)

def case_continuation_limit_and_failure():
 w=Worker();trace=[];m=Model([({'content':'A'},'length'),({'content':'B'},'length'),({'content':'C'},'length')]);r=mod.run_tool_loop([],tools(),w,trace,'answer',100,2,0,m)
 assert r['status']=='truncated' and r['text']=='ABC' and len(m.seen)==3
 w=Worker();trace=[];m=Model([({'content':'first'},'length'),({'content':'','tool_calls':[tool('memory_write','{}','x')]},'tool_calls')]);r=mod.run_tool_loop([],tools('memory_write'),w,trace,'answer',100,2,3,m)
 assert r['status']=='unexpected_tool_call_in_continuation' and r['text']=='first' and not w.calls
 w=Worker();trace=[];m=Model([({'tool_calls':[tool('memory_search','{}','a')],'content':None},'tool_calls'),({'content':'part'},'length'),({'content':' end'},'stop')]);r=mod.run_tool_loop([],tools('memory_search'),w,trace,'answer',100,0,0,m)
 assert r['status']=='ok' and r['text']=='part end' and r['finalizedAfterLimit'] and not w.calls

for fn in (case_limit,case_duplicate_and_write,case_no_answer,case_duplicate_write_and_uncertain_failure,case_truncated_continuation,case_continuation_limit_and_failure):fn()
print('pilot loop regression passed')
