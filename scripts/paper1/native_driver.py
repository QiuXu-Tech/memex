#!/usr/bin/env python3
"""Read-only preparation, or one explicitly requested four-arm native block.

Default inspection starts no process, sends no request, reads no credential
file bytes, creates no output and writes no ledger. --run uses the original
canonical controller and one live backend/helper lifetime for all four arms.
This is not experiment.py's per-unit executable ABI or scientific acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import stat
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import paired_runtime as paired
import reader_profile as reader
import runtime_controller as controller_api
import rawrag_adapter as rawrag
from public_workspace import SandboxRunner, WORKFLOW


class DriverError(ValueError):
    pass


def _code(error, fallback):
    value = str(error)
    return value if re.fullmatch(r'[a-z][a-z0-9_]{0,100}', value) else fallback


def _absolute(value):
    if (not isinstance(value, str) or not value or '\x00' in value
            or not Path(value).is_absolute() or '..' in Path(value).parts):
        raise DriverError('explicit_absolute_local_path_required')
    return value


def _settings(value):
    paired.exact(value, ('codex', 'node', 'tokenizer_path', 'credential_file', 'rawrag_upstream', 'tasks'),
                 'invalid_settings_fields')
    for key in ('codex', 'node', 'tokenizer_path', 'credential_file', 'rawrag_upstream'):
        _absolute(value[key])
    paired.exact(value['tasks'], paired.PROJECTS, 'exactly_two_task_runtime_settings_required')
    for task in value['tasks'].values():
        paired.exact(task, ('python', 'sandbox'), 'invalid_task_runtime_settings')
        _absolute(task['python'])
        sandbox = task['sandbox']
        paired.exact(sandbox, ('kind', 'executable', 'python', 'dependencies', 'runtime_roots'), 'invalid_sandbox_settings')
        if sandbox['kind'] not in ('bwrap', 'sandbox-exec') or not isinstance(sandbox['runtime_roots'], list):
            raise DriverError('invalid_sandbox_settings')
        for key in ('executable', 'python', 'dependencies'):
            _absolute(sandbox[key])
        for path in sandbox['runtime_roots']:
            _absolute(path)
    return value


def _load_local(path, label, report, inputs):
    if path is None:
        report['blockers'].append(label + '_required')
        return None
    try:
        path = paired.plain_path(path)
        raw = controller_api.BATCH['regular_bytes'](path)
        value = controller_api.BATCH['strict_json'](raw.decode('utf-8'))
        inputs[str(path)] = hashlib.sha256(raw).hexdigest()
        return value
    except (OSError, ValueError, UnicodeError):
        report['blockers'].append(label + '_invalid_json')
        return None


def _services(settings):
    values = {'deepseek_file_metadata_acceptable': False,
        'embedding_environment_present': 'VECTORIZE_API_KEY' in os.environ,
        'reranker_environment_present': 'RERANK_API_KEY' in os.environ,
        'provider_authentication_checked': False, 'provider_billing_checked': False,
        'credential_file_contents_read': False}
    if settings:
        try:
            path = paired.plain_path(settings['credential_file'])
            info = path.lstat()
            values['deepseek_file_metadata_acceptable'] = (stat.S_ISREG(info.st_mode)
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == os.getuid()
                and info.st_nlink == 1 and 16 <= info.st_size <= 1024)
        except (OSError, ValueError):
            pass
    return values


def _fresh_paths(state_root, output, protected):
    if state_root is None or output is None:
        raise DriverError('new_state_and_output_paths_required')
    state_root = paired.plain_path(_absolute(str(state_root)), exists=False)
    output = paired.plain_path(_absolute(str(output)), exists=False)
    if state_root.exists():
        raise DriverError('fresh_backend_state_required')
    if output.exists():
        raise DriverError('new_output_directory_required')
    if state_root.is_relative_to(output) or output.is_relative_to(state_root):
        raise DriverError('output_state_paths_overlap')
    for root in protected:
        root = Path(root).absolute()
        for target in (state_root, output):
            if target.is_relative_to(root) or root.is_relative_to(target):
                raise DriverError('output_overlaps_protected_input')
    return state_root, output


def _required_scopes(task, replicate, profile_hash, *, arms=paired.ARMS):
    deepseek = {'provider': 'deepseek', 'model': 'deepseek-flash',
        'endpoint': 'https://api.deepseek.com/responses', 'config_sha256': profile_hash}
    native = paired.native_scope_id(task, replicate)
    result = {native: {'kind': 'native', 'unit': None, 'public_path': None, 'providers': [deepseek]}}
    for arm in arms:
        name = 'p1-method-' + paired.digest({'task': task, 'replicate': replicate, 'arm': arm})[:24]
        providers = [deepseek]
        if arm == 'B':
            providers += [
                {'provider': 'openai', 'model': 'text-embedding-3-small',
                 'endpoint': 'https://api.openai.com/v1/embeddings', 'config_sha256': controller_api.RAWRAG_CONFIG_SHA256},
                {'provider': 'cohere', 'model': 'rerank-v3.5',
                 'endpoint': 'https://api.cohere.com/v2/rerank', 'config_sha256': controller_api.RAWRAG_CONFIG_SHA256}]
        result[name] = {'kind': 'method', 'unit': f"{task['task_id']}:{arm}:{replicate}",
                        'public_path': task['public_path'], 'providers': providers}
    return result


def _check_scopes(specs, required, task, replicate, status):
    controller = controller_api.CanonicalPairedController(specs, repo_root=ROOT, run=False)
    if not set(required) <= set(specs):
        raise DriverError('selected_block_scope_specs_missing')
    total = 0
    for name, binding in required.items():
        spec = specs[name]
        if any(spec[key] != binding[key] for key in ('kind', 'unit', 'public_path')):
            raise DriverError('selected_block_scope_binding_mismatch')
        minimum = 3 if spec['kind'] == 'native' or ':B:' in (spec['unit'] or '') else 1
        if spec['max_http_dispatches'] < minimum:
            raise DriverError('scope_dispatch_envelope_below_required_components')
        declared = [{key: provider[key] for key in ('provider', 'model', 'endpoint', 'config_sha256')}
                    for provider in spec['providers']]
        if sorted(declared, key=lambda row: row['provider']) != sorted(binding['providers'], key=lambda row: row['provider']):
            raise DriverError('selected_block_provider_binding_mismatch')
        total += controller_api.BATCH['fen'](spec['upper_bound_cny'])
    if total > controller_api.BATCH['fen'](status['remaining_cash_capacity']):
        raise DriverError('whole_block_cash_envelope_does_not_fit')
    for name, binding in required.items():
        spec = specs[name]
        # This uses the existing read-only reservation check. No provisional
        # checkpoint hash, fake receipt, reservation or fresh ledger is created.
        controller.ledger.reserve(kind=spec['kind'], attempt_id=name,
            upper_bound_cny=spec['upper_bound_cny'], billing_basis=spec['billing_basis'],
            unit=spec['unit'], public_path=spec['public_path'],
            native_binding=controller.native_binding(task_id=task['task_id'], project_id=task['project_id'],
                                                     replicate=replicate) if spec['kind'] == 'native' else None,
            run=False)
    return {'status': 'checked', 'selected_scope_count': len(required),
        'selected_total_upper_bound_cny': controller_api.BATCH['money'](total),
        'evidence_hashes_verified': True, 'pricing_truth_independently_verified': False,
        'reservation_performed': False}


def _device(settings, tasks, profile, report, *, arms=paired.ARMS):
    checks = report['checks']
    checks['executables'] = {}
    for name in ('codex', 'node'):
        candidate = Path(settings[name])
        available = candidate.is_file() and os.access(candidate, os.X_OK)
        checks['executables'][name] = {'file_executable': available, 'version_process_executed': False,
                                      'version_verified': False}
        if not available:
            report['blockers'].append(name + '_executable_unavailable')
    checks['tokenizer'] = {'verified': False, 'provider_billable_input_exact': False}
    if profile:
        try:
            counter = reader.ReferenceTokenizer(settings['tokenizer_path'], profile)
            checks['tokenizer'].update(verified=True, identity=counter.identity)
        except (OSError, ValueError, ImportError) as error:
            report['blockers'].append(_code(error, 'tokenizer_preflight_failed'))
    checks['python_workflows'] = {}
    for task_id, binding in tasks.items():
        config = settings['tasks'][task_id]
        try:
            observation = WORKFLOW['inspect'](binding['public_path'], config['python'])
            sandbox = SandboxRunner(config['sandbox'])
            if (Path(config['python']).resolve(strict=True) != Path(sandbox.config['python'])
                    or Path(config['python']).parent.parent / 'lib/python3.10/site-packages'
                    != Path(sandbox.config['dependencies'])):
                raise DriverError('sandbox_python_dependency_binding_mismatch')
            checks['python_workflows'][task_id] = {'status': 'pins_inspected',
                'inspection': observation, 'sandbox_configuration_checked': True,
                'sandbox_probe_executed': False, 'sandbox_instance_verified': False,
                'python_version_executed': False}
            if not observation['environment']['requirements_match']:
                report['blockers'].append(task_id + '_dependency_pins_mismatch')
        except (OSError, ValueError, KeyError, ImportError) as error:
            checks['python_workflows'][task_id] = {'status': 'blocked',
                'error_code': _code(error, 'python_workflow_preflight_failed'),
                'source_executions': 0, 'sandbox_probe_executed': False, 'python_version_executed': False}
            report['blockers'].append(task_id + '_runtime_unavailable')
    if 'B' not in arms:
        checks['rawrag'] = {'status': 'not_required_for_selected_development_arms',
            'config_sha256': controller_api.RAWRAG_CONFIG_SHA256,
            'pinned_source_bytes_verified': False, 'git_commit_and_cleanliness_checked': False,
            'transport_hooks_exercised': False}
        return
    dependency = rawrag.dependency_report()
    checks['rawrag'] = {'config_sha256': controller_api.RAWRAG_CONFIG_SHA256,
        'dependencies': dependency, 'pinned_source_bytes_verified': False,
        'git_commit_and_cleanliness_checked': False, 'transport_hooks_exercised': False}
    if not dependency['available']:
        report['blockers'].append('rawrag_runtime_dependencies_unavailable')
    try:
        rawrag.verify_source_files(settings['rawrag_upstream'])
        checks['rawrag']['pinned_source_bytes_verified'] = True
    except (OSError, ValueError, rawrag.ContractError):
        report['blockers'].append('rawrag_pinned_source_bytes_unavailable')


def _inspect(*, settings_path=None, scope_specs_path=None, state_root=None, output=None,
             task_id='w-101', replicate=1, order=paired.ARMS, profile_path=reader.PROFILE,
             development_selection=None):
    report = {'schema_version': 1, 'kind': 'p1-native-driver-preflight', 'mode': 'check',
        'status': 'blocked', 'dispatch_ready': False, 'scientific_ready': False,
        'model_requests': 0, 'network_requests': 0, 'source_executions': 0,
        'subprocesses_started': 0, 'ledger_writes': 0, 'credential_file_contents_read': False,
        'environment_credential_values_reported': False,
        'inspection_environment': {'platform': sys.platform, 'python_version': sys.version.split()[0],
            'remote_device_queried': False, 'settings_provided': settings_path is not None,
            'scope_specs_provided': scope_specs_path is not None},
        'checks': {}, 'required_scope_bindings': {}, 'blockers': [],
        'limits': ['Local eligibility is not service authentication, a price audit, native-host validation, or scientific readiness.',
                   'Actual host version, Python version, OS isolation and HTTP behavior remain checked during an explicit run.',
                   'Every real scope and provider request still requires the original canonical controller admission.',
                   'This block entry is not the experiment.py single-unit executable ABI.']}
    checks, inputs = report['checks'], {}
    base = ROOT / 'docs/research/p1-evidence-verification'
    auth_path = ROOT / controller_api.BATCH['AUTH_RELATIVE']
    ledger, status, relocation, task, profile = None, None, None, None, None
    if task_id not in paired.PROJECTS or type(replicate) is not int or replicate not in (1, 2):
        report['blockers'].append('unapproved_task_or_replicate')
    arms = paired.ARMS
    if development_selection is not None:
        # This internal seam is used only by development_driver. The full
        # native CLI and the frozen four-arm orchestration retain their gates.
        if (not isinstance(development_selection, (tuple, list))
                or tuple(development_selection) != ('A', 'C', 'D')):
            report['blockers'].append('exact_development_selection_required')
        else:
            arms = ('A', 'C', 'D')
        if not isinstance(order, (tuple, list)) or tuple(order) != arms:
            report['blockers'].append('exact_development_arm_order_required')
    elif (not isinstance(order, (tuple, list)) or len(order) != 4
            or not all(isinstance(arm, str) for arm in order) or set(order) != set(paired.ARMS)):
        report['blockers'].append('exact_four_arm_order_required')
    try:
        base_controller = controller_api.CanonicalPairedController({}, repo_root=ROOT, run=False)
        ledger = base_controller.ledger
        status = ledger.status()
        inputs[str(auth_path)] = ledger.auth_sha256
        checks['authorization'] = {'status': 'verified', 'sha256': ledger.auth_sha256,
            'batch_id': ledger.auth['batch_id'], 'new_authorization_created': False}
        fields = ('native_attempts_reserved', 'native_attempts_remaining', 'method_units_reserved',
            'method_units_remaining', 'diagnostic_attempts_reserved', 'added_cash_cap',
            'committed_cash_upper_bound', 'remaining_cash_capacity', 'actual_added_cash_total',
            'budget_breach_observed', 'journal_events', 'journal_head_sha256',
            'native_original_attempts_reserved', 'native_original_attempts_remaining',
            'native_supplemental_attempts_reserved', 'native_supplemental_attempts_remaining',
            'native_supplement_active', 'native_supplement_id', 'native_supplement_sha256', 'native_available_grants')
        checks['ledger'] = {key: status[key] for key in fields}
        if status['native_attempts_remaining'] < 1:
            report['blockers'].append('native_attempt_budget_exhausted')
        if status['budget_breach_observed']:
            report['blockers'].append('previous_budget_breach_blocks_dispatch')
        plan = ROOT / ledger.auth['source_plan']['relative_path']
        packages = [base / 'tasks/workflows/packages' / name for name in paired.PROJECTS]
        relocation = paired.create_relocation_receipt(plan, packages, auth_path)
        inputs[str(plan)] = paired.file_sha(plan)
        checks['relocation'] = {'status': 'verified', 'receipt_sha256': relocation['receipt_sha256'],
            'planned_development_units': relocation['planned_units'], 'original_plan_modified': False,
            'method_attempts_reserved': 0, 'native_attempts_created': 0}
    except (OSError, ValueError, KeyError) as error:
        report['blockers'].append(_code(error, 'authorization_ledger_or_relocation_failed'))
    try:
        profile_path = paired.plain_path(profile_path)
        profile = reader.load_profile(profile_path)
        inputs[str(profile_path)] = paired.file_sha(profile_path)
        checks['reader'] = {'status': 'configuration_verified', 'profile_sha256': paired.digest(profile),
                            'formal_study_frozen': False, 'host_runtime_executed': False}
    except (OSError, ValueError, KeyError) as error:
        report['blockers'].append(_code(error, 'reader_profile_invalid'))
    if relocation and profile and task_id in paired.PROJECTS and type(replicate) is int and replicate in (1, 2):
        source = next(row for row in relocation['tasks'] if row['task_id'] == task_id)
        task = {key: source[key] for key in ('task_id', 'project_id', 'public_path', 'public_sha256', 'taskpack_public_sha256')}
        task.update(original_request_sha256=paired.file_sha(Path(source['public_path']) / 'request.txt'),
                    shared_reader_config_sha256=paired.digest(profile))
        report['required_scope_bindings'] = _required_scopes(task, replicate, paired.digest(profile), arms=arms)
    settings = _load_local(settings_path, 'settings', report, inputs)
    if settings is not None:
        try:
            settings = _settings(settings)
        except (ValueError, TypeError) as error:
            report['blockers'].append(_code(error, 'settings_invalid'))
            settings = None
    checks['services'] = _services(settings)
    required_services = [('deepseek_file_metadata_acceptable', 'deepseek_credential_file_metadata_unavailable')]
    if 'B' in arms:
        required_services += [('embedding_environment_present', 'embedding_environment_unavailable'),
                              ('reranker_environment_present', 'reranker_environment_unavailable')]
    for key, code in required_services:
        if not checks['services'][key]:
            report['blockers'].append(code)
    if settings:
        _device(settings, {row['task_id']: row for row in relocation['tasks']} if relocation else {}, profile, report, arms=arms)
    specs = _load_local(scope_specs_path, 'scope_specs', report, inputs)
    if specs is not None and task and status:
        try:
            checks['scope_specs'] = _check_scopes(specs, report['required_scope_bindings'], task, replicate, status)
        except (OSError, ValueError, TypeError, KeyError) as error:
            report['blockers'].append(_code(error, 'scope_specs_invalid'))
    try:
        protected = [auth_path, *(Path(path) for path in inputs)]
        if ledger:
            protected += [ledger.state_dir]
        if relocation:
            protected += [row['public_path'] for row in relocation['tasks']]
        if settings:
            protected += [settings[key] for key in ('credential_file', 'tokenizer_path', 'rawrag_upstream')]
            protected += [config['sandbox']['dependencies'] for config in settings['tasks'].values()]
        state_root, output = _fresh_paths(state_root, output, protected)
        checks['output_paths'] = {'fresh': True, 'disjoint': True, 'created': False}
    except (OSError, ValueError) as error:
        report['blockers'].append(_code(error, 'output_paths_invalid'))
    report['blockers'] = list(dict.fromkeys(report['blockers']))
    report['dispatch_ready'] = not report['blockers']
    report['status'] = 'eligible_for_explicit_run' if report['dispatch_ready'] else 'blocked'
    report['input_file_sha256'] = [{'filename': Path(path).name, 'sha256': value} for path, value in inputs.items()]
    context = {'task': task, 'replicate': replicate, 'order': tuple(order) if isinstance(order, (tuple, list)) else (), 'settings': settings,
        'scope_specs': specs, 'state_root': state_root, 'output': output, 'profile_path': profile_path,
        'input_files': inputs, 'relocation': relocation}
    return report, context


def preflight(**kwargs):
    return _inspect(**kwargs)[0]


def _new_backend(**kwargs):
    # NativeBackend construction creates state. It is never imported/constructed
    # by the default read-only path, and never reached after a blocked preflight.
    from native_backend import NativeBackend
    return NativeBackend(**kwargs)


def run_block(*, run=False, **kwargs):
    if type(run) is not bool:
        raise DriverError('explicit_run_boolean_required')
    report, context = _inspect(**kwargs)
    if not run:
        return report
    if not report['dispatch_ready']:
        return {'schema_version': 1, 'kind': 'p1-native-driver-execution', 'mode': 'run',
            'status': 'blocked', 'dispatch_ready': False, 'execution_complete': False,
            'scientific_ready': False, 'quality_scored': False, 'model_requests': 0,
            'ledger_writes': 0, 'preflight': report}
    backend = None
    result = {'schema_version': 1, 'kind': 'p1-native-driver-execution', 'mode': 'run',
        'status': 'failed', 'dispatch_ready': False, 'execution_complete': False,
        'scientific_ready': False, 'quality_scored': False, 'model_requests': None,
        'ledger_writes': None, 'preflight': report,
        'counts_note': 'Use retained scope/provider artifacts for actual dispatch and measurement counts; wrapper status is not a scientific score.'}
    try:
        for path, expected in context['input_files'].items():
            if paired.file_sha(path) != expected:
                raise DriverError('input_changed_after_preflight')
        controller = controller_api.CanonicalPairedController(context['scope_specs'], repo_root=ROOT, run=True)
        backend = _new_backend(controller=controller, settings=context['settings'],
            state_root=context['state_root'], profile=context['profile_path'])
        observed = paired.run_paired_block(context['task'], context['replicate'], backend, controller,
            context['output'], order=context['order'], execution_mode='live')
        result['execution'] = observed
        complete = (observed.get('preparation', {}).get('status') == 'completed'
            and set(observed.get('arms', {})) == set(paired.ARMS)
            and all(row.get('status') == 'completed' for row in observed['arms'].values()))
        result['execution_complete'] = complete
        result['status'] = 'component_execution_completed' if complete else 'component_execution_incomplete'
    except Exception as error:
        result['error_code'] = _code(error, 'driver_execution_failed') if isinstance(error, DriverError) else 'driver_execution_failed'
    finally:
        if backend is not None:
            try:
                backend.close()
                result['backend_closed'] = True
            except Exception:
                result.update(status='failed', execution_complete=False, backend_closed=False,
                              cleanup_error='backend_close_failed')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', type=Path)
    parser.add_argument('--scope-specs', type=Path)
    parser.add_argument('--profile', type=Path, default=reader.PROFILE)
    parser.add_argument('--state-root', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--task', choices=tuple(paired.PROJECTS), default='w-101')
    parser.add_argument('--replicate', type=int, choices=(1, 2), default=1)
    parser.add_argument('--order', default='A,B,C,D', help='Previously selected four-arm order, each arm exactly once')
    parser.add_argument('--run', action='store_true', help='Explicitly attempt one native preparation plus four separately admitted method units')
    args = parser.parse_args(argv)
    try:
        result = run_block(run=args.run, settings_path=args.settings, scope_specs_path=args.scope_specs,
            profile_path=args.profile, state_root=args.state_root, output=args.output,
            task_id=args.task, replicate=args.replicate, order=tuple(args.order.split(',')))
        print(paired.canonical(result))
        return 0 if not args.run or result.get('execution_complete') is True else 2
    except (OSError, ValueError, TypeError, KeyError):
        print(paired.canonical({'status': 'blocked', 'error_code': 'invalid_driver_input',
                               'scientific_ready': False, 'dispatch_ready': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
