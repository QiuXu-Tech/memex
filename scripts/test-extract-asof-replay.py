#!/usr/bin/env python3
"""A JSONL parser must not split valid JSON strings on Unicode separators."""
import json,pathlib,subprocess,tempfile
with tempfile.TemporaryDirectory(prefix='asof-jsonl-') as d:
 root=pathlib.Path(d);events=[]
 for i in range(3):
  data={'kind':'fact','title':f'topic {i}','body':'alpha\u2028beta\u0085gamma'}
  events.append({'type':'tool/call','seq':i*2+1,'data':{'name':'memory_write','callId':f'call-{i}','arguments':json.dumps(data,ensure_ascii=False)}})
  events.append({'type':'tool/result','seq':i*2+2,'data':{'message':{'toolCallId':f'call-{i}','isError':False}}})
 events.append({'type':'user/message','seq':8,'data':{'content':[{'type':'text','text':'What did we decide about this topic?'}]}})
 source=root/'session.jsonl';source.write_text(''.join(json.dumps(e,ensure_ascii=False)+'\n' for e in events));compressed=root/'session.jsonl.zstd';subprocess.run(['zstd','-q',str(source),'-o',str(compressed)],check=True)
 out=root/'episodes.json';subprocess.run(['python3','scripts/extract-asof-replay.py','--session',str(compressed),'--out',str(out)],check=True,capture_output=True,text=True)
 result=json.loads(out.read_text());assert result['malformedLinesSkipped']==0, result['malformedLinesSkipped'];assert len(result['episodes'])==1;assert len(result['episodes'][0]['pages'])==3;assert '\u2028' in result['episodes'][0]['pages'][0]['body']
print('as-of JSONL Unicode separator regression passed')
