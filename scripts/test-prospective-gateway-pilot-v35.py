#!/usr/bin/env python3
import importlib.util,json,pathlib,tempfile,unittest
from unittest.mock import patch
p=pathlib.Path(__file__).with_name('prospective-gateway-pilot-v35.py');s=importlib.util.spec_from_file_location('pilot_v35',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_unstarted_evidence_rejects_started_or_partially_attempted_slot(self):
  with tempfile.TemporaryDirectory() as td:
   base=pathlib.Path(td);root=base/'20261031-independent-batch32';root.mkdir()
   (root/'manifest.json').write_text(json.dumps({'schedule':[{'issue':'2252','arm':'keyword'},{'issue':'2252','arm':'memex'}]}))
   trace=root/'solver-calls.jsonl';trace.write_text(json.dumps({'label':'03:0#attempt-1','status':'started'})+'\n')
   for n in (1,2):
    out=root/'runs'/f'{n:02d}';out.mkdir(parents=True);(out/'result.json').write_text(json.dumps({'status':'NOT_RUN_AFTER_STOP'}))
   with patch.object(m,'PRIVATE',base):
    self.assertEqual(m.unstarted_evidence()['slots'],[1,2])
    trace.write_text(trace.read_text()+json.dumps({'label':'01:0#attempt-1','status':'started'})+'\n')
    with self.assertRaises(SystemExit):m.unstarted_evidence()
    trace.write_text('');(root/'runs/02/result.json').write_text(json.dumps({'status':'model_failure'}))
    with self.assertRaises(SystemExit):m.unstarted_evidence()
if __name__=='__main__':unittest.main()
