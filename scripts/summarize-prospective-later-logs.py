#!/usr/bin/env python3
"""Summarize the original logged votes without inferring missing citation IDs."""
import argparse, collections, json, pathlib
p=argparse.ArgumentParser();p.add_argument('--private',required=True);p.add_argument('--out',required=True);a=p.parse_args();base=pathlib.Path(a.private);rows=[];usage=collections.defaultdict(lambda:{'calls':0,'promptTokens':0,'completionTokens':0,'missingUsage':0,'failures':0})
def events(path):
    return [json.loads(line) for line in path.read_text().splitlines() if json.loads(line).get('status') != 'started']
def count(event):
    u=usage[event['model']];u['calls']+=1;u['failures']+=event.get('status')!='ok';v=event.get('usage',{})
    if isinstance(v.get('prompt_tokens'),int) and isinstance(v.get('completion_tokens'),int):u['promptTokens']+=v['prompt_tokens'];u['completionTokens']+=v['completion_tokens']
    else:u['missingUsage']+=1
for cohort in ('third-screening','fourth-screening'):
    root=base/cohort/'candidate-ai-review';packets=json.loads((root/'packets.json').read_text());raw=events(root/'calls.jsonl');adjs=events(root/'adjudication-normalized'/'calls.jsonl')
    for i,packet in enumerate(packets,1):
        votes=[]
        for model in ('claude-haiku-4-5','deepseek-flash'):
            found=[x for x in raw if x['index']==i and x['model']==model]
            if len(found)!=1: votes.append({'model':model,'status':'MISSING_OR_DUPLICATE'});continue
            e=found[0];count(e);v=e.get('vote',{});votes.append({'model':model,'status':v.get('status','invalid'),'decision':v.get('decision'),'invalidReason':v.get('reason') if v.get('status')!='valid' else None})
        pair='MISSING_OR_INVALID'
        if all(v['status']=='valid' for v in votes):pair='AGREED_'+votes[0]['decision'].upper() if votes[0]['decision']==votes[1]['decision'] else 'DISAGREED'
        found=[x for x in adjs if x['index']==i];adj=None
        if len(found)>1:raise ValueError('duplicate adjudication')
        if found:
            e=found[0];count(e);v=e.get('vote',{});adj={'model':e['model'],'status':v.get('status','invalid'),'decision':v.get('decision'),'initialVoteNormalization':e.get('initialVoteNormalization')}
        rows.append({'cohort':cohort,'issue':packet['url'],'historyClipped':packet['clipped'],'pairFromLoggedRawVotes':pair,'votes':votes,'adjudication':adj,'eligibility':'NOT_FROZEN'})
out={'kind':'ai-screening-not-task-outcomes','rows':rows,'rawPairCounts':dict(collections.Counter(r['pairFromLoggedRawVotes'] for r in rows)),'adjudicationDecisions':dict(collections.Counter(r['adjudication']['decision'] or 'invalid' for r in rows if r['adjudication'])),'modelUsage':dict(usage),'clippedHistories':sum(r['historyClipped'] for r in rows),'warning':'Original raw votes are not modified; normalized adjudications are post hoc. Cite IDs and model opinions do not establish factual support or task eligibility.'}
pathlib.Path(a.out).write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='rows'}))
