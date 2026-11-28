#!/usr/bin/env python3
"""Preserve the live archive epoch through experiment.py's first-attempt path.

The frozen executable is a hash binding to the actual implementation tree. It
fails closed if started as an ordinary subprocess. PairedLauncher executes the
bound implementation in the same controller process, one scheduled unit per
invocation, while experiment.py retains reservation, collection, sealing/join.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import paired_runtime as paired
import experiment
from native_backend import NativeBackend

ROOT = HERE.parents[1]
PREFIX = '# P1_INPROCESS_BINDING '
MARKER = "#!/usr/bin/env python3\n"
TAIL = ("import sys\n"
        "sys.stderr.write('This implementation binding requires the live in-process PairedLauncher; no unit was dispatched.\\n')\n"
        "raise SystemExit(2)\n")


class DispatchBindingError(paired.RuntimeContractError):
    pass


def implementation_sources():
    paths = [HERE.parent / 'codex-retention-host.py']
    paths.extend(p for p in HERE.rglob('*') if p.suffix in ('.py', '.mjs', '.json') and p.is_file())
    paths.extend(p for p in (ROOT / 'packages/memex-core/lib').rglob('*') if p.suffix in ('.js', '.mjs', '.json') and p.is_file())
    paths.append(ROOT / 'packages/memex-core/package.json')
    paths.append(ROOT / 'packages/memex-core/index.js')
    return {p.relative_to(ROOT).as_posix(): paired.file_sha(p) for p in sorted(set(paths))}


def create_binding(path):
    """Freeze implementation identity only; create no study, permit or attempt."""
    path = paired.plain_path(path, exists=False)
    if path.is_relative_to(HERE) or path.is_relative_to(ROOT / 'packages/memex-core'):
        raise DispatchBindingError('runner_binding_must_live_outside_implementation_tree')
    binding = {'schema_version': 1, 'kind': 'p1-paired-inprocess-runner-binding',
               'entrypoint': 'paired_dispatch.PairedLauncher.__call__', 'sources': implementation_sources(),
               'native_state': 'same_live_backend_and_evidence_process', 'model_requests': 0,
               'scientific_ready': False}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(MARKER + PREFIX + paired.canonical(binding) + '\n' + TAIL)
        stream.flush(); os.fsync(stream.fileno())
    path.chmod(0o700)
    return {'runner': str(path), 'runner_sha256': paired.file_sha(path), 'binding_sha256': paired.digest(binding),
            'model_requests': 0, 'study_frozen': False, 'scientific_ready': False}


def load_binding(path):
    path = paired.plain_path(path)
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise DispatchBindingError('runner_binding_size_or_type')
    raw = path.read_text(encoding='utf-8'); lines = raw.splitlines()
    if len(lines) != 5 or lines[0] + '\n' != MARKER or not lines[1].startswith(PREFIX):
        raise DispatchBindingError('runner_binding_format')
    binding = experiment.strict_json(lines[1][len(PREFIX):])
    expected = {'schema_version': 1, 'kind': 'p1-paired-inprocess-runner-binding',
                'entrypoint': 'paired_dispatch.PairedLauncher.__call__', 'sources': implementation_sources(),
                'native_state': 'same_live_backend_and_evidence_process', 'model_requests': 0, 'scientific_ready': False}
    if binding != expected or raw != MARKER + PREFIX + paired.canonical(binding) + '\n' + TAIL:
        raise DispatchBindingError('actual_runner_implementation_changed')
    return binding


class PairedLauncher:
    def __init__(self, *, plan, state, checkpoints, backend, controller, execution_mode='live'):
        self.frozen = experiment.load_frozen(plan)
        if self.frozen['manifest']['study_phase'] != 'development':
            raise DispatchBindingError('current_authorized_backend_is_development_only')
        self.state = paired.plain_path(state, exists=False)
        self.backend, self.controller, self.execution_mode = backend, controller, execution_mode
        paired.validate_origin(backend, execution_mode)
        if execution_mode == 'live' and type(backend) is not NativeBackend:
            raise DispatchBindingError('concrete_bound_native_backend_required')
        if execution_mode == 'live' and backend.controller is not controller:
            raise DispatchBindingError('same_canonical_backend_controller_required')
        blocks = {(u['key']['task_id'], u['key']['replicate']) for u in self.frozen['schedule']['units']}
        if not isinstance(checkpoints, dict) or set(checkpoints) != blocks:
            raise DispatchBindingError('exact_scheduled_checkpoint_map_required')
        self.checkpoints = {key: paired.plain_path(value) for key, value in checkpoints.items()}
        self.seen = set()
        self.initial_binding = self.validate_frozen(self.frozen, self.state)

    def validate_frozen(self, frozen, state):
        if frozen != self.frozen or Path(state).absolute() != self.state:
            raise DispatchBindingError('launcher_frozen_plan_or_state_changed')
        schedule = frozen['schedule']
        binding = load_binding(schedule['runner'])
        if paired.file_sha(schedule['runner']) != schedule['runner_sha256']:
            raise DispatchBindingError('launcher_binding_changed_after_freeze')
        identities = {}
        for key, path in self.checkpoints.items():
            checkpoint = paired.load_checkpoint(path)
            paired.validate_origin(self.backend, self.execution_mode, checkpoint)
            task = checkpoint['task']
            if (task['task_id'], checkpoint['replicate']) != key:
                raise DispatchBindingError('checkpoint_schedule_identity_mismatch')
            units = [u for u in schedule['units'] if (u['key']['task_id'], u['key']['replicate']) == key]
            if any(u['key']['project_id'] != task['project_id'] or u['public'] != task['public_path']
                   or u['public_sha256'] != task['public_sha256'] for u in units):
                raise DispatchBindingError('checkpoint_frozen_public_mismatch')
            if self.execution_mode == 'live' and any(u['key']['arm'] in ('C', 'D') for u in units):
                scope = paired.native_scope_id(task, checkpoint['replicate'])
                helper = self.backend.evidence.get(scope)
                if helper is None or helper.proc.poll() is not None:
                    raise DispatchBindingError('original_live_evidence_epoch_required')
            identities[str(key)] = checkpoint['sealed_checkpoint_sha256']
        result = {'schema_version': 1, 'kind': 'bound_in_process_paired_launcher',
                'runner_sha256': schedule['runner_sha256'], 'implementation_binding_sha256': paired.digest(binding),
                'checkpoint_bindings_sha256': paired.digest(identities), 'evidence_origin': self.backend.evidence_origin,
                'wrapper_subprocesses_started': 0, 'scientific_ready': False}
        if hasattr(self, 'initial_binding') and result != self.initial_binding:
            raise DispatchBindingError('launcher_checkpoint_bindings_changed')
        return result

    def __call__(self, argv, *, cwd, env, timeout, stdout, stderr):
        started = time.monotonic()
        self.validate_frozen(self.frozen, self.state)
        if (not isinstance(argv, list) or len(argv) != 13 or argv[0] != self.frozen['schedule']['runner']
                or argv[1::2] != ['--public', '--arm', '--replicate', '--run-id', '--output', '--timeout-seconds']
                or type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 300):
            raise DispatchBindingError('fixed_unit_invocation_required')
        values = dict(zip(argv[1::2], argv[2::2]))
        run_id = values['--run-id']
        units = [unit for unit in self.frozen['schedule']['units'] if unit['run_id'] == run_id]
        if len(units) != 1 or run_id in self.seen:
            raise DispatchBindingError('unit_not_scheduled_or_already_invoked')
        unit = units[0]; output = self.state / 'runs' / run_id
        expected_env = {name: os.environ[name] for name in self.frozen['schedule']['env_allowlist'] if name in os.environ}
        if (values['--public'] != unit['public'] or values['--arm'] != unit['key']['arm']
                or values['--replicate'] != str(unit['key']['replicate'])
                or Path(values['--output']).absolute() != output or Path(cwd).absolute() != output
                or float(values['--timeout-seconds']) != timeout or env != expected_env
                or paired.EXPERIMENT['public_digest'](unit['public']) != unit['public_sha256']):
            raise DispatchBindingError('frozen_unit_invocation_mismatch')
        # Only the original experiment dispatcher may invoke this adapter. It
        # has durably reserved the exact first attempt before this call.
        records = experiment.read_ledger(self.state / 'run-ledger.jsonl')
        _, attempts, finished = experiment.state_snapshot(self.frozen, records)
        reservation = attempts.get(run_id)
        if reservation is None or run_id in finished or reservation['key'] != unit['key']:
            raise DispatchBindingError('experiment_first_attempt_reservation_required')
        available = timeout - (time.monotonic() - started) - 5
        if available <= 0:
            raise DispatchBindingError('insufficient_bounded_unit_time')
        self.seen.add(run_id)
        result = paired.run_unit(self.checkpoints[(unit['key']['task_id'], unit['key']['replicate'])],
            unit['key']['arm'], run_id, output, self.backend, self.controller,
            timeout_seconds=available, execution_mode=self.execution_mode)
        stdout.write((paired.canonical({'status': result['status'], 'run_id': run_id,
                                       'evidence_origin': self.backend.evidence_origin}) + '\n').encode())
        stdout.flush()
        # Status, not the process exit code, describes a successful/failed
        # research execution. No quality score is constructed by this adapter.
        return 0
