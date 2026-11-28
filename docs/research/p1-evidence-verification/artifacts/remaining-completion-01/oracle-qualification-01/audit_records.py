"""Read-only revalidation of reference provenance, inputs and actual observers.

This closes the first runner's missing execution-time source-manifest assertion
using the exact captured before/after file inventories. It does not retroactively
claim that this check ran before the original invocation, or run source code.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import importlib.util
import json
import runpy

ROOT = Path(__file__).resolve().parent


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--canonical-root', type=Path, required=True)
    parser.add_argument('--settings', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('reference_runner', ROOT / 'run_qualification.py')
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    workflow = runpy.run_path(str(ROOT / 'tooling/scripts/paper1/python_workflow.py'))
    taskpack = runpy.run_path(str(ROOT / 'tooling/scripts/paper1/taskpack.py'))
    prep = original.read(ROOT / 'source-preparation.json')
    original_plan = original.read(ROOT / 'execution-plan.json')
    original_results = original.read(ROOT / 'qualification.json')
    revision_plan = original.read(ROOT / 'revision-02/revision-plan.json')
    revision_results = original.read(ROOT / 'revision-02/qualification.json')
    require(original.sha((ROOT / 'source-preparation.json').read_bytes()) == original_plan['source_preparation_sha256'], 'source_preparation_digest_changed')
    source_rows = {row['task_id']: row for row in prep['tasks']}
    helpers = original.read(ROOT / 'tooling-manifest.json')['files']
    for name, value in helpers.items():
        require(original.sha((ROOT / 'tooling' / name).read_bytes()) == value, 'frozen_controller_helper_changed')
        require(original.sha((ROOT / 'revision-02/tooling' / name).read_bytes()) == value, 'revision_controller_helper_changed')
    require(original.sha(args.settings.read_bytes()) == original_plan['settings_sha256'] == revision_plan['settings_sha256'], 'runtime_settings_changed')
    reference_snapshots, public_checks = {}, []
    for task in original.TASKS:
        package = args.canonical_root / 'docs/research/p1-evidence-verification/tasks/workflows/packages' / task
        checked = taskpack['validate_package'](package)
        require(checked['public_sha256'] == source_rows[task]['taskpack_public_sha256'], 'canonical_public_tree_changed')
        profile = workflow['profile'](package / 'public')
        public_checks.append({'task_id': task, 'taskpack_public_sha256': checked['public_sha256'],
            'experiment_public_sha256': profile['public_sha256'], 'full_public_tree_rechecked': True})
        original.save(ROOT / 'source-exports' / (task + '-base.json'), original.read(package / 'controller/source-export.json'))
        for reference in ('base', 'fixed'):
            source = ROOT / 'sources' / task / reference
            inventory = taskpack['inventory'](source)
            require(taskpack['digest'](inventory) == source_rows[task][reference + '_inventory_sha256'], 'prepared_reference_inventory_changed')
            reference_snapshots[(task, reference)] = workflow['snapshot'](source)
            exported = original.read(package / 'controller/source-export.json') if reference == 'base' else original.read(ROOT / 'sources' / task / 'fixed-export.json')
            require(exported['base_commit'] == source_rows[task][reference + '_commit'], 'reference_commit_binding_changed')
            actual_files = {row['path']: row for row in inventory if row['kind'] == 'file'}
            require(set(actual_files) == {row['path'] for row in exported['files']}, 'source_export_file_set_changed')
            for entry in exported['files']:
                value = (source / entry['path']).read_bytes()
                blob = hashlib.sha1(b'blob ' + str(len(value)).encode() + b'\0' + value).hexdigest()
                require(original.sha(value) == entry['sha256'] and blob == entry['git_blob'], 'source_git_blob_changed')
    rows = []
    for root, results in [(ROOT, original_results['results']), (ROOT / 'revision-02', revision_results['results'])]:
        for result in results:
            task, variant = result['task_id'], result['variant']
            run = root / result['run']
            admission, config = original.read(run / 'admission.json'), original.read(run / 'child-config.json')
            before, after = original.read(run / 'workspace-before.json'), original.read(run / 'workspace-after.json')
            reference = 'base' if variant == 'base' else 'fixed'
            bound = reference_snapshots[(task, reference)]
            require(admission['reference_workspace_sha256'] == bound['version'], 'captured_reference_snapshot_not_prepared_source')
            oracle = (root / 'oracles' / (task + '.py')).read_bytes()
            expected_oracle_sha = original_plan['request_oracle_sha256'][task] if root == ROOT else revision_plan['request_oracle_sha256']
            require(original.sha(oracle) == expected_oracle_sha == admission['oracle_original_sha256'], 'oracle_snapshot_changed')
            expected = {r['path']: copy.deepcopy(r) for r in bound['files']}
            expected['_p1_oracles'] = {'path': '_p1_oracles', 'kind': 'directory', 'mode': 0o755}
            selected = b'# Deliberate zero-test collection control.\n' if variant == 'empty_oracle' else oracle
            expected[original.SELECTOR] = {'path': original.SELECTOR, 'kind': 'file', 'mode': 0o644,
                'bytes': len(selected), 'sha256': original.sha(selected)}
            if variant == 'incorrect_behavior':
                name, text = original.MUTATIONS[task]
                content = (ROOT / 'sources' / task / 'fixed' / name).read_bytes() + text.encode()
                expected[name].update(bytes=len(content), sha256=original.sha(content))
                require(admission['mutation']['append_utf8'] == text, 'behavior_control_diff_changed')
            if variant in ('missing_source', 'installed_fallback'):
                removed = 'src/flask' if task == 'w-101' else 'requests'
                expected = {key: value for key, value in expected.items() if key != removed and not key.startswith(removed + '/')}
            require(expected == {r['path']: r for r in before['files']}, 'actual_execution_input_not_exact_reference_plus_declared_control')
            require(before['version'] == workflow['digest'](before['files']), 'before_snapshot_digest_invalid')
            require(before == after == workflow['snapshot'](run / 'workspace'), 'captured_or_current_execution_workspace_changed')
            require(original.sha(selected) == admission['executed_test_file_sha256'] == result['selected_test_file_sha256'], 'executed_oracle_hash_changed')
            require(config['workspace'] == str(run / 'workspace') and config['tests'] == [original.SELECTOR], 'observer_workspace_or_selector_changed')
            bootstrap = root / admission['source_observer']
            require(original.sha(bootstrap.read_bytes()) == admission['source_observer_sha256'] == helpers['scripts/paper1/python_workflow_child.py'], 'observer_source_changed')
            observation = original.read(run / 'execution/sandbox-output/pytest-observation.json')
            process = original.read(run / 'execution/process.json')
            for stream, record in process['streams'].items():
                raw = (run / 'execution/capture' / (stream + '.raw')).read_bytes()
                require(original.sha(raw) == record['sha256'] and len(raw) == record['bytes'], 'original_process_stream_changed')
            if variant == 'installed_fallback':
                dependencies = workflow['snapshot'](ROOT / 'fallback-environments' / task / 'lib/python3.10/site-packages',
                    max_bytes=256 * 1024 * 1024, max_files=40000)
            else:
                dep_path = ROOT / 'runtimes' / (task + '-dependency-snapshot.json')
                dependencies = original.read(dep_path)
            summary = workflow['summarize'](process, observation, before, after, nonce=config['nonce'], tests=config['tests'],
                module=config['module'], dependencies=dependencies['files'])
            require(summary == result['summary'], 'recomputed_observer_summary_differs')
            rows.append({'round': 1 if root == ROOT else 2, 'task_id': task, 'variant': variant,
                'reference_preparation_and_all_git_blobs_bound': True, 'exact_execution_inputs_reconstructed': True,
                'unchanged_oracle_bound_to_initial_plan': True, 'observer_summary_recomputed': True,
                'actual_stream_hashes_rechecked': True, 'summary': summary, 'run': str(run.relative_to(ROOT))})
    original.save(ROOT / 'posthoc-integrity-audit.json', {'kind': 'reference_qualification_posthoc_integrity_recheck',
        'status': 'passed', 'all_actual_runs_retained': len(rows) == 15, 'checked_runs': len(rows), 'runs': rows,
        'public_source_checks': public_checks, 'existing_settings_sha256': original_plan['settings_sha256'],
        'source_preparation_and_every_executed_file_reconstructed': True,
        'source_oracle_pins_checked_before_revision_02': True,
        'first_round_missing_admission_check': 'source inventory and oracle initial SHA were not asserted per invocation; this later independent audit reconstructs every captured input against those earlier pins',
        'posthoc_not_retroactive_preregistration': True, 'source_executions_in_this_audit': 0,
        'native_attempts': 0, 'method_units': 0, 'model_requests': 0, 'canonical_ledger_accessed': False})
    print(json.dumps({'status': 'posthoc_integrity_audit_passed', 'actual_observer_records_recomputed': len(rows),
        'source_executions_in_this_audit': 0, 'all_original_failures_retained': True}))


if __name__ == '__main__':
    main()
