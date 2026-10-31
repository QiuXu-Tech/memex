#!/usr/bin/env python3
"""Two isolated Lodash issue pairs, including a no-history negative control."""
import importlib.util
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pilot_v22', REPO / 'scripts/prospective-gateway-pilot-v22.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot
pilot.TASKS = {'6191': 'lodash', '5948': 'lodash'}
pilot.SEED = 2026103126
pilot.BASES = {'lodash': '/opt/memex-pilot/workspaces/lodash-full-base'}
pilot.COMMITS = {'lodash': '2b5e6f7399a7b48005140b5d5c6bc6c0e62919a8'}
pilot.ROOT = '/opt/memex-pilot/workspaces/gateway-recovery-v23'


def prepare(root, snapshot):
    if root.exists():
        raise SystemExit('output exists; refusing overwrite')
    source = json.loads(pathlib.Path(snapshot).read_text())['issues']
    if set(source) != {f'lodash-{number}' for number in pilot.TASKS}:
        raise SystemExit('unexpected issue set')
    issues = {str(issue['number']): issue for issue in source.values()}
    for number, issue in issues.items():
        comments = issue['comments']
        if (issue['url'] != f'https://github.com/lodash/lodash/issues/{number}' or issue['state'] != 'OPEN' or
                comments['pageInfo']['hasNextPage'] or comments['totalCount'] != len(comments['nodes'])):
            raise SystemExit('issue is closed, mismatched, or comments are incomplete')
    root.mkdir(parents=True, mode=0o700)
    contexts = {number: pilot.store_context(issue, root / 'stores' / number) for number, issue in issues.items()}
    pilot.save(root / 'issues.json', issues)
    pilot.save(root / 'contexts.json', contexts)
    template = REPO / 'docs/assets/benchmarks/production-prospective-agent-batch22/manifest.json'
    manifest = json.loads(template.read_text())
    manifest.update({'kind': 'registered-two-lodash-issue-pairs', 'createdAt': pilot.NOW(), 'sourceCommit': pilot.COMMITS,
                     'tasks': pilot.TASKS, 'issuesSha256': pilot.SHA((root / 'issues.json').read_bytes()),
                     'contextsSha256': pilot.SHA((root / 'contexts.json').read_bytes()), 'seed': pilot.SEED,
                     'schedule': pilot.schedule(),
                     'checks': {n: {name: pilot.SHA(path.read_bytes()) for name, path in pilot.check_paths(n, project).items()}
                                for n, project in pilot.TASKS.items()}})
    manifest['files'][str(pathlib.Path(__file__).relative_to(REPO))] = pilot.SHA(pathlib.Path(__file__).read_bytes())
    manifest['files'][str(template.relative_to(REPO))] = pilot.SHA(template.read_bytes())
    manifest['runtime']['dependencies'] = 'Node loads the pinned lodash.js source directly without external npm packages.'
    manifest['limitations'].append('Issue #5948 has no discussion records; both retrieval arms receive no history and it is a negative control, not evidence of a memory effect.')
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
    base = pilot.BASES['lodash']
    status = pilot.guest(['git', '-C', base, 'status', '--porcelain=v1'])
    head = pilot.guest(['git', '-C', base, 'rev-parse', 'HEAD'])
    node = pilot.guest(['sha256sum', '/opt/memex-pilot/node/bin/node'])
    if (status.returncode or status.stdout.strip() or head.returncode or head.stdout.strip() != manifest['sourceCommit']['lodash'] or
            node.returncode or not node.stdout.startswith(previous.previous.NODE_SHA + ' ')):
        raise SystemExit('guest source or runtime mismatch')


pilot.prepare = prepare
pilot.verify_guest = verify_guest

if __name__ == '__main__':
    pilot.main()
