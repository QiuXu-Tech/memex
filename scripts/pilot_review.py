"""Build reviewer requests and distinguish empty, invalid and complete responses."""
import json

def review_request(model,messages,max_tokens):
 body={'model':model,'messages':messages,'max_tokens':max_tokens,'temperature':0}
 if model.startswith('deepseek'):body['thinking']={'type':'disabled'}
 return body

def review_status(text,finish_reason,kind):
 if not isinstance(text,str) or not text.strip():return 'empty_response'
 if finish_reason=='length':return 'truncated_response'
 try:obj=json.loads(text)
 except (ValueError,TypeError):return 'invalid_json'
 if not isinstance(obj,dict):return 'invalid_schema'
 if kind=='answer':
  keys={'correctness','coverage','evidence_support','unsupported_claims','relevantSourceIds','reason'}
  if not keys.issubset(obj):return 'invalid_schema'
  if any(obj[k] is not None and (type(obj[k]) is not int or obj[k] not in (0,1,2)) for k in ['correctness','coverage','evidence_support']):return 'invalid_schema'
  if obj['unsupported_claims'] is not None and (type(obj['unsupported_claims']) is not int or obj['unsupported_claims']<0):return 'invalid_schema'
  ids=obj['relevantSourceIds']
 elif kind=='autonomy':
  keys={'memory_needed','writes_faithful','answer_used_prior_write','supportingSourceIds','reason'}
  if not keys.issubset(obj):return 'invalid_schema'
  if any(obj[k] not in ('yes','no','unknown',None) for k in ['memory_needed','writes_faithful','answer_used_prior_write']):return 'invalid_schema'
  ids=obj['supportingSourceIds']
  if 'supportingMemoryIds' in obj and (not isinstance(obj['supportingMemoryIds'],list) or any(not isinstance(x,str) for x in obj['supportingMemoryIds'])):return 'invalid_schema'
 else:raise ValueError('unknown review kind')
 if not isinstance(ids,list) or any(not isinstance(x,str) for x in ids) or not isinstance(obj['reason'],str):return 'invalid_schema'
 return 'ok'
