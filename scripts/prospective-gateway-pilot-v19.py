#!/usr/bin/env python3
"""Two additional isolated Prettier issue pairs."""
import importlib.util
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('pilot_v17', REPO / 'scripts/prospective-gateway-pilot-v17.py')
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
pilot = previous.pilot
pilot.TASKS = {'11982': 'prettier', '16925': 'prettier'}
pilot.SEED = 2026103122
pilot.BASES = {'prettier': '/opt/memex-pilot/workspaces/prettier-base'}
pilot.COMMITS = {'prettier': 'bed4edbb1cf2a9db4004215b0ce5707cdb02b5d9'}
pilot.LOCKS = {'prettier': '41b9c8ed4b436f246269727c8fbf8cda521ecc1d97d3ef5569b05c67eee34876'}
pilot.ROOT = '/opt/memex-pilot/workspaces/gateway-recovery-v19'


def prepare(root, snapshot):
    previous.previous.previous.prepare(root, snapshot)
    manifest = pilot.integrity(root)
    manifest['kind'] = 'registered-two-prettier-issue-pairs'
    manifest['reviewOutputTokenLimits'] = {'deepseek-flash': 700, 'qwen3.8-flash': 2048}
    manifest['adjudicationOutputTokenLimit'] = 2048
    manifest.pop('maxReviewTokens', None)
    for name in ('prospective-gateway-pilot-v19.py', 'prospective-gateway-pilot-v17.py', 'prospective-gateway-pilot-v16.py'):
        manifest['files'][f'scripts/{name}'] = pilot.SHA((REPO / 'scripts' / name).read_bytes())
    manifest['limitations'] = [
        'Two additional issues selected after earlier observed batches; not a pre-registered 30–50-task independent cohort.',
        'Public discussions and PRs can disclose solutions or appear in model training; common repositories can correlate.',
        'Source-only references and small custom tests do not establish full upstream acceptance.',
        'Pre-seeded short issue discussions are not long production sessions or autonomous memory management.',
        'Same-proxy AI model provenance is unverified; larger model budgets were selected after observed truncation.',
        'Retrieved context content and size differ between arms; no production effect or savings claim.']
    pilot.save(root / 'manifest.json', manifest)
    pilot.integrity(root)
    print('final manifest sha256:', pilot.SHA((root / 'manifest.json').read_bytes()))


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
    base = pilot.BASES['prettier']
    status = pilot.guest(['git', '-C', base, 'status', '--porcelain=v1'])
    head = pilot.guest(['git', '-C', base, 'rev-parse', 'HEAD'])
    lock = pilot.guest(['bash', '-lc', 'sha256sum "$HOME/staging/prettier-runtime/package-lock.json"'])
    node = pilot.guest(['sha256sum', '/opt/memex-pilot/node/bin/node'])
    if (status.returncode or status.stdout.strip() or head.returncode or head.stdout.strip() != manifest['sourceCommit']['prettier'] or
            lock.returncode or not lock.stdout.startswith(pilot.LOCKS['prettier'] + ' ') or
            node.returncode or not node.stdout.startswith(previous.previous.NODE_SHA256 + ' ')):
        raise SystemExit('guest source or runtime mismatch')


pilot.prepare = prepare
pilot.verify_guest = verify_guest

if __name__ == '__main__':
    pilot.main()
