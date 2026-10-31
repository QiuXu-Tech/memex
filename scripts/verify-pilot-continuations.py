#!/usr/bin/env python3
"""Verify concatenated output preserves returned segments without exposing text."""
import argparse,collections,json,pathlib
p=argparse.ArgumentParser();p.add_argument('--trials',required=True);p.add_argument('--out',required=True);a=p.parse_args();out=pathlib.Path(a.out)
if out.exists():raise SystemExit('refusing to overwrite continuation verification')
runs=[json.loads(p.read_text()) for p in sorted(pathlib.Path(a.trials).glob('pilot-*.json'))];cases=[]
for r in runs:
 trace=r['trace'];indices=[i for i,x in enumerate(trace) if x.get('kind')=='answer_continuation']
 if not indices:continue
 first=indices[0];initial=None
 for e in reversed(trace[:first-1]):
  m=e.get('responseMessage') or {}
  if e.get('kind')=='model' and e.get('stage')=='answer' and not m.get('tool_calls') and m.get('content'):
   initial=m['content'];break
 if initial is None:raise SystemExit('continuation without an initial answer')
 pieces=[initial];overlap=False
 for i in indices:
  e=trace[i-1];assert e['kind']=='model' and e['stage']=='answer'
  m=e.get('responseMessage') or {};chunk=m.get('content') or ''
  if m.get('tool_calls') or not chunk.strip():continue
  before=''.join(pieces)
  if any(before.endswith(chunk[:n]) for n in range(32,min(len(before),len(chunk),500)+1)):overlap=True
  pieces.append(chunk)
 assert r.get('answer','')==''.join(pieces)
 cases.append({'trial':r['trial'],'calls':len(indices),'finalStatus':r['status'],'exactSuffixPrefixOverlapAtLeast32Chars':overlap,'segmentsPreserved':True})
result={'runs':len(runs),'runsWithContinuation':len(cases),'continuationCalls':sum(x['calls'] for x in cases),'statusCounts':dict(collections.Counter(x['finalStatus'] for x in cases)),'casesWithExactSuffixPrefixOverlapAtLeast32Chars':sum(x['exactSuffixPrefixOverlapAtLeast32Chars'] for x in cases),'allSegmentsPreserved':all(x['segmentsPreserved'] for x in cases),'note':'Only exact adjacent-character overlap is checked; semantic repetition, omission and contradictions remain possible. Raw answer segments stay private.'}
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
