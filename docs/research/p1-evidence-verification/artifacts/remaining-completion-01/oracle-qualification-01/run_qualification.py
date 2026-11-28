"""Reference-only oracle qualification through the existing verified sandbox.

No method artifact, model, provider, experiment ledger or native attempt is read
or created. The unchanged request-derived oracle is evaluated on known source
references and deliberately incorrect controls. --run is mandatory for execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import uuid

ROOT = Path(__file__).resolve().parent
TASKS = ('w-101', 'w-102')
VARIANTS = ('base', 'fixed', 'incorrect_behavior', 'empty_oracle', 'missing_source', 'installed_fallback')
SELECTOR = '_p1_oracles/test_request_contract.py'
MUTATIONS = {
    'w-101': ('src/flask/blueprints.py', '\n\n# Deliberately incorrect qualification control: rejects all names.\n'
        'def _p1_reject_every_blueprint_name(self, *args, **kwargs):\n'
        '    raise ValueError("qualification control: every name rejected")\n'
        'Blueprint.__init__ = _p1_reject_every_blueprint_name\n'),
    'w-102': ('requests/utils.py', '\n\n# Deliberately incorrect qualification control: invents the same credentials.\n'
        'def get_auth_from_url(url):\n'
        '    return ("reviewer", "fixture-password")\n'),
}
EXPECTED = {
    'w-101': {'base': (5, 4, 1), 'fixed': (5, 5, 0), 'incorrect_behavior': (5, 2, 3)},
    'w-102': {'base': (6, 2, 4), 'fixed': (6, 6, 0), 'incorrect_behavior': (6, 3, 3)},
}


def sha(content):
    return hashlib.sha256(content).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def read(path):
    return json.loads(path.read_text())


def tooling(canonical):
    destination = ROOT / 'tooling'
    if destination.exists():
        raise RuntimeError('qualification_tooling_directory_must_be_new')
    names = ['scripts/paper1/' + name + '.py' for name in (
        'public_workspace', 'python_workflow', 'python_workflow_child', 'experiment', 'taskpack')]
    names += ['docs/research/p1-evidence-verification/tasks/reproduction/' + candidate + '/requirements-pinned.txt'
        for candidate in ('pallets__flask-5014', 'psf__requests-6028')]
    before = {name: sha((canonical / name).read_bytes()) for name in names}
    for name in names:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(canonical / name, target)
    if any(sha((canonical / name).read_bytes()) != value or sha((destination / name).read_bytes()) != value
           for name, value in before.items()):
        raise RuntimeError('canonical_helpers_changed_during_snapshot')
    save(ROOT / 'tooling-manifest.json', {'kind': 'detached_controller_helper_snapshot', 'files': before})
    module = runpy.run_path(str(destination / 'scripts/paper1/public_workspace.py'))
    return module, before


def expected_result(task, variant, summary, observation, process):
    if variant in EXPECTED[task]:
        total, passed, failed = EXPECTED[task][variant]
        expected = {'collected': total, 'passed': passed, 'failed': failed, 'errors': 0, 'skipped': 0}
        return (summary['status'] == ('tests_failed' if failed else 'tests_passed')
            and summary['test_counts'] == expected and process['returncode'] == (1 if failed else 0))
    if variant == 'empty_oracle':
        return (summary['status'] == 'capture_incomplete' and process['returncode'] == 5
            and observation is not None and observation.get('collected') == []
            and observation.get('pytest_started') is True and observation.get('pytest_finished') is True)
    error = (observation or {}).get('error') or {}
    expected_error = ('project_import_outside_current_workspace' if variant == 'installed_fallback' else None)
    return (summary['status'] == 'capture_incomplete' and process['returncode'] == 78
        and observation is not None and observation.get('pytest_started') is False
        and (error.get('code') == expected_error if expected_error else error.get('type') == 'ModuleNotFoundError'))


def dependency_fallback(task, env, sandbox_settings, workflow, sandbox_class):
    """Copy, never alter, the existing dependencies; add one wrong-origin marker.

    This new private directory is only a deliberately malformed import control.
    It gets its own SandboxRunner instance and actual probe. It is never used for
    the base, fixed or behavioral controls and never substituted into settings.
    """
    base = ROOT / 'fallback-environments' / task
    site = base / 'lib/python3.10/site-packages'
    site.parent.mkdir(parents=True)
    shutil.copytree(env['site'], site, copy_function=shutil.copy2)
    if workflow['snapshot'](site, max_bytes=256 * 1024 * 1024, max_files=40000) != env['dependency_snapshot']:
        raise RuntimeError('dependency_control_copy_mismatch')
    module = 'flask' if task == 'w-101' else 'requests'
    fake = site / module
    if fake.exists():
        raise RuntimeError('installed_target_already_present_control_needs_reassessment')
    fake.mkdir()
    (fake / '__init__.py').write_text('"""Wrong-origin import control, not the upstream package."""\n'
        'P1_WRONG_ORIGIN_CONTROL = True\n')
    config = {**sandbox_settings, 'dependencies': str(site)}
    sandbox = sandbox_class(config)
    probe = sandbox.probe(ROOT / 'probes' / (task + '-installed-fallback'), timeout=15)
    if probe['status'] != 'passed' or not sandbox.verified:
        raise RuntimeError('installed_fallback_control_sandbox_probe_failed')
    snapshot = workflow['snapshot'](site, max_bytes=256 * 1024 * 1024, max_files=40000)
    save(base / 'control.json', {'kind': 'intentional_wrong_origin_dependency_control',
        'original_dependency_tree_sha256': env['dependency_snapshot']['version'],
        'control_dependency_tree_sha256': snapshot['version'],
        'added_file': module + '/__init__.py', 'added_file_sha256': sha((fake / '__init__.py').read_bytes()),
        'original_dependencies_modified': False, 'package_installed': False})
    return sandbox, snapshot, probe


def execute_variant(task, variant, recipe, env, sandbox, dependencies, workflow, sandbox_probe):
    run = ROOT / 'runs' / task / variant
    run.mkdir(parents=True)
    workspace = run / 'workspace'
    reference = ROOT / 'sources' / task / ('base' if variant == 'base' else 'fixed')
    shutil.copytree(reference, workspace, copy_function=shutil.copy2)
    original = workflow['snapshot'](reference)
    if workflow['snapshot'](workspace) != original:
        raise RuntimeError('independent_reference_copy_mismatch')
    oracle = (ROOT / 'oracles' / (task + '.py')).read_bytes()
    selector = workspace / SELECTOR
    selector.parent.mkdir()
    selector.write_bytes(oracle)
    mutation = None
    if variant == 'incorrect_behavior':
        name, text = MUTATIONS[task]
        target = workspace / name
        before = target.read_bytes()
        target.write_bytes(before + text.encode())
        mutation = {'path': name, 'before_sha256': sha(before), 'after_sha256': sha(target.read_bytes()),
            'append_utf8': text, 'purpose': 'known_incorrect_behavior_negative_control'}
    elif variant == 'empty_oracle':
        selector.write_text('# Deliberate zero-test collection control.\n')
        mutation = {'path': SELECTOR, 'purpose': 'zero_collected_tests_must_not_pass'}
    elif variant in ('missing_source', 'installed_fallback'):
        name = 'src/flask' if task == 'w-101' else 'requests'
        shutil.rmtree(workspace / name)
        mutation = {'removed_directory': name, 'purpose': 'missing_current_project_must_not_pass'}
    nonce = uuid.uuid4().hex
    before = workflow['snapshot'](workspace)
    save(run / 'workspace-before.json', before)
    bootstrap = ROOT / 'tooling/scripts/paper1/python_workflow_child.py'
    mapped = sandbox.paths(workspace, run / 'execution/sandbox-output')
    config = {'nonce': nonce, 'workspace': mapped['workspace'], 'dependencies': mapped['dependencies'],
        'module': recipe['module'], 'import_root': recipe['import_root'], 'tests': [SELECTOR],
        'plugins': recipe['plugins'], 'requirements': recipe['requirements'], 'python_version': recipe['python_version'],
        'temporary': mapped['output'] + '/pytest-tmp', 'junit': mapped['output'] + '/pytest.junit.xml',
        'result': mapped['output'] + '/pytest-observation.json'}
    save(run / 'child-config.json', config)
    save(run / 'admission.json', {'kind': 'reference_oracle_qualification_admission',
        'task_id': task, 'variant': variant, 'source_reference': 'base' if variant == 'base' else 'official_fixed',
        'oracle_original_sha256': sha(oracle), 'executed_test_file_sha256': sha(selector.read_bytes()),
        'reference_workspace_sha256': original['version'], 'workspace_before_sha256': before['version'],
        'mutation': mutation, 'sandbox_probe_binding': sandbox_probe['binding'],
        'source_observer': str(bootstrap.relative_to(ROOT)), 'source_observer_sha256': sha(bootstrap.read_bytes()),
        'max_wall_seconds': 60, 'external_network_permitted': False,
        'model_requests': 0, 'native_attempts': 0, 'method_units': 0, 'canonical_ledger_accessed': False})
    capture = sandbox.run_observer(workspace=workspace, bootstrap=bootstrap, config=run / 'child-config.json',
        output=run / 'execution', timeout=60)
    observation_path = Path(capture['result_dir']) / 'pytest-observation.json'
    observation = read(observation_path) if observation_path.is_file() else None
    after = workflow['snapshot'](workspace)
    save(run / 'workspace-after.json', after)
    summary = workflow['summarize'](capture['process'], observation, before, after,
        nonce=nonce, tests=[SELECTOR], module=recipe['module'], dependencies=dependencies['files'])
    runtime_unchanged = workflow['runtime'](env['python'], recipe)['report'] == env['report']
    if not runtime_unchanged:
        summary.update(status='capture_incomplete', reason='original_dependency_or_interpreter_changed')
    binding = (observation or {}).get('project_origins_after', (observation or {}).get('project_origins_before', {}))
    result = {'kind': 'independent_reference_oracle_observation', 'task_id': task, 'variant': variant,
        'summary': summary, 'expected_control_outcome_observed': expected_result(task, variant, summary, observation, capture['process']),
        'process_returncode': capture['process']['returncode'], 'observer_error': (observation or {}).get('error'),
        'observed_python_version': (observation or {}).get('python_version'),
        'observed_main_import': binding.get(recipe['module']), 'original_runtime_unchanged': runtime_unchanged,
        'same_sandbox_instance_still_verified': sandbox.verified,
        'selected_test_file_sha256': sha(selector.read_bytes()), 'run': str(run.relative_to(ROOT)),
        'observer_processes': int(capture['process']['spawned']),
        'research_method_result': False, 'decision_success': None, 'human_annotators': 0,
        'method_units': 0, 'native_attempts': 0, 'model_requests': 0, 'provider_requests': 0}
    save(run / 'result.json', result)
    print(json.dumps({'task_id': task, 'variant': variant, 'summary': summary,
        'expected_control_outcome_observed': result['expected_control_outcome_observed']}), flush=True)
    if not runtime_unchanged or not result['same_sandbox_instance_still_verified']:
        raise RuntimeError('runtime_binding_changed_stop_remaining_execution')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--canonical-root', type=Path, required=True)
    parser.add_argument('--settings', type=Path, required=True)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if not args.run:
        print(json.dumps({'kind': 'reference_oracle_zero_execution_preflight', 'run_requested': False,
            'planned_tasks': list(TASKS), 'planned_variants': list(VARIANTS), 'observer_processes': 0,
            'native_attempts': 0, 'model_requests': 0, 'ledger_accessed': False}))
        return
    if any((ROOT / name).exists() for name in ('qualification.json', 'runs', 'tooling', 'probes')):
        raise RuntimeError('fresh_qualification_run_required')
    preparation = read(ROOT / 'source-preparation.json')
    if {row['task_id'] for row in preparation['tasks']} != set(TASKS):
        raise RuntimeError('qualified_reference_source_preparation_required')
    settings_bytes = args.settings.read_bytes()
    settings = json.loads(settings_bytes)
    module, tooling_hashes = tooling(args.canonical_root)
    workflow, sandbox_class = module['WORKFLOW'], module['SandboxRunner']
    packages = args.canonical_root / 'docs/research/p1-evidence-verification/tasks/workflows/packages'
    save(ROOT / 'execution-plan.json', {'kind': 'reference_oracle_qualification_plan',
        'tasks': list(TASKS), 'variants': list(VARIANTS), 'expected_test_counts': EXPECTED,
        'negative_control_mutations': MUTATIONS, 'max_wall_seconds_per_observer': 60,
        'source_preparation_sha256': sha((ROOT / 'source-preparation.json').read_bytes()),
        'request_oracle_sha256': {task: sha((ROOT / 'oracles' / (task + '.py')).read_bytes()) for task in TASKS},
        'settings_sha256': sha(settings_bytes), 'tooling': tooling_hashes,
        'request_oracles_changed_after_reference_observation': False,
        'new_native_or_method_outputs_read': False, 'canonical_ledger_accessed': False,
        'accepted_research_tasks': 0, 'human_annotators': 0, 'source_only_oracle_qualification': True})
    results, probes = [], []
    for task in TASKS:
        public = packages / task / 'public'
        recipe = workflow['profile'](public)
        task_settings = settings['tasks'][task]
        env = workflow['runtime'](task_settings['python'], recipe)
        if (not env['report']['requirements_match']
                or Path(task_settings['sandbox']['python']).resolve() != env['target']
                or Path(task_settings['sandbox']['dependencies']).resolve() != env['site']):
            raise RuntimeError('task_runtime_and_sandbox_binding_mismatch')
        save(ROOT / 'runtimes' / (task + '.json'), env['report'])
        save(ROOT / 'runtimes' / (task + '-dependency-snapshot.json'), env['dependency_snapshot'])
        sandbox = sandbox_class(task_settings['sandbox'])
        probe = sandbox.probe(ROOT / 'probes' / task, timeout=15)
        probes.append({'task_id': task, 'variant': 'original_dependencies', 'status': probe['status']})
        if probe['status'] != 'passed' or not sandbox.verified:
            raise RuntimeError('actual_sandbox_probe_failed_no_source_execution')
        for variant in VARIANTS[:-1]:
            results.append(execute_variant(task, variant, recipe, env, sandbox, env['dependency_snapshot'], workflow, probe))
        fallback, dependencies, fallback_probe = dependency_fallback(task, env, task_settings['sandbox'], workflow, sandbox_class)
        probes.append({'task_id': task, 'variant': 'copied_dependencies_with_wrong_origin_marker', 'status': fallback_probe['status']})
        results.append(execute_variant(task, 'installed_fallback', recipe, env, fallback, dependencies, workflow, fallback_probe))
        if workflow['profile'](public) != recipe:
            raise RuntimeError('canonical_public_task_changed')
    if args.settings.read_bytes() != settings_bytes:
        raise RuntimeError('canonical_runtime_settings_changed')
    expected = all(row['expected_control_outcome_observed'] for row in results)
    save(ROOT / 'qualification.json', {'kind': 'request_derived_oracle_reference_qualification', 'schema_version': 1,
        'status': 'reference_controls_validated' if expected else 'reference_control_expectation_not_met',
        'results': results, 'sandbox_probes': probes, 'settings_sha256': sha(settings_bytes),
        'settings_unchanged': True, 'canonical_public_tasks_unchanged': True,
        'original_interpreter_and_dependency_trees_unchanged': all(row['original_runtime_unchanged'] for row in results),
        'observer_processes': sum(row['observer_processes'] for row in results),
        'sandbox_probe_processes': len(probes), 'qualified_request_derived_oracles': 2 if expected else 0,
        'qualification_scope': 'known_base_official_fixed_and_constructed_negative_controls_only',
        'research_method_result': False, 'decision_success': None, 'human_annotators': 0,
        'accepted_research_tasks': 0, 'native_attempts': 0, 'method_units': 0, 'model_requests': 0, 'provider_requests': 0,
        'canonical_ledger_accessed': False, 'new_native_or_method_outputs_read': False,
        'oracle_delivered_to_model': False, 'request_oracles_changed_after_reference_observation': False,
        'limitations': ['No experiment-arm artifact was evaluated.',
            'Requests controls do not reproduce Python 3.8.12 or an end-to-end HTTP 407 proxy interaction.',
            'A source behavior oracle does not establish evidence-use, authorization, decision correctness or task acceptance.',
            'These known-reference controls are engineering qualification, not an estimate of method success or oracle completeness.']})
    print(json.dumps({'status': 'qualification_complete', 'all_expected_controls_observed': expected,
        'observer_processes': sum(row['observer_processes'] for row in results), 'sandbox_probe_processes': len(probes)}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        save(ROOT / 'qualification-failure.json', {'status': 'blocked', 'type': type(error).__name__,
            'reason': str(error) if isinstance(error, (RuntimeError, ValueError)) else 'qualification_controller_error',
            'completed_result_files': [str(p.relative_to(ROOT)) for p in sorted((ROOT / 'runs').glob('*/*/result.json'))],
            'native_attempts': 0, 'method_units': 0, 'model_requests': 0, 'canonical_ledger_accessed': False})
        raise
