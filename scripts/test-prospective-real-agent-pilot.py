#!/usr/bin/env python3
import importlib.util, json, pathlib, tempfile, unittest
from unittest.mock import patch
p=pathlib.Path(__file__).with_name('prospective-real-agent-pilot.py');spec=importlib.util.spec_from_file_location('pilot',p);pilot=importlib.util.module_from_spec(spec);spec.loader.exec_module(pilot)

class PilotTests(unittest.TestCase):
 def test_schedule_is_paired_and_deterministic(self):
  a=pilot.schedule();self.assertEqual(a,pilot.schedule());self.assertEqual(len(a),6)
  for task in pilot.TASKS:self.assertEqual({x['arm'] for x in a if x['issue']==task},{'keyword','memex'})
 def test_review_format_and_invalid_missing_scores(self):
  v={'correctness':2,'side_effects':None,'reason':'partial checks','references':['issue','checks']}
  self.assertTrue(pilot.check_rating(json.dumps(v),'stop')['valid'])
  for text,finish in [('', 'stop'),(json.dumps(v),'length'),('{','stop')]:self.assertFalse(pilot.check_rating(text,finish)['valid'])
  for field,bad in [('correctness',True),('correctness',3),('side_effects',1.5),('references',['invented']),('references',[])]:
   u=dict(v);u[field]=bad;self.assertFalse(pilot.check_rating(json.dumps(u),'stop')['valid'])
 def test_gateway_missing_usage_is_recorded_and_stops_stage(self):
  class Response:
   status=200
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self):return json.dumps({'choices':[{'message':{'content':'done'},'finish_reason':'stop'}]}).encode()
  with tempfile.TemporaryDirectory() as td,patch.object(pilot.urllib.request,'urlopen',return_value=Response()):
   trace=pathlib.Path(td)/'calls.jsonl';event=pilot.api('test','example',[],10,trace,'test')
   self.assertEqual(event['status'],'missing_usage');lines=[json.loads(x) for x in trace.read_text().splitlines()];self.assertEqual([x['status'] for x in lines],['started','missing_usage']);self.assertNotIn('test-key',trace.read_text())
 def test_blind_mapping_excludes_empty_attempts(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td)
   for n,data,diff in [(1,{'status':'completed','final':'ok'},''),(2,{'status':'model_failure','final':''},''),(3,{'status':'turn_limit','final':''},'diff')]:
    d=root/'runs'/f'{n:02d}';d.mkdir(parents=True);(d/'result.json').write_text(json.dumps(data));(d/'candidate.diff').write_text(diff)
   m=pilot.make_blind_key(root,{'schedule':[{}, {}, {}]});self.assertEqual(set(m.values()),{1,3})

if __name__=='__main__':unittest.main()
