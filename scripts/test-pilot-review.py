#!/usr/bin/env python3
"""Reviewer request and output validation without network calls."""
import importlib.util,pathlib
path=pathlib.Path('scripts/pilot_review.py');spec=importlib.util.spec_from_file_location('pilot_review',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
a=m.review_request('deepseek-flash',[{'role':'user','content':'test'}],2500);assert a['thinking']=={'type':'disabled'} and a['max_tokens']==2500
b=m.review_request('gpt-6-astra',[],2500);assert 'thinking' not in b
assert m.review_status('', 'stop', 'answer')=='empty_response'
assert m.review_status('{bad', 'stop', 'answer')=='invalid_json'
assert m.review_status('{"correctness":2}', 'stop', 'answer')=='invalid_schema'
valid='{"correctness":2,"coverage":1,"evidence_support":1,"unsupported_claims":0,"relevantSourceIds":[],"reason":"ok"}'
assert m.review_status(valid,'stop','answer')=='ok' and m.review_status(valid,'length','answer')=='truncated_response'
auto='{"memory_needed":"unknown","writes_faithful":null,"answer_used_prior_write":"no","supportingSourceIds":[],"reason":"ok"}'
assert m.review_status(auto,'stop','autonomy')=='ok'
print('pilot review request and validation regression passed')
