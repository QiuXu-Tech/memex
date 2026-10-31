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
print('Separate audit citation namespaces regression passed')
