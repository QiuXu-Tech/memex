#!/usr/bin/env python3
import importlib.util, pathlib, unittest
from unittest.mock import patch
p=pathlib.Path(__file__).with_name('prospective-issue-triage-20261102.py')
s=importlib.util.spec_from_file_location('triage_budget',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class BudgetTests(unittest.TestCase):
 def test_concurrent_reservations_and_unknown_charges_count_against_target(self):
  with patch.object(m,'BUDGET',0.12),patch.object(m,'TOTAL_BUDGET',0.30):
   b=m.Budget()
   self.assertTrue(b.acquire());self.assertTrue(b.acquire());self.assertFalse(b.acquire())
   b.finish(0.03);self.assertTrue(b.acquire());b.finish(None)
   self.assertEqual(b.unknown,1);self.assertAlmostEqual(b.committed,0.15)
   self.assertFalse(b.acquire())
if __name__=='__main__':unittest.main()
