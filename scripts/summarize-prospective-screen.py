#!/usr/bin/env python3
"""Sanitize machine screening results; model votes do not establish eligibility."""
import argparse,collections,json,pathlib,re
p=argparse.ArgumentParser();p.add_argument('--private',required=True);p.add_argument('--out',required=True);a=p.parse_args();base=pathlib.Path(a.private).resolve();all_rows=[];usage=collections.defaultdict(lambda:{'calls':0,'promptTokens':0,'completionTokens':0,'missingUsage':0,'failures':0})
for cohort in ('candidate-ai-review','extra-screening/candidate-ai-review'):
 root=base/cohort;packets=json.loads((root/'packets.json').read_text())
 for i,item in enumerate(packets,1):
  allowed={x['id'] for x in item['source']};votes=[]
  for name in ('haiku','deepseek'):
   f=root/'responses'/f'{i:02d}-{name}.json'
   if not f.exists():votes.append({'model':name,'status':'MISSING'});continue
   raw=json.loads(f.read_text());v=raw.get('vote',{});u=raw.get('usage',{});total=usage[raw['model']];total['calls']+=1;total['failures']+=raw.get('status')!='ok'
   if isinstance(u.get('prompt_tokens'),int) and isinstance(u.get('completion_tokens'),int):total['promptTokens']+=u['prompt_tokens'];total['completionTokens']+=u['completion_tokens']
   else:total['missingUsage']+=1
   mentions=set(re.findall(r'comment-\d+',v.get('reason','')));invalid=sorted(mentions-allowed);unlisted=sorted(mentions-set(v.get('references',[])))
   votes.append({'model':raw['model'],'status':v.get('status','invalid'),'decision':v.get('decision'),'references':v.get('references',[]),'reasonMentionsUnknownIds':invalid,'reasonMentionsNotInReferences':unlisted})
  result='MISSING_OR_INVALID'
  if all(x['status']=='valid' and not x.get('reasonMentionsUnknownIds') for x in votes):
   result='AGREED_'+votes[0]['decision'].upper() if votes[0]['decision']==votes[1]['decision'] else 'DISAGREED'
  af=root/'adjudication'/f'{i:02d}.json';adj=None
  if af.exists():
   raw=json.loads(af.read_text());u=raw.get('usage',{});total=usage[raw['model']];total['calls']+=1;total['failures']+=raw.get('status')!='ok'
   if isinstance(u.get('prompt_tokens'),int) and isinstance(u.get('completion_tokens'),int):total['promptTokens']+=u['prompt_tokens'];total['completionTokens']+=u['completion_tokens']
   else:total['missingUsage']+=1
   v=raw.get('vote',{});mentions=set(re.findall(r'comment-\d+',v.get('reason','')));adj={'model':raw['model'],'status':v.get('status','invalid'),'decision':v.get('decision'),'references':v.get('references',[]),'reasonMentionsUnknownIds':sorted(mentions-allowed),'reasonMentionsNotInReferences':sorted(mentions-set(v.get('references',[])))}
  all_rows.append({'cohort':cohort,'issue':item['url'],'currentState':item['currentState'],'historyClipped':item['clipped'],'pair':result,'votes':votes,'adjudication':adj,'eligibility':'NOT_FROZEN'})
counts=collections.Counter(r['pair'] for r in all_rows);unlisted=sum(bool(v.get('reasonMentionsNotInReferences')) for r in all_rows for v in r['votes']+([r['adjudication']] if r['adjudication'] else []));unknown=sum(bool(v.get('reasonMentionsUnknownIds')) for r in all_rows for v in r['votes']+([r['adjudication']] if r['adjudication'] else []));d={'kind':'ai-issue-screening-not-randomized-trial','rows':all_rows,'counts':dict(counts),'modelUsage':dict(usage),'clippedHistories':sum(r['historyClipped'] for r in all_rows),'reasonMentionsOutsideReferenceList':unlisted,'reasonMentionsUnknownIds':unknown,'warning':'Valid JSON and existing IDs do not verify that a claim is supported. A candidate vote does not freeze eligibility. Adjudication was added after initial screening began; all votes and missing outputs remain visible.'};pathlib.Path(a.out).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'issues':len(all_rows),'counts':d['counts'],'usage':d['modelUsage'],'clipped':d['clippedHistories'],'unlisted':unlisted,'unknownIds':unknown}))
