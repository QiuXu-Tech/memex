#!/usr/bin/env python3
import importlib.util,json,pathlib,unittest
spec=importlib.util.spec_from_file_location('normalizer',pathlib.Path(__file__).with_name('prospective-review-normalize-v2.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_explicit_and_known_aliases_only(self):
  obj={'correctness':2,'side_effects':1,'reason':'partial','references':['issue: text','candidateDiff','acceptance','upstreamRegression']}
  r=m.normalize(json.dumps(obj),'stop');self.assertEqual(r['status'],'posthoc_normalized');self.assertEqual(r['parsed']['rating']['references'],['issue','candidate','checks'])
  obj['references']=['issue: text','invented'];self.assertEqual(m.normalize(json.dumps(obj),'stop')['status'],'invalid')
 def test_unchanged_and_truncated(self):
  obj={'correctness':None,'side_effects':0,'reason':'partial','references':['issue']};s=json.dumps(obj)
  self.assertEqual(m.normalize(s,'stop')['status'],'valid_unchanged');self.assertEqual(m.normalize(s,'length')['status'],'invalid')
 def test_other_invalid_fields_are_not_repaired(self):
  obj={'correctness':True,'side_effects':0,'reason':'x','references':['candidateDiff']};self.assertEqual(m.normalize(json.dumps(obj),'stop')['status'],'invalid')
if __name__=='__main__':unittest.main()
