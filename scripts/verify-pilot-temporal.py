#!/usr/bin/env python3
"""Check pilot sequence cutoffs and elapsed wall time without publishing conversation content."""
import argparse,datetime,hashlib,json,pathlib,subprocess
p=argparse.ArgumentParser();p.add_argument('--session',action='append',required=True);p.add_argument('--frozen',required=True);p.add_argument('--out',required=True);a=p.parse_args();target=pathlib.Path(a.out)
if target.exists():raise SystemExit('refusing overwrite')
data=json.loads((pathlib.Path(a.frozen)/'episodes.json').read_text());results=[]
for i,path in enumerate(a.session):
 path=pathlib.Path(path);project=f'project-{i+1}';source=next(x for x in data['sources'] if x['project']==project);assert hashlib.sha256(path.read_bytes()).hexdigest()==source['sha256'];tasks=[e for e in data['episodes'] if e['project']==project];proc=subprocess.Popen(['zstd','-dc',str(path)],stdout=subprocess.PIPE,text=True) if path.suffix=='.zstd' else None;stream=proc.stdout if proc else path.open();first=None;times={};bad=0
 for line_no,line in enumerate(stream,1):
  try:event=json.loads(line)
  except json.JSONDecodeError:bad+=1;continue
  timestamp=event.get('time')
  if not proc and event.get('timestamp'):
   try:timestamp=datetime.datetime.fromisoformat(event['timestamp'].replace('Z','+00:00')).timestamp()*1000
   except (TypeError,ValueError):timestamp=None
  seq=event.get('seq') if proc else line_no
  if isinstance(timestamp,(int,float)):
   if first is None:first=timestamp
   if any(seq==e['querySeq'] for e in tasks):times[seq]=timestamp
 if proc and proc.wait()!=0:raise SystemExit('decompression failed')
 if not proc:stream.close()
 assert hashlib.sha256(path.read_bytes()).hexdigest()==source['sha256']
 for e in tasks:
  results.append({'task':e['id'],'elapsedWallHoursFromFirstEvent':round((times[e['querySeq']]-first)/3600000,2),'earlierArchiveMessages':len(e['pages']),'allArchiveBeforeQuestion':all(p['availableAfter']<e['querySeq'] for p in e['fullReferencePages']),'summaryBeforeQuestion':e['summarySeq'] is None or e['summarySeq']<e['querySeq'],'tailBeforeQuestion':all(t['seq']<e['querySeq'] for t in e['tail'])})
 assert bad==source['malformedLinesSkipped']
assert all(x['allArchiveBeforeQuestion'] and x['summaryBeforeQuestion'] and x['tailBeforeQuestion'] for x in results)
target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps({'tasks':results,'note':'Elapsed wall time includes inactive periods; it is not active work time.'},indent=2)+'\n');print(json.dumps(results))
