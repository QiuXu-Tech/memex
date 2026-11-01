"""Post-hoc independent blind review after an original reviewer returned no output."""
import hashlib, importlib.util, json, pathlib, subprocess, sys
BASE = pathlib.Path(__file__).resolve().parent / 'claude-chalk-retry'
MODULE = BASE.parent / 'review-chalk-retry.py'
spec = importlib.util.spec_from_file_location('prior_review', MODULE)
prior = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prior)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path): return json.loads(path.read_text())
def save(path, data):
    with path.open('x') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
def prepare():
    folder = BASE / 'reviews'
    original = load(folder / 'registration.json')
    original_claude = load(folder / 'chalk-claude-haiku-4-5.json')
    assert original_claude['ratings'] is None
    packet = folder / 'chalk-packet.json'
    mapping = folder / 'chalk-key.json'
    assert sha(packet) == original['packets'][0]['packetSha256']
    assert sha(mapping) == original['packets'][0]['keySha256']
    reg = {'registeredAt': prior.now(), 'reason': 'The original Claude reviewer returned empty invalid output; retain it and add one independent blinded opinion.',
           'originalReviewRegistrationSha256': sha(folder / 'registration.json'), 'originalClaudeResultSha256': sha(folder / 'chalk-claude-haiku-4-5.json'),
           'packetSha256': sha(packet), 'keySha256': sha(mapping), 'runnerSha256': sha(pathlib.Path(__file__)),
           'reviewer': 'qwen3.8-flash', 'adjudicator': 'deepseek-flash', 'reviewOutputLimit': 2048, 'adjudicationOutputLimit': 1000,
           'reviewPrompt': prior.RUBRIC, 'adjudicationPrompt': prior.ADJ,
           'method': 'The supplemental reviewer receives only the original anonymized packet, not other reviews. A new adjudication receives both valid independent reviews if available. This is post-hoc recovery, not an original prespecified reviewer.',
           'retries': 'Only explicit bounded 503 responses are retried by prospective_gateway; ambiguous timeouts or invalid output are not silently retried.'}
    save(folder / 'supplement-registration.json', reg)
    print(json.dumps({'registrationSha256': sha(folder / 'supplement-registration.json')}))
def run():
    folder = BASE / 'reviews'; reg = load(folder / 'supplement-registration.json')
    packet = folder / 'chalk-packet.json'; mapping = folder / 'chalk-key.json'
    assert sha(pathlib.Path(__file__)) == reg['runnerSha256'] and sha(packet) == reg['packetSha256'] and sha(mapping) == reg['keySha256']
    key = subprocess.run(['ruby','-ryaml','-e','print YAML.load_file(File.expand_path("~/.dsh/.credentials.yaml")).dig("refs","APIMASTER_API_KEY")'], capture_output=True, text=True, check=True).stdout
    if not key: raise ValueError('missing configured gateway key')
    data = load(packet); gateway = folder / 'supplement-gateway.jsonl'
    event = prior.prospective_gateway.call(key, reg['reviewer'], [{'role':'system','content':'Score anonymous coding-task candidates from evidence.'},
        {'role':'user','content':prior.RUBRIC+'\n\n'+json.dumps(data,ensure_ascii=False)}], reg['reviewOutputLimit'], gateway, 'chalk:supplemental-review', timeout=90)
    try: ratings, error = prior.parse(event), None
    except Exception as exc: ratings, error = None, str(exc)
    review = {'model':reg['reviewer'],'status':event.get('status'),'ratings':ratings,'error':error}
    save(folder / 'chalk-supplemental-review.json', review)
    print(json.dumps({'stage':'supplemental-review','status':event.get('status'),'valid':ratings is not None}), flush=True)
    original = load(folder / 'chalk-gpt-6.1-sol.json')
    if ratings is None or original.get('ratings') is None: return
    event = prior.prospective_gateway.call(key, reg['adjudicator'], [{'role':'system','content':'Resolve anonymous reviews from evidence.'},
        {'role':'user','content':prior.ADJ+'\n\n'+json.dumps({'packet':data,'reviews':[original,review]},ensure_ascii=False)}], reg['adjudicationOutputLimit'], gateway, 'chalk:supplemental-adjudication', timeout=90)
    try: ratings, error = prior.parse(event, True), None
    except Exception as exc: ratings, error = None, str(exc)
    save(folder / 'chalk-supplemental-adjudication.json', {'model':reg['adjudicator'],'status':event.get('status'),'ratings':ratings,'error':error})
    print(json.dumps({'stage':'supplemental-adjudication','status':event.get('status'),'valid':ratings is not None}), flush=True)
if __name__ == '__main__':
    if sys.argv[1:] == ['prepare']: prepare()
    elif sys.argv[1:] == ['run']: run()
    else: raise SystemExit('usage: review-chalk-retry-supplement.py prepare|run')
