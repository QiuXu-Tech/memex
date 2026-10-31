#!/usr/bin/env python3
import importlib.util,io,json,pathlib,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
p=pathlib.Path(__file__).with_name('prospective-real-agent-pilot-v13.py');spec=importlib.util.spec_from_file_location('pilot2',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Worker:
 def __init__(self,*args,**kwargs):self.stdin=io.StringIO();self.stdout=io.StringIO('{"ok":true,"result":{"matches":[]}}\n'*2);self.stderr=io.StringIO()
 def wait(self,timeout=None):return 0
 def kill(self):pass
class Tests(unittest.TestCase):
 def test_schedule_and_read_limit(self):
  a=m.schedule();self.assertEqual(len(a),6)
  for task in m.TASKS:self.assertEqual({x['arm'] for x in a if x['issue']==task},{'memex','keyword'})
  read=next(x for x in m.TOOLS if x['function']['name']=='repo_read');self.assertEqual(read['function']['parameters']['properties']['count']['maximum'],150)
 def test_forced_final_has_no_tools(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);issue='9955';manifest={'schedule':[{'issue':issue,'arm':'memex'}]}
   (root/'issues.json').write_text(json.dumps({issue:{'body':'issue'}}));(root/'contexts.json').write_text(json.dumps({issue:{'memex':'history'}}))
   calls=[]
   def fake_api(key,model,messages,limit,trace,label,tools=None):
    calls.append(tools)
    if tools is None:return {'status':'ok','finishReason':'stop','message':{'content':'Could not complete.'}}
    return {'status':'ok','finishReason':'tool_calls','message':{'content':None,'tool_calls':[{'id':str(len(calls)),'function':{'name':'repo_search','arguments':'{"query":"invert"}'}}]}}
   with patch.object(m,'integrity',return_value=manifest),patch.object(m,'verify_guest'),patch.object(m,'gateway_key',return_value='x'),patch.object(m,'make_workspace',return_value=SimpleNamespace(returncode=0)),patch.object(m.subprocess,'Popen',Worker),patch.object(m,'api',side_effect=fake_api),patch.object(m,'MAX_TURNS',2),patch.object(m,'diffs',return_value=''),patch.object(m,'run_check',return_value={'exitCode':1}):m.solve(root)
   result=json.loads((root/'runs/01/result.json').read_text());self.assertTrue(result['forcedFinal']);self.assertEqual(result['status'],'completed');self.assertEqual(result['modelCalls'],3);self.assertIsNone(calls[-1])
 def test_invalid_reference_stays_invalid(self):
  x={'correctness':2,'side_effects':1,'reason':'x','references':['invented']};self.assertFalse(m.check_rating(json.dumps(x),'stop')['valid'])
 def test_disagreement_uses_registered_third_model(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);(root/'reviews').mkdir();run=root/'runs/01';run.mkdir(parents=True)
   (root/'blind-key.json').write_text(json.dumps({'B01':1}));(root/'issues.json').write_text(json.dumps({'9955':{'body':'issue'}}));(run/'result.json').write_text(json.dumps({'issue':'9955','status':'completed','final':'done'}))
   for i,model in enumerate(m.REVIEWERS):
    value={'correctness':i,'side_effects':1,'reason':'partial','references':['issue']};(root/'reviews'/f'B01-{model}.json').write_text(json.dumps({'parsed':{'valid':True,'rating':value}}))
   value={'correctness':1,'side_effects':1,'reason':'partial','references':['issue']};event={'status':'ok','finishReason':'stop','message':{'content':json.dumps(value)}}
   with patch.object(m,'integrity',return_value={}),patch.object(m,'gateway_key',return_value='x'),patch.object(m,'api',return_value=event) as api:m.adjudicate(root)
   self.assertEqual(api.call_args.args[1],m.ADJUDICATOR);self.assertNotIn(m.ADJUDICATOR,(*m.REVIEWERS,m.SOLVER));self.assertTrue(json.loads((root/'adjudications/B01.json').read_text())['parsed']['valid'])
if __name__=='__main__':unittest.main()
