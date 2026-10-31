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
 def test_solver_output_limit_accounts_for_forced_final_budget(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);p=root/'solver-calls.jsonl';events=[{'model':'m','status':'ok','operationLabel':'01:0','usage':{'completion_tokens':1001}},
     {'model':'m','status':'ok','operationLabel':'01:final','usage':{'completion_tokens':1100}}]
   p.write_text('\n'.join(json.dumps(e) for e in events)+'\n')
   rows=m.solver_limit_observations(root,{'maxOutputTokens':1000,'maxForcedFinalTokens':1200})
   self.assertEqual(len(rows),1);self.assertEqual(rows[0]['requestedMaxTokens'],1000)
 def test_unstarted_followup_preserves_missing_and_invalid_ratings(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);source=root/'source';followup=root/'followup';source.mkdir();followup.mkdir();(followup/'reviews').mkdir();(followup/'adjudications').mkdir()
   (source/'manifest.json').write_text(json.dumps({'schedule':[{'issue':'42','arm':'keyword'}]}))
   (followup/'manifest.json').write_text(json.dumps({'kind':'test','selection':'unstarted','limitations':[],'reviewers':['a','b'],'adjudicator':'c','candidates':[{'blind':'U01','originalBlind':'B01','slot':1}]}))
   (followup/'reviews/U01-a.json').write_text(json.dumps({'eventStatus':'ok','parsed':{'valid':True,'rating':{'correctness':2,'side_effects':1}}}))
   (followup/'adjudications/U01-c.json').write_text(json.dumps({'eventStatus':'ok','parsed':{'valid':False}}))
   row=m.batch17_unstarted_reviews(followup,source)['candidates'][0]
   self.assertEqual([x['status'] for x in row['ratings']],['VALID','MISSING']);self.assertEqual(row['adjudication']['status'],'INVALID')
 def test_supplementary_coverage_excludes_controls_and_incomplete_runs(self):
  def run(slot,issue,arm,history,status):return {'slot':slot,'project':'mathjs','issue':issue,'arm':arm,'historyRecords':history,'status':status,'attemptOutcome':'PASS' if status=='completed' else 'INCOMPLETE'}
  runs=[run(1,'3614','keyword',3,'completed'),run(2,'3614','memex',3,'completed'),run(3,'x','keyword',0,'completed'),run(4,'x','memex',0,'completed'),run(5,'y','keyword',2,'turn_limit'),run(6,'y','memex',2,'completed')]
  reviews=[{'slot':n,'ratings':[{'status':v} for v in ratings]} for n,ratings in [(1,['MISSING','MISSING']),(2,['VALID','VALID']),(3,['VALID','VALID']),(4,['VALID','VALID']),(5,['VALID','VALID']),(6,['VALID','VALID'])]]
  follow={'candidates':[{'issue':'3614','arm':'keyword','ratings':[{'status':'VALID'},{'status':'VALID'}]}]}
  value=m.supplemental_coverage([{'batch':'moment-mathjs','runs':runs,'reviews':reviews}],None,None,follow)
  self.assertEqual((value['issuePairsWithOriginalOrSupplementaryRatings'],value['issuePairsExcludingNoHistoryControls']),(2,1))
  self.assertEqual(value['additionalIssuesAfterSupplementaryReviews'],['mathjs#3614'])
 def test_followup_requires_complete_arms_and_valid_adjudication_for_disagreements(self):
  def run(slot,issue,arm,status):return {'slot':slot,'project':'p','issue':issue,'arm':arm,'attemptOutcome':'PASS' if status=='completed' else 'UNKNOWN','status':status}
  def review(slot,a,b,adj=None):return {'slot':slot,'ratings':[{'status':'VALID','correctness':a,'sideEffects':1},{'status':'VALID','correctness':b,'sideEffects':1}],'registeredAdjudication':adj}
  batch={'batch':'independent-27','runs':[run(1,'1','keyword','completed'),run(2,'1','memex','completed'),run(3,'2','keyword','model_failure'),run(4,'2','memex','completed')],
         'reviews':[review(1,2,1,{'status':'INVALID'}),review(2,2,2),review(3,2,2),review(4,2,2)]}
  value=m.followup_summary([batch]);self.assertEqual(value['distinctIssues'],2);self.assertEqual(value['bothArmsCompleteWithTwoFormatValidReviews'],1)
  self.assertEqual(value['bothArmsCompleteWithDisagreementsResolved'],0);self.assertEqual(value['disagreementAdjudications'],{'INVALID':1})
  batch['reviews'][0]['registeredAdjudication']={'status':'VALID'}
  self.assertEqual(m.followup_summary([batch])['bothArmsCompleteWithDisagreementsResolved'],1)
 def test_historical_posthoc_adjudication_does_not_overwrite_original(self):
  runs=[{'slot':i,'project':'luxon','issue':'1189','arm':arm,'historyRecords':2,'status':'completed','attemptOutcome':'PASS'} for i,arm in [(1,'keyword'),(2,'memex')]]
  reviews=[{'slot':i,'ratings':[{'status':'VALID','correctness':2,'sideEffects':1},{'status':'VALID','correctness':score,'sideEffects':1}],
            'registeredAdjudication':{'status':'INVALID'}} for i,score in [(1,1),(2,2)]]
  batch={'batch':'luxon-new','runs':runs,'reviews':reviews}
  posthoc={'candidates':[{'source':'20261031-luxon-batch22','slot':1,'arm':'keyword','result':{'status':'VALID'}}]}
  result=m.historical_resolution_coverage([batch],None,None,None,None,None,posthoc)
  self.assertEqual(result['beforeV33']['pairsWithValidDisagreementAdjudications'],0)
  self.assertEqual(result['includingV33']['pairsWithValidDisagreementAdjudications'],1)
  self.assertEqual(reviews[0]['registeredAdjudication']['status'],'INVALID')
 def test_alternate_review_is_separate_and_needs_valid_adjudication(self):
  runs=[{'slot':i,'project':'p','issue':'1','arm':arm,'status':'completed','attemptOutcome':'PASS'} for i,arm in [(1,'keyword'),(2,'memex')]]
  valid={'status':'VALID','correctness':2,'sideEffects':1};invalid={'status':'INVALID'}
  reviews=[{'slot':1,'ratings':[valid,invalid],'registeredAdjudication':None},{'slot':2,'ratings':[valid,valid],'registeredAdjudication':None}]
  batch={'batch':'independent-31','runs':runs,'reviews':reviews}
  replacement={'status':'VALID','correctness':1,'sideEffects':1}
  follow={'candidates':[{'source':'20261031-independent-batch31','slot':1,'supplementaryReview':replacement,'supplementaryAdjudication':{'status':'MISSING'}}]}
  result=m.followup_summary([batch],follow)
  self.assertEqual(result['bothArmsCompleteWithTwoFormatValidReviews'],1)
  self.assertEqual(result['bothArmsCompleteWithDisagreementsResolved'],0)
  self.assertEqual(reviews[0]['ratings'][1]['status'],'INVALID')
  follow['candidates'][0]['supplementaryAdjudication']={'status':'VALID'}
  self.assertEqual(m.followup_summary([batch],follow)['bothArmsCompleteWithDisagreementsResolved'],1)
 def test_followup_unstarted_reregistration_is_counted_once(self):
  def run(outcome,status):return {'slot':1,'project':'yup','issue':'2252','arm':'keyword','status':status,'attemptOutcome':outcome}
  old={'batch':'independent-32','runs':[run('NOT_RUN','NOT_RUN_AFTER_STOP')],'reviews':[]}
  new={'batch':'independent-35','runs':[run('PASS','completed')],'reviews':[]}
  result=m.followup_summary([old,new]);self.assertEqual(result['distinctIssues'],1);self.assertEqual(result['assignmentOutcomes'],{'PASS':1})
  old['runs']=[run('UNKNOWN','model_failure')]
  with self.assertRaises(ValueError):m.followup_summary([old,new])
if __name__=='__main__':unittest.main()
