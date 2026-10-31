import unittest
from production_prospective_guard import accepts

class GuardTests(unittest.TestCase):
 def test_valid_function_keyword_and_two_checks(self):
  self.assertTrue(accepts('function customOmitClone(value) { return isPlainObject(value) || isArray(value) ? undefined : value; }'))
 def test_rejects_process_and_constructor(self):
  for s in ['function customOmitClone(value) { return process; }','function customOmitClone(value) { return value.constructor; }','function customOmitClone(value) { return require(value); }','function customOmitClone(value) { return value; } process.exit()']:
   self.assertFalse(accepts(s),s)
 def test_rejects_side_effect_syntax(self):
  self.assertFalse(accepts('function customOmitClone(value) { value.x = 1; return value; }'))
if __name__=='__main__': unittest.main()
