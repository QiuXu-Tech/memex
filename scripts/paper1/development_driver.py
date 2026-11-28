#!/usr/bin/env python3
"""Inspect, or explicitly run, native preparation followed by development A/C/D.

The fixed B baseline remains a planned, unscored unit and is never dispatched
by this entry. One real backend and evidence-helper lifetime spans preparation
and all selected units. Default inspection creates no attempt or output. This
entry does not freeze a study, accept a task package, or produce quality scores.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import native_driver as native

paired = native.paired
SELECTED_ARMS = ('A', 'C', 'D')


def _deferred_baseline():
    return {'status': 'not_dispatched_dependency_blocked', 'score_status': 'not_scored',
        'attempt_created': False, 'scope_reserved': False, 'model_requests': 0,
        'fixed_config_sha256': native.controller_api.RAWRAG_CONFIG_SHA256,
        'reason': 'fixed_B_dependencies_not_admitted_for_selected_execution',
        'dependency_readiness_inspected': False}


def _metadata():
    return {'schema_version': 1, 'study_phase': 'development', 'development_only': True,
        'selected_arms': list(SELECTED_ARMS), 'planned_arms': list(paired.ARMS),
        'planned_block_units': 4, 'planned_development_units': 16,
        'execution_complete': False, 'selected_execution_complete': False,
        'scientific_ready': False, 'quality_scored': False, 'score_status': 'not_scored'}


def _unstarted(status):
    return {'preparation': {'status': status}, 'arms': {
        arm: (_deferred_baseline() if arm == 'B' else {'status': status, 'score_status': 'not_scored'})
        for arm in paired.ARMS}}


def run_selected(*, run=False, settings_path=None, scope_specs_path=None, state_root=None,
                 output=None, task_id='w-101', replicate=1, profile_path=native.reader.PROFILE):
    """Execute first attempts only; no retry, checkpoint import, or B reservation."""
    if type(run) is not bool:
        raise native.DriverError('explicit_run_boolean_required')
    report, context = native._inspect(settings_path=settings_path, scope_specs_path=scope_specs_path,
        state_root=state_root, output=output, task_id=task_id, replicate=replicate,
        profile_path=profile_path, order=SELECTED_ARMS, development_selection=SELECTED_ARMS)
    report = {**report, **_metadata(), 'kind': 'p1-development-selection-preflight', 'mode': 'check',
        'deferred_arms': {'B': _deferred_baseline()}}
    if not run:
        return report
    result = {**_metadata(), 'kind': 'p1-development-selection-execution', 'mode': 'run',
        'status': 'blocked', 'dispatch_ready': False, 'model_requests': 0, 'ledger_writes': 0,
        'preflight': report, 'execution': _unstarted('not_dispatched_preflight_blocked'),
        'counts_note': 'Retained scope and provider artifacts determine actual counts and costs; every planned unit remains unscored.'}
    if not report['dispatch_ready']:
        return result
    backend, output_root, active_arm = None, None, None
    result.update(status='failed', model_requests=None, ledger_writes=None,
                  execution=_unstarted('not_dispatched_execution_aborted'))
    try:
        for path, expected in context['input_files'].items():
            if paired.file_sha(path) != expected:
                raise native.DriverError('input_changed_after_preflight')
        controller = native.controller_api.CanonicalPairedController(context['scope_specs'], repo_root=native.ROOT, run=True)
        backend = native._new_backend(controller=controller, settings=context['settings'],
            state_root=context['state_root'], profile=context['profile_path'])
        output_root = paired._new_output(context['output'], context['task']['public_path'])
        prepared = paired.prepare_block(context['task'], context['replicate'], backend, controller,
            output_root / 'block', execution_mode='live')
        result['execution']['preparation'] = prepared
        if prepared.get('status') == 'completed':
            # Retain the original checkpoint and its first-attempt registry.
            # Calling run_unit(B) to discover a dependency failure would spend
            # B's registry slot before its scope admission, so it is not called.
            for arm in SELECTED_ARMS:
                active_arm = arm
                run_id = 'p1-method-' + paired.digest({
                    'task': context['task'], 'replicate': context['replicate'], 'arm': arm})[:24]
                result['execution']['arms'][arm] = paired.run_unit(output_root / 'block/checkpoint.json',
                    arm, run_id, output_root / run_id, backend, controller, execution_mode='live')
                active_arm = None
            result['selected_execution_complete'] = all(
                result['execution']['arms'][arm].get('status') == 'completed' for arm in SELECTED_ARMS)
        else:
            for arm in SELECTED_ARMS:
                result['execution']['arms'][arm] = {'status': 'not_dispatched_preparation_incomplete',
                                                    'score_status': 'not_scored'}
        result['status'] = ('selected_components_completed' if result['selected_execution_complete']
                            else 'selected_components_incomplete')
    except Exception as error:
        result['error_code'] = (native._code(error, 'development_execution_failed')
            if isinstance(error, native.DriverError) else 'development_execution_failed')
        if active_arm is not None:
            result['execution']['arms'][active_arm] = {'status': 'execution_exception',
                'score_status': 'not_scored', 'attempt_state': 'consult_original_checkpoint_registry',
                'usage_capture_complete': False}
    finally:
        if backend is not None:
            try:
                backend.close()
                result['backend_closed'] = True
            except Exception:
                result.update(status='failed', selected_execution_complete=False, backend_closed=False,
                              cleanup_error='backend_close_failed')
    if output_root is not None:
        try:
            paired.write_json(output_root / 'development-selection-result.json', result)
        except (OSError, ValueError):
            result.update(status='failed', selected_execution_complete=False,
                          artifact_error='development_result_write_failed')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', type=Path)
    parser.add_argument('--scope-specs', type=Path)
    parser.add_argument('--profile', type=Path, default=native.reader.PROFILE)
    parser.add_argument('--state-root', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--task', choices=tuple(paired.PROJECTS), default='w-101')
    parser.add_argument('--replicate', type=int, choices=(1, 2), default=1)
    parser.add_argument('--run', action='store_true',
        help='Explicitly attempt native preparation and the fixed development A/C/D first attempts')
    args = parser.parse_args(argv)
    try:
        result = run_selected(run=args.run, settings_path=args.settings, scope_specs_path=args.scope_specs,
            profile_path=args.profile, state_root=args.state_root, output=args.output,
            task_id=args.task, replicate=args.replicate)
        print(paired.canonical(result))
        return 0 if not args.run or result.get('selected_execution_complete') is True else 2
    except (OSError, ValueError, TypeError, KeyError):
        print(paired.canonical({**_metadata(), 'status': 'blocked',
            'error_code': 'invalid_development_driver_input', 'dispatch_ready': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
