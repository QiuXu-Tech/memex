#!/usr/bin/env python3
import importlib.util,pathlib,unittest
p=pathlib.Path(__file__).with_name('prospective-gateway-adjudication-v33.py');s=importlib.util.spec_from_file_location('adjudication',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_packet_requires_complete_disagreement_and_omits_arm(self):
  result={'status':'completed','issue':'1','arm':'memex','final':'done'};ratings=[{'valid':True,'rating':{'correctness':2,'side_effects':1}},{'valid':True,'rating':{'correctness':1,'side_effects':1}}]
  packet=m.make_packet({'body':'issue'},result,'diff',ratings)
  self.assertNotIn('arm',packet);self.assertNotIn('issueId',packet);self.assertEqual(len(packet['reviews']),2)
  with self.assertRaises(ValueError):m.make_packet({'body':'issue'},{'status':'model_failure'},'diff',ratings)
  with self.assertRaises(ValueError):m.make_packet({'body':'issue'},result,'diff',[ratings[0],ratings[0]])
if __name__=='__main__':unittest.main()
