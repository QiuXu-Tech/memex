#!/usr/bin/env python3
"""Create a private blinded audit packet and blank human ratings after model reviews."""
import argparse,csv,json,os,pathlib
p=argparse.ArgumentParser();p.add_argument('--frozen',required=True);p.add_argument('--trials',required=True);p.add_argument('--reviews',required=True);a=p.parse_args();f=pathlib.Path(a.frozen);trials=pathlib.Path(a.trials);reviews=pathlib.Path(a.reviews);episodes={x['id']:x for x in json.loads((f/'episodes.json').read_text())['episodes']};key=json.loads((reviews/'private-blind-key.json').read_text());out=reviews/'blind-review.md';sheet=reviews/'human-ratings.csv'
if out.exists() or sheet.exists():raise SystemExit('refusing to overwrite audit packet')
lines=['# Confidential blinded pilot review packet','','Real historical content and model outputs: keep private. No human labels have been supplied.','Source archive entries below contain full retained message text; missing historical events remain UNKNOWN.','Assess without opening private-blind-key.json. Failed or empty runs remain in the sheet and should not be silently excluded.','']
with sheet.open('x',newline='',encoding='utf-8') as h:
 os.chmod(sheet,0o600);w=csv.writer(h);w.writerow(['blind_id','task_id','run_status','correctness_0_2','coverage_0_2','evidence_support_0_2','reviewer','reviewed_at','notes'])
 for blind,ref in sorted(key.items()):
  r=json.loads((trials/(ref['trial']+'.json')).read_text());e=episodes[r['episode']];lines+=['## '+blind,'',f"Task: {e['id']}",f"Execution status: {r['status']}",'','### Question','',e['question'],'','### Earlier summary','',e['summary'] or '[No earlier summary]','','### Earlier chat tail','']
  for t in e['tail']:lines += [f"**{t['role']}** ({t['seq']}): {t['text']}",'']
  lines+=['### Earlier archive evidence','']
  for x in e['fullReferencePages']:lines += [f"**{x['id']}** {x['title']}",x['body'],'']
  lines+=['### Anonymous answer','',r.get('answer','') or '[No answer]',''];w.writerow([blind,e['id'],r['status'],'','','','','',''])
out.write_text('\n'.join(lines));out.chmod(0o600);print(json.dumps({'anonymousTrials':len(key),'ratingRows':len(key),'humanRatings':0}))
