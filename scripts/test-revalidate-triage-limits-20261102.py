#!/usr/bin/env python3
import importlib.util,json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).parent));p=pathlib.Path(__file__).with_name('revalidate-triage-limits-20261102.py');s=importlib.util.spec_from_file_location('limits_review',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Revalidation(unittest.TestCase):
 def test_only_visible_limits_reference_is_recovered(self):
  with tempfile.TemporaryDirectory() as td:
   f=pathlib.Path(td);packet={'evidence':{'final:C01':'a','final:C02':'b'},'limits':'Partial evidence.'};(f/'packet.json').write_text(json.dumps(packet))
   (f/'gpt-6.1-sol.json').write_text(json.dumps({'rating':None,'error':'invalid references'}))
   rows=[{'id':'C01','score':1,'reason':'reason','references':['final:C01','limits'],'unsupportedClaims':[]},
         {'id':'C02','score':2,'reason':'reason','references':['final:C02'],'unsupportedClaims':[]}]
   event={'model':'gpt-6.1-sol','status':'ok','finishReason':'stop','message':{'content':json.dumps({'candidates':rows})}}
   (f/'gateway.jsonl').write_text(json.dumps(event)+'\n');self.assertIsNotNone(m.candidate(f,'gpt-6.1-sol'))
   rows[0]['references'].append('invented');event['message']['content']=json.dumps({'candidates':rows});(f/'gateway.jsonl').write_text(json.dumps(event)+'\n')
   self.assertIsNone(m.candidate(f,'gpt-6.1-sol'))
if __name__=='__main__':unittest.main()
