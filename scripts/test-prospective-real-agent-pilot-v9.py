#!/usr/bin/env python3
import importlib.util,io,json,pathlib,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
p=pathlib.Path(__file__).with_name('prospective-real-agent-pilot-v9.py');spec=importlib.util.spec_from_file_location('pilot2',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Worker:
 def __init__(self,*args,**kwargs):self.stdin=io.StringIO();self.stdout=io.StringIO('{"ok":true,"result":{"matches":[]}}\n'*2);self.stderr=io.StringIO()
 def wait(self,timeout=None):return 0
 def kill(self):pass
class Tests(unittest.TestCase):
 def test_schedule_and_read_limit(self):
  a=m.schedule();self.assertEqual(len(a),8)
  for task in m.TASKS:self.assertEqual({x['arm'] for x in a if x['issue']==task},{'memex','keyword'})
  read=next(x for x in m.TOOLS if x['function']['name']=='repo_read');self.assertEqual(read['function']['parameters']['properties']['count']['maximum'],150)
 def test_forced_final_has_no_tools(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);issue='20307';manifest={'schedule':[{'issue':issue,'arm':'memex'}]}
   (root/'issues.json').write_text(json.dumps({issue:{'body':'issue'}}));(root/'contexts.json').write_text(json.dumps({issue:{'memex':'history'}}))
   calls=[]
   def fake_api(key,model,messages,limit,trace,label,tools=None):
    calls.append(tools)
    if tools is None:return {'status':'ok','finishReason':'stop','message':{'content':'Could not complete.'}}
    return {'status':'ok','finishReason':'tool_calls','message':{'content':None,'tool_calls':[{'id':str(len(calls)),'function':{'name':'repo_search','arguments':'{"query":"invert"}'}}]}}
   with patch.object(m,'integrity',return_value=manifest),patch.object(m,'verify_guest'),patch.object(m,'gateway_key',return_value='x'),patch.object(m,'make_workspace',return_value=SimpleNamespace(returncode=0)),patch.object(m.subprocess,'Popen',Worker),patch.object(m,'api',side_effect=fake_api),patch.object(m,'MAX_TURNS',2),patch.object(m,'diffs',return_value=''),patch.object(m,'run_check',return_value={'exitCode':1}):m.solve(root)
   result=json.loads((root/'runs/01/result.json').read_text());self.assertTrue(result['forcedFinal']);self.assertEqual(result['status'],'completed');self.assertEqual(result['modelCalls'],3);self.assertIsNone(calls[-1])
 def test_eslint_regression_dependencies_added_after_solving(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);issue='21361';manifest={'schedule':[{'issue':issue,'arm':'keyword'}]}
   (root/'issues.json').write_text(json.dumps({issue:{'body':'issue'}}));(root/'contexts.json').write_text(json.dumps({issue:{'keyword':'history'}}));calls=[]
   def fake_guest(args,**kwargs):calls.append(args);return SimpleNamespace(returncode=0)
   with patch.object(m,'integrity',return_value=manifest),patch.object(m,'verify_guest'),patch.object(m,'gateway_key',return_value='x'),patch.object(m,'make_workspace',return_value=SimpleNamespace(returncode=0)),patch.object(m.subprocess,'Popen',Worker),patch.object(m,'api',return_value={'status':'ok','finishReason':'stop','message':{'content':'done'}}),patch.object(m,'diffs',return_value=''),patch.object(m,'guest',side_effect=fake_guest),patch.object(m,'run_check',return_value={'exitCode':0}):m.solve(root)
   self.assertEqual(len(calls),1);self.assertIn('eslint-regression-deps',calls[0][2]);self.assertEqual(json.loads((root/'runs/01/result.json').read_text())['regressionControls']['exitCode'],0)
 def test_invalid_reference_stays_invalid(self):
  x={'correctness':2,'side_effects':1,'reason':'x','references':['invented']};self.assertFalse(m.check_rating(json.dumps(x),'stop')['valid'])
if __name__=='__main__':unittest.main()
