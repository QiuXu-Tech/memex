#!/usr/bin/env python3
import importlib.util,json,pathlib,tempfile,unittest
p=pathlib.Path(__file__).with_name('recover-supplement-reviews-20261102.py')
s=importlib.util.spec_from_file_location('supplement_rescue',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class RecoverySelection(unittest.TestCase):
 def test_missing_review_and_invalid_adjudication_are_selected(self):
  with tempfile.TemporaryDirectory() as td:
   f=pathlib.Path(td);valid={'status':'ok','rating':{'candidates':[{'score':None}]}}
   def write(name,value):(f/(name+'.json')).write_text(json.dumps(value))
   for model in m.m.REVIEWERS:write(model,valid)
   write('adjudication',{'status':'NOT_RUN'});self.assertFalse(m.needs_rescue(f))
   write(m.m.REVIEWERS[0],{'status':'error','rating':None});self.assertTrue(m.needs_rescue(f))
   write(m.m.REVIEWERS[0],valid);write('adjudication',{'status':'ok','rating':None});self.assertTrue(m.needs_rescue(f))
 def test_commitment_changes_if_key_mapping_changes(self):
  with tempfile.TemporaryDirectory() as td:
   f=pathlib.Path(td)/'01';f.mkdir();(f/'key.json').write_text('{"C01":"baseline"}')
   first=m.key_commitment(f,{'01':'11'*32});(f/'key.json').write_text('{"C01":"memex"}')
   self.assertNotEqual(first,m.key_commitment(f,{'01':'11'*32}))
if __name__=='__main__':unittest.main()
