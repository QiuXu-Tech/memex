import json,unittest
from prospective_candidate_review import validate_vote,build_packet
from prospective_candidate_review_v2 import validate_vote as validate_vote_v2
class ReviewTest(unittest.TestCase):
 def test_valid_and_invalid_evidence(self):
  self.assertEqual(validate_vote('{"decision":"candidate","references":["issue"],"reason":"specific behavior"}',{'issue'},'stop')['status'],'valid')
  for text in ('','{}','{"decision":"candidate","references":["fake"],"reason":"specific behavior"}'):
   self.assertEqual(validate_vote(text,{'issue'},'stop')['status'],'invalid')
  self.assertEqual(validate_vote('{"decision":"candidate","references":["issue"],"reason":"specific behavior"}',{'issue'},'length')['status'],'invalid')
 def test_reason_source_coverage(self):
  x=json.dumps({'decision':'candidate','references':['issue'],'reason':'see comment-1 for details'})
  self.assertEqual(validate_vote_v2(x,{'issue','comment-1'},'stop')['reason'],'reason_mentions_unlisted_source')
  x=json.dumps({'decision':'candidate','references':['issue','comment-1'],'reason':'see comment-1 for details'})
  self.assertEqual(validate_vote_v2(x,{'issue','comment-1'},'stop')['status'],'valid')
 def test_clipping_is_explicit(self):
  issue={'url':'u','title':'t','repo':'r','number':1,'created_at':'t','body':'b','comments':[{'body':'x'*2500,'created_at':'t'}]}
  current={'state':'OPEN','labels':{'nodes':[]},'comments':{'totalCount':1}}
  self.assertTrue(build_packet(issue,current)['clipped'])
if __name__=='__main__':unittest.main()
