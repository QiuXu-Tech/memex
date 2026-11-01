#!/usr/bin/env python3
"""Commit blinded packet keys with private salts; reveal only after reviews finish."""
import datetime,hashlib,json,os,pathlib,secrets,sys
ROOT=pathlib.Path(__file__).resolve().parent.parent
BASE=pathlib.Path('/Users/mk-q/.local/share/memex-forward-20261102/supplement-triage')
ASSETS=ROOT/'docs/assets/benchmarks/production-autonomy-20261102'
PRIVATE=BASE/'reviews'/'packet-key-salts.json'
PUBLIC=ASSETS/'supplement-triage-packet-commitments.json'
REVEAL=ASSETS/'supplement-triage-packet-unblinding.json'
os.umask(0o077)
def load(p):return json.loads(p.read_text())
def sha(b):return hashlib.sha256(b).hexdigest()
def commitment(salt,key):return sha(b'memex-blind-key-v1\0'+salt+key)
def save_new(p,value):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
def records():
 tasks=load(BASE/'reviews'/'packets.json')['packets']
 assert len(tasks)==30
 for row in tasks:
  folder=BASE/'reviews'/row['task'];reg=load(folder/'packet-registration.json');key=(folder/'key.json').read_bytes()
  assert sha(key)==reg['keySha256'] and sha((folder/'packet.json').read_bytes())==reg['packetSha256']
  yield row['task'],reg,key
def freeze():
 assert not PRIVATE.exists() and not PUBLIC.exists() and not (BASE/'reviews'/'started.json').exists()
 items=list(records());salts={task:secrets.token_bytes(32) for task,_,_ in items}
 save_new(PRIVATE,{task:salt.hex() for task,salt in salts.items()})
 save_new(PUBLIC,{'createdAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
   'method':'SHA256(UTF8("memex-blind-key-v1\\0") || 32-byte private salt || exact key.json bytes); salts and mappings are revealed after review finishes.',
   'packets':[{'task':task,'packetSha256':reg['packetSha256'],'reviewPlanSha256':reg['reviewPlanSha256'],
               'saltedKeyCommitmentSha256':commitment(salts[task],key)} for task,reg,key in items]})
 print(f'committed {len(items)} packets without exposing their two-way keys')
def reveal():
 assert (BASE/'reviews'/'finished.json').exists() and not REVEAL.exists()
 salts=load(PRIVATE);public={r['task']:r for r in load(PUBLIC)['packets']};out=[]
 for task,reg,key in records():
  salt=bytes.fromhex(salts[task]);assert public[task]['saltedKeyCommitmentSha256']==commitment(salt,key)
  assert public[task]['packetSha256']==reg['packetSha256']
  out.append({'task':task,'saltHex':salts[task],'key':json.loads(key),'keySha256':reg['keySha256']})
 save_new(REVEAL,{'revealedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'packets':out})
 print(f'verified and unblinded {len(out)} packet keys')
if __name__=='__main__':
 if len(sys.argv)!=2 or sys.argv[1] not in ('freeze','reveal'):raise SystemExit('usage: commit-supplement-blind-packets-20261102.py freeze|reveal')
 {'freeze':freeze,'reveal':reveal}[sys.argv[1]]()
