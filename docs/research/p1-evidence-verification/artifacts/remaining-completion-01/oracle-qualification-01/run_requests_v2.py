"""Validate the narrower explicit-URL contract; retain all first-round results.

No new method output is read. This revision is developed after reference-only
observations and does not claim prospective registration before those controls.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import runpy
import shutil

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--canonical-root', type=Path, required=True)
    parser.add_argument('--settings', type=Path, required=True)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if not args.run:
        print(json.dumps({'kind': 'request_oracle_revision_zero_execution_preflight',
            'observer_processes': 0, 'model_requests': 0, 'canonical_ledger_accessed': False}))
        return
    spec = importlib.util.spec_from_file_location('reference_qualification', ROOT / 'run_qualification.py')
    original = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(original)
    target = ROOT / 'revision-02'
    if target.exists():
        raise RuntimeError('new_revision_directory_required')
    taskpack = runpy.run_path(str(ROOT / 'tooling/scripts/paper1/taskpack.py'))
    original_receipt = original.read(ROOT / 'source-preparation.json')
    source_row = next(row for row in original_receipt['tasks'] if row['task_id'] == 'w-102')
    # Compare source bytes to the original, already qualified preparation before
    # any revised run. Every before-snapshot is verified again by audit_records.
    for reference in ('base', 'fixed'):
        source = ROOT / 'sources/w-102' / reference
        if taskpack['digest'](taskpack['inventory'](source)) != source_row[reference + '_inventory_sha256']:
            raise RuntimeError('pinned_reference_source_inventory_changed')
    first = original.read(ROOT / 'qualification.json')
    if len(first['results']) != 12:
        raise RuntimeError('original_results_must_be_retained_complete')
    oracle = (ROOT / 'test_requests_request_contract_v2.py').read_bytes()
    oracle_sha = original.sha(oracle)
    settings_bytes = args.settings.read_bytes()
    settings = json.loads(settings_bytes)
    helpers = original.read(ROOT / 'tooling-manifest.json')['files']
    for name, expected in helpers.items():
        if original.sha((ROOT / 'tooling' / name).read_bytes()) != expected:
            raise RuntimeError('frozen_helper_snapshot_changed')
    target.mkdir()
    shutil.copytree(ROOT / 'tooling', target / 'tooling', copy_function=shutil.copy2)
    shutil.copytree(ROOT / 'sources/w-102', target / 'sources/w-102', copy_function=shutil.copy2)
    (target / 'oracles').mkdir()
    (target / 'oracles/w-102.py').write_bytes(oracle)
    original.ROOT = target
    original.EXPECTED = {'w-102': {'base': (5, 2, 3), 'fixed': (5, 5, 0), 'incorrect_behavior': (5, 2, 3)}}
    module = runpy.run_path(str(target / 'tooling/scripts/paper1/public_workspace.py'))
    workflow, sandbox_class = module['WORKFLOW'], module['SandboxRunner']
    public = args.canonical_root / 'docs/research/p1-evidence-verification/tasks/workflows/packages/w-102/public'
    recipe = workflow['profile'](public)
    public_before = workflow['EXPERIMENT']['public_digest'](public)
    env = workflow['runtime'](settings['tasks']['w-102']['python'], recipe)
    sandbox_config = settings['tasks']['w-102']['sandbox']
    if (not env['report']['requirements_match'] or Path(sandbox_config['python']).resolve() != env['target']
            or Path(sandbox_config['dependencies']).resolve() != env['site']):
        raise RuntimeError('runtime_binding_mismatch')
    original.save(target / 'revision-plan.json', {'kind': 'request_oracle_reference_revision_plan', 'version': 2,
        'source_preparation_sha256': original.sha((ROOT / 'source-preparation.json').read_bytes()),
        'source_reference': source_row, 'original_qualification_sha256': original.sha((ROOT / 'qualification.json').read_bytes()),
        'original_draft_six_cases_preserved': True, 'original_fixed_failures_preserved': 1,
        'revision_controller_sha256': original.sha(Path(__file__).read_bytes()),
        'original_controller_sha256': original.sha((ROOT / 'run_qualification.py').read_bytes()),
        'request_oracle_sha256': oracle_sha, 'settings_sha256': original.sha(settings_bytes),
        'public_before_sha256': public_before, 'expected_test_counts': original.EXPECTED,
        'selected_scope': 'explicit_http_https_proxy_credentials_plus_unauthenticated_proxy_controls',
        'excluded_exploratory_input': 'ordinary_username_colon_password_at_host_without_url_scheme',
        'rationale': 'The original draft assumed this ambiguous string is parsed as credentials; the known fixed reference does not satisfy it. The revised contract explicitly scopes ordinary credential URLs; the original failure remains an unresolved extension.',
        'uncovered_behavior': ['full_HTTP_407_end_to_end', 'Python_3_8_12', 'ambiguous_schemeless_credential_URL'],
        'revision_after_reference_observation': True, 'new_method_outputs_read': False,
        'method_score_produced': False, 'human_annotators': 0})
    sandbox = sandbox_class(sandbox_config)
    probe = sandbox.probe(target / 'probes/w-102', timeout=15)
    if probe['status'] != 'passed' or not sandbox.verified:
        raise RuntimeError('revision_sandbox_probe_failed')
    original.save(target / 'runtime.json', env['report'])
    original.save(target / 'dependency-snapshot.json', env['dependency_snapshot'])
    results = []
    for variant in ('base', 'fixed', 'incorrect_behavior'):
        # Check the immutable oracle bytes and prepared-source inventories both
        # before and after each invocation. Inputs never come from a method run.
        for reference in ('base', 'fixed'):
            if taskpack['digest'](taskpack['inventory'](target / 'sources/w-102' / reference)) != source_row[reference + '_inventory_sha256']:
                raise RuntimeError('revision_reference_inventory_changed')
        if (target / 'oracles/w-102.py').read_bytes() != oracle:
            raise RuntimeError('request_oracle_bytes_changed_before_run')
        results.append(original.execute_variant('w-102', variant, recipe, env, sandbox,
            env['dependency_snapshot'], workflow, probe))
        if (target / 'oracles/w-102.py').read_bytes() != oracle:
            raise RuntimeError('request_oracle_bytes_changed_after_run')
    public_after = workflow['EXPERIMENT']['public_digest'](public)
    if public_after != public_before or args.settings.read_bytes() != settings_bytes:
        raise RuntimeError('canonical_public_or_runtime_settings_changed')
    original.save(target / 'qualification.json', {'kind': 'request_derived_oracle_reference_revision_qualification',
        'schema_version': 2, 'task_id': 'w-102', 'status': 'reference_controls_validated' if all(
            row['expected_control_outcome_observed'] for row in results) else 'reference_control_expectation_not_met',
        'results': results, 'observed_main_import_required_scope': 'workspace',
        'request_oracle_sha256': oracle_sha, 'public_before_sha256': public_before,
        'public_after_sha256': public_after, 'settings_unchanged': True,
        'observer_processes': 3, 'sandbox_probe_processes': 1,
        'original_six_case_draft_remains_not_fully_qualified': True,
        'vacuity_and_wrong_origin_controls': '../qualification.json (first round, same frozen observer code)',
        'decision_success': None, 'accepted_research_tasks': 0, 'human_annotators': 0,
        'native_attempts': 0, 'method_units': 0, 'model_requests': 0, 'provider_requests': 0,
        'canonical_ledger_accessed': False, 'new_native_or_method_outputs_read': False})
    print(json.dumps({'status': 'revision_qualification_complete',
        'expected_controls_observed': all(row['expected_control_outcome_observed'] for row in results)}), flush=True)


if __name__ == '__main__':
    main()
