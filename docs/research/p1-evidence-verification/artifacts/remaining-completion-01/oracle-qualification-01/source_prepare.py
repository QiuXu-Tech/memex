"""Prepare known reference bytes only; no target Python or oracle is executed."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
# Portable published entry point: the actually executed version's literal
# private path is redacted in evidence.zip and its raw SHA is retained there.
CANONICAL = Path(os.environ['P1_ORACLE_CANONICAL_ROOT'])
GIT = '/Library/Developer/CommandLineTools/usr/bin/git'
sys.path.insert(0, str(CANONICAL / 'scripts/paper1'))
import taskpack

env = {'PATH': '/Library/Developer/CommandLineTools/usr/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8',
       'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null', 'GIT_TERMINAL_PROMPT': '0',
       'GIT_OPTIONAL_LOCKS': '0'}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as handle:
        json.dump(value, handle, sort_keys=True, indent=2)
        handle.write('\n')


def run(command, task, name):
    result = subprocess.run(command, env=env, capture_output=True, timeout=75, check=False)
    prefix = ROOT / 'acquisition' / task / name
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix('.stdout').write_bytes(result.stdout)
    prefix.with_suffix('.stderr').write_bytes(result.stderr)
    save(prefix.with_suffix('.json'), {'argv': command, 'returncode': result.returncode,
        'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(), 'stderr_sha256': hashlib.sha256(result.stderr).hexdigest(),
        'model_requests': 0, 'source_executions': 0})
    if result.returncode:
        raise RuntimeError('known_reference_source_acquisition_failed')
    return result.stdout


def main():
    if (ROOT / 'sources').exists():
        raise RuntimeError('new_reference_source_directory_required')
    if shutil.which('git', path=env['PATH']) != GIT:
        raise RuntimeError('explicit_known_git_required')
    packages = CANONICAL / 'docs/research/p1-evidence-verification/tasks/workflows/packages'
    rows = []
    for task in ('w-101', 'w-102'):
        package = packages / task
        checked = taskpack.validate_package(package)
        spec = taskpack.read_json(package / 'controller/spec.json')
        target = ROOT / 'sources' / task
        target.mkdir(parents=True)
        shutil.copytree(package / 'public/workspace', target / 'base', copy_function=shutil.copy2)
        if taskpack.inventory(target / 'base') != taskpack.inventory(package / 'public/workspace'):
            raise RuntimeError('base_copy_changed')
        repository = ROOT / 'repositories' / (task + '.git')
        repository.parent.mkdir(exist_ok=True)
        run([GIT, '-c', 'core.hooksPath=/dev/null', 'init', '--bare', '--template=', str(repository)], task, 'init')
        fix = spec['evaluator']['source_fix_commit']
        run([GIT, '-C', str(repository), '-c', 'credential.helper=', '-c', 'core.hooksPath=/dev/null',
             'fetch', '--no-tags', '--depth=1', spec['source']['repository_url'], fix], task, 'fetch-fixed')
        # Exact pinned Git objects are read by the existing allowlisted exporter.
        source = {**spec['source'], 'base_commit': fix}
        export = taskpack.export_source(source, repository, target / 'fixed')
        save(target / 'fixed-export.json', export)
        qualification = spec['evaluator']['program_qualification']
        receipt_path = CANONICAL / qualification['receipt']
        if hashlib.sha256(receipt_path.read_bytes()).hexdigest() != qualification['receipt_sha256']:
            raise RuntimeError('original_qualification_hash_changed')
        receipt = taskpack.read_json(receipt_path)
        for row in receipt['fixed_file_checks']:
            if hashlib.sha256((target / 'fixed' / row['path']).read_bytes()).hexdigest() != row['working_sha256']:
                raise RuntimeError('official_fixed_source_differs_from_known_qualification')
        rows.append({'task_id': task, 'repository_url': source['repository_url'],
            'base_commit': spec['source']['base_commit'], 'fixed_commit': fix,
            'base_source': 'existing_verified_canonical_public_workspace',
            'taskpack_public_sha256': checked['public_sha256'],
            'base_inventory_sha256': taskpack.digest(taskpack.inventory(target / 'base')),
            'fixed_inventory_sha256': taskpack.digest(taskpack.inventory(target / 'fixed')),
            'fixed_export_sha256': hashlib.sha256((target / 'fixed-export.json').read_bytes()).hexdigest(),
            'original_qualification_sha256': qualification['receipt_sha256'],
            'fixed_relevant_files_match_original_qualification': True})
        print(json.dumps({'task_id': task, 'status': 'reference_bytes_prepared', 'source_executions': 0}), flush=True)
    result = {'kind': 'independent_oracle_reference_source_preparation', 'schema_version': 1,
        'finished_at': datetime.now(timezone.utc).isoformat(), 'tasks': rows, 'source_executions': 0,
        'model_requests': 0, 'provider_requests': 0, 'native_attempts': 0, 'method_units': 0,
        'canonical_ledger_accessed': False, 'existing_taskpacks_modified': False,
        'git_public_fetches': 2, 'licenses_or_accounts_accepted': False}
    save(ROOT / 'source-preparation.json', result)
    print(json.dumps({'status': 'reference_source_preparation_complete', 'tasks': len(rows)}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        save(ROOT / 'source-preparation-failure.json', {'status': 'blocked', 'type': type(error).__name__,
            'reason': str(error) if type(error) is RuntimeError else 'reference_preparation_error',
            'source_executions': 0, 'model_requests': 0, 'canonical_ledger_accessed': False})
        raise
