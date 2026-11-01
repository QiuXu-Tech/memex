#!/usr/bin/env python3
import hashlib,importlib.util,json,pathlib,tempfile,unittest
p=pathlib.Path(__file__).with_name('commit-supplement-blind-packets-20261102.py')
s=importlib.util.spec_from_file_location('commit_blind_packets',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class BlindCommitments(unittest.TestCase):
 def test_key_mapping_commitments_are_salted_and_bound_to_exact_bytes(self):
  key=b'{"C01":"baseline","C02":"memex"}\n';other=b'{"C01":"memex","C02":"baseline"}\n'
  salt=bytes(range(32));commit=m.commitment(salt,key)
  self.assertEqual(commit,m.commitment(salt,key))
  self.assertNotEqual(commit,m.commitment(bytes(reversed(salt)),key))
  self.assertNotEqual(commit,m.commitment(salt,other))
  self.assertNotEqual(commit,hashlib.sha256(key).hexdigest())
 def test_freeze_and_reveal_check_timing_and_packet_integrity(self):
  old={k:getattr(m,k) for k in ('BASE','PRIVATE','PUBLIC','REVEAL')}
  with tempfile.TemporaryDirectory() as td:
   try:
    root=pathlib.Path(td);m.BASE=root/'study';m.PRIVATE=m.BASE/'reviews'/'packet-key-salts.json'
    m.PUBLIC=root/'public'/'commitments.json';m.REVEAL=root/'public'/'unblinding.json'
    review=m.BASE/'reviews';review.mkdir(parents=True);packets=[]
    for i in range(30):
     task=f'{i:02}';folder=review/task;folder.mkdir();key=b'{"C01":"baseline","C02":"memex"}\n';packet=f'packet {i}'.encode()
     (folder/'key.json').write_bytes(key);(folder/'packet.json').write_bytes(packet)
     (folder/'packet-registration.json').write_text(json.dumps({'keySha256':m.sha(key),'packetSha256':m.sha(packet),'reviewPlanSha256':'plan'}))
     packets.append({'task':task})
    (review/'packets.json').write_text(json.dumps({'packets':packets}))
    m.freeze();public=json.loads(m.PUBLIC.read_text());self.assertNotIn('keySha256',public['packets'][0])
    with self.assertRaises(AssertionError):m.reveal()
    (review/'finished.json').write_text('{}');(review/'00'/'packet.json').write_text('tampered')
    with self.assertRaises(AssertionError):m.reveal()
    (review/'00'/'packet.json').write_text('packet 0');m.reveal()
    self.assertEqual(len(json.loads(m.REVEAL.read_text())['packets']),30)
   finally:
    for key,value in old.items():setattr(m,key,value)
if __name__=='__main__':unittest.main()
