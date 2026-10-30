#!/usr/bin/env python3
"""Check for the exact future question in pre-question model requests, without publishing text."""
import argparse,json,pathlib
p=argparse.ArgumentParser();p.add_argument('--frozen',required=True);p.add_argument('--trials',required=True);p.add_argument('--out',required=True);a=p.parse_args();out=pathlib.Path(a.out)
if out.exists():raise SystemExit('refusing overwrite')
episodes={e['id']:e for e in json.loads((pathlib.Path(a.frozen)/'episodes.json').read_text())['episodes']};runs=[json.loads(x.read_text()) for x in pathlib.Path(a.trials).glob('pilot-*.json')];rows=[]
for r in runs:
 if r['arm']!='pager_tools_write':continue
 q=episodes[r['episode']]['question'];events=[x for x in r['trace'] if x['kind']=='model' and x.get('stage')=='intake'];matches=sum(any(q in str(m.get('content') or '') for m in x.get('requestMessages',[])) for x in events);rows.append({'trial':r['trial'],'intakeRequestsChecked':len(events),'exactFutureQuestionMatches':matches})
assert len(rows)==4
result={'runs':rows,'intakeRequestsChecked':sum(x['intakeRequestsChecked'] for x in rows),'exactFutureQuestionMatches':sum(x['exactFutureQuestionMatches'] for x in rows),'note':'Exact-string check only; it does not establish absence of semantic leakage.'};out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
