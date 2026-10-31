#!/usr/bin/env python3
import importlib.util,pathlib,unittest
p=pathlib.Path(__file__).with_name('prospective-gateway-review-v34.py');s=importlib.util.spec_from_file_location('review',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_packet_requires_completed_attempt_and_omits_arm(self):
  p=m.packet_for({'body':'issue'},{'status':'completed','issue':'1','arm':'memex'},'diff')
  self.assertNotIn('arm',p);self.assertNotIn('issueId',p)
  with self.assertRaises(ValueError):m.packet_for({'body':'issue'},{'status':'model_failure'},'diff')
if __name__=='__main__':unittest.main()
