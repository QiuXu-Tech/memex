#!/usr/bin/env python3
import importlib.util,json,pathlib,tempfile,unittest
p=pathlib.Path(__file__).with_name('aggregate-production-autonomy-20261102.py');s=importlib.util.spec_from_file_location('autonomy_aggregate',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class AggregateValidation(unittest.TestCase):
 def test_cached_input_and_charged_zero_usage_are_not_conflated(self):
  usage={'input_tokens':2,'cache_creation_input_tokens':3,'cache_read_input_tokens':4,'output_tokens':5}
  self.assertEqual(m.model_tokens({'usage':usage,'clientListPriceUsd':0.01})['input'],9)
  self.assertIsNone(m.model_tokens({'usage':dict.fromkeys(usage,0),'clientListPriceUsd':0.01}))
  self.assertIsNone(m.model_tokens({'usage':None,'clientListPriceUsd':0.01}))
 def test_unresolved_judge_disagreement_is_not_a_score(self):
  with tempfile.TemporaryDirectory() as td:
   base=pathlib.Path(td);folder=base/'reviews'/'01';folder.mkdir(parents=True)
   (folder/'key.json').write_text(json.dumps({'C01':'baseline','C02':'memex'}))
   for model,score in (('gpt-6.1-sol',1),('deepseek-flash',2)):
    (folder/f'{model}.json').write_text(json.dumps({'rating':{'candidates':[{'id':'C01','score':score,'unsupportedClaims':[]},{'id':'C02','score':1,'unsupportedClaims':[]}]}}))
   (folder/'adjudication.json').write_text(json.dumps({'status':'ok','rating':None}))
   self.assertEqual(m.review_summary(base,'01')['status'],'UNRESOLVED_DISAGREEMENT')
 def test_unverified_label_must_belong_to_written_id(self):
  with tempfile.TemporaryDirectory() as td:
   base=pathlib.Path(td);trace=base/'01/traces';trace.mkdir(parents=True)
   one=[{'type':'assistant','message':{'content':[{'type':'tool_use','id':'t1','name':'mcp__memex__memory_write'}]}},
        {'type':'user','message':{'content':[{'type':'tool_result','tool_use_id':'t1','content':'Stored mem_1234567890'}]}}]
   two=[{'subtype':'hook_response','hook_name':'UserPromptSubmit','stdout':'mem_1234567890 other mem_abcdefghij [unverified]'}]
   (trace/'memex-s1-events.jsonl').write_text('\n'.join(map(json.dumps,one))+'\n');(trace/'memex-s2-events.jsonl').write_text('\n'.join(map(json.dumps,two))+'\n')
   chain=m.writes_and_opens(base,'01');self.assertTrue(chain['writtenIdInAutomaticRecall']);self.assertFalse(chain['unverifiedRecallLabel'])
if __name__=='__main__':unittest.main()
