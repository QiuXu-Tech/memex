#!/usr/bin/env python3
import importlib.util,pathlib,unittest
from unittest.mock import patch
p=pathlib.Path(__file__).with_name('prospective-issue-triage-recovery-20261102.py')
s=importlib.util.spec_from_file_location('triage_recovery',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class RecoveryAccounting(unittest.TestCase):
 def test_cumulative_resume_cost_is_not_double_counted(self):
  first={'total_cost_usd':0.05};last={'total_cost_usd':0.06}
  self.assertEqual(m.client_total(first,last,True),0.06)
  self.assertIsNone(m.client_total(first,{'total_cost_usd':0.01},True))
  self.assertIsNone(m.client_total(first,{},True))
 def test_charged_zero_usage_is_a_gap(self):
  event={'total_cost_usd':0.005,'usage':{'input_tokens':0,'cache_creation_input_tokens':0,'cache_read_input_tokens':0,'output_tokens':0}}
  self.assertTrue(m.zero_usage_with_charge(event))
  event['usage']['input_tokens']=3;self.assertFalse(m.zero_usage_with_charge(event))
 def test_budget_reserves_before_concurrent_launch(self):
  with patch.object(m,'BUDGET',0.10),patch.object(m,'TOTAL_BUDGET',0.25):
   b=m.Budget();self.assertTrue(b.acquire());self.assertTrue(b.acquire());self.assertFalse(b.acquire())
   b.finish(None);self.assertEqual(b.unknown,1);self.assertFalse(b.acquire())
 def test_unavailable_tool_error_is_distinct_from_an_unverified_execution(self):
  call={'type':'assistant','message':{'content':[{'type':'tool_use','id':'t1','name':'mcp__pilot__repo_open'}]}}
  rejected={'type':'user','message':{'content':[{'type':'tool_result','tool_use_id':'t1','is_error':True,'content':'Error: No such tool available: mcp__pilot__repo_open'}]}}
  self.assertEqual(m.classify_tool_attempts([call,rejected],[]),([],['mcp__pilot__repo_open']))
  self.assertEqual(m.classify_tool_attempts([call],[]),(['mcp__pilot__repo_open'],[]))
  rejected['message']['content'][0]['content']='Tool failed after running'
  self.assertEqual(m.classify_tool_attempts([call,rejected],[]),(['mcp__pilot__repo_open'],[]))
if __name__=='__main__':unittest.main()
