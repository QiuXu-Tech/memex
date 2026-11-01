#!/usr/bin/env python3
"""Enforce separate historical-evidence and observed-memory citation namespaces."""
from pilot_citations import audit_memory_ids, validate_autonomy_citations

episode={'pages':[{'id':'history-1'},{'id':'history-2'}]}
run={'trace':[{'kind':'tool','name':'memory_write','status':'ok','result':'Saved mem_abc'}, {'kind':'tool','name':'memory_search','status':'ok','result':'Found mem_def'}, {'kind':'tool','name':'memory_open','status':'error','arguments':{'id':'mem_fake'}},{'kind':'pager','ids':['mem_xyz']}]}
assert audit_memory_ids(run)=={'mem_abc','mem_def','mem_xyz'}
assert validate_autonomy_citations({'supportingSourceIds':['history-1'],'supportingMemoryIds':['mem_abc']},episode,run,True) is None
assert validate_autonomy_citations({'supportingSourceIds':['mem_abc'],'supportingMemoryIds':[]},episode,run,True)=='source_ids'
assert validate_autonomy_citations({'supportingSourceIds':[],'supportingMemoryIds':['mem_fake']},episode,run,True)=='memory_ids'
assert validate_autonomy_citations({'supportingSourceIds':['history-2']},episode,run,True)=='missing_memory_ids'
assert validate_autonomy_citations({'supportingSourceIds':['history-2']},episode,run,False) is None

claim={'supportingSourceIds':['history-1'],'supportingMemoryIds':['mem_abc'],'answer_used_prior_write':'yes'}
write={'kind':'tool','stage':'intake','name':'memory_write','status':'ok','result':'Saved mem_abc'}
opened={'kind':'tool','stage':'answer','name':'memory_open','status':'ok','arguments':{'id':'mem_abc'}}
pager={'kind':'pager','status':'ok','ids':['mem_abc']}
def check(trace,answer,valid,obj=claim):
 result=validate_autonomy_citations(obj,episode,{'trace':trace,'answer':answer},True)
 assert (result is None)==valid,(result,valid)
check([write],'Nothing was opened.',False)
check([write,opened],'The record was not cited.',False)
check([write,opened],'Based on mem_abc.',True)
check([write,pager],'Based on mem_abc.',True)
check([write,{**opened,'status':'error'}],'Based on mem_abc.',False)
check([write,{**pager,'status':'error'}],'Based on mem_abc.',False)
check([opened,write],'Based on mem_abc.',False)
check([opened,write,opened],'Based on mem_abc.',True)
check([write,opened],'Based on mem_abcd.',False)
check([write,opened],'Based on mem_abc.',False,{**claim,'supportingMemoryIds':['mem_fake']})
check([write],'Nothing was opened.',True,{**claim,'answer_used_prior_write':'no'})
assert validate_autonomy_citations({'supportingSourceIds':[],'answer_used_prior_write':'yes'},episode,{'trace':[write],'answer':''},False)=='missing_memory_ids'
print('Separate audit citation namespaces regression passed')
