#!/usr/bin/env python3
import importlib.util,json,pathlib,tempfile,unittest
from unittest.mock import patch
p=pathlib.Path(__file__).with_name('prospective-posthoc-rubric-review.py');s=importlib.util.spec_from_file_location('rer',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_prepare_only_patches_and_no_arm_in_packet(self):
  with tempfile.TemporaryDirectory() as td:
   base=pathlib.Path(td);root=base/'batch';root.mkdir();(root/'manifest.json').write_text(json.dumps({'solver':'x','reviewers':['a','b']}));(root/'issues.json').write_text(json.dumps({'1':{'body':'issue'}}))
   for n,text in [(1,'+change'),(2,'')]:
    d=root/'runs'/f'{n:02d}';d.mkdir(parents=True);(d/'candidate.diff').write_text(text);(d/'result.json').write_text(json.dumps({'slot':n,'issue':'1','arm':'memex','status':'completed','final':'done'}))
   out=base/'posthoc'
   with patch.object(m,'BATCHES',['batch']):m.prepare(base,out)
   manifest=m.integrity(out);self.assertEqual(len(manifest['candidates']),1);self.assertNotIn('memex',(out/'packets.json').read_text());self.assertIn('0 means',manifest['rubric'])
   (out/'packets.json').write_text('{}')
   with self.assertRaises(SystemExit):m.integrity(out)
if __name__=='__main__':unittest.main()
