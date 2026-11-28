#!/usr/bin/env python3
"""Controller-side paired runtime with injectable, accountable operations.

No provider, credential discovery, host or shell is implemented in this module.
Backends perform actual operations; controllers durably admit them before calls.
Existing authorizations and frozen source plans are read, never rewritten.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import sys
import time
from contextlib import contextmanager
from typing import Protocol

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
TASKPACK = runpy.run_path(str(HERE / 'taskpack.py'))
EXPERIMENT = runpy.run_path(str(HERE / 'experiment.py'))
LIMITS_API = runpy.run_path(str(HERE / 'batch_limits.py'))
ARMS = ('A', 'B', 'C', 'D')
PROJECTS = {'w-101': 'pallets/flask', 'w-102': 'psf/requests'}
HEX = re.compile(r'[a-f0-9]{64}\Z')
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
TASK_FIELDS = ('task_id', 'project_id', 'public_path', 'public_sha256',
               'taskpack_public_sha256', 'original_request_sha256', 'shared_reader_config_sha256')
CHECKPOINT_IDENTITY_FIELDS = ('task_id', 'replicate', 'public_sha256', 'workspace_snapshot_sha256',
    'native_parent_thread_id', 'native_capture_sha256', 'native_compaction_item_id',
    'source_archive_sha256', 'shared_reader_config_sha256', 'original_request_sha256')
LIMIT_FIELDS = ('max_initial_context_bytes', 'max_model_input_tokens', 'max_model_output_tokens',
    'max_source_open_bytes_per_call', 'max_source_open_bytes_total', 'max_source_open_calls',
    'max_tool_calls', 'max_wall_seconds')


class RuntimeContractError(ValueError):
    """Stable contract error, never arbitrary backend exception text."""


class PairedBackend(Protocol):
    """Each call returns exactly {value, usage_rows, trace_refs}.

    Contexts are controller-only. They MUST NOT be forwarded wholesale to a
    model. Artifact references are relative to the operation's output directory.
    The backend owns interruption/cancellation inside its supplied deadline.
    evidence_origin is 'native_host' or, only for isolated tests, 'contract_fixture'.
    No production code creates a synthetic native event.
    """
    evidence_origin: str

    def capture_parent(self, context: dict, *, output: Path, deadline: float) -> dict: ...
    def prime_D(self, context: dict, *, output: Path, deadline: float) -> dict: ...
    def compact_parent(self, context: dict, *, output: Path, deadline: float) -> dict: ...
    def verify_checkpoint(self, context: dict, *, output: Path, deadline: float) -> dict: ...
    def fork_parent(self, context: dict, *, output: Path, deadline: float) -> dict: ...
    def build_packet(self, context: dict, *, output: Path, deadline: float) -> dict: ...
    def continue_reader(self, context: dict, *, output: Path, deadline: float) -> dict: ...


class PairedController(Protocol):
    """One trusted issuer owns the actual batch ledger, including all clones.

    Admission returns the existing seven-field p1-dispatch-admission-receipt
    envelope. request_sha256 and intent_sha256 are supplied in the intent;
    receipts are bound to dispatch_id and cannot authorize another operation.
    admit_scope reserves one native attempt or one method unit, never both.
    before_operation durably records the operation before its backend call.
    finish_scope must retain unknown actual costs and uncertain dispatches.
    """
    def admit_scope(self, intent: dict) -> dict: ...
    def before_operation(self, intent: dict) -> dict: ...
    def finish_scope(self, intent: dict, result: dict) -> None: ...


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(plain_path(path).read_bytes()).hexdigest()


def plain_path(value, *, exists=True):
    candidate = Path(value).absolute()
    if any(p.is_symlink() for p in (candidate, *candidate.parents)):
        raise RuntimeContractError('symlink_path_component')
    if exists and not candidate.exists():
        raise RuntimeContractError('path_missing')
    return candidate


def read_json(path):
    return EXPERIMENT['read_json'](plain_path(path))


def exact(value, keys, code):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise RuntimeContractError(code)


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def create_relocation_receipt(plan_path, packages, authorization):
    """Explicitly derive local paths while retaining the original plan identity.

    The only admitted difference is each known public_by_replicate location.
    Original paths are treated as recorded identities and never dereferenced.
    Every other plan field, both tree digests and permission modes must match.
    This makes no reservation, grants no host permission, and freezes no study.
    """
    plan_path, authorization = plain_path(plan_path), plain_path(authorization)
    plan = read_json(plan_path)
    auth = LIMITS_API['validate_authorization'](read_json(authorization))
    if file_sha(plan_path) != auth['source_plan']['sha256']:
        raise RuntimeContractError('relocation_original_plan_binding_mismatch')
    if len(packages) != 2:
        raise RuntimeContractError('relocation_exactly_two_packages_required')
    roots, reports = {}, {}
    for package in packages:
        root = plain_path(package)
        report = TASKPACK['validate_package'](root)
        task = report['task_id']
        if task in roots or task not in PROJECTS or report['project_id'] != PROJECTS[task] or report['kind'] != 'real_source_seed':
            raise RuntimeContractError('relocation_source_identity_mismatch')
        roots[task], reports[task] = root, report
    if set(roots) != set(PROJECTS):
        raise RuntimeContractError('relocation_source_identity_mismatch')
    wanted = TASKPACK['draft_plan']([roots[t] for t in PROJECTS], list(ARMS), 2)
    original_tasks = plan.get('experiment_spec_fragment', {}).get('tasks')
    if not isinstance(original_tasks, list) or len(original_tasks) != 2:
        raise RuntimeContractError('relocation_original_task_binding_mismatch')
    restored, rows = copy.deepcopy(wanted), []
    for original, generated in zip(original_tasks, restored['experiment_spec_fragment']['tasks']):
        if original.get('task_id') != generated['task_id'] or original.get('project_id') != generated['project_id']:
            raise RuntimeContractError('relocation_original_task_binding_mismatch')
        locations = original.get('public_by_replicate')
        if (not isinstance(locations, dict) or set(locations) != {'1', '2'}
                or len(set(locations.values())) != 1
                or not all(isinstance(p, str) and Path(p).is_absolute() for p in locations.values())):
            raise RuntimeContractError('relocation_original_locations_invalid')
        task = generated['task_id']
        generated['public_by_replicate'] = copy.deepcopy(locations)
        approved = [u for u in auth['units'] if u['task_id'] == task]
        public = roots[task] / 'public'
        source_hash = EXPERIMENT['public_digest'](public)
        if any(u['public_sha256'] != source_hash or u['taskpack_public_sha256'] != reports[task]['public_sha256'] for u in approved):
            raise RuntimeContractError('relocation_authorized_public_mismatch')
        if file_sha(public / 'budget.json') != auth['source_plan']['shared_budget_sha256']:
            raise RuntimeContractError('relocation_shared_budget_mismatch')
        rows.append({'task_id': task, 'project_id': PROJECTS[task],
                     'original_public_path': locations['1'], 'public_path': str(public),
                     'public_sha256': source_hash, 'taskpack_public_sha256': reports[task]['public_sha256']})
    if restored != plan:
        raise RuntimeContractError('relocation_nonpath_plan_change')
    approved_units = [{k: u[k] for k in ('task_id', 'project_id', 'arm', 'replicate', 'public_sha256', 'taskpack_public_sha256')}
                      for u in auth['units']]
    if approved_units != plan['units']:
        raise RuntimeContractError('relocation_authorized_unit_mismatch')
    receipt = {'schema_version': 'p1-public-relocation-1', 'kind': 'explicit_public_path_relocation',
               'original_plan_file_sha256': file_sha(plan_path), 'authorization_file_sha256': file_sha(authorization),
               'shared_budget_file_sha256': auth['source_plan']['shared_budget_sha256'],
               'tasks': rows, 'planned_units': 16, 'native_attempts_created': 0,
               'method_attempts_reserved': 0, 'scientific_ready': False,
               'original_plan_modified': False}
    return {**receipt, 'receipt_sha256': digest(receipt)}


def admit_relocation(receipt, plan_path, packages, authorization):
    expected = create_relocation_receipt(plan_path, packages, authorization)
    if receipt != expected:
        raise RuntimeContractError('relocation_receipt_mismatch')
    return expected


def artifact(root, relative):
    if (not isinstance(relative, str) or not relative or Path(relative).is_absolute()
            or '..' in Path(relative).parts or Path(relative).as_posix() != relative or relative == '.'):
        raise RuntimeContractError('invalid_artifact_reference')
    root = plain_path(root)
    target = plain_path(root / relative)
    if not target.is_relative_to(root):
        raise RuntimeContractError('artifact_outside_output')
    return target


def artifact_record(root, target):
    target = plain_path(target)
    return {'path': target.relative_to(plain_path(root)).as_posix(),
            'sha256': EXPERIMENT['public_digest'](target) if target.is_dir() else file_sha(target),
            'kind': 'directory' if target.is_dir() else 'file'}


def validate_native_compaction(events_path, *, parent_thread_id, turn_id, item_id):
    """Check saved native protocol events, never infer a receipt from a summary.

    This validates capture structure and bytes. It does not authenticate the
    producer, associate another task with an old host run, or add observations.
    """
    for value in (parent_thread_id, turn_id, item_id):
        if not isinstance(value, str) or not LABEL.fullmatch(value):
            raise RuntimeContractError('native_compaction_identity_invalid')
    path = plain_path(events_path)
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise RuntimeContractError('native_compaction_capture_bound')
    data = path.read_bytes()
    if not data or not data.endswith(b'\n'):
        raise RuntimeContractError('native_compaction_capture_incomplete')
    try:
        rows = [EXPERIMENT['strict_json'](line) for line in data.splitlines() if line.strip()]
    except (ValueError, UnicodeError):
        raise RuntimeContractError('native_compaction_capture_invalid') from None
    if len(rows) > 20000 or any(not isinstance(row, dict) for row in rows):
        raise RuntimeContractError('native_compaction_capture_invalid')
    scoped = [(index, row) for index, row in enumerate(rows)
              if row.get('threadId') == parent_thread_id and row.get('turnId') == turn_id]
    starts = [i for i, row in scoped if row.get('event') == 'turn/started']
    items = [i for i, row in scoped if row.get('event') == 'item/completed'
             and row.get('item', {}).get('type') == 'contextCompaction' and row['item'].get('id') == item_id]
    ends = [i for i, row in scoped if row.get('event') == 'turn/completed' and row.get('status') == 'completed'
            and row.get('error') is None]
    all_compactions = [row for _, row in scoped if row.get('event') == 'item/completed'
                       and row.get('item', {}).get('type') == 'contextCompaction']
    if not (len(starts) == len(items) == len(ends) == len(all_compactions) == 1 and starts[0] < items[0] < ends[0]):
        raise RuntimeContractError('native_compaction_completed_item_and_turn_required')
    return {'kind': 'native_compaction_log_check', 'native_parent_thread_id': parent_thread_id,
            'native_compaction_turn_id': turn_id, 'native_compaction_item_id': item_id,
            'native_capture_sha256': hashlib.sha256(data).hexdigest(), 'authenticity_attested': False}


def _native_prelude(events_path, parent, request):
    path = plain_path(events_path)
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise RuntimeContractError('native_prelude_capture_bound')
    data = path.read_bytes()
    if not data or not data.endswith(b'\n'):
        raise RuntimeContractError('native_prelude_capture_incomplete')
    try:
        rows = [EXPERIMENT['strict_json'](line) for line in data.splitlines() if line.strip()]
    except (ValueError, UnicodeError):
        raise RuntimeContractError('native_prelude_capture_invalid') from None
    turns = {row.get('turnId') for row in rows if isinstance(row, dict) and row.get('threadId') == parent
             and row.get('event') == 'turn/completed' and row.get('status') == 'completed' and row.get('error') is None}
    requests = []
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeContractError('native_prelude_capture_invalid')
        if (row.get('threadId') == parent and row.get('turnId') in turns and row.get('event') == 'item/completed'
                and row.get('item', {}).get('type') == 'userMessage'):
            requests.extend(part.get('text', '') for part in row['item'].get('content', [])
                            if isinstance(part, dict) and part.get('type') == 'text')
    if not request.strip() or not any(request.strip() in text for text in requests if isinstance(text, str)):
        raise RuntimeContractError('native_prelude_original_request_not_observed')
    return data


def validate_task(task, replicate):
    exact(task, TASK_FIELDS, 'invalid_runtime_task')
    if (task['task_id'] not in PROJECTS or task['project_id'] != PROJECTS[task['task_id']]
            or type(replicate) is not int or replicate not in (1, 2)):
        raise RuntimeContractError('unapproved_task_or_replicate')
    for key in TASK_FIELDS:
        if key.endswith('_sha256') and not HEX.fullmatch(str(task[key])):
            raise RuntimeContractError('invalid_runtime_digest')
    public = plain_path(task['public_path'])
    if (str(public) != task['public_path'] or EXPERIMENT['public_digest'](public) != task['public_sha256']
            or TASKPACK['digest'](TASKPACK['inventory'](public)) != task['taskpack_public_sha256']
            or file_sha(public / 'request.txt') != task['original_request_sha256']):
        raise RuntimeContractError('runtime_public_binding_mismatch')
    descriptor, budget = read_json(public / 'task.json'), read_json(public / 'budget.json')
    if descriptor.get('task_handle') != task['task_id'] or descriptor.get('material_kind') != 'real_source_seed':
        raise RuntimeContractError('runtime_source_descriptor_mismatch')
    TASKPACK['validate_budget'](budget)
    initial = {'task': descriptor, 'request': (public / 'request.txt').read_text(), 'budget': budget}
    if len(canonical(initial).encode()) > budget['max_initial_context_bytes']:
        raise RuntimeContractError('runtime_initial_context_budget')
    return {key: budget[key] for key in LIMIT_FIELDS}


def native_scope_id(task, replicate):
    return 'p1-native-' + digest({'task': task, 'replicate': replicate})[:24]


def validate_origin(backend, execution_mode, checkpoint=None):
    origin = getattr(backend, 'evidence_origin', None)
    required = {'live': 'native_host', 'contract_test': 'contract_fixture'}.get(execution_mode)
    if required is None or origin != required or (checkpoint is not None and checkpoint['evidence_origin'] != required):
        raise RuntimeContractError('runtime_evidence_origin_mismatch')


def limits_for(task, replicate, overrides=None):
    maximum = validate_task(task, replicate)
    if overrides is None:
        return maximum
    exact(overrides, LIMIT_FIELDS, 'invalid_runtime_limits')
    if any(type(overrides[key]) is not int or not 0 < overrides[key] <= maximum[key] for key in LIMIT_FIELDS):
        raise RuntimeContractError('runtime_limit_exceeds_public_budget')
    return dict(overrides)


def _admission(receipt, intent):
    exact(receipt, ('schema_version', 'kind', 'decision', 'dispatch_id', 'intent_sha256', 'request_sha256', 'admission_id'),
          'runtime_admission_invalid')
    if (receipt['schema_version'] != 1 or receipt['kind'] != 'p1-dispatch-admission-receipt'
            or receipt['decision'] != 'allow' or not isinstance(receipt['admission_id'], str)
            or not LABEL.fullmatch(receipt['admission_id'])
            or any(receipt[k] != intent[k] for k in ('dispatch_id', 'intent_sha256', 'request_sha256'))):
        raise RuntimeContractError('runtime_admission_binding_mismatch')


class _Scope:
    """Single process forward-only journal. A started operation is never replayed."""
    def __init__(self, task, replicate, arm, run_id, kind, output, controller, backend, timeout, checkpoint=None):
        self.task, self.replicate, self.arm = task, replicate, arm
        self.run_id, self.kind, self.output = run_id, kind, output
        self.scope_id = native_scope_id(task, replicate) if kind == 'native' else run_id
        self.controller, self.backend, self.checkpoint = controller, backend, checkpoint
        self.deadline = time.monotonic() + timeout
        self.journal = EXPERIMENT['Journal'](output / 'operations.jsonl')
        self.index, self.usages, self.endings = 0, [], []
        self.admitted = False
        self.admit_intent = self.intent('admit_scope', {'task': task, 'replicate': replicate, 'arm': arm}, 'admit_scope')
        (output / 'usage.jsonl').touch(exist_ok=False)

    def intent(self, operation, request, suffix):
        value = {'schema_version': 1, 'scope_id': self.scope_id, 'kind': self.kind, 'operation': operation,
            'task_id': self.task['task_id'], 'project_id': self.task['project_id'], 'replicate': self.replicate,
            'arm': self.arm, 'run_id': self.run_id,
            'checkpoint_sha256': self.checkpoint['checkpoint_sha256'] if self.checkpoint else None,
            'sealed_checkpoint_sha256': self.checkpoint['sealed_checkpoint_sha256'] if self.checkpoint else None,
            'dispatch_id': self.scope_id + ':' + suffix, 'request_sha256': digest(request)}
        return {**value, 'intent_sha256': digest(value)}

    def check_deadline(self):
        if time.monotonic() >= self.deadline:
            raise RuntimeContractError('runtime_deadline_exhausted')

    def admit(self):
        self.check_deadline()
        self.journal.append({'event': 'scope_requested', 'intent': self.admit_intent})
        receipt = self.controller.admit_scope(copy.deepcopy(self.admit_intent))
        _admission(receipt, self.admit_intent)
        write_json(self.output / 'scope-admission.json', receipt)
        self.journal.append({'event': 'scope_admitted', 'admission_sha256': digest(receipt)})
        self.admitted = True
        self.check_deadline()

    def capture_usage(self, rows, root):
        if not isinstance(rows, list):
            raise RuntimeContractError('invalid_runtime_usage_rows')
        for source in rows:
            if not isinstance(source, dict) or source.get('event') not in ('usage', 'component_end'):
                raise RuntimeContractError('invalid_runtime_usage_row')
            row = copy.deepcopy(source)
            if row['event'] == 'component_end':
                exact(row, ('event', 'component', 'coverage', 'usage_ids', 'reason', 'evidence_ref'), 'invalid_component_end')
                if (not isinstance(row['usage_ids'], list) or any(not isinstance(i, str) or not LABEL.fullmatch(i) for i in row['usage_ids'])
                        or row['coverage'] not in ('measured', 'not_applicable', 'not_performed', 'incomplete')
                        or not all(isinstance(row[k], str) and row[k] for k in ('component', 'reason', 'evidence_ref'))):
                    raise RuntimeContractError('invalid_component_end')
            else:
                required = {'event', 'usage_id', 'measurement_id', 'operation_id', 'component', 'counter_kind', 'values', 'source_ref'}
                optional = {'provider', 'model', 'request_id', 'source_sha256'}
                if not required <= set(row) or set(row) - required - optional:
                    raise RuntimeContractError('invalid_runtime_usage_row')
                if not all(isinstance(row[k], str) and row[k] for k in required - {'values'}):
                    raise RuntimeContractError('invalid_runtime_usage_row')
            field = 'source_ref' if row['event'] == 'usage' else 'evidence_ref'
            target = artifact(root, row.get(field))
            if not target.is_file():
                raise RuntimeContractError('usage_evidence_must_be_file')
            row[field] = target.relative_to(self.output).as_posix()
            if row['event'] == 'component_end':
                self.endings.append(row)
                continue
            if row.get('counter_kind') != 'delta' or not isinstance(row.get('values'), dict):
                raise RuntimeContractError('runtime_usage_requires_observed_delta')
            if 'source_sha256' in row and row['source_sha256'] != file_sha(target):
                raise RuntimeContractError('usage_source_hash_mismatch')
            self.usages.append(row)
            with (self.output / 'usage.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(canonical(row) + '\n'); stream.flush(); os.fsync(stream.fileno())

    def operation(self, name, context):
        self.check_deadline()
        self.index += 1
        folder = self.output / 'operations' / f'{self.index:02d}-{name}'
        folder.mkdir(parents=True)
        intent = self.intent(name, context, str(self.index) + ':' + name)
        self.journal.append({'event': 'operation_started', 'operation': name, 'intent': intent,
                             'output': folder.relative_to(self.output).as_posix()})
        receipt = self.controller.before_operation(copy.deepcopy(intent))
        _admission(receipt, intent)
        write_json(folder / 'admission.json', receipt)
        self.journal.append({'event': 'operation_admitted', 'operation': name, 'dispatch_id': intent['dispatch_id']})
        self.check_deadline()
        try:
            response = getattr(self.backend, name)(copy.deepcopy(context), output=folder, deadline=self.deadline)
        except Exception:
            # A failed host/baseline may still have incurred measured usage.
            # This optional hook reads only artifacts already durably captured;
            # it must not dispatch, retry, load credentials or infer missing usage.
            hook = getattr(self.backend, 'capture_failure_usage', None)
            if callable(hook):
                try:
                    self.capture_usage(hook(copy.deepcopy(context), output=folder), folder)
                    self.journal.append({'event': 'failed_operation_usage_retained', 'operation': name})
                except Exception:
                    self.journal.append({'event': 'failed_operation_usage_unavailable', 'operation': name})
            raise
        exact(response, ('value', 'usage_rows', 'trace_refs'), 'invalid_backend_response')
        if not isinstance(response['value'], dict) or not isinstance(response['trace_refs'], list):
            raise RuntimeContractError('invalid_backend_response')
        for ref in response['trace_refs']:
            exact(ref, ('path', 'sha256'), 'invalid_backend_trace_reference')
            if file_sha(artifact(folder, ref['path'])) != ref['sha256']:
                raise RuntimeContractError('backend_trace_hash_mismatch')
        write_json(folder / 'response.json', response)
        self.capture_usage(response['usage_rows'], folder)
        self.check_deadline()
        self.journal.append({'event': 'operation_completed', 'operation': name,
            'dispatch_id': intent['dispatch_id'], 'response_sha256': file_sha(folder / 'response.json')})
        return response['value'], folder

    def seal_usage(self):
        # Preserve every original stage seal. Repeated measured components can
        # be merged only after all stages finish; no unobserved quantity is added.
        inventory = {'original_component_ends': self.endings, 'usage_ids': [r.get('usage_id') for r in self.usages]}
        write_json(self.output / 'usage-inventory.json', inventory)
        for component in sorted({r.get('component') for r in self.endings if isinstance(r.get('component'), str)}):
            ends = [r for r in self.endings if r.get('component') == component]
            measured = all(r.get('coverage') == 'measured' for r in ends)
            declared = [uid for r in ends for uid in r.get('usage_ids', [])]
            actual = [r.get('usage_id') for r in self.usages if r.get('component') == component]
            if len(ends) == 1:
                row = ends[0]
            else:
                row = {'event': 'component_end', 'component': component,
                    'coverage': 'measured' if measured and len(declared) == len(set(declared)) and sorted(declared) == sorted(actual) else 'incomplete',
                    'usage_ids': declared, 'reason': 'aggregated_observed_stage_seals', 'evidence_ref': 'usage-inventory.json'}
            with (self.output / 'usage.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(canonical(row) + '\n'); stream.flush(); os.fsync(stream.fileno())

    def finish(self, result):
        self.seal_usage()
        proposal = {'scope_id': self.scope_id, 'status': result['status'],
            'failure_reason': result.get('failure_reason'), 'actual_added_cost_cny': None,
            'usage_capture_complete': False, 'output_sha256': None}
        write_json(self.output / 'terminal-proposal.json', proposal)
        if self.admitted:
            try:
                self.controller.finish_scope(copy.deepcopy(self.admit_intent), proposal)
            except Exception:
                result = {'status': 'capture_incomplete', 'failure_reason': 'runtime_controller_finish_unconfirmed',
                          'trace_ref': 'terminal-proposal.json'}
        self.journal.append({'event': 'scope_finished', 'status': result['status'], 'actual_added_cost_cny': None})
        write_json(self.output / 'result.json', result)
        write_json(self.output / 'runtime-receipt.json', {'schema_version': 1, 'scope_id': self.scope_id,
            'evidence_origin': self.backend.evidence_origin, 'status': result['status'],
            'scientific_ready': False, 'actual_added_cost_cny': None, 'standardized_cost': None,
            'usage_capture_complete': False, 'cost_note': 'Full-pipeline completeness requires the frozen measurement audit.'})
        return result


def _error_result(error):
    code = str(error) if isinstance(error, RuntimeContractError) else 'runtime_backend_or_controller_error'
    exhausted = 'budget' in code or 'deadline' in code or 'limit_exceeds' in code
    return {'status': 'budget_exhausted' if exhausted else 'capture_incomplete',
            'failure_reason': code, 'trace_ref': 'operations.jsonl'}


def _new_output(output, *protected, allow_wrapper_logs=False):
    output = plain_path(output, exists=False)
    for root in protected:
        root = plain_path(root)
        if output == root or output.is_relative_to(root) or root.is_relative_to(output):
            raise RuntimeContractError('runtime_output_overlaps_input')
    if output.exists():
        if not allow_wrapper_logs or not output.is_dir() or {p.name for p in output.iterdir()} - {'stdout.log', 'stderr.log'}:
            raise RuntimeContractError('runtime_output_already_exists')
    else:
        output.mkdir(parents=True)
    return output


def _workspace(path):
    path = plain_path(path)
    if not path.is_dir() or any(p.is_file() and p.stat().st_nlink != 1 for p in path.rglob('*')):
        raise RuntimeContractError('workspace_must_be_independent_regular_tree')
    return EXPERIMENT['public_digest'](path)


def _archive(path, task_id):
    api = runpy.run_path(str(HERE / 'rawrag_adapter.py'))
    config = api['load_config']()
    archive = api['validate_archive'](read_json(path), config['limits'])
    if archive['taskId'] != task_id:
        raise RuntimeContractError('source_archive_task_binding_mismatch')
    return archive


def _checkpoint_fields():
    return set(CHECKPOINT_IDENTITY_FIELDS) | {'schema_version', 'evidence_origin', 'task', 'project_id',
        'native_compaction_turn_id', 'extraction_sha256', 'd_prime_sha256', 'artifacts', 'checkpoint_sha256', 'sealed_checkpoint_sha256'}


def load_checkpoint(checkpoint_path, *, expected_task=None, replicate=None, _candidate=False):
    checkpoint_path = plain_path(checkpoint_path)
    # Imports and per-unit materialization copy ancillary evidence too. Reject
    # every non-regular/symlink entry before copytree can follow an unreferenced
    # sidecar outside the admitted checkpoint. This is a safety check, not a
    # new checkpoint identity or a rewrite of any frozen scientific input.
    EXPERIMENT['public_digest'](checkpoint_path.parent)
    if not _candidate:
        if checkpoint_path.name != 'checkpoint.json':
            raise RuntimeContractError('checkpoint_must_be_published')
        terminal, terminal_error = EXPERIMENT['result_metadata'](checkpoint_path.parent)
        if terminal_error or terminal.get('status') != 'completed':
            raise RuntimeContractError('checkpoint_preparation_not_completed')
    value, root = read_json(checkpoint_path), checkpoint_path.parent
    exact(value, _checkpoint_fields(), 'invalid_task_bound_checkpoint_schema')
    if value['schema_version'] != 'p1-task-native-checkpoint-1' or value['evidence_origin'] not in ('native_host', 'contract_fixture'):
        raise RuntimeContractError('invalid_task_bound_checkpoint_schema')
    if digest({k: v for k, v in value.items() if k != 'sealed_checkpoint_sha256'}) != value['sealed_checkpoint_sha256']:
        raise RuntimeContractError('checkpoint_seal_mismatch')
    if digest({k: value[k] for k in CHECKPOINT_IDENTITY_FIELDS}) != value['checkpoint_sha256']:
        raise RuntimeContractError('checkpoint_identity_mismatch')
    validate_task(value['task'], value['replicate'])
    if (expected_task is not None and value['task'] != expected_task) or (replicate is not None and value['replicate'] != replicate):
        raise RuntimeContractError('checkpoint_task_binding_mismatch')
    for key in ('task_id', 'project_id', 'public_sha256', 'original_request_sha256', 'shared_reader_config_sha256'):
        if value[key] != value['task'][key]:
            raise RuntimeContractError('checkpoint_task_binding_mismatch')
    exact(value['artifacts'], ('workspace', 'source_archive', 'native_capture', 'native_prelude', 'extraction', 'd_prime'), 'checkpoint_artifacts_missing')
    paths = {}
    for name, ref in value['artifacts'].items():
        exact(ref, ('path', 'sha256', 'kind'), 'checkpoint_artifact_invalid')
        target = artifact(root, ref['path'])
        if artifact_record(root, target) != ref:
            raise RuntimeContractError('checkpoint_artifact_changed')
        paths[name] = target
    if (_workspace(paths['workspace']) != value['workspace_snapshot_sha256']
            or any(file_sha(paths[name]) != value[field] for name, field in
                [('source_archive', 'source_archive_sha256'), ('native_capture', 'native_capture_sha256'),
                 ('extraction', 'extraction_sha256'), ('d_prime', 'd_prime_sha256')])):
        raise RuntimeContractError('checkpoint_artifact_binding_mismatch')
    _archive(paths['source_archive'], value['task_id'])
    validate_native_compaction(paths['native_capture'], parent_thread_id=value['native_parent_thread_id'],
        turn_id=value['native_compaction_turn_id'], item_id=value['native_compaction_item_id'])
    prefix = _native_prelude(paths['native_prelude'], value['native_parent_thread_id'],
                            (Path(value['task']['public_path']) / 'request.txt').read_text())
    if not paths['native_capture'].read_bytes().startswith(prefix):
        raise RuntimeContractError('compaction_capture_dropped_native_prelude')
    extraction, prime = read_json(paths['extraction']), read_json(paths['d_prime'])
    if (extraction.get('ok') is not True or not isinstance(extraction.get('claims'), list) or not extraction['claims']
            or not isinstance(extraction.get('rawOutput'), str) or extraction.get('coverageEstablished') is not False
            or prime.get('extraction_sha256') != value['extraction_sha256']
            or prime.get('source_archive_sha256') != value['source_archive_sha256']
            or not isinstance(prime.get('receipts'), list) or not prime['receipts']):
        raise RuntimeContractError('checkpoint_extraction_or_priming_unbound')
    return value


def prepare_block(task, replicate, backend, controller, output, *, timeout_seconds=600, execution_mode='live'):
    """Capture, prime and compact once. Controller must reserve a native attempt.

    Existing consumed native slots remain consumed. This cannot use a method
    reservation to create a parent, and failures never mint a checkpoint.
    """
    limits = validate_task(task, replicate)
    validate_origin(backend, execution_mode)
    if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= 600:
        raise RuntimeContractError('native_wall_limit_exceeds_approval')
    output = _new_output(output, task['public_path'])
    scope = _Scope(task, replicate, None, native_scope_id(task, replicate), 'native', output, controller, backend, timeout_seconds)
    context = {'task': task, 'replicate': replicate, 'original_request': (Path(task['public_path']) / 'request.txt').read_text(), 'limits': limits}
    checkpoint = None
    try:
        scope.admit()
        captured, folder = scope.operation('capture_parent', context)
        exact(captured, ('task_binding', 'native_parent_thread_id', 'workspace_path', 'source_archive_path', 'native_capture_path'),
              'invalid_parent_capture')
        binding = {key: (replicate if key == 'replicate' else task[key]) for key in
                   ('task_id', 'replicate', 'public_sha256', 'original_request_sha256', 'shared_reader_config_sha256')}
        if captured['task_binding'] != binding or not LABEL.fullmatch(str(captured['native_parent_thread_id'])):
            raise RuntimeContractError('parent_capture_task_mismatch')
        workspace = artifact(folder, captured['workspace_path'])
        archive = artifact(folder, captured['source_archive_path'])
        initial_events = artifact(folder, captured['native_capture_path'])
        prefix = _native_prelude(initial_events, captured['native_parent_thread_id'], context['original_request'])
        prelude_snapshot = output / 'prelude-native-prefix.jsonl'
        with prelude_snapshot.open('xb') as stream:
            stream.write(prefix); stream.flush(); os.fsync(stream.fileno())
        _archive(archive, task['task_id'])
        parent = {**captured, 'workspace_path': str(workspace), 'source_archive_path': str(archive),
            'native_capture_path': str(initial_events), 'source_archive_sha256': file_sha(archive),
            'workspace_snapshot_sha256': _workspace(workspace)}
        context['parent'] = parent
        primed, prime_folder = scope.operation('prime_D', context)
        exact(primed, ('extraction_path', 'receipts_path'), 'invalid_priming_result')
        extraction, prime = artifact(prime_folder, primed['extraction_path']), artifact(prime_folder, primed['receipts_path'])
        context['prime'] = {'extraction_path': str(extraction), 'receipts_path': str(prime),
                            'extraction_sha256': file_sha(extraction), 'd_prime_sha256': file_sha(prime)}
        compacted, compact_folder = scope.operation('compact_parent', context)
        exact(compacted, ('native_parent_thread_id', 'turn_id', 'item_id', 'native_capture_path'), 'invalid_compaction_result')
        if compacted['native_parent_thread_id'] != parent['native_parent_thread_id']:
            raise RuntimeContractError('compaction_parent_mismatch')
        events = artifact(compact_folder, compacted['native_capture_path'])
        if not events.read_bytes().startswith(prefix):
            raise RuntimeContractError('compaction_capture_dropped_native_prelude')
        validate_native_compaction(events, parent_thread_id=parent['native_parent_thread_id'],
                                  turn_id=compacted['turn_id'], item_id=compacted['item_id'])
        if file_sha(archive) != parent['source_archive_sha256'] or _workspace(workspace) != parent['workspace_snapshot_sha256']:
            raise RuntimeContractError('parent_changed_during_priming_or_compaction')
        checkpoint = {'schema_version': 'p1-task-native-checkpoint-1', 'evidence_origin': backend.evidence_origin,
            'task': task, 'task_id': task['task_id'], 'project_id': task['project_id'], 'replicate': replicate,
            'public_sha256': task['public_sha256'], 'original_request_sha256': task['original_request_sha256'],
            'shared_reader_config_sha256': task['shared_reader_config_sha256'],
            'workspace_snapshot_sha256': parent['workspace_snapshot_sha256'], 'source_archive_sha256': file_sha(archive),
            'native_parent_thread_id': parent['native_parent_thread_id'], 'native_capture_sha256': file_sha(events),
            'native_compaction_turn_id': compacted['turn_id'], 'native_compaction_item_id': compacted['item_id'],
            'extraction_sha256': file_sha(extraction), 'd_prime_sha256': file_sha(prime),
            'artifacts': {name: artifact_record(output, path) for name, path in
                [('workspace', workspace), ('source_archive', archive), ('native_capture', events), ('native_prelude', prelude_snapshot),
                 ('extraction', extraction), ('d_prime', prime)]}}
        checkpoint['checkpoint_sha256'] = digest({key: checkpoint[key] for key in CHECKPOINT_IDENTITY_FIELDS})
        checkpoint['sealed_checkpoint_sha256'] = digest(checkpoint)
        # Validate a private candidate before publishing the immutable checkpoint.
        write_json(output / 'checkpoint-candidate.json', checkpoint)
        load_checkpoint(output / 'checkpoint-candidate.json', expected_task=task, replicate=replicate, _candidate=True)
        scope.check_deadline()
        result = {'status': 'completed', 'trace_ref': 'checkpoint-candidate.json'}
    except Exception as error:
        result = _error_result(error)
    result = scope.finish(result)
    if result['status'] == 'completed':
        write_json(output / 'checkpoint.json', checkpoint)
    return {**result, 'scientific_ready': False,
        'checkpoint_sha256': checkpoint['checkpoint_sha256'] if result['status'] == 'completed' else None,
        'sealed_checkpoint_sha256': checkpoint['sealed_checkpoint_sha256'] if result['status'] == 'completed' else None}


@contextmanager
def _unit_registry(root):
    state = plain_path(root / 'unit-state', exists=False)
    state.mkdir(exist_ok=True)
    lock_path = state / 'lock'
    if lock_path.is_symlink():
        raise RuntimeContractError('runtime_registry_symlink')
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'r+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield EXPERIMENT['Journal'](state / 'events.jsonl')
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _reserve_unit(root, checkpoint, arm, run_id, output):
    with _unit_registry(root) as journal:
        if any(row.get('arm') == arm or row.get('run_id') == run_id for row in journal.records if row.get('event') == 'unit_reserved'):
            raise RuntimeContractError('paired_method_unit_already_reserved')
        journal.append({'event': 'unit_reserved', 'arm': arm, 'run_id': run_id,
            'checkpoint_sha256': checkpoint['checkpoint_sha256'], 'output': str(output)})


def _register_fork(root, checkpoint, arm, run_id, fork):
    with _unit_registry(root) as journal:
        if any(row.get('thread_id') == fork['thread_id'] or row.get('workspace_path') == fork['workspace_path']
               for row in journal.records if row.get('event') == 'fork_registered'):
            raise RuntimeContractError('fork_or_workspace_reused_across_arms')
        journal.append({'event': 'fork_registered', 'arm': arm, 'run_id': run_id,
            'checkpoint_sha256': checkpoint['checkpoint_sha256'], 'thread_id': fork['thread_id'],
            'workspace_path': fork['workspace_path']})


def _verify_parent(scope, context):
    value, _ = scope.operation('verify_checkpoint', context)
    exact(value, ('binding',), 'invalid_checkpoint_revalidation')
    expected = {key: context['checkpoint'][key] for key in CHECKPOINT_IDENTITY_FIELDS}
    if value['binding'] != expected:
        raise RuntimeContractError('native_parent_changed_after_checkpoint')


def _check_budget(value, limits):
    fields = {'model_input_tokens': 'max_model_input_tokens', 'model_output_tokens': 'max_model_output_tokens',
        'tool_calls': 'max_tool_calls', 'source_open_calls': 'max_source_open_calls', 'source_open_bytes': 'max_source_open_bytes_total'}
    exact(value, fields, 'invalid_continuation_budget_capture')
    for key, limit in fields.items():
        if type(value[key]) is not int or value[key] < 0:
            raise RuntimeContractError('continuation_budget_measurement_missing')
        if value[key] > limits[limit]:
            raise RuntimeContractError('continuation_budget_exceeded')


def run_unit(checkpoint_path, arm, run_id, output, backend, controller, limits=None, *, timeout_seconds=300, execution_mode='live'):
    """Run exactly one fixed-ABI method unit from one unchanged native parent."""
    checkpoint = load_checkpoint(checkpoint_path)
    validate_origin(backend, execution_mode, checkpoint)
    if arm not in ARMS or not isinstance(run_id, str) or not LABEL.fullmatch(run_id):
        raise RuntimeContractError('invalid_paired_unit_identity')
    task, replicate = checkpoint['task'], checkpoint['replicate']
    limits = limits_for(task, replicate, limits)
    if type(timeout_seconds) not in (int, float) or not 0 < timeout_seconds <= min(300, limits['max_wall_seconds']):
        raise RuntimeContractError('method_wall_limit_exceeds_approval')
    checkpoint_root = plain_path(checkpoint_path).parent
    output = plain_path(output, exists=False)
    # Reserve before materialization and admission; a crash cannot free this arm.
    _reserve_unit(checkpoint_root, checkpoint, arm, run_id, output)
    output = _new_output(output, task['public_path'], checkpoint_root, allow_wrapper_logs=True)
    scope = _Scope(task, replicate, arm, run_id, 'method', output, controller, backend, timeout_seconds, checkpoint)
    context = {'task': task, 'replicate': replicate, 'arm': arm, 'run_id': run_id, 'checkpoint': checkpoint,
        'original_request': (Path(task['public_path']) / 'request.txt').read_text(), 'limits': limits}
    try:
        scope.admit()
        shutil.copytree(checkpoint_root, output / 'checkpoint-input', ignore=shutil.ignore_patterns('unit-state'))
        context['checkpoint_root'] = str(output / 'checkpoint-input')
        load_checkpoint(output / 'checkpoint-input/checkpoint.json', expected_task=task, replicate=replicate)
        shared_usage = output / 'checkpoint-input/usage.jsonl'
        if shared_usage.exists():
            rows = [EXPERIMENT['strict_json'](line) for line in shared_usage.read_bytes().splitlines() if line.strip()]
            scope.capture_usage(rows, output / 'checkpoint-input')
        _verify_parent(scope, context)
        fork, folder = scope.operation('fork_parent', context)
        exact(fork, ('native_parent_thread_id', 'thread_id', 'workspace_path', 'fork_response_path'), 'invalid_fork_result')
        workspace, response = artifact(folder, fork['workspace_path']), read_json(artifact(folder, fork['fork_response_path']))
        if (fork['native_parent_thread_id'] != checkpoint['native_parent_thread_id']
                or not LABEL.fullmatch(str(fork['thread_id'])) or fork['thread_id'] == checkpoint['native_parent_thread_id']
                or response.get('method') != 'thread/fork'
                or response.get('request', {}).get('threadId') != checkpoint['native_parent_thread_id']
                or response.get('response', {}).get('thread', {}).get('id') != fork['thread_id']
                or _workspace(workspace) != checkpoint['workspace_snapshot_sha256']):
            raise RuntimeContractError('fork_parent_or_workspace_binding_mismatch')
        fork = {**fork, 'workspace_path': str(workspace), 'fork_response_path': str(artifact(folder, fork['fork_response_path']))}
        _register_fork(checkpoint_root, checkpoint, arm, run_id, fork)
        context['fork'] = fork
        context['packet'] = None
        if arm != 'A':
            built, _ = scope.operation('build_packet', context)
            exact(built, ('packet', 'checkpoint_sha256', 'source_archive_sha256', 'original_request_sha256',
                         'extraction_sha256', 'd_prime_sha256', 'shared_reader_config_sha256'), 'invalid_method_packet')
            for key in ('checkpoint_sha256', 'source_archive_sha256', 'original_request_sha256', 'shared_reader_config_sha256'):
                if built[key] != checkpoint[key]:
                    raise RuntimeContractError('method_packet_checkpoint_mismatch')
            if (built['extraction_sha256'] != (checkpoint['extraction_sha256'] if arm in ('C', 'D') else None)
                    or built['d_prime_sha256'] != (checkpoint['d_prime_sha256'] if arm == 'D' else None)
                    or not isinstance(built['packet'], (dict, str))):
                raise RuntimeContractError('method_packet_extraction_or_priming_mismatch')
            context['packet'] = built['packet']
            write_json(output / 'method-packet.json', built)
        continued, folder = scope.operation('continue_reader', context)
        exact(continued, ('result', 'budget_usage'), 'invalid_continuation_result')
        _check_budget(continued['budget_usage'], limits)
        result = copy.deepcopy(continued['result'])
        # Reuse experiment.py's exact result schema without accepting a score.
        write_json(folder / 'result.json', result)
        validated, error = EXPERIMENT['result_metadata'](folder)
        if error:
            raise RuntimeContractError('invalid_experiment_result_metadata')
        if 'trace_ref' not in result:
            raise RuntimeContractError('continuation_trace_required')
        trace = artifact(folder, result['trace_ref'])
        result['trace_ref'] = trace.relative_to(output).as_posix()
        _verify_parent(scope, context)
        load_checkpoint(checkpoint_path, expected_task=task, replicate=replicate)
    except Exception as error:
        result = _error_result(error)
    return scope.finish(result)


def import_checkpoint(checkpoint_path, task, replicate, output):
    """Import an already task-bound native checkpoint, preserving its identity.

    A generic prior native summary is not a task checkpoint. Import performs no
    model call, creates no native permit and never clears an attempt registry.
    """
    checkpoint = load_checkpoint(checkpoint_path, expected_task=task, replicate=replicate)
    source = plain_path(checkpoint_path).parent
    output = _new_output(output, task['public_path'], source)
    # Copy reservations too. Relocation cannot reset already used method arms.
    for item in source.iterdir():
        if item.is_symlink():
            raise RuntimeContractError('checkpoint_import_symlink')
        if item.is_dir():
            shutil.copytree(item, output / item.name)
        else:
            shutil.copy2(item, output / item.name)
    checked = load_checkpoint(output / Path(checkpoint_path).name, expected_task=task, replicate=replicate)
    if checked != checkpoint:
        raise RuntimeContractError('checkpoint_import_changed_identity')
    return {'status': 'imported', 'checkpoint_sha256': checked['checkpoint_sha256'], 'native_attempts_created': 0,
            'scientific_ready': False, 'copied_attempt_registry': (output / 'unit-state').exists()}


def run_paired_block(task, replicate, backend, controller, output, *, order=ARMS, execution_mode='live'):
    """Convenience orchestration; experiment.py must call run_unit only once.

    A native preparation scope and four separate method scopes are required.
    The order must be the already selected four-arm order, without omissions.
    """
    if not isinstance(order, (list, tuple)) or len(order) != 4 or set(order) != set(ARMS):
        raise RuntimeContractError('exact_four_arm_order_required')
    output = _new_output(output, task['public_path'])
    prepared = prepare_block(task, replicate, backend, controller, output / 'block', execution_mode=execution_mode)
    result = {'kind': 'paired_runtime_component_execution', 'preparation': prepared, 'arms': {}, 'scientific_ready': False}
    if prepared['status'] != 'completed':
        return result
    for arm in order:
        run_id = 'p1-method-' + digest({'task': task, 'replicate': replicate, 'arm': arm})[:24]
        result['arms'][arm] = run_unit(output / 'block/checkpoint.json', arm, run_id, output / run_id,
                                      backend, controller, execution_mode=execution_mode)
    write_json(output / 'paired-block-result.json', result)
    return result
