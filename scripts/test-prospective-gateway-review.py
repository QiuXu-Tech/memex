#!/usr/bin/env python3
import json,pathlib,tempfile,unittest
import prospective_gateway_review as gateway
class Response:
 status=200
 def __enter__(self):return self
 def __exit__(self,*args):return False
 def read(self):return json.dumps({'id':'r1','model':'m','choices':[{'message':{'content':'ok'},'finish_reason':'stop'}],
                                   'usage':{'prompt_tokens':7,'completion_tokens':2}}).encode()
class ReviewOptions(unittest.TestCase):
 def test_gemini_low_effort_and_default_temperature_are_sent(self):
  with tempfile.TemporaryDirectory() as td:
   seen=[]
   def opener(req,timeout):seen.append(json.loads(req.data));return Response()
   result=gateway.call('not-a-real-key','gemini-3.8-flash',[{'role':'user','content':'test'}],2500,pathlib.Path(td)/'calls.jsonl','review',opener=opener)
   self.assertEqual(result['status'],'ok');self.assertEqual(seen[0]['reasoning_effort'],'low');self.assertEqual(seen[0]['temperature'],1)
 def test_deepseek_still_disables_thinking(self):
  with tempfile.TemporaryDirectory() as td:
   seen=[]
   def opener(req,timeout):seen.append(json.loads(req.data));return Response()
   gateway.call('not-a-real-key','deepseek-flash',[{'role':'user','content':'test'}],1200,pathlib.Path(td)/'calls.jsonl','review',opener=opener)
   self.assertEqual(seen[0]['thinking'],{'type':'disabled'})
if __name__=='__main__':unittest.main()
