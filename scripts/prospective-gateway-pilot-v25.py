#!/usr/bin/env python3
"""Three isolated validator.js and Chart.js issue pairs."""
import importlib.util
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pilot_v24', REPO / 'scripts/prospective-gateway-pilot-v24.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot
pilot.TASKS = {'2497': 'validator', '912': 'validator', '12191': 'chartjs'}
pilot.SEED = 2026103128
pilot.BASES = {'validator': '/opt/memex-pilot/workspaces/validator-base', 'chartjs': '/opt/memex-pilot/workspaces/chartjs-base'}
pilot.COMMITS = {'validator': '9ff342479591ca5a43cb30000195bcf55c1bbed9', 'chartjs': '71d44219e79e3ac41e6f9dc907022eebf574868d'}
pilot.ROOT = '/opt/memex-pilot/workspaces/gateway-recovery-v25'
NODE_SHA = '6bf69d0eda41a12030d5f28d958cd09ce323bc0c13f1ab4d8bb426933aa08812'
LOCK_SHA = 'd7a35e7d49830c15f2a4d0873e9eda706fb7dfacf009a3697fe51b59f07eba54'


def prepare(root, snapshot):
    if root.exists():
        raise SystemExit('output exists; refusing overwrite')
    source = json.loads(pathlib.Path(snapshot).read_text())['issues']
    if set(source) != {f'{project}-{number}' for number, project in pilot.TASKS.items()}:
        raise SystemExit('unexpected issue set')
    issues = {str(issue['number']): issue for issue in source.values()}
    owners = {'validator': 'validatorjs/validator.js', 'chartjs': 'chartjs/Chart.js'}
    for number, issue in issues.items():
        comments = issue['comments']
        if (issue['url'] != f"https://github.com/{owners[pilot.TASKS[number]]}/issues/{number}" or
                issue['state'] != 'OPEN' or comments['pageInfo']['hasNextPage'] or
                comments['totalCount'] != len(comments['nodes'])):
            raise SystemExit('issue is closed, mismatched, or comments are incomplete')
    root.mkdir(parents=True, mode=0o700)
    contexts = {number: pilot.store_context(issue, root / 'stores' / number) for number, issue in issues.items()}
    pilot.save(root / 'issues.json', issues)
    pilot.save(root / 'contexts.json', contexts)
    template = REPO / 'docs/assets/benchmarks/production-prospective-agent-batch24/manifest.json'
    manifest = json.loads(template.read_text())
    manifest.update({'kind': 'registered-three-validator-chartjs-issue-pairs', 'createdAt': pilot.NOW(),
                     'sourceCommit': pilot.COMMITS, 'tasks': pilot.TASKS,
                     'runtimeLockSha256': LOCK_SHA,
                     'runtime': {'nodeVersion': 'v24.18.0', 'nodeBinarySha256': NODE_SHA,
                                 'validator': 'Node module hooks load source ESM without npm packages.',
                                 'chartjs': 'A test-only TypeScript hook and generated dependency lock; lifecycle scripts disabled.'},
                     'issuesSha256': pilot.SHA((root / 'issues.json').read_bytes()),
                     'contextsSha256': pilot.SHA((root / 'contexts.json').read_bytes()), 'seed': pilot.SEED,
                     'schedule': pilot.schedule(),
                     'checks': {n: {name: pilot.SHA(path.read_bytes()) for name, path in pilot.check_paths(n, project).items()}
                                for n, project in pilot.TASKS.items()}})
    manifest['files'][str(pathlib.Path(__file__).relative_to(REPO))] = pilot.SHA(pathlib.Path(__file__).read_bytes())
    manifest['files'][str(template.relative_to(REPO))] = pilot.SHA(template.read_bytes())
    manifest['limitations'][0] = 'Three additional pairs selected after earlier batches; not a pre-registered 30–50-task independent cohort.'
    manifest['limitations'].append('Chart.js #12191 has no discussion records and is a no-history negative control; its check exercises a listener and mocked controller, not browser rendering.')
    manifest['limitations'].append('Validator #912 uses the candidate PR source option name, which differs from the PR prose; acceptance was selected after inspecting that reference.')
    pilot.save(root / 'manifest.json', manifest)
    print(json.dumps({'manifestSha256': pilot.SHA((root / 'manifest.json').read_bytes()), 'schedule': manifest['schedule']}))


def verify_guest(manifest):
    pairs = [(REPO / 'scripts/prospective-agent-worker-v3.py', '/opt/memex-pilot/prospective-agent-worker-v3.py'),
             (REPO / 'scripts/prospective-vm-sandbox.sh', '/opt/memex-pilot/prospective-vm-sandbox.sh')]
    for number, project in pilot.TASKS.items():
        paths = pilot.check_paths(number, project)
        pairs.extend([(paths['public'], f'{pilot.CHECKS}/{project}-{number}-public/verify.js'),
                      (paths['acceptance'], f'{pilot.CHECKS}/{project}-{number}-acceptance/verify.js'),
                      (paths['regressionControls'], f'{pilot.CHECKS}/regression-{project}-{number}/verify.js')])
    for local, remote in pairs:
        result = pilot.guest(['sha256sum', remote])
        if result.returncode or not result.stdout.startswith(pilot.SHA(local.read_bytes()) + ' '):
            raise SystemExit('guest file mismatch: ' + remote)
    for project, base in pilot.BASES.items():
        status = pilot.guest(['git', '-C', base, 'status', '--porcelain=v1'])
        head = pilot.guest(['git', '-C', base, 'rev-parse', 'HEAD'])
        if status.returncode or status.stdout.strip() or head.returncode or head.stdout.strip() != manifest['sourceCommit'][project]:
            raise SystemExit('guest source tree or commit mismatch: ' + project)
    lock = pilot.guest(['bash', '-lc', 'sha256sum "$HOME/staging/chartjs-runtime-20261031/package-lock.json"'])
    node = pilot.guest(['sha256sum', '/opt/memex-pilot/node/bin/node'])
    if lock.returncode or not lock.stdout.startswith(LOCK_SHA + ' ') or node.returncode or not node.stdout.startswith(NODE_SHA + ' '):
        raise SystemExit('guest runtime mismatch')


pilot.prepare = prepare
pilot.verify_guest = verify_guest

if __name__ == '__main__':
    pilot.main()
