"""Bounded pilot tool loop with read deduplication and a tool-free final attempt."""
import datetime,json,time
from zoneinfo import ZoneInfo

now=lambda:datetime.datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
READ_SEARCHES={'memory_search','archive_search'}

def finish_response(message,messages,trace,stage,max_tokens,call,already_appended,after_limit):
 text=message.get('content') or '';finish=trace[-1].get('finishReason');suffix='_after_limit' if after_limit else ''
 if not text.strip():return 'empty'+suffix,text
 if finish!='length':return 'ok',text
 if stage!='answer':return 'truncated'+suffix,text
 if not already_appended:messages.append({'role':'assistant','content':text})
 for index in range(2):
  messages.append({'role':'user','content':'Your previous answer was cut off by the output limit. Continue exactly where it stopped. Do not repeat earlier text, request tools, or invent missing evidence.'})
  part=call(messages,[],max_tokens,trace,stage)
  if part is None:
   trace.append({'kind':'answer_continuation','stage':stage,'at':now(),'attempt':index+1,'status':'model_failure'})
   return 'continuation_model_failure',text
  reason=trace[-1].get('finishReason')
  if part.get('tool_calls'):
   trace.append({'kind':'answer_continuation','stage':stage,'at':now(),'attempt':index+1,'status':'unexpected_tool_call'})
   return 'unexpected_tool_call_in_continuation',text
  chunk=part.get('content') or ''
  if not chunk.strip():
   trace.append({'kind':'answer_continuation','stage':stage,'at':now(),'attempt':index+1,'status':'empty'})
   return 'empty_continuation',text
  text+=chunk;messages.append({'role':'assistant','content':chunk});trace.append({'kind':'answer_continuation','stage':stage,'at':now(),'attempt':index+1,'status':'truncated' if reason=='length' else 'ok'})
  if reason!='length':return 'ok',text
 return 'truncated'+suffix,text

def run_tool_loop(messages,tools,worker,trace,stage,max_tokens,max_rounds,write_budget,call):
 names={t['function']['name'] for t in tools};writes=0;search_cache={};write_attempts={}
 for round_index in range(max_rounds+1):
  msg=call(messages,tools,max_tokens,trace,stage)
  if msg is None:return {'status':'model_failure','text':'','writes':writes,'finalizedAfterLimit':False}
  calls=msg.get('tool_calls') or []
  assistant={'role':'assistant','content':msg.get('content')}
  if calls:assistant['tool_calls']=calls
  if msg.get('reasoning_content') is not None:assistant['reasoning_content']=msg['reasoning_content']
  messages.append(assistant)
  if not calls:
   status,text=finish_response(msg,messages,trace,stage,max_tokens,call,True,False)
   return {'status':status,'text':text,'writes':writes,'finalizedAfterLimit':False}
  if round_index==max_rounds:
   trace.append({'kind':'tool_limit','stage':stage,'at':now(),'requestedNames':[c.get('function',{}).get('name') for c in calls]})
   for c in calls:messages.append({'role':'tool','tool_call_id':c.get('id',''),'content':'Tool budget exhausted; this requested action was not executed.'})
   messages.append({'role':'user','content':'The tool budget is exhausted. Do not request further tools. Respond using only the information already available; explicitly state uncertainty or abstain when the evidence is insufficient.'})
   final=call(messages,[],max_tokens,trace,stage)
   if final is None:status,text='model_failure_after_limit',''
   elif final.get('tool_calls'):status,text='unexpected_tool_call_after_limit',''
   else:
    status,text=finish_response(final,messages,trace,stage,max_tokens,call,False,True)
   trace.append({'kind':'tool_finalization','stage':stage,'at':now(),'status':status})
   return {'status':status,'text':text,'writes':writes,'finalizedAfterLimit':True}
  for callrow in calls:
   fn=callrow.get('function',{});name=fn.get('name','');event={'kind':'tool','stage':stage,'name':name,'at':now(),'callId':callrow.get('id')};start=time.monotonic()
   try:
    argv=json.loads(fn.get('arguments','{}'));event['arguments']=argv
    if name not in names:raise RuntimeError('tool not allowed in arm')
    cache_key=(name,json.dumps(argv,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    if name=='memory_write' and cache_key in write_attempts:
     previous=write_attempts[cache_key];value='Identical write was already attempted and was not executed again. Previous outcome: '+previous;event.update(status='duplicate_write_blocked',result=value)
    elif name=='memory_write' and writes>=write_budget:raise RuntimeError('write limit reached')
    elif name in READ_SEARCHES and cache_key in search_cache:
     value=search_cache[cache_key]+'\n[Repeated search: no new call was made; use existing results or answer with uncertainty.]';event.update(status='duplicate_reused',result=value)
    else:
     if name=='memory_write':write_attempts[cache_key]='UNKNOWN';search_cache.clear()
     value=worker.rpc({'op':'tool','name':name,'args':argv})['text'];event.update(status='ok',result=value)
     if name in READ_SEARCHES:search_cache[cache_key]=value
     if name=='memory_write':writes+=1;write_attempts[cache_key]=value
   except Exception as e:event.update(status='error',errorType=type(e).__name__,error=str(e));value='Tool failed: '+str(e)
   event['elapsedSeconds']=round(time.monotonic()-start,5);trace.append(event);messages.append({'role':'tool','tool_call_id':callrow.get('id',''),'content':value})
 return {'status':'tool_round_limit','text':'','writes':writes,'finalizedAfterLimit':False}
