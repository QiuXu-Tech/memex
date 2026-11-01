#!/usr/bin/env python3
"""Separately registered rescue of missing supplemental reviews and adjudications."""
import datetime,hashlib,importlib.util,json,pathlib,subprocess,sys
import prospective_gateway_review as gateway
ROOT=pathlib.Path(__file__).resolve().parent.parent
BASE=pathlib.Path('/Users/mk-q/.local/share/memex-forward-20261102/supplement-triage/reviews');OUT=BASE/'posthoc-rescue'
REVIEW=ROOT/'scripts/prospective-review-triage-recovery-20261102.py'
spec=importlib.util.spec_from_file_location('supplement_review',REVIEW);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
PUBLIC=ROOT/'docs/assets/benchmarks/production-autonomy-20261102/supplement-triage-packet-commitments.json'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def key_commitment(folder,salts):
 return hashlib.sha256(b'memex-blind-key-v1\0'+bytes.fromhex(salts[folder.name])+(folder/'key.json').read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def save(p,data):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
def needs_rescue(folder):
 reviews=[load(folder/f'{model}.json') for model in m.REVIEWERS]
 adj=load(folder/'adjudication.json')
 return any(not r.get('rating') for r in reviews) or (adj.get('status')!='NOT_RUN' and not adj.get('rating'))
def prepare():
 assert (BASE/'finished.json').exists() and not OUT.exists()
 commits={x['task']:x for x in load(PUBLIC)['packets']};salts=load(BASE/'packet-key-salts.json');checks=[]
 for folder in sorted(BASE.glob('[0-9][0-9]')):
  if (folder/'review-status.json').exists():continue
  if not needs_rescue(folder):continue
  assert key_commitment(folder,salts)==commits[folder.name]['saltedKeyCommitmentSha256']
  reviews=[load(folder/f'{model}.json') for model in m.REVIEWERS]
  assert sum(not x.get('rating') for x in reviews)<=1, 'two missing reviewers require a separate recovery plan'
  checks.append({'task':folder.name,'packetSha256':sha(folder/'packet.json'),
   'saltedKeyCommitmentSha256':commits[folder.name]['saltedKeyCommitmentSha256'],
   'reviewSha256':{model:sha(folder/f'{model}.json') for model in m.REVIEWERS},
   'adjudicationSha256':sha(folder/'adjudication.json')})
 assert checks, 'no eligible invalid reviews or adjudications'
 reg={'registeredAt':now(),'kind':'supplemental-post-hoc-blind-review-rescue','tasks':checks,
  'runnerSha256':sha(pathlib.Path(__file__)),'parserSha256':sha(REVIEW),'gatewayHelperSha256':sha(ROOT/'scripts/prospective_gateway_review.py'),
  'reviewPlanSha256':sha(BASE/'plan.json'),'fallbackReviewer':'gpt-6.1-terra','adjudicator':m.ADJUDICATOR,
  'reviewPrompt':m.RUBRIC,'adjudicationPrompt':m.ADJ,'reviewMaxOutputTokens':1200,'adjudicationMaxOutputTokens':3000,
  'protocol':'Keep the original files. Replace at most one absent/invalid reviewer per pair with a fresh blinded Terra review; perform a fresh adjudication when the resulting reviews disagree. A malformed adjudication is retried separately. Unresolved results remain missing.',
  'limits':['Post-hoc sensitivity analysis, not the primary review.','Timed-out calls may have incurred unknown fees.','Gateway model identity and independence are not independently verified.']}
 save(OUT/'registration.json',reg);print(json.dumps({'tasks':[x['task'] for x in checks],'registrationSha256':sha(OUT/'registration.json')}),flush=True)
def run():
 reg=load(OUT/'registration.json')
 assert reg['runnerSha256']==sha(pathlib.Path(__file__)) and reg['parserSha256']==sha(REVIEW) and reg['gatewayHelperSha256']==sha(ROOT/'scripts/prospective_gateway_review.py')
 key=subprocess.run(['ruby','-ryaml','-e','print YAML.load_file(File.expand_path("~/.dsh/.credentials.yaml")).dig("refs","APIMASTER_API_KEY")'],capture_output=True,text=True,check=True).stdout;assert key
 salts=load(BASE/'packet-key-salts.json')
 for task in reg['tasks']:
  folder=BASE/task['task'];assert sha(folder/'packet.json')==task['packetSha256'] and sha(folder/'adjudication.json')==task['adjudicationSha256']
  assert key_commitment(folder,salts)==task['saltedKeyCommitmentSha256']
  assert all(sha(folder/f'{model}.json')==task['reviewSha256'][model] for model in m.REVIEWERS)
 save(OUT/'started.json',{'at':now()})
 for task in reg['tasks']:
  tid=task['task'];folder=BASE/tid;packet=load(folder/'packet.json');reviews=[];corrected=[]
  for model in m.REVIEWERS:
   row=load(folder/f'{model}.json')
   if not row.get('rating'):
    ev=gateway.call(key,reg['fallbackReviewer'],[{'role':'system','content':'Review anonymous engineering triage from the evidence only.'},
      {'role':'user','content':reg['reviewPrompt']+'\n\n'+json.dumps(packet,ensure_ascii=False)}],reg['reviewMaxOutputTokens'],OUT/f'{tid}-gateway.jsonl',tid+':fallback',timeout=120)
    try:rating,error=m.parse(ev,packet['evidence']),None
    except Exception as exc:rating,error=None,str(exc)
    row={'model':reg['fallbackReviewer'],'status':ev.get('status'),'rating':rating,'error':error};corrected.append(reg['fallbackReviewer'])
   reviews.append(row)
  adjud={'status':'NOT_RUN','reason':'At least one review is invalid.'}
  if all(x.get('rating') for x in reviews):
   def keyed(r):return {x['id']:(x['score'],tuple(sorted(x['unsupportedClaims']))) for x in r['rating']['candidates']}
   if keyed(reviews[0])==keyed(reviews[1]):adjud={'status':'NOT_RUN','reason':'No numeric or unsupported-claim disagreement.'}
   else:
    ev=gateway.call(key,reg['adjudicator'],[{'role':'system','content':'Adjudicate anonymous engineering reviews using evidence.'},
      {'role':'user','content':reg['adjudicationPrompt']+'\n\n'+json.dumps({'packet':packet,'reviews':reviews},ensure_ascii=False)}],reg['adjudicationMaxOutputTokens'],OUT/f'{tid}-gateway.jsonl',tid+':adjudication',timeout=120)
    try:rating,error=m.parse(ev,packet['evidence'],True),None
    except Exception as exc:rating,error=None,str(exc)
    adjud={'model':reg['adjudicator'],'status':ev.get('status'),'rating':rating,'error':error}
  save(OUT/f'{tid}-result.json',{'task':tid,'correctedModels':corrected,'reviews':reviews,'adjudication':adjud})
  print(json.dumps({'task':tid,'reviewsValid':all(x.get('rating') is not None for x in reviews),'adjudicationStatus':adjud.get('status'),'adjudicationValid':bool(adjud.get('rating'))}),flush=True)
 save(OUT/'finished.json',{'at':now()})
if __name__=='__main__':
 if sys.argv[1:]==['prepare']:prepare()
 elif sys.argv[1:]==['run']:run()
 else:raise SystemExit('prepare|run')
