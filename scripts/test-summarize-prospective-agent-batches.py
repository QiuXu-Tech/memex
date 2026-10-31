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
 def test_missing_posthoc_review_is_not_a_valid_rating(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);(root/'reviews').mkdir()
   (root/'manifest.json').write_text(json.dumps({'kind':'posthoc','selection':'diffs only','limitations':[],'candidates':[{'blind':'R01','reviewers':['a','b']}]}))
   (root/'blind-key.json').write_text(json.dumps({'R01':{'batch':'x','slot':1,'issue':'42','arm':'memex'}}))
   (root/'reviews/R01-a.json').write_text(json.dumps({'parsed':{'valid':False}}))
   row=m.posthoc_review(root)['candidates'][0]
   self.assertEqual([r['status'] for r in row['ratings']],['INVALID','MISSING']);self.assertIsNone(row['adjudication'])
if __name__=='__main__':unittest.main()
