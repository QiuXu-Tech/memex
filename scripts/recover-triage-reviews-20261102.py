#!/usr/bin/env python3
"""Separate post-hoc rescue of one timed-out reviewer and one malformed adjudication."""
import datetime,hashlib,importlib.util,json,pathlib,subprocess,sys
import prospective_gateway_review as gateway
ROOT=pathlib.Path(__file__).resolve().parent.parent;BASE=pathlib.Path('/Users/mk-q/.local/share/memex-forward-20261102/cohort30-triage/reviews');OUT=BASE/'posthoc-rescue'
REVIEW=ROOT/'scripts/prospective-review-triage-20261102.py';spec=importlib.util.spec_from_file_location('original_review',REVIEW);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ADJ=('Independently reassess both anonymous triage answers and the AI reviews against the frozen criterion and evidence. '
 'Resolve material score or unsupported-claim disagreements. Return JSON only: {"materialDisagreement":true,"candidates":['
 '{"id":"C01","score":1,"reason":"...","references":["final:C01"],"unsupportedClaims":[]},'
 '{"id":"C02","score":1,"reason":"...","references":["final:C02"],"unsupportedClaims":[]}]}. '
 'Scores are 0, 1, 2 or null. Use only evidence IDs in the packet; each candidate must cite its own final, source or session evidence.')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def load(p):return json.loads(p.read_text())
def save(p,o):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(o,f,ensure_ascii=False,indent=2);f.write('\n')
def prepare():
 assert (BASE/'finished.json').exists();OUT.mkdir(exist_ok=False)
 checks=[]
 for task in ('17','29'):
  folder=BASE/task;checks.append({'task':task,'packetSha256':sha(folder/'packet.json'),'keySha256':sha(folder/'key.json'),
   'gptReviewSha256':sha(folder/'gpt-6.1-sol.json'),'deepseekReviewSha256':sha(folder/'deepseek-flash.json'),
   'adjudicationSha256':sha(folder/'adjudication.json')})
 assert load(BASE/'17/gpt-6.1-sol.json')['rating'] is None and load(BASE/'29/adjudication.json')['rating'] is None
 reg={'registeredAt':now(),'kind':'post-hoc-review-and-adjudication-recovery','runnerSha256':sha(pathlib.Path(__file__)),
  'originalReviewPlanSha256':sha(BASE/'plan.json'),'parserSha256':sha(REVIEW),'gatewayHelperSha256':sha(ROOT/'scripts/prospective_gateway_review.py'),
  'tasks':checks,'task17':'Do not replay the ambiguous timed-out GPT Sol call; request a fresh blinded opinion from GPT-6.1 Terra alongside the existing DeepSeek review.',
  'task29':'Retain the malformed Gemini adjudication and request a new adjudication with the explicit candidate schema.',
  'fallbackReviewer':'gpt-6.1-terra','adjudicator':'gemini-3.8-flash','reviewMaxOutputTokens':1200,'adjudicationMaxOutputTokens':3000,
  'reviewPrompt':m.RUBRIC,'adjudicationPrompt':ADJ,'reasoningEffortForGemini':'low','temperatureForGemini':1,
  'limits':['Post-hoc recovery is a sensitivity analysis, not the original primary review.','The timed-out request may have incurred an unknown charge.','Model identity and independence cannot be independently verified through the gateway.']}
 save(OUT/'registration.json',reg);print(json.dumps({'registrationSha256':sha(OUT/'registration.json')}),flush=True)
def run():
 reg=load(OUT/'registration.json');assert reg['runnerSha256']==sha(pathlib.Path(__file__)) and reg['parserSha256']==sha(REVIEW) and reg['gatewayHelperSha256']==sha(ROOT/'scripts/prospective_gateway_review.py')
 for t in reg['tasks']:
  folder=BASE/t['task']
  for key,file in [('packetSha256','packet.json'),('keySha256','key.json'),('gptReviewSha256','gpt-6.1-sol.json'),('deepseekReviewSha256','deepseek-flash.json'),('adjudicationSha256','adjudication.json')]:assert sha(folder/file)==t[key]
 key=subprocess.run(['ruby','-ryaml','-e','print YAML.load_file(File.expand_path("~/.dsh/.credentials.yaml")).dig("refs","APIMASTER_API_KEY")'],capture_output=True,text=True,check=True).stdout;assert key
 save(OUT/'started.json',{'at':now()})
 for task in ('17','29'):
  folder=BASE/task;packet=load(folder/'packet.json');evidence={**packet['evidence'],'limits':packet['limits']};corrected=[]
  if task=='17':
   ev=gateway.call(key,reg['fallbackReviewer'],[{'role':'system','content':'Review anonymous engineering triage from evidence only.'},
     {'role':'user','content':reg['reviewPrompt']+'\n\n'+json.dumps(packet,ensure_ascii=False)}],reg['reviewMaxOutputTokens'],OUT/f'{task}-gateway.jsonl',task+':fallback',timeout=120)
   try:rating,error=m.parse(ev,evidence),None
   except Exception as e:rating,error=None,str(e)
   replacement={'model':reg['fallbackReviewer'],'status':ev.get('status'),'rating':rating,'error':error};reviews=[replacement,load(folder/'deepseek-flash.json')];corrected=[reg['fallbackReviewer']]
  else:reviews=[load(folder/'gpt-6.1-sol.json'),load(folder/'deepseek-flash.json')]
  adjud={'status':'NOT_RUN','reason':'At least one review is still invalid.'}
  if all(x.get('rating') for x in reviews):
   def keyed(row):return {z['id']:(z['score'],tuple(sorted(z['unsupportedClaims']))) for z in row['rating']['candidates']}
   if keyed(reviews[0])==keyed(reviews[1]):adjud={'status':'NOT_RUN','reason':'No numeric or unsupported-claim disagreement.'}
   else:
    ev=gateway.call(key,reg['adjudicator'],[{'role':'system','content':'Adjudicate anonymous engineering reviews using evidence.'},
      {'role':'user','content':ADJ+'\n\n'+json.dumps({'packet':packet,'reviews':reviews},ensure_ascii=False)}],reg['adjudicationMaxOutputTokens'],OUT/f'{task}-gateway.jsonl',task+':adjudication',timeout=120)
    try:rating,error=m.parse(ev,evidence,True),None
    except Exception as e:rating,error=None,str(e)
    adjud={'model':reg['adjudicator'],'status':ev.get('status'),'rating':rating,'error':error}
  save(OUT/f'{task}-result.json',{'task':task,'correctedModels':corrected,'reviews':reviews,'adjudication':adjud})
  print(json.dumps({'task':task,'reviewsValid':all(x.get('rating') is not None for x in reviews),'adjudicationStatus':adjud.get('status'),'adjudicationValid':bool(adjud.get('rating'))}),flush=True)
 save(OUT/'finished.json',{'at':now()})
if __name__=='__main__':
 if sys.argv[1:]==['prepare']:prepare()
 elif sys.argv[1:]==['run']:run()
 else:raise SystemExit('prepare|run')
