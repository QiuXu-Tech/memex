#!/usr/bin/env python3
"""Post-hoc reevaluation of saved canary proposals; no model requests."""
import argparse,json,os,pathlib,shutil,subprocess
from production_prospective_guard import accepts
p=argparse.ArgumentParser();p.add_argument('--private',required=True);a=p.parse_args();P=pathlib.Path(a.private).resolve();Q=P/'qualification';out=P/'canary';dest=out/'posthoc-results.json'
if dest.exists():raise SystemExit('refusing to overwrite post-hoc results')
source=(P/'lodash/lodash.js').read_text();old='function customOmitClone(value) {\n      return isPlainObject(value) ? undefined : value;\n    }';assert source.count(old)==1
rows=[]
for arm in ('recent','keyword','memex'):
 obj=json.loads((out/(arm+'.json')).read_text());row={'arm':arm,'originalCandidateStatus':obj['candidateStatus'],'originalTestStatus':obj['testStatus'],'posthocCandidateStatus':'INVALID','posthocTestStatus':'NOT_RUN'}
 try:
  candidate=json.loads(obj['content'])['replacement']
  if not accepts(candidate):raise ValueError('outside restricted expression grammar')
  root=Q/('posthoc-'+arm);root.mkdir();shutil.copy2(P/'lodash/lodash.js',root/'lodash.js');shutil.copytree(P/'lodash/fp',root/'fp');(root/'lodash.js').write_text(source.replace(old,candidate));row['posthocCandidateStatus']='VALID'
  proc=subprocess.run(['sandbox-exec','-f',str(P/'isolation.sb'),'/opt/homebrew/bin/node',str(Q/'lodash-5610-canary-test.js'),str(root)],cwd=P/'lodash',env={'PATH':'/usr/bin:/bin','HOME':str(Q),'LANG':'C'},capture_output=True,text=True,timeout=15);row['posthocTestStatus']='PASS' if proc.returncode==0 else 'FAIL';row['testExit']=proc.returncode
  log=out/('posthoc-'+arm+'-test.log');log.write_text((proc.stdout+proc.stderr)[:10000]);log.chmod(0o600)
 except Exception as exc:row['errorType']=type(exc).__name__;row['error']=str(exc)[:200]
 rows.append(row)
dest.write_text(json.dumps({'posthoc':True,'reason':'The registered filter incorrectly rejected the JavaScript function keyword in all three candidates. This is a uniform re-evaluation of unchanged responses, not a rerun.','rows':rows},indent=2)+'\n');dest.chmod(0o600);print(json.dumps(rows))
