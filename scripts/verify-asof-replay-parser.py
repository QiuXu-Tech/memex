#!/usr/bin/env python3
"""Compare a prior private replay extraction with a newline-correct extraction."""
import argparse,collections,hashlib,json,pathlib,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('--session',required=True);p.add_argument('--prior',required=True);p.add_argument('--out',required=True);a=p.parse_args();out=pathlib.Path(a.out)
if out.exists():raise SystemExit('refusing to overwrite evidence')
source=pathlib.Path(a.session);raw=subprocess.check_output(['zstd','-dc',str(source)]).decode();prior=json.loads(pathlib.Path(a.prior).read_text());source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
if prior['sourceSha256']!=source_hash:raise SystemExit('prior source mismatch')
invalid=[]
for line in raw.splitlines():
 try:json.loads(line)
 except json.JSONDecodeError:invalid.append(1)
valid_split=[];bad_lines=0
for line in raw.split('\n'):
 if not line:continue
 try:e=json.loads(line)
 except json.JSONDecodeError:bad_lines+=1;continue
 if len(line.splitlines())>1:valid_split.append(e)
with tempfile.TemporaryDirectory(prefix='asof-verify-') as d:
 new=pathlib.Path(d)/'corrected.json';subprocess.run(['python3','scripts/extract-asof-replay.py','--session',str(source),'--out',str(new)],check=True,capture_output=True,text=True);corrected=json.loads(new.read_text())
 result={'sourceSha256':source_hash,'legacyInvalidFragments':len(invalid),'validJsonLinesSplitByLegacyParser':len(valid_split),'splitLineTypes':dict(collections.Counter(x.get('type') for x in valid_split)),'actualInvalidJsonLines':bad_lines,'priorQuestionCount':len(prior['episodes']),'correctedQuestionCount':len(corrected['episodes']),'sameAllEpisodes':prior['episodes']==corrected['episodes'],'sameCandidateCount':prior['candidates']==corrected['candidates'],'sameSourceSha256':prior['sourceSha256']==corrected['sourceSha256']}
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
