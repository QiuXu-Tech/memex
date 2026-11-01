#!/usr/bin/env python3
import importlib.util, pathlib, sys, unittest
sys.path.insert(0,str(pathlib.Path(__file__).parent))
p=pathlib.Path(__file__).with_name('prospective-review-triage-recovery-20261102.py')
s=importlib.util.spec_from_file_location('review_triage',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class ReviewValidation(unittest.TestCase):
 def setUp(self):
  import json
  self.rows={'candidates':[{'id':'C01','score':1,'reason':'partial','references':['final:C01'],'unsupportedClaims':[]},
                           {'id':'C02','score':2,'reason':'supported','references':['source:C02'],'unsupportedClaims':[]}]}
  self.event={'status':'ok','finishReason':'stop','message':{'content':json.dumps(self.rows)}}
  self.evidence={'final:C01':'answer','source:C02':{'events':[]}}
 def test_valid_result(self): self.assertEqual(m.parse(self.event,self.evidence),self.rows)
 def test_empty_and_truncated_are_not_scores(self):
  for event in ({'status':'ok','message':{'content':''}},dict(self.event,finishReason='length'),{'status':'http_error'}):
   with self.assertRaises(ValueError):m.parse(event,self.evidence)
 def test_invalid_reference_or_missing_reason_is_rejected(self):
  import json
  for field,value in (('references',['imaginary:source']),('reason','')):
   rows=json.loads(json.dumps(self.rows));rows['candidates'][0][field]=value
   with self.assertRaises(ValueError):m.parse(dict(self.event,message={'content':json.dumps(rows)}),self.evidence)
 def test_adjudication_requires_explicit_disagreement_flag(self):
  with self.assertRaises(ValueError):m.parse(self.event,self.evidence,True)
 def test_missing_score_or_other_candidates_evidence_is_rejected(self):
  import json
  rows=json.loads(json.dumps(self.rows));del rows['candidates'][0]['score']
  with self.assertRaises(ValueError):m.parse(dict(self.event,message={'content':json.dumps(rows)}),self.evidence)
  rows=json.loads(json.dumps(self.rows));rows['candidates'][0]['references']=['source:C02']
  with self.assertRaises(ValueError):m.parse(dict(self.event,message={'content':json.dumps(rows)}),self.evidence)
if __name__=='__main__':unittest.main()
