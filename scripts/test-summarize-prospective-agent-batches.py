#!/usr/bin/env python3
import importlib.util,json,pathlib,tempfile,unittest
p=pathlib.Path(__file__).with_name('summarize-prospective-agent-batches.py');s=importlib.util.spec_from_file_location('summary',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_missing_and_interrupted_are_not_success(self):
  self.assertEqual(m.outcome(None,False),'NOT_RUN');self.assertEqual(m.outcome(None,True),'INTERRUPTED')
  self.assertEqual(m.outcome({'status':'model_failure'},True),'UNKNOWN');self.assertEqual(m.outcome({'status':'turn_limit'},True),'INCOMPLETE')
 def test_complete_requires_both_checks(self):
  x={'status':'completed','acceptance':{'exitCode':0},'_regression':{'exitCode':0}};self.assertEqual(m.outcome(x,True),'PASS')
  x['_regression']={'exitCode':1};self.assertEqual(m.outcome(x,True),'CHECKS_NONZERO');x['_regression']=None;self.assertEqual(m.outcome(x,True),'UNKNOWN')
 def test_unmatched_and_failed_usage_stay_visible(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td)/'solver-calls.jsonl'
   events=[{'model':'m','label':'1','status':'started'},{'model':'m','label':'1','status':'error'},{'model':'m','label':'2','status':'started'}]
   p.write_text('\n'.join(json.dumps(x) for x in events)+'\n');v=m.usage(pathlib.Path(td))['m']
   self.assertEqual((v['started'],v['completed'],v['unmatchedStarted'],v['missingUsage'],v['failedResponses']),(2,1,1,1,1))
 def test_review_provider_failure_is_distinct_from_missing(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);(root/'reviews').mkdir();(root/'adjudications').mkdir()
   (root/'blind-key.json').write_text(json.dumps({'B01':1}))
   (root/'reviews/B01-a.json').write_text(json.dumps({'eventStatus':'http_error','parsed':{'valid':False}}))
   (root/'adjudications/B01.json').write_text(json.dumps({'eventStatus':'error','parsed':{'valid':False}}))
   row=m.reviews(root,['a','b'])[0]
   self.assertEqual([(x['status'],x.get('eventStatus')) for x in row['ratings']],[('INVALID','http_error'),('MISSING',None)])
   self.assertEqual(row['registeredAdjudication']['eventStatus'],'error')
 def test_missing_posthoc_review_is_not_a_valid_rating(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);(root/'reviews').mkdir()
   (root/'manifest.json').write_text(json.dumps({'kind':'posthoc','selection':'diffs only','limitations':[],'candidates':[{'blind':'R01','reviewers':['a','b']}]}))
   (root/'blind-key.json').write_text(json.dumps({'R01':{'batch':'x','slot':1,'issue':'42','arm':'memex'}}))
   (root/'reviews/R01-a.json').write_text(json.dumps({'parsed':{'valid':False}}))
   row=m.posthoc_review(root)['candidates'][0]
   self.assertEqual([r['status'] for r in row['ratings']],['INVALID','MISSING']);self.assertIsNone(row['adjudication'])
 def test_unstarted_followup_is_counted_once_and_double_starts_rejected(self):
  def run(arm,outcome,status):return {'slot':1 if arm=='keyword' else 2,'project':'chartjs','issue':'12191','arm':arm,'historyRecords':0,'attemptOutcome':outcome,'status':status}
  first={'batch':'validator-chartjs','runs':[run('keyword','NOT_RUN','NOT_RUN_AFTER_STOP'),run('memex','NOT_RUN','NOT_RUN_AFTER_STOP')],'reviews':[]}
  second={'batch':'chartjs-unstarted','runs':[run('keyword','PASS','completed'),run('memex','UNKNOWN','model_failure')],'reviews':[]}
  summary=m.new_pilot_summary([first,second]);self.assertEqual(summary['distinctIssues'],1);self.assertEqual(summary['assignmentOutcomes'],{'PASS':1,'UNKNOWN':1});self.assertEqual(summary['noHistoryControls'],['chartjs#12191'])
  first['runs'][0]=run('keyword','PASS','completed')
  with self.assertRaises(ValueError):m.new_pilot_summary([first,second])
 def test_reported_completion_above_requested_limit_is_visible(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);p=root/'review-calls.jsonl';p.write_text(json.dumps({'model':'qwen3.8-flash','status':'ok','usage':{'completion_tokens':701,'completion_tokens_details':{'reasoning_tokens':600}}})+'\n')
   manifest={'reviewers':['qwen3.8-flash'],'maxReviewTokens':700};row=m.qwen_limit_observations(root,manifest)[0]
   self.assertEqual((row['requestedMaxTokens'],row['reportedCompletionTokens'],row['reportedReasoningTokens']),(700,701,600))
 def test_unstarted_followup_preserves_missing_and_invalid_ratings(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);source=root/'source';followup=root/'followup';source.mkdir();followup.mkdir();(followup/'reviews').mkdir();(followup/'adjudications').mkdir()
   (source/'manifest.json').write_text(json.dumps({'schedule':[{'issue':'42','arm':'keyword'}]}))
   (followup/'manifest.json').write_text(json.dumps({'kind':'test','selection':'unstarted','limitations':[],'reviewers':['a','b'],'adjudicator':'c','candidates':[{'blind':'U01','originalBlind':'B01','slot':1}]}))
   (followup/'reviews/U01-a.json').write_text(json.dumps({'eventStatus':'ok','parsed':{'valid':True,'rating':{'correctness':2,'side_effects':1}}}))
   (followup/'adjudications/U01-c.json').write_text(json.dumps({'eventStatus':'ok','parsed':{'valid':False}}))
   row=m.batch17_unstarted_reviews(followup,source)['candidates'][0]
   self.assertEqual([x['status'] for x in row['ratings']],['VALID','MISSING']);self.assertEqual(row['adjudication']['status'],'INVALID')
if __name__=='__main__':unittest.main()
