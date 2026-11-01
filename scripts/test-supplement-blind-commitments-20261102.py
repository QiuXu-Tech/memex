#!/usr/bin/env python3
import hashlib,importlib.util,pathlib,unittest
p=pathlib.Path(__file__).with_name('commit-supplement-blind-packets-20261102.py')
s=importlib.util.spec_from_file_location('commit_blind_packets',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class BlindCommitments(unittest.TestCase):
 def test_key_mapping_commitments_are_salted_and_bound_to_exact_bytes(self):
  key=b'{"C01":"baseline","C02":"memex"}\n';other=b'{"C01":"memex","C02":"baseline"}\n'
  salt=bytes(range(32));commit=m.commitment(salt,key)
  self.assertEqual(commit,m.commitment(salt,key))
  self.assertNotEqual(commit,m.commitment(bytes(reversed(salt)),key))
  self.assertNotEqual(commit,m.commitment(salt,other))
  self.assertNotEqual(commit,hashlib.sha256(key).hexdigest())
if __name__=='__main__':unittest.main()
