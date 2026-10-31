#!/usr/bin/env python3
import importlib.util,json,pathlib,tempfile,unittest
p=pathlib.Path(__file__).with_name('prospective-unstarted-adjudication.py');s=importlib.util.spec_from_file_location('extra',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_only_unstarted_valid_disagreements_are_selected(self):
  with tempfile.TemporaryDirectory() as td:
   root=pathlib.Path(td);source=root/'source';source.mkdir();(source/'reviews').mkdir();(source/'adjudications').mkdir()
   (source/'manifest.json').write_text(json.dumps({'reviewers':['a','b']}));(source/'blind-key.json').write_text(json.dumps({'B01':1,'B02':2,'B03':3}));(source/'issues.json').write_text(json.dumps({'42':{'body':'issue'}}))
   for blind,slot in [('B01',1),('B02',2),('B03',3)]:
    run=source/'runs'/f'{slot:02d}';run.mkdir(parents=True);(run/'result.json').write_text(json.dumps({'issue':'42','arm':'keyword','status':'completed','final':'done'}))
    for i,model in enumerate(['a','b']):
     rating={'correctness':i,'side_effects':1,'reason':'r','references':['issue']};(source/'reviews'/f'{blind}-{model}.json').write_text(json.dumps({'parsed':{'valid':blind!='B02' or model!='b','rating':rating}}))
   (source/'adjudications/B03.json').write_text(json.dumps({'eventStatus':'error'}));out=root/'out';m.prepare(source,out)
   self.assertEqual(len(json.loads((out/'manifest.json').read_text())['candidates']),1);self.assertEqual(json.loads((out/'blind-key.json').read_text())['U01']['originalBlind'],'B01')
if __name__=='__main__':unittest.main()
