#!/usr/bin/env python3
"""A 403 blocks subsequent calls to that model but not other reviewers."""
from pilot_review_guard import ReviewGuard

guard=ReviewGuard();sent=[]
def attempt(model,status):
 if guard.is_blocked(model):return 'skipped_after_403'
 sent.append(model)
 if status==403:guard.block(model)
 return status
assert attempt('astra',403)==403
assert attempt('astra',200)=='skipped_after_403'
assert attempt('deepseek',200)==200
assert sent==['astra','deepseek']
print('Reviewer 403 guard blocks only the denied model')
