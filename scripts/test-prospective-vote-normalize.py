import json,unittest
from prospective_vote_normalize import normalize
class TestNormalize(unittest.TestCase):
 def test_normalizes_only_explicit_existing_comment_ids(self):
  x=json.dumps({'decision':'candidate','references':['issue'],'reason':'See comment-1 for details.'})
  a=normalize(x,{'issue','comment-1'},'stop');self.assertEqual(a['status'],'normalized_from_explicit_reason_ids');self.assertEqual(a['normalizedReferences'],['comment-1'])
  self.assertEqual(normalize(x,{'issue'},'stop')['status'],'invalid')
 def test_does_not_repair_fabricated_or_truncated_output(self):
  x=json.dumps({'decision':'candidate','references':['unknown'],'reason':'Specific issue text.'})
  self.assertEqual(normalize(x,{'issue'},'stop')['status'],'invalid')
  self.assertEqual(normalize(x,{'issue'},'length')['status'],'invalid')
 def test_keeps_already_valid(self):
  x=json.dumps({'decision':'uncertain','references':['issue'],'reason':'Evidence is incomplete.'})
  self.assertEqual(normalize(x,{'issue'},'stop')['status'],'valid')
if __name__=='__main__':unittest.main()
