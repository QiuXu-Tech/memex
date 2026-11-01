#!/usr/bin/env python3
"""Post-hoc revalidate reviews that cited a visible top-level packet limitation."""
import datetime,hashlib,importlib.util,json,pathlib,subprocess,sys
import prospective_gateway_review as gateway
ROOT=pathlib.Path(__file__).resolve().parent.parent
BASE=pathlib.Path('/Users/mk-q/.local/share/memex-forward-20261102/cohort30-triage')
OUT=BASE/'reviews'/'posthoc-limits';REVIEW=ROOT/'scripts/prospective-review-triage-20261102.py'
s=importlib.util.spec_from_file_location('original_review',REVIEW);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def load(p):return json.loads(p.read_text())
def save(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
def response_for(folder,model):
 terminal=[x for x in m_events(folder/'gateway.jsonl') if x.get('model')==model and x.get('status')!='started']
 return terminal[-1] if terminal else None
def m_events(p):
 if not p.exists():return []
 return [json.loads(x) for x in p.read_text().splitlines()]
def candidate(folder,model):
 f=folder/f'{model}.json';original=load(f) if f.exists() else None
 if not original or original.get('rating') is not None or original.get('error')!='invalid references':return None
 event=response_for(folder,model);packet=load(folder/'packet.json')
 if not event or not isinstance(packet.get('limits'),str):return None
 evidence={**packet['evidence'],'limits':packet['limits']}
 try:rating=m.parse(event,evidence)
 except Exception:return None
 return {'model':model,'rating':rating,'originalReviewSha256':sha(f),'packetSha256':sha(folder/'packet.json'),
         'gatewayTraceSha256':sha(folder/'gateway.jsonl')}
def prepare():
 assert (BASE/'reviews'/'finished.json').exists();OUT.mkdir(exist_ok=False);items=[]
 for folder in sorted((BASE/'reviews').glob('[0-9][0-9]')):
  for model in m.REVIEWERS:
   corrected=candidate(folder,model)
   if corrected:items.append({'task':folder.name,'model':model,'originalReviewSha256':corrected['originalReviewSha256'],
                              'packetSha256':corrected['packetSha256'],'gatewayTraceSha256':corrected['gatewayTraceSha256']})
 reg={'registeredAt':now(),'kind':'post-hoc-review-reference-revalidation','reason':'The original parser rejected references to limits even though the exact limits text was visible at the top level of the frozen packet.',
      'originalPlanSha256':sha(BASE/'reviews'/'plan.json'),'runnerSha256':sha(pathlib.Path(__file__)),
      'reviewParserSha256':sha(REVIEW),'gatewayHelperSha256':sha(ROOT/'scripts/prospective_gateway_review.py'),'items':items,
      'method':'Revalidate existing raw responses without new reviewer calls, allowing only the exact visible packet limits field as an additional evidence ID. Preserve original statuses. If two valid reviews disagree, request a separate low-effort Gemini adjudication.',
      'adjudicator':'gemini-3.8-flash','adjudicationMaxOutputTokens':3000,'reasoningEffort':'low','temperature':1,
      'limits':['This correction is post hoc and is reported separately from the frozen primary analysis.','Responses invalid for any other reason remain invalid.']}
 save(OUT/'registration.json',reg);print(json.dumps({'eligibleReviewResponses':len(items),'registrationSha256':sha(OUT/'registration.json')}),flush=True)
def run():
 reg=load(OUT/'registration.json');assert reg['runnerSha256']==sha(pathlib.Path(__file__)) and reg['reviewParserSha256']==sha(REVIEW) and reg['gatewayHelperSha256']==sha(ROOT/'scripts/prospective_gateway_review.py')
 key=subprocess.run(['ruby','-ryaml','-e','print YAML.load_file(File.expand_path("~/.dsh/.credentials.yaml")).dig("refs","APIMASTER_API_KEY")'],capture_output=True,text=True,check=True).stdout;assert key
 save(OUT/'started.json',{'at':now()});bytask={}
 for item in reg['items']:
  folder=BASE/'reviews'/item['task'];new=candidate(folder,item['model'])
  assert new and all(new[k]==item[k] for k in ('originalReviewSha256','packetSha256','gatewayTraceSha256'))
  bytask.setdefault(item['task'],{})[item['model']]={'model':item['model'],'status':'POSTHOC_REVALIDATED','rating':new['rating'],'error':None}
 for task,corrected in sorted(bytask.items()):
  folder=BASE/'reviews'/task;packet=load(folder/'packet.json');evidence={**packet['evidence'],'limits':packet['limits']}
  reviews=[corrected.get(model) or load(folder/f'{model}.json') for model in m.REVIEWERS]
  adjud={'status':'NOT_RUN','reason':'At least one review is still invalid.'}
  if all(x.get('rating') for x in reviews):
   def keyed(row):return {z['id']:(z['score'],tuple(sorted(z['unsupportedClaims']))) for z in row['rating']['candidates']}
   if keyed(reviews[0])==keyed(reviews[1]):adjud={'status':'NOT_RUN','reason':'No numeric or unsupported-claim disagreement.'}
   else:
    ev=gateway.call(key,reg['adjudicator'],[{'role':'system','content':'Adjudicate anonymous engineering reviews using evidence.'},
      {'role':'user','content':m.ADJ+'\n\n'+json.dumps({'packet':packet,'reviews':reviews},ensure_ascii=False)}],reg['adjudicationMaxOutputTokens'],OUT/f'{task}-gateway.jsonl',task+':posthoc-limits',timeout=120)
    try:rating,error=m.parse(ev,evidence,True),None
    except Exception as e:rating,error=None,str(e)
    adjud={'model':reg['adjudicator'],'status':ev.get('status'),'rating':rating,'error':error}
  save(OUT/f'{task}-result.json',{'task':task,'correctedModels':list(corrected),'reviews':reviews,'adjudication':adjud})
  print(json.dumps({'task':task,'correctedModels':list(corrected),'adjudicationStatus':adjud.get('status'),'adjudicationValid':bool(adjud.get('rating'))}),flush=True)
 save(OUT/'finished.json',{'at':now()})
if __name__=='__main__':
 if sys.argv[1:]==['prepare']:prepare()
 elif sys.argv[1:]==['run']:run()
 else:raise SystemExit('prepare|run')
