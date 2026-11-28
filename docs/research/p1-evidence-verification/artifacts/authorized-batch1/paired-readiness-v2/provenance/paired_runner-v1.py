#!/usr/bin/env python3
"""Prepare exact, detached public inputs for the authorized P1 source batch.

This controller-side bridge does not contain a Python workflow observer, a
native shared-parent capture implementation or an all-arm runtime. Inspection
and staging never launch providers, models, source tests or method attempts.
The experiment.py-compatible invocation fails closed with a readable result.
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
import tempfile

HERE = Path(__file__).resolve().parent
# taskpack's existing draft-plan bridge imports its sibling experiment module.
# Resolve that trusted sibling identically when called as a CLI or via runpy.
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
TASKPACK = runpy.run_path(str(HERE / 'taskpack.py'))
EXPERIMENT = runpy.run_path(str(HERE / 'experiment.py'))
ARMS = ('A', 'B', 'C', 'D')
EXPECTED = {'w-101': 'pallets/flask', 'w-102': 'psf/requests'}
SCHEMA = 'p1-paired-source-preparation-1'


class ContractError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plain_path(value, *, exists=True):
    path = Path(value).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ContractError('symlink_path_component')
    if exists and not path.exists():
        raise ContractError('path_missing')
    return path


def read_json(path):
    return TASKPACK['read_json'](plain_path(path))


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def inspect_plan(plan_path, packages):
    """Validate the complete 16-unit plan against explicitly supplied packages.

    Paths inside the draft plan are never followed. The caller selects the two
    package roots, which are fully checked before their public/ trees are read.
    A regenerated plan must match in full, including modes and public digests.
    """
    plan_path = plain_path(plan_path)
    plan = read_json(plan_path)
    if len(packages) != 2:
        raise ContractError('exactly_two_source_packages_required')
    roots, reports = {}, {}
    for candidate in packages:
        root = plain_path(candidate)
        report = TASKPACK['validate_package'](root)
        task = report['task_id']
        if task in roots or task not in EXPECTED or report['project_id'] != EXPECTED[task]:
            raise ContractError('approved_source_identity_mismatch')
        if report['kind'] != 'real_source_seed':
            raise ContractError('source_seed_required')
        roots[task], reports[task] = root, report
    if set(roots) != set(EXPECTED):
        raise ContractError('approved_source_identity_mismatch')
    wanted = TASKPACK['draft_plan']([roots[t] for t in EXPECTED], list(ARMS), 2)
    if plan != wanted:
        raise ContractError('source_plan_changed_or_unapproved_units')
    if len(plan['units']) != 16 or len({tuple(u[k] for k in ('task_id', 'arm', 'replicate')) for u in plan['units']}) != 16:
        raise ContractError('invalid_paired_denominator')
    budget = read_json(roots['w-101'] / 'public/budget.json')
    if budget != read_json(roots['w-102'] / 'public/budget.json') or budget['max_wall_seconds'] > 300:
        raise ContractError('shared_budget_mismatch_or_exceeds_approval')
    return plan, roots, reports, budget


def credential_presence(environ=None):
    """Only booleans; never read env files, key values into reports, or providers."""
    environ = os.environ if environ is None else environ
    return {name: bool(environ.get(name)) for name in ('VECTORIZE_API_KEY', 'RERANK_API_KEY')}


def public_initial_input(public):
    """Only the three admitted initial files. Source is available by later tools.

    Controller source mappings, evaluation folders, plan identity and complete
    source trees are deliberately not included in this initial reader payload.
    """
    public = plain_path(public)
    TASKPACK['inventory'](public)
    descriptor = read_json(public / 'task.json')
    required = {'schema_version', 'task_handle', 'material_kind', 'request_path',
                'workspace_path', 'budget_path', 'archive_path'}
    if (set(descriptor) != required or descriptor['schema_version'] != 'p1-public-task-1'
            or descriptor['task_handle'] not in EXPECTED or descriptor['material_kind'] != 'real_source_seed'
            or descriptor['request_path'] != 'request.txt' or descriptor['workspace_path'] != 'workspace'
            or descriptor['budget_path'] != 'budget.json' or descriptor['archive_path'] is not None):
        raise ContractError('unexpected_source_descriptor')
    budget = read_json(public / 'budget.json')
    TASKPACK['validate_budget'](budget)
    request = (public / 'request.txt').read_text(encoding='utf-8')
    data = {'task': descriptor, 'request': request, 'budget': budget}
    TASKPACK['reject_private_json_keys'](data)
    # Serialization overhead is also counted; no free wrapper or truncation.
    size = len(canonical(data).encode())
    if size > budget['max_initial_context_bytes']:
        raise ContractError('initial_reader_payload_budget_exceeded')
    return data, size


def admit_authorization(path, plan_path, plan):
    """Bind the recorded conversation scope; do not create a ledger or reserve."""
    if path is None:
        return None
    api = runpy.run_path(str(HERE / 'batch_limits.py'))
    value = api['validate_authorization'](read_json(path))
    binding = value['source_plan']
    if binding['sha256'] != file_sha(plan_path):
        raise ContractError('authorization_plan_binding_mismatch')
    shared = HERE.parents[1] / binding['shared_budget_relative_path']
    if file_sha(shared) != binding['shared_budget_sha256']:
        raise ContractError('authorization_shared_budget_binding_mismatch')
    keys = ('task_id', 'project_id', 'arm', 'replicate', 'public_sha256', 'taskpack_public_sha256')
    approved = [{k: row[k] for k in keys} for row in value['units']]
    if approved != plan['units']:
        raise ContractError('authorization_unit_binding_mismatch')
    return {'batch_id': value['batch_id'], 'authorization_file_sha256': file_sha(path),
            'approved_native_attempts': value['limits']['native_attempts'],
            'approved_method_units': value['limits']['method_units'],
            'added_cash_currency': 'CNY', 'added_cash_cap': value['limits']['added_cash_total'],
            'host_approval_attested': False, 'human_identity_attested': False}


def inspect(plan_path, packages, *, environ=None, authorization=None):
    plan, roots, reports, budget = inspect_plan(plan_path, packages)
    permission = admit_authorization(authorization, plan_path, plan)
    presence = credential_presence(environ)
    sources = []
    for task in EXPECTED:
        public = roots[task] / 'public'
        initial, size = public_initial_input(public)
        blockers = [
            'no_task_bound_native_prelude', 'no_task_bound_native_compaction_checkpoint',
            'no_complete_current_original_archive', 'python_execution_observer_not_implemented',
            'all_arm_runtime_not_integrated', 'runtime_isolation_not_enforced',
            'shared_reader_and_tokenizer_not_frozen', 'reader_token_limits_not_enforced',
            'full_usage_and_cost_capture_not_integrated',
        ]
        per_arm = {}
        for arm in ARMS:
            arm_blocks = list(blockers)
            if arm == 'B':
                arm_blocks.extend(['faithful_rawrag_provider_access_unverified',
                                   'rawrag_output_not_bound_to_this_checkpoint'])
                arm_blocks.extend('missing_' + key for key, present in presence.items() if not present)
            if arm in ('C', 'D'):
                arm_blocks.append('actual_claim_extraction_not_captured_for_this_checkpoint')
            if arm == 'D':
                arm_blocks.append('priming_and_reuse_receipts_not_bound_to_this_checkpoint')
            per_arm[arm] = {'runtime_ready': False, 'blocking_gates': arm_blocks}
        sources.append({'task_id': task, 'project_id': EXPECTED[task],
            'public_sha256': EXPERIMENT['public_digest'](public),
            'taskpack_public_sha256': reports[task]['public_sha256'],
            'initial_payload_sha256': digest(initial), 'initial_payload_bytes': size,
            'source_archive_present': False, 'arms': per_arm,
            'scientific_gates': reports[task]['acceptance']['blocking_gates']})
    return {'schema_version': SCHEMA, 'kind': 'zero_call_preflight',
        'plan_sha256': digest(plan), 'plan_file_sha256': file_sha(plan_path),
        'permissions_granted': True if permission else None, 'authorization_evidence': permission,
        'permission_note': 'Recorded conversation scope is not native-host or human-identity attestation.',
        'runtime_ready': False, 'scientific_ready': False, 'accepted_p1_task_count': 0,
        'planned_development_units': 16, 'prepared_source_count': 2,
        'model_requests': 0, 'provider_requests': 0, 'native_compactions': 0,
        'source_executions': 0, 'method_attempts_reserved': 0,
        'credentials_present': presence, 'credential_access_verified': False,
        'shared_budget': budget, 'sources': sources,
        'backend_contract': backend_contract(),
        'cost': {'actual_spend': None, 'standardized_cost': None,
                 'note': 'This preflight makes no provider calls; no cost is imputed for future work.'}}


def backend_contract():
    """Concrete integration seams; no boolean switch can activate a backend."""
    return {
        'implementation_registered': False,
        'required_runtime_operations': [
            'capture_actual_task_prelude_and_state_transition',
            'normalize_python_executions_with_before_after_workspace_binding',
            'admit_complete_original_archive_for_checkpoint',
            'compact_actual_native_parent_and_retain_native_receipt',
            'fork_same_unchanged_parent_for_all_four_arms',
            'run_official_rawrag_with_original_request_for_B',
            'extract_actual_proposals_without_evaluator_inputs_for_C_D',
            'prime_and_verify_unchanged_receipts_for_D',
            'deliver_full_method_packet_to_shared_reader_with_measured_budget',
            'capture_actual_continuation_actions_and_usage_without_evaluator_access',
        ],
        'checkpoint_identity_fields': ['task_id', 'replicate', 'public_sha256',
            'workspace_snapshot_sha256', 'native_parent_thread_id', 'native_capture_sha256',
            'native_compaction_item_id', 'source_archive_sha256', 'shared_reader_config_sha256'],
        'model_visible_inputs': ['detached verified public tree', 'shared original request',
                                'actual compacted parent', 'arm-produced evidence'],
        'controller_only_inputs': ['authorization', 'schedule', 'source mappings',
                                   'private evaluation', 'checkpoint admission receipts'],
        'evaluator_supplied_claims_or_source_locations_permitted': False,
        'B_lexical_or_dummy_fallback_permitted': False,
        'A_supplemental_evidence_permitted': False,
        'tokenizer_fallback_permitted': False,
        'host_or_OS_isolation_implemented_here': False,
    }


def stage(plan_path, packages, output, *, environ=None, authorization=None):
    """Materialize only verified public bytes, without dispatch or quota use."""
    before = inspect(plan_path, packages, environ=environ, authorization=authorization)
    _, roots, _, _ = inspect_plan(plan_path, packages)
    output = plain_path(output, exists=False)
    if output.exists():
        raise ContractError('output_already_exists')
    if any(output == root or output.is_relative_to(root) or root.is_relative_to(output) for root in roots.values()):
        raise ContractError('output_overlaps_source_package')
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix='.p1-paired-', dir=output.parent))
    try:
        (temp / 'public').mkdir()
        (temp / 'controller').mkdir(mode=0o700)
        exports = {}
        for task, root in roots.items():
            result = TASKPACK['export_public'](root, temp / 'public' / task)
            # taskpack inventories descendants; experiment.py also seals root mode.
            (temp / 'public' / task).chmod((root / 'public').stat().st_mode & 0o7777)
            source_hash = EXPERIMENT['public_digest'](root / 'public')
            staged_hash = EXPERIMENT['public_digest'](temp / 'public' / task)
            if staged_hash != source_hash:
                raise ContractError('detached_public_identity_mismatch')
            exports[task] = {'public_relative_path': 'public/' + task,
                'public_sha256': staged_hash, 'taskpack_public_sha256': result['public_sha256']}
        after = inspect(plan_path, packages, environ=environ, authorization=authorization)
        if before != after:
            raise ContractError('source_or_plan_changed_during_preparation')
        plan = read_json(plan_path)
        units = []
        for unit in plan['units']:
            key = {k: unit[k] for k in ('task_id', 'project_id', 'arm', 'replicate')}
            units.append({**key, 'unit_id': 'p1dev_' + digest({'key': key,
                'plan_sha256': before['plan_sha256'], 'public_sha256': unit['public_sha256']})[:24],
                **exports[unit['task_id']], 'timeout_seconds': 300,
                'status': 'prepared_not_dispatched', 'runtime_ready': False})
        preparation = {**before, 'kind': 'detached_public_preparation', 'exports': exports,
            'prepared_units': units, 'output_is_not_an_OS_sandbox': True,
            'preparation_sha256': digest({'plan_sha256': before['plan_sha256'], 'exports': exports,
                                          'prepared_units': units})}
        write_json(temp / 'controller/preparation.json', preparation)
        write_json(temp / 'controller/units.json', {'schema_version': SCHEMA, 'units': units})
        write_json(temp / 'controller/runtime-readiness.json', before)
        write_json(temp / 'controller/backend-contract.json', backend_contract())
        temp.rename(output)
        return preparation
    except BaseException:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def reject_dispatch(public, arm, replicate, run_id, output, timeout_seconds):
    """Fail before host/provider launch, with experiment.py-readable metadata.

    The outer dispatcher may already have reserved this attempt. We report
    failure honestly; never call it a skipped/unused allocation or completed arm.
    """
    if (arm not in ARMS or type(replicate) is not int or replicate not in (1, 2)
            or type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 300):
        raise ContractError('unapproved_runner_scope')
    if not isinstance(run_id, str) or not run_id or len(run_id) > 200:
        raise ContractError('invalid_run_id')
    public_initial_input(public)
    output = plain_path(output)
    if not output.is_dir() or output == Path(public).resolve() or output.is_relative_to(Path(public).resolve()) or Path(public).resolve().is_relative_to(output):
        raise ContractError('invalid_result_directory')
    result = {'schema_version': 1, 'status': 'host_error',
        'failure_reason': 'source_workflow_backend_not_implemented', 'trace_ref': 'pre-dispatch-block.json'}
    write_json(output / 'pre-dispatch-block.json', {'kind': 'blocked_before_backend_launch',
        'run_id': run_id, 'arm': arm, 'replicate': replicate, 'model_requests': 0,
        'provider_requests': 0, 'native_compactions': 0, 'source_executions': 0,
        'outer_attempt_reservation': 'Caller may already have reserved; do not reset or relabel it.',
        'backend_contract': backend_contract()})
    write_json(output / 'result.json', result)
    return result


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    if arguments and arguments[0].startswith('--'):
        # The fixed experiment.py runner ABI has no subcommand or --run flag.
        parser.add_argument('--public', type=Path, required=True)
        parser.add_argument('--arm', required=True)
        parser.add_argument('--replicate', type=int, required=True)
        parser.add_argument('--run-id', required=True)
        parser.add_argument('--output', type=Path, required=True)
        parser.add_argument('--timeout-seconds', type=float, required=True)
        args = parser.parse_args(arguments)
        result = reject_dispatch(args.public, args.arm, args.replicate, args.run_id,
                                 args.output, args.timeout_seconds)
        print(json.dumps(result, ensure_ascii=False))
        return 0  # Explicit host_error is read by experiment.py; never completed.
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('inspect', 'stage'):
        command = commands.add_parser(name)
        command.add_argument('--plan', type=Path, required=True)
        command.add_argument('--package', type=Path, required=True, action='append')
        command.add_argument('--authorization', type=Path)
        if name == 'stage':
            command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(arguments)
    result = (stage(args.plan, args.package, args.output, authorization=args.authorization)
              if args.command == 'stage' else inspect(args.plan, args.package, authorization=args.authorization))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ContractError, TASKPACK['ContractError'], EXPERIMENT['ContractError'], OSError, ValueError) as error:
        print(json.dumps({'status': 'contract_error', 'error_type': type(error).__name__,
                          'reason': str(error) if isinstance(error, ValueError) else 'filesystem_error',
                          'model_requests': 0, 'provider_requests': 0}), file=sys.stderr)
        raise SystemExit(2)
