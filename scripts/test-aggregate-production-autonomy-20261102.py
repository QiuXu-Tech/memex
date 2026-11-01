#!/usr/bin/env python3
import importlib.util,json,pathlib,tempfile,unittest
p=pathlib.Path(__file__).with_name('aggregate-production-autonomy-20261102.py');s=importlib.util.spec_from_file_location('autonomy_aggregate',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class AggregateValidation(unittest.TestCase):
 def test_tool_repetition_is_counted_within_each_session_only(self):
  def call(name,args):return {'type':'assistant','message':{'content':[{'type':'tool_use','name':name,'input':args}]}}
  read=call('mcp__pilot__repo_read',{'path':'a','start':1})
  memory=call('mcp__memex__memory_open',{'id':'x'})
  counts=m.tool_counts([[read,read,memory],[read]])
  self.assertEqual(counts,{'total':4,'exactRepeated':1,'memory':1,'source':3,'archive':0,'other':0})
 def test_paired_client_price_preserves_missing_values(self):
  row={'sessions':{'baseline-s1':{'clientListPriceUsd':0.1},'baseline-s2':{'clientListPriceUsd':0.2}}}
  self.assertAlmostEqual(m.paired_client_prices([row],'baseline'),0.3)
  row['sessions']['baseline-s2']['clientListPriceUsd']=None
  self.assertIsNone(m.paired_client_prices([row],'baseline'))
 def test_message_contexts_deduplicate_streamed_blocks_within_session(self):
  def message(mid,reads):return {'type':'assistant','message':{'id':mid,'usage':{'input_tokens':1,'cache_creation_input_tokens':2,'cache_read_input_tokens':reads}}}
  self.assertEqual(m.message_contexts([[message('a',3),message('a',4)],[message('a',5)]]),{'messageIds':2,'inputTokens':15})
  self.assertEqual(m.first_message_context([[message('a',3),message('a',4)],[message('b',5)]]),{'sessions':2,'inputTokens':14})
 def test_budget_recovery_does_not_erase_failure_or_rejected_tool(self):
  rows=[{'runnerError':None,'sessions':{'a':{'status':'error_max_budget_usd','responseCompleted':False},
       'b':{'status':'success','responseCompleted':True,'recovery':{'status':'success'},'unavailableToolAttempts':['missing']}}}]
  out=m.session_outcomes(rows)
  self.assertEqual(out['notCompletedByStatus'],{'error_max_budget_usd':1})
  self.assertEqual((out['resumedAfterBudget'],out['resumedAndCompleted'],out['unavailableToolAttempts']),(1,1,1))
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
 def test_automatic_checkpoint_is_matched_to_actual_client_session(self):
  with tempfile.TemporaryDirectory() as td:
   base=pathlib.Path(td);task=base/'01';trace=task/'traces';trace.mkdir(parents=True);(task/'results').mkdir()
   (task/'results/memex-s1.json').write_text(json.dumps({'sessionId':'session-one'}))
   records=task/'memory/memex/records/workspace';records.mkdir(parents=True)
   (records/'mem_1234567890.md').write_text('---\nprovenance: {"source":"claude-stop","sourceSession":"session-one"}\n---\nbody')
   (records/'mem_abcdefghij.md').write_text('---\nprovenance: {"source":"claude-stop","sourceSession":"other"}\n---\nbody')
   event={'type':'assistant','message':{'content':[{'type':'tool_use','name':'mcp__memex__memory_open','input':{'id':'mem_1234567890'}}]}}
   (trace/'memex-s2-events.jsonl').write_text(json.dumps(event)+'\n')
   chain=m.writes_and_opens(base,'01');self.assertEqual(chain['automaticCheckpointIds'],['mem_1234567890']);self.assertTrue(chain['automaticCheckpointOpenedNext'])
 def test_posthoc_revalidation_is_separate_from_primary(self):
  with tempfile.TemporaryDirectory() as td:
   base=pathlib.Path(td);folder=base/'reviews/01';folder.mkdir(parents=True);post=base/'reviews/posthoc-limits';post.mkdir()
   (folder/'key.json').write_text(json.dumps({'C01':'baseline','C02':'memex'}))
   ratings={'candidates':[{'id':'C01','score':2,'unsupportedClaims':[]},{'id':'C02','score':1,'unsupportedClaims':[]}]}
   (post/'01-result.json').write_text(json.dumps({'reviews':[{'rating':ratings},{'rating':ratings}],'adjudication':{'status':'NOT_RUN'},'correctedModels':['gpt-6.1-sol']}))
   self.assertEqual(m.review_summary(base,'01')['status'],'MISSING_VALID_REVIEW')
   self.assertEqual(m.posthoc_review_summary(base,'01')['scoresByArm'],{'baseline':2,'memex':1})
if __name__=='__main__':unittest.main()
