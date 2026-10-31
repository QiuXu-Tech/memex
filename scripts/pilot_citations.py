"""Separate earlier-history evidence from IDs observed in memory actions."""
import re

MEMORY_ID=re.compile(r'\bmem_[a-z0-9]+\b')

def audit_memory_ids(run):
 ids=set()
 for event in run['trace']:
  if event.get('kind')=='pager':ids.update(i for i in event.get('ids',[]) if isinstance(i,str) and MEMORY_ID.fullmatch(i))
  elif event.get('kind')=='tool' and event.get('status')=='ok':
   ids.update(MEMORY_ID.findall(str(event.get('result',''))))
   if event.get('name')=='memory_open':
    value=event.get('arguments',{}).get('id')
    if isinstance(value,str) and MEMORY_ID.fullmatch(value):ids.add(value)
 return ids

def validate_autonomy_citations(obj,episode,run,require_memory=False):
 sources=obj.get('supportingSourceIds');allowed={x['id'] for x in episode['pages']}
 if not isinstance(sources,list) or any(not isinstance(x,str) or x not in allowed for x in sources):return 'source_ids'
 memory=obj.get('supportingMemoryIds')
 if memory is None:return 'missing_memory_ids' if require_memory else None
 if not isinstance(memory,list) or any(not isinstance(x,str) or x not in audit_memory_ids(run) for x in memory):return 'memory_ids'
 return None
