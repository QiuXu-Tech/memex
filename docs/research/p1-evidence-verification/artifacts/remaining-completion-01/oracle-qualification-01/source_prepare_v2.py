"""Resume known source acquisition after an undeployed historical receipt.

This only reads Git objects and copies files. It executes no target source.
The first preparation failure is retained instead of overwritten.
"""
from pathlib import Path
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import source_prepare as original

save, run, taskpack = original.save, original.run, original.taskpack
CANONICAL, GIT = original.CANONICAL, original.GIT


def main():
    if (ROOT / 'source-preparation.json').exists():
        raise RuntimeError('completed_preparation_cannot_be_repeated')
    rows = []
    packages = CANONICAL / 'docs/research/p1-evidence-verification/tasks/workflows/packages'
    for task in ('w-101', 'w-102'):
        package = packages / task
        checked = taskpack.validate_package(package)
        spec = taskpack.read_json(package / 'controller/spec.json')
        qualification = spec['evaluator']['program_qualification']
        receipt_path = ROOT / 'reference-qualification' / (task + '.json')
        if hashlib.sha256(receipt_path.read_bytes()).hexdigest() != qualification['receipt_sha256']:
            raise RuntimeError('historical_qualification_hash_mismatch')
        receipt = taskpack.read_json(receipt_path)
        target = ROOT / 'sources' / task
        target.mkdir(parents=True, exist_ok=True)
        if not (target / 'base').exists():
            shutil.copytree(package / 'public/workspace', target / 'base', copy_function=shutil.copy2)
        if taskpack.inventory(target / 'base') != taskpack.inventory(package / 'public/workspace'):
            raise RuntimeError('base_copy_changed')
        repository = ROOT / 'repositories' / (task + '.git')
        fix = spec['evaluator']['source_fix_commit']
        source = {**spec['source'], 'base_commit': fix}
        if not repository.exists():
            run([GIT, '-c', 'core.hooksPath=/dev/null', 'init', '--bare', '--template=', str(repository)], task, 'init')
            run([GIT, '-C', str(repository), '-c', 'credential.helper=', '-c', 'core.hooksPath=/dev/null',
                 'fetch', '--no-tags', '--depth=1', source['repository_url'], fix], task, 'fetch-fixed')
        if not (target / 'fixed').exists():
            save(target / 'fixed-export.json', taskpack.export_source(source, repository, target / 'fixed'))
        export = taskpack.read_json(target / 'fixed-export.json')
        if any(export.get(k) != value for k, value in source.items()):
            raise RuntimeError('fixed_export_identity_mismatch')
        files = {row['path']: row for row in taskpack.inventory(target / 'fixed') if row['kind'] == 'file'}
        if set(files) != {row['path'] for row in export['files']}:
            raise RuntimeError('fixed_export_file_set_mismatch')
        for row in export['files']:
            content = (target / 'fixed' / row['path']).read_bytes()
            git_blob = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
            if hashlib.sha256(content).hexdigest() != row['sha256'] or git_blob != row['git_blob']:
                raise RuntimeError('fixed_export_blob_mismatch')
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
    save(ROOT / 'source-preparation.json', {'kind': 'independent_oracle_reference_source_preparation',
        'schema_version': 2, 'finished_at': datetime.now(timezone.utc).isoformat(), 'tasks': rows,
        'source_executions': 0, 'model_requests': 0, 'provider_requests': 0, 'native_attempts': 0, 'method_units': 0,
        'canonical_ledger_accessed': False, 'existing_taskpacks_modified': False, 'git_public_fetches': 2,
        'prior_failure_retained': 'source-preparation-failure.json',
        'prior_failure_reason': 'historical_receipt_not_deployed_to_canonical_runtime',
        'recovery': 'copied_exact_preexisting_repository_receipts_to_private_qualification_directory',
        'licenses_or_accounts_accepted': False})
    print(json.dumps({'status': 'reference_source_preparation_complete', 'tasks': len(rows)}), flush=True)


if __name__ == '__main__':
    main()
