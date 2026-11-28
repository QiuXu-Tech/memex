#!/usr/bin/env python3
"""One approved development batch: durable attempts and added-cash reservations.

No provider calls, host approval, subprocess launch, task acceptance or scientific
freeze is implemented. All dispatchers must share the one declared ledger and
reserve before starting external work. The ledger is tamper-evident, not a
security boundary against its filesystem owner.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid

BATCH_ID = 'p1-20261128-approved-batch1'
AUTH_RELATIVE = 'docs/research/p1-evidence-verification/artifacts/authorized-batch1/authorization.json'
LEDGER_RELATIVE = 'docs/research/p1-evidence-verification/artifacts/authorized-batch1/ledger'
PLAN_RELATIVE = 'docs/research/p1-evidence-verification/tasks/workflows/source-draft-plan.json'
NATIVE_SUPPLEMENT_ID = 'p1-20261129-native-preparation-supplement1'
NATIVE_SUPPLEMENT_RELATIVE = 'docs/research/p1-evidence-verification/artifacts/authorized-batch1/native-preparation-supplement1.json'
NATIVE_SUPPLEMENT_QUOTE = '确认追加\n真人如无必要尽可能由你代劳'
NATIVE_SUPPLEMENT_EVENT = 'native_supplement_activated'
PROJECTS = {'w-101': 'pallets/flask', 'w-102': 'psf/requests'}
MAX_FILE_BYTES = 16 * 1024 * 1024
HEX = re.compile(r'[a-f0-9]{64}\Z')
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
TERMINAL = {'completed', 'failed', 'host_blocked', 'provider_blocked', 'timeout', 'capture_incomplete'}
EVENT_LIMITS = {'native': {'generation_start': 5, 'compaction_start': 2,
                           'test_execution': 6, 'public_tool_call': 20},
                'method': {'public_tool_call': 64, 'source_open': 32},
                'diagnostic': {'provider_request': 1}}


class LimitError(ValueError):
    """Stable non-secret error codes."""


def canonical(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def digest(x):
    return hashlib.sha256(canonical(x).encode()).hexdigest()


def strict_json(text):
    def pairs(xs):
        d = {}
        for k, v in xs:
            if k in d:
                raise LimitError('duplicate_json_key')
            d[k] = v
        return d
    def constant(_):
        raise LimitError('nonfinite_json')
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LimitError('invalid_json') from exc


def regular_bytes(path):
    path = Path(path)
    # Check every existing component, including parent symlinks.
    absolute = Path(os.path.abspath(path))
    for p in (absolute, *absolute.parents):
        if p.is_symlink():
            raise LimitError('symlink_forbidden')
    try:
        fd = os.open(absolute, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except OSError as exc:
        raise LimitError('file_unavailable') from exc
    with os.fdopen(fd, 'rb') as f:
        info = os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            raise LimitError('unsafe_or_oversized_file')
        value = f.read(MAX_FILE_BYTES + 1)
    if len(value) > MAX_FILE_BYTES:
        raise LimitError('oversized_file')
    return value


def read_json(path):
    return strict_json(regular_bytes(path).decode('utf-8'))


def fields(value, required, optional=()):
    if (not isinstance(value, dict) or not set(required) <= set(value)
            or set(value) - set(required) - set(optional)):
        raise LimitError('schema_fields')


def fen(value):
    # Strings avoid binary-float ambiguity and make the approved cash boundary explicit.
    if not isinstance(value, str) or not re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?', value):
        raise LimitError('money_requires_nonnegative_decimal_string')
    try:
        result = Decimal(value) * 100
    except InvalidOperation as exc:
        raise LimitError('invalid_money') from exc
    if not result.is_finite() or result > 10**12:
        raise LimitError('invalid_money')
    return int(result)


def money(value):
    return f'{value // 100}.{value % 100:02d}'


def unit_key(unit):
    return ':'.join(str(unit[k]) for k in ('task_id', 'arm', 'replicate'))


def validate_diagnostic_binding(value):
    """Only the selected provider's one-request extraction diagnostic.

    This is a controller binding, not a native attempt or a scientific unit.
    The caller enforces the diagnostic prompt, service access and token limits.
    """
    fields(value, {'provider', 'model', 'endpoint', 'dispatch_id',
                   'intent_sha256', 'request_sha256', 'config_sha256'})
    if (value['provider'] != 'deepseek' or value['model'] != 'deepseek-flash'
            or value['endpoint'] != 'https://api.deepseek.com/chat/completions'
            or not isinstance(value['dispatch_id'], str)
            or not LABEL.fullmatch(value['dispatch_id']) or value['dispatch_id'].startswith('sk-')
            or any(not isinstance(value[k], str) or not HEX.fullmatch(value[k])
                   for k in ('intent_sha256', 'request_sha256', 'config_sha256'))):
        raise LimitError('invalid_diagnostic_binding')
    # Own the scalar-only snapshot; later caller mutation cannot alter admission.
    return dict(value)


def public_digest(path):
    spec = importlib.util.spec_from_file_location('_p1_batch_experiment', Path(__file__).with_name('experiment.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        return module.public_digest(path)
    except (ValueError, OSError) as exc:
        raise LimitError('invalid_public_snapshot') from exc


def validate_authorization(value):
    """Read-only structural validation. This does not authenticate a human or host."""
    fields(value, {'schema_version', 'batch_id', 'approval', 'limits', 'source_plan', 'units',
                   'ledger_relative_path', 'scientific_state', 'allowed_scope', 'excluded_scope'})
    if value['schema_version'] != 1 or type(value['schema_version']) is not int or value['batch_id'] != BATCH_ID:
        raise LimitError('unsupported_authorization')
    if value['ledger_relative_path'] != LEDGER_RELATIVE:
        raise LimitError('canonical_ledger_required')
    a = value['approval']
    fields(a, {'date', 'timezone', 'user_quote', 'proposal_id', 'interpretation'})
    if a['date'] != '2026-11-28' or a['timezone'] != 'Asia/Shanghai' or a['user_quote'] != '全部批准':
        raise LimitError('approval_record_mismatch')
    if a['proposal_id'] != 'P1 统一审批单 · 第 1 批' or not isinstance(a['interpretation'], str):
        raise LimitError('approval_record_mismatch')
    limits = value['limits']
    if limits != {'native_attempts': 2, 'native_generation_starts_per_attempt': 5,
                  'native_compactions_per_attempt': 2, 'native_wall_seconds_per_attempt': 600,
                  'method_units': 16, 'method_wall_seconds_per_unit': 300,
                  'added_cash_currency': 'CNY', 'added_cash_total': '100.00'}:
        raise LimitError('approved_limits_mismatch')
    if (value['scientific_state'] != {'phase': 'development', 'frozen': False,
                                    'accepted_p1_tasks': 0, 'human_reviews_completed': 0,
                                    'host_approval_attested': False, 'permissions_are_not_results': True}
            or value['scientific_state'].get('frozen') is not False
            or value['scientific_state'].get('host_approval_attested') is not False
            or value['scientific_state'].get('permissions_are_not_results') is not True):
        raise LimitError('authorization_is_not_scientific_acceptance')
    plan = value['source_plan']
    fields(plan, {'relative_path', 'sha256', 'shared_budget_relative_path', 'shared_budget_sha256'})
    if plan['relative_path'] != PLAN_RELATIVE or not HEX.fullmatch(str(plan['sha256'])):
        raise LimitError('source_plan_binding_required')
    if (plan['shared_budget_relative_path'] != str(Path(PLAN_RELATIVE).with_name('shared-budget.json'))
            or not HEX.fullmatch(str(plan['shared_budget_sha256']))):
        raise LimitError('shared_budget_binding_required')
    units = value['units']
    if not isinstance(units, list) or len(units) != 16:
        raise LimitError('sixteen_units_required')
    expected = {f'{task}:{arm}:{rep}' for task in PROJECTS for arm in 'ABCD' for rep in (1, 2)}
    seen = set()
    task_bindings = {}
    for u in units:
        fields(u, {'task_id', 'project_id', 'arm', 'replicate', 'public_sha256',
                   'taskpack_public_sha256', 'public_relative_path'})
        if (not isinstance(u['task_id'], str) or u['task_id'] not in PROJECTS
                or u['project_id'] != PROJECTS[u['task_id']]
                or not isinstance(u['arm'], str) or u['arm'] not in 'ABCD' or len(u['arm']) != 1
                or type(u['replicate']) is not int or u['replicate'] not in (1, 2)):
            raise LimitError('unit_outside_approval')
        key = unit_key(u)
        if key in seen:
            raise LimitError('duplicate_approved_unit')
        seen.add(key)
        if any(not HEX.fullmatch(str(u[k])) for k in ('public_sha256', 'taskpack_public_sha256')):
            raise LimitError('public_binding_required')
        expected_path = str(Path(PLAN_RELATIVE).parent / 'packages' / u['task_id'] / 'public')
        if u['public_relative_path'] != expected_path:
            raise LimitError('public_path_outside_approval')
        binding = (u['public_sha256'], u['taskpack_public_sha256'])
        if u['task_id'] in task_bindings and task_bindings[u['task_id']] != binding:
            raise LimitError('cross_arm_public_input_mismatch')
        task_bindings[u['task_id']] = binding
    if seen != expected:
        raise LimitError('unit_set_mismatch')
    for key in ('allowed_scope', 'excluded_scope'):
        if not isinstance(value[key], list) or not value[key] or any(not isinstance(x, str) or not x for x in value[key]):
            raise LimitError('scope_description_required')
    return value


def validate_native_binding(value, authorization):
    """A native grant identifies an approved public task, never just a label."""
    fields(value, {'task_id', 'project_id', 'replicate', 'public_sha256'})
    if (not isinstance(value['task_id'], str) or value['task_id'] not in PROJECTS
            or value['project_id'] != PROJECTS[value['task_id']]
            or type(value['replicate']) is not int or value['replicate'] not in (1, 2)
            or not isinstance(value['public_sha256'], str) or not HEX.fullmatch(value['public_sha256'])):
        raise LimitError('invalid_native_task_binding')
    approved = next(u for u in authorization['units']
                    if u['task_id'] == value['task_id'] and u['replicate'] == value['replicate'])
    if value['public_sha256'] != approved['public_sha256']:
        raise LimitError('native_public_binding_mismatch')
    return dict(value)


def validate_native_supplement(value, authorization, authorization_sha256):
    """Validate this one explicit four-scope approval; presence never activates it.

    The original authorization remains byte-for-byte authoritative for cash,
    method units and per-attempt limits. Only an explicit canonical journal
    activation can make these four named native preparation grants available.
    This records the user's supplied approval, not an identity attestation.
    """
    fields(value, {'schema_version', 'kind', 'supplement_id', 'batch_id', 'approval',
                   'authorization', 'source_plan', 'ledger_relative_path', 'prior_journal',
                   'additional_native_attempts', 'unchanged_limits', 'native_scope_limits', 'grants'})
    if (type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['kind'] != 'p1-native-preparation-supplement'
            or value['supplement_id'] != NATIVE_SUPPLEMENT_ID or value['batch_id'] != BATCH_ID):
        raise LimitError('unsupported_native_supplement')
    if value['approval'] != {'date': '2026-11-29', 'timezone': 'Asia/Shanghai',
                             'user_quote': NATIVE_SUPPLEMENT_QUOTE}:
        raise LimitError('native_supplement_approval_mismatch')
    if (value['authorization'] != {'relative_path': AUTH_RELATIVE, 'sha256': authorization_sha256}
            or value['source_plan'] != authorization['source_plan']
            or value['ledger_relative_path'] != LEDGER_RELATIVE):
        raise LimitError('native_supplement_original_binding_mismatch')
    if (type(value['additional_native_attempts']) is not int or value['additional_native_attempts'] != 4
            or value['unchanged_limits'] != authorization['limits']
            or value['native_scope_limits'] != {'wall_seconds': 600, **EVENT_LIMITS['native']}):
        raise LimitError('native_supplement_limits_mismatch')
    anchor = value['prior_journal']
    fields(anchor, {'events', 'head_sha256', 'sha256'})
    if (type(anchor['events']) is not int or anchor['events'] != 7
            or any(not isinstance(anchor[k], str) or not HEX.fullmatch(anchor[k])
                   for k in ('head_sha256', 'sha256'))):
        raise LimitError('native_supplement_prior_journal_required')
    if not isinstance(value['grants'], list) or len(value['grants']) != 4:
        raise LimitError('exact_four_native_grants_required')
    tasks, scopes = set(), set()
    for grant in value['grants']:
        fields(grant, {'scope_id', 'task_id', 'project_id', 'replicate',
                       'public_sha256', 'taskpack_public_sha256'})
        validate_native_binding({k: grant[k] for k in
            ('task_id', 'project_id', 'replicate', 'public_sha256')}, authorization)
        identity = (grant['task_id'], grant['replicate'])
        if (not isinstance(grant['scope_id'], str)
                or not re.fullmatch(r'p1-native-[a-f0-9]{24}', grant['scope_id'])
                or grant['scope_id'] in scopes or identity in tasks):
            raise LimitError('duplicate_or_invalid_native_grant')
        approved = next(u for u in authorization['units'] if u['task_id'] == grant['task_id'])
        if grant['taskpack_public_sha256'] != approved['taskpack_public_sha256']:
            raise LimitError('native_taskpack_binding_mismatch')
        tasks.add(identity); scopes.add(grant['scope_id'])
    if tasks != {(task, rep) for task in PROJECTS for rep in (1, 2)}:
        raise LimitError('native_supplement_task_set_mismatch')
    return value


class BatchLedger:
    def __init__(self, auth_path, state_dir=None, repo_root=None):
        self.auth_path = Path(os.path.abspath(auth_path))
        self.repo_root = Path(os.path.abspath(repo_root or Path(__file__).parents[2]))
        self.auth_raw = regular_bytes(self.auth_path)
        self.auth = validate_authorization(strict_json(self.auth_raw.decode()))
        self.auth_sha256 = hashlib.sha256(self.auth_raw).hexdigest()
        expected = self.repo_root / self.auth['ledger_relative_path']
        self.state_dir = Path(os.path.abspath(state_dir or expected))
        if self.state_dir != expected:
            raise LimitError('one_canonical_ledger_required')
        self.journal = self.state_dir / 'events.jsonl'
        self.lock_path = self.state_dir / 'ledger.lock'
        self.head_path = self.state_dir / 'HEAD.json'
        self._fresh_context = False

    def _check_auth(self):
        if hashlib.sha256(regular_bytes(self.auth_path)).hexdigest() != self.auth_sha256:
            raise LimitError('authorization_changed_after_load')

    @contextmanager
    def _lock(self, write=False):
        self._check_auth()
        for p in (self.state_dir, *self.state_dir.parents):
            if p.is_symlink():
                raise LimitError('symlink_forbidden')
        if not self.state_dir.exists():
            if not write:
                yield
                return
            self.state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
            self._fsync_dir(self.state_dir.parent)
        flags = os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0) | (os.O_CREAT if write else 0)
        fresh = write and not self.lock_path.exists()
        try:
            fd = os.open(self.lock_path, flags, 0o600)
        except FileNotFoundError:
            # Only a never-used directory may have no lock. Existing journal cannot be read unlocked.
            if self.journal.exists():
                raise LimitError('ledger_lock_missing')
            yield
            return
        except OSError as exc:
            raise LimitError('unsafe_ledger_lock') from exc
        with os.fdopen(fd, 'r+b') as lock:
            if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
                raise LimitError('unsafe_ledger_lock')
            fcntl.flock(lock, fcntl.LOCK_EX if write else fcntl.LOCK_SH)
            try:
                self._fresh_context = fresh
                yield
            finally:
                self._fresh_context = False
                fcntl.flock(lock, fcntl.LOCK_UN)

    @staticmethod
    def _fsync_dir(path):
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def _read(self):
        if not self.journal.exists():
            if self.head_path.exists() or self.lock_path.exists() and not self._fresh_context:
                raise LimitError('journal_missing_requires_manual_reconciliation')
            return []
        data = regular_bytes(self.journal)
        if not data:
            raise LimitError('empty_journal_requires_manual_reconciliation')
        if data and not data.endswith(b'\n'):
            raise LimitError('partial_journal_requires_manual_reconciliation')
        events, previous = [], '0' * 64
        for line in data.splitlines():
            event = strict_json(line.decode())
            fields(event, {'seq', 'previous_sha256', 'authorization_sha256', 'at_unix_ns',
                           'event', 'data', 'sha256'})
            body = {k: v for k, v in event.items() if k != 'sha256'}
            if (event['seq'] != len(events) + 1 or event['previous_sha256'] != previous
                    or event['authorization_sha256'] != self.auth_sha256
                    or not isinstance(event['at_unix_ns'], int) or event['at_unix_ns'] < 0
                    or event['sha256'] != digest(body)):
                raise LimitError('journal_integrity_failure')
            if events and event['at_unix_ns'] < events[-1]['at_unix_ns']:
                raise LimitError('journal_clock_regression')
            events.append(event)
            previous = event['sha256']
        head = read_json(self.head_path)
        if head != {'authorization_sha256': self.auth_sha256, 'seq': len(events), 'sha256': previous}:
            raise LimitError('journal_head_mismatch_requires_manual_reconciliation')
        return events

    def _append(self, events, event, data):
        now = time.time_ns()
        if events and now < events[-1]['at_unix_ns']:
            raise LimitError('clock_regression')
        item = {'seq': len(events) + 1, 'previous_sha256': events[-1]['sha256'] if events else '0' * 64,
                'authorization_sha256': self.auth_sha256, 'at_unix_ns': now, 'event': event, 'data': data}
        item['sha256'] = digest(item)
        encoded = (canonical(item) + '\n').encode()
        fd = os.open(self.journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'ab') as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                raise LimitError('unsafe_ledger_file')
            f.write(encoded)
            f.flush()
            os.fsync(f.fileno())
        head = {'authorization_sha256': self.auth_sha256, 'seq': item['seq'], 'sha256': item['sha256']}
        temporary = self.state_dir / ('head-' + uuid.uuid4().hex + '.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(canonical(head) + '\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, self.head_path)
        self._fsync_dir(self.state_dir)
        events.append(item)
        return item

    def _source_plan_binding(self):
        plan = self.auth['source_plan']
        for path_key, hash_key in (('relative_path', 'sha256'), ('shared_budget_relative_path', 'shared_budget_sha256')):
            if hashlib.sha256(regular_bytes(self.repo_root / plan[path_key])).hexdigest() != plan[hash_key]:
                raise LimitError('source_plan_drift')

    def _load_native_supplement(self, expected_sha256):
        if not isinstance(expected_sha256, str) or not HEX.fullmatch(expected_sha256):
            raise LimitError('native_supplement_expected_hash_required')
        raw = regular_bytes(self.repo_root / NATIVE_SUPPLEMENT_RELATIVE)
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise LimitError('native_supplement_hash_mismatch')
        value = validate_native_supplement(strict_json(raw.decode('utf-8')), self.auth, self.auth_sha256)
        self._source_plan_binding()
        return value

    def _check_supplement_anchor(self, value, prior_events):
        anchor = value['prior_journal']
        if (len(prior_events) != anchor['events']
                or not prior_events or prior_events[-1]['sha256'] != anchor['head_sha256']):
            raise LimitError('native_supplement_journal_anchor_mismatch')
        # Hash the actual pre-existing bytes, not a reformatted reconstruction.
        # Subsequent journal appends never rewrite this historical prefix.
        prefix = b''.join(regular_bytes(self.journal).splitlines(keepends=True)[:anchor['events']])
        if hashlib.sha256(prefix).hexdigest() != anchor['sha256']:
            raise LimitError('native_supplement_journal_bytes_mismatch')

    @staticmethod
    def _activation(events):
        rows = [event for event in events if event['event'] == NATIVE_SUPPLEMENT_EVENT]
        if len(rows) > 1:
            raise LimitError('duplicate_native_supplement_activation')
        return rows[0] if rows else None

    def activate_native_supplement(self, *, expected_sha256, run=False):
        """Explicitly append the one approved supplement; never reserve a run.

        Only the fixed repo-relative supplement is accepted. The reviewed byte
        hash and seven-event journal anchor must both match at activation.
        Every later ledger replay revalidates that same file and its binding.
        """
        if type(run) is not bool:
            raise LimitError('run_must_be_boolean')
        if not all(path.exists() for path in (self.journal, self.head_path, self.lock_path)):
            raise LimitError('native_supplement_requires_existing_journal')
        with self._lock(write=run):
            events = self._read()
            attempts, _, _, breach = self._state(events)
            if self._activation(events) is not None:
                raise LimitError('native_supplement_already_activated')
            if breach:
                raise LimitError('previous_budget_breach_blocks_dispatch')
            value = self._load_native_supplement(expected_sha256)
            self._check_supplement_anchor(value, events)
            if sum(a['kind'] == 'native' for a in attempts.values()) != 2:
                raise LimitError('native_supplement_requires_original_two_attempts')
            if any(grant['scope_id'] in attempts for grant in value['grants']):
                raise LimitError('native_grant_scope_already_used')
            for grant in value['grants']:
                self._public_binding(f"{grant['task_id']}:A:{grant['replicate']}")
            data = {'supplement_id': NATIVE_SUPPLEMENT_ID,
                    'supplement_relative_path': NATIVE_SUPPLEMENT_RELATIVE,
                    'supplement_sha256': expected_sha256, 'prior_journal': dict(value['prior_journal'])}
            if not run:
                return {'dry_run': True, 'activation_performed': False, 'dispatch_allowed': False,
                        'activation_would_fit': True, 'proposed': data, 'status': self._status(events)}
            event = self._append(events, NATIVE_SUPPLEMENT_EVENT, data)
            return {'dry_run': False, 'activation_performed': True, 'dispatch_allowed': False,
                    'event': event, 'status': self._status(events)}

    def _state(self, events):
        attempts, used_units, diagnostic_dispatches = {}, set(), set()
        original_native, native_grants, supplement = 0, {}, None
        for ordinal, event in enumerate(events):
            d = event['data']
            if event['event'] == NATIVE_SUPPLEMENT_EVENT:
                fields(d, {'supplement_id', 'supplement_relative_path', 'supplement_sha256', 'prior_journal'})
                if (supplement is not None or d['supplement_id'] != NATIVE_SUPPLEMENT_ID
                        or d['supplement_relative_path'] != NATIVE_SUPPLEMENT_RELATIVE):
                    raise LimitError('invalid_native_supplement_activation_history')
                value = self._load_native_supplement(d['supplement_sha256'])
                if d['prior_journal'] != value['prior_journal'] or original_native != 2:
                    raise LimitError('invalid_native_supplement_activation_history')
                self._check_supplement_anchor(value, events[:ordinal])
                native_grants = {grant['scope_id']: grant for grant in value['grants']}
                if set(native_grants) & set(attempts):
                    raise LimitError('native_grant_scope_already_used')
                supplement = d
            elif event['event'] == 'reserved':
                if d['attempt_id'] in attempts or d['kind'] not in ('native', 'method', 'diagnostic'):
                    raise LimitError('invalid_reservation_history')
                if d['kind'] == 'native':
                    if 'native_supplement_id' in d:
                        fields(d, {'attempt_id', 'kind', 'unit_key', 'public_sha256', 'upper_bound_fen',
                                   'billing_basis', 'wall_seconds', 'native_binding',
                                   'native_supplement_id', 'native_supplement_sha256'})
                        grant = native_grants.get(d['attempt_id'])
                        binding = validate_native_binding(d['native_binding'], self.auth)
                        if (supplement is None or grant is None or d['unit_key'] is not None
                                or d['native_supplement_id'] != NATIVE_SUPPLEMENT_ID
                                or d['native_supplement_sha256'] != supplement['supplement_sha256']
                                or binding != {k: grant[k] for k in binding}
                                or d['public_sha256'] != binding['public_sha256']
                                or type(d['wall_seconds']) is not int or d['wall_seconds'] != 600):
                            raise LimitError('invalid_supplemental_native_reservation_history')
                    else:
                        if original_native >= 2 or any(k.startswith('native_') for k in d):
                            raise LimitError('invalid_original_native_reservation_history')
                        original_native += 1
                elif any(k.startswith('native_') for k in d):
                    raise LimitError('native_supplement_outside_native_attempt')
                if d['kind'] == 'diagnostic':
                    fields(d, {'attempt_id', 'kind', 'unit_key', 'public_sha256',
                               'upper_bound_fen', 'billing_basis', 'wall_seconds', 'binding'})
                    binding = validate_diagnostic_binding(d['binding'])
                    fields(d['billing_basis'], {'kind', 'evidence'})
                    if (d['unit_key'] is not None or d['public_sha256'] is not None
                            or type(d['wall_seconds']) is not int or d['wall_seconds'] != 30
                            or type(d['upper_bound_fen']) is not int or not 0 < d['upper_bound_fen'] <= 10000
                            or d['billing_basis']['kind'] != 'priced_upper_bound'
                            or binding['dispatch_id'] in diagnostic_dispatches):
                        raise LimitError('invalid_diagnostic_reservation_history')
                    diagnostic_dispatches.add(binding['dispatch_id'])
                if d['unit_key'] is not None:
                    if d['unit_key'] in used_units:
                        raise LimitError('duplicate_unit_history')
                    used_units.add(d['unit_key'])
                attempts[d['attempt_id']] = dict(d, state='reserved', counters={}, operations=[],
                                                 reserved_at_unix_ns=event['at_unix_ns'],
                                                 actual_added_cost_fen=None)
            elif event['event'] == 'operation_reserved':
                a = attempts.get(d['attempt_id'])
                if not a or a['state'] != 'reserved' or d['operation_id'] in a['operations']:
                    raise LimitError('invalid_operation_history')
                if a['kind'] == 'diagnostic' and (d['kind'] != 'provider_request'
                        or d['operation_id'] != a['binding']['dispatch_id'] or a['operations']):
                    raise LimitError('invalid_diagnostic_operation_history')
                a['operations'].append(d['operation_id'])
                a['counters'][d['kind']] = a['counters'].get(d['kind'], 0) + 1
            elif event['event'] in ('finished', 'cost_settled'):
                a = attempts.get(d['attempt_id'])
                if not a or (event['event'] == 'finished' and a['state'] != 'reserved'):
                    raise LimitError('invalid_finish_history')
                if a['actual_added_cost_fen'] is not None:
                    raise LimitError('duplicate_cost_settlement')
                if event['event'] == 'finished':
                    a['state'] = d['status']
                elif a['state'] == 'reserved' or d['actual_added_cost_fen'] is None:
                    raise LimitError('invalid_cost_settlement')
                a['actual_added_cost_fen'] = d['actual_added_cost_fen']
            else:
                raise LimitError('unknown_ledger_event')
        held = sum(a['upper_bound_fen'] if a['actual_added_cost_fen'] is None else a['actual_added_cost_fen']
                   for a in attempts.values())
        breach = any(a['actual_added_cost_fen'] is not None and a['actual_added_cost_fen'] > a['upper_bound_fen']
                     for a in attempts.values()) or held > 10000
        return attempts, used_units, held, breach

    def _status(self, events):
        attempts, units, held, breach = self._state(events)
        native = sum(a['kind'] == 'native' for a in attempts.values())
        supplemental = sum(a.get('native_supplement_id') == NATIVE_SUPPLEMENT_ID for a in attempts.values())
        original = native - supplemental
        activation = self._activation(events)
        additional = 4 if activation is not None else 0
        supplement = self._load_native_supplement(activation['data']['supplement_sha256']) if activation else None
        unknown = [k for k, a in attempts.items() if a['actual_added_cost_fen'] is None]
        return {'schema_version': 1, 'batch_id': BATCH_ID, 'authorization_sha256': self.auth_sha256,
                'permissions_recorded': True, 'host_approval_attested': False,
                'scientific_ready': False, 'formal_runs': 0,
                'native_attempts_reserved': native,
                'native_attempts_remaining': max(0, 2 - original) + additional - supplemental,
                'native_original_attempts_reserved': original, 'native_original_attempts_remaining': max(0, 2 - original),
                'native_supplemental_attempts_reserved': supplemental,
                'native_supplemental_attempts_remaining': additional - supplemental,
                'native_supplement_active': activation is not None,
                'native_supplement_id': NATIVE_SUPPLEMENT_ID if activation else None,
                'native_supplement_sha256': activation['data']['supplement_sha256'] if activation else None,
                'native_available_grants': [grant for grant in supplement['grants'] if grant['scope_id'] not in attempts]
                                           if supplement else [],
                'method_units_reserved': len(units), 'method_units_remaining': max(0, 16 - len(units)),
                'diagnostic_attempts_reserved': sum(a['kind'] == 'diagnostic' for a in attempts.values()),
                'added_cash_currency': 'CNY', 'added_cash_cap': '100.00',
                'committed_cash_upper_bound': money(held), 'remaining_cash_capacity': money(max(0, 10000 - held)),
                'actual_added_cash_total': None if unknown else money(held),
                'attempts_with_unsettled_cost': unknown, 'budget_breach_observed': breach,
                'attempts': attempts, 'journal_events': len(events),
                'journal_head_sha256': events[-1]['sha256'] if events else None}

    def status(self):
        with self._lock():
            return self._status(self._read())

    def _evidence(self, value):
        fields(value, {'ref', 'sha256'})
        ref = value['ref']
        if (not isinstance(ref, str) or Path(ref).is_absolute() or '..' in Path(ref).parts
                or not HEX.fullmatch(str(value['sha256']))):
            raise LimitError('repo_relative_hashed_evidence_required')
        if hashlib.sha256(regular_bytes(self.repo_root / ref)).hexdigest() != value['sha256']:
            raise LimitError('evidence_hash_mismatch')
        return value

    def _public_binding(self, requested_key, public_path=None):
        approved = next((u for u in self.auth['units'] if unit_key(u) == requested_key), None)
        if approved is None:
            raise LimitError('unit_outside_approval')
        self._source_plan_binding()
        actual_path = Path(public_path) if public_path is not None else self.repo_root / approved['public_relative_path']
        if public_digest(actual_path) != approved['public_sha256']:
            raise LimitError('public_snapshot_drift')
        return approved['public_sha256']

    def reserve(self, *, kind, attempt_id, upper_bound_cny, billing_basis, unit=None,
                public_path=None, native_binding=None, run=False):
        """Reserve before dispatch. run=False checks only and creates no state."""
        if type(run) is not bool:
            raise LimitError('run_must_be_boolean')
        if kind not in ('native', 'method') or not isinstance(attempt_id, str) or not LABEL.fullmatch(attempt_id):
            raise LimitError('invalid_attempt_identity')
        if native_binding is not None:
            if kind != 'native':
                raise LimitError('native_binding_outside_native_attempt')
            native_binding = validate_native_binding(native_binding, self.auth)
        upper = fen(upper_bound_cny)
        if upper > 10000:
            raise LimitError('added_cash_budget_exhausted')
        fields(billing_basis, {'kind', 'evidence'})
        if billing_basis['kind'] not in ('included_subscription', 'priced_upper_bound'):
            raise LimitError('billing_upper_bound_required')
        if (billing_basis['kind'] == 'included_subscription' and upper != 0
                or billing_basis['kind'] == 'priced_upper_bound' and upper <= 0):
            raise LimitError('billing_basis_amount_mismatch')
        self._evidence(billing_basis['evidence'])
        public_sha = None
        if kind == 'method':
            public_sha = self._public_binding(unit, public_path)
        elif unit is not None or public_path is not None:
            raise LimitError('native_attempt_has_no_source_task')
        with self._lock(write=run):
            events = self._read()
            attempts, used, held, breach = self._state(events)
            if breach:
                raise LimitError('previous_budget_breach_blocks_dispatch')
            if attempt_id in attempts:
                raise LimitError('attempt_already_reserved_do_not_redispatch')
            supplemental = None
            if kind == 'native':
                original_used = sum(a['kind'] == 'native' and 'native_supplement_id' not in a
                                    for a in attempts.values())
                if original_used >= 2:
                    activation = self._activation(events)
                    if activation is None or native_binding is None:
                        raise LimitError('native_attempt_budget_exhausted')
                    supplemental = activation['data']
                    supplement = self._load_native_supplement(supplemental['supplement_sha256'])
                    grant = next((row for row in supplement['grants'] if row['scope_id'] == attempt_id), None)
                    if grant is None or native_binding != {k: grant[k] for k in native_binding}:
                        raise LimitError('native_scope_outside_supplemental_grants')
                if native_binding is not None:
                    actual = self._public_binding(f"{native_binding['task_id']}:A:{native_binding['replicate']}")
                    if actual != native_binding['public_sha256']:
                        raise LimitError('native_public_binding_mismatch')
            if kind == 'method' and unit in used:
                raise LimitError('method_unit_already_reserved_do_not_redispatch')
            if upper + held > 10000:
                raise LimitError('added_cash_budget_exhausted')
            record = {'attempt_id': attempt_id, 'kind': kind, 'unit_key': unit,
                      'public_sha256': public_sha, 'upper_bound_fen': upper,
                      'billing_basis': billing_basis,
                      'wall_seconds': 600 if kind == 'native' else 300}
            if supplemental is not None:
                record.update(native_binding=dict(native_binding), public_sha256=native_binding['public_sha256'],
                              native_supplement_id=NATIVE_SUPPLEMENT_ID,
                              native_supplement_sha256=supplemental['supplement_sha256'])
            if not run:
                return {'dry_run': True, 'dispatch_allowed': False, 'reservation_would_fit': True,
                        'proposed': record, 'status': self._status(events)}
            event = self._append(events, 'reserved', record)
            return {'dry_run': False, 'dispatch_allowed': True, 'reservation': event,
                    'status': self._status(events)}

    def reserve_diagnostic(self, *, attempt_id, binding, upper_bound_cny, billing_basis, run=False):
        """Reserve independent setup cash in the SAME approved batch journal.

        Does not allocate a native attempt or a method unit. A separate, bound
        provider_request event must be admitted immediately before dispatch.
        The existing approval includes setup diagnostics; its file is unchanged.
        """
        if type(run) is not bool:
            raise LimitError('run_must_be_boolean')
        if (not isinstance(attempt_id, str) or not LABEL.fullmatch(attempt_id)
                or attempt_id.startswith('sk-')):
            raise LimitError('invalid_attempt_identity')
        binding = validate_diagnostic_binding(binding)
        upper = fen(upper_bound_cny)
        if upper > 10000:
            raise LimitError('added_cash_budget_exhausted')
        fields(billing_basis, {'kind', 'evidence'})
        if billing_basis['kind'] != 'priced_upper_bound' or upper <= 0:
            raise LimitError('diagnostic_priced_upper_bound_required')
        self._evidence(billing_basis['evidence'])
        basis = strict_json(canonical(billing_basis))
        with self._lock(write=run):
            events = self._read()
            attempts, _, held, breach = self._state(events)
            if breach:
                raise LimitError('previous_budget_breach_blocks_dispatch')
            if attempt_id in attempts:
                raise LimitError('attempt_already_reserved_do_not_redispatch')
            if any(a['kind'] == 'diagnostic' and a['binding']['dispatch_id'] == binding['dispatch_id']
                   for a in attempts.values()):
                raise LimitError('diagnostic_dispatch_already_reserved_do_not_redispatch')
            if upper + held > 10000:
                raise LimitError('added_cash_budget_exhausted')
            record = {'attempt_id': attempt_id, 'kind': 'diagnostic', 'unit_key': None,
                      'public_sha256': None, 'upper_bound_fen': upper, 'billing_basis': basis,
                      'wall_seconds': 30, 'binding': binding}
            if not run:
                return {'dry_run': True, 'dispatch_allowed': False, 'reservation_would_fit': True,
                        'proposed': record, 'status': self._status(events)}
            event = self._append(events, 'reserved', record)
            return {'dry_run': False, 'dispatch_allowed': True, 'reservation': event,
                    'status': self._status(events)}

    def record_event(self, attempt_id, kind, operation_id):
        """Reserve an observable operation before invoking it; duplicate IDs fail closed."""
        if not self.state_dir.exists():
            raise LimitError('active_reservation_required')
        if not isinstance(operation_id, str) or not LABEL.fullmatch(operation_id):
            raise LimitError('invalid_operation_id')
        with self._lock(write=True):
            events = self._read()
            attempts, _, _, breach = self._state(events)
            if breach:
                raise LimitError('previous_budget_breach_blocks_dispatch')
            a = attempts.get(attempt_id)
            if not a or a['state'] != 'reserved':
                raise LimitError('active_reservation_required')
            if operation_id in a['operations']:
                raise LimitError('operation_already_reserved_do_not_redispatch')
            elapsed = (time.time_ns() - a['reserved_at_unix_ns']) / 10**9
            if elapsed < 0 or elapsed >= a['wall_seconds']:
                raise LimitError('attempt_wall_budget_exhausted_or_clock_regressed')
            limits = EVENT_LIMITS[a['kind']]
            if kind not in limits:
                raise LimitError('unsupported_counted_operation')
            if a['kind'] == 'diagnostic' and operation_id != a['binding']['dispatch_id']:
                raise LimitError('diagnostic_operation_binding_mismatch')
            if a['counters'].get(kind, 0) >= limits[kind]:
                raise LimitError('operation_budget_exhausted')
            event = self._append(events, 'operation_reserved', {'attempt_id': attempt_id,
                                  'kind': kind, 'operation_id': operation_id})
            return {'dispatch_allowed': True, 'reservation': event,
                    'remaining_wall_seconds': a['wall_seconds'] - elapsed}

    def finish(self, attempt_id, *, status, actual_added_cost_cny=None, cost_evidence=None):
        if status not in TERMINAL:
            raise LimitError('invalid_terminal_status')
        return self._close(attempt_id, 'finished', status, actual_added_cost_cny, cost_evidence)

    def settle_cost(self, attempt_id, *, actual_added_cost_cny, cost_evidence):
        if actual_added_cost_cny is None:
            raise LimitError('known_cost_required')
        return self._close(attempt_id, 'cost_settled', None, actual_added_cost_cny, cost_evidence)

    def _close(self, attempt_id, event_name, status, actual, evidence):
        if not self.state_dir.exists():
            raise LimitError('reservation_required')
        paid = None if actual is None else fen(actual)
        if paid is not None:
            self._evidence(evidence)
        elif evidence is not None:
            raise LimitError('unknown_cost_must_not_claim_settlement_evidence')
        with self._lock(write=True):
            events = self._read()
            attempts, _, _, _ = self._state(events)
            a = attempts.get(attempt_id)
            if not a:
                raise LimitError('reservation_required')
            if event_name == 'finished' and a['state'] != 'reserved':
                raise LimitError('attempt_already_finished')
            if event_name == 'cost_settled' and a['state'] == 'reserved':
                raise LimitError('finish_before_cost_settlement')
            if a['actual_added_cost_fen'] is not None:
                raise LimitError('cost_already_settled')
            event = self._append(events, event_name, {'attempt_id': attempt_id, 'status': status,
                                  'actual_added_cost_fen': paid, 'cost_evidence': evidence})
            # A real cost above its bound is retained, then blocks all future dispatch.
            return {'event': event, 'status': self._status(events)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--authorization', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    activate = sub.add_parser('activate-native-supplement', help='Explicit one-time activation of the fixed four-scope supplement')
    activate.add_argument('--expected-sha256', required=True, help='Reviewed SHA-256 of the exact supplement file bytes')
    activate.add_argument('--run', action='store_true')
    reserve = sub.add_parser('reserve')
    reserve.add_argument('--kind', choices=('native', 'method'), required=True)
    reserve.add_argument('--attempt-id', required=True)
    reserve.add_argument('--upper-bound-cny', required=True)
    reserve.add_argument('--billing-basis', type=Path, required=True, help='JSON with kind and hashed evidence reference; no secrets')
    reserve.add_argument('--unit')
    reserve.add_argument('--public-path', type=Path)
    reserve.add_argument('--native-binding', type=Path, help='Exact approved task/project/replicate/public SHA binding JSON')
    reserve.add_argument('--run', action='store_true')
    diagnostic = sub.add_parser('reserve-diagnostic')
    diagnostic.add_argument('--attempt-id', required=True)
    diagnostic.add_argument('--binding', type=Path, required=True, help='Exact provider/request binding JSON; no secrets')
    diagnostic.add_argument('--upper-bound-cny', required=True)
    diagnostic.add_argument('--billing-basis', type=Path, required=True, help='Priced upper bound with hashed evidence reference')
    diagnostic.add_argument('--run', action='store_true')
    event = sub.add_parser('event')
    event.add_argument('--attempt-id', required=True)
    event.add_argument('--kind', required=True)
    event.add_argument('--operation-id', required=True)
    end = sub.add_parser('finish')
    end.add_argument('--attempt-id', required=True)
    end.add_argument('--status', choices=sorted(TERMINAL), required=True)
    end.add_argument('--actual-added-cost-cny')
    end.add_argument('--cost-evidence', type=Path, help='JSON object with ref and sha256')
    settle = sub.add_parser('settle-cost')
    settle.add_argument('--attempt-id', required=True)
    settle.add_argument('--actual-added-cost-cny', required=True)
    settle.add_argument('--cost-evidence', type=Path, required=True)
    args = parser.parse_args()
    try:
        ledger = BatchLedger(args.authorization or args.repo_root / AUTH_RELATIVE, repo_root=args.repo_root)
        if args.command == 'status':
            result = ledger.status()
        elif args.command == 'activate-native-supplement':
            result = ledger.activate_native_supplement(expected_sha256=args.expected_sha256, run=args.run)
        elif args.command == 'reserve':
            result = ledger.reserve(kind=args.kind, attempt_id=args.attempt_id,
                                    upper_bound_cny=args.upper_bound_cny,
                                    billing_basis=read_json(args.billing_basis), unit=args.unit,
                                    public_path=args.public_path,
                                    native_binding=read_json(args.native_binding) if args.native_binding else None,
                                    run=args.run)
        elif args.command == 'reserve-diagnostic':
            result = ledger.reserve_diagnostic(attempt_id=args.attempt_id, binding=read_json(args.binding),
                                               upper_bound_cny=args.upper_bound_cny,
                                               billing_basis=read_json(args.billing_basis), run=args.run)
        elif args.command == 'event':
            result = ledger.record_event(args.attempt_id, args.kind, args.operation_id)
        elif args.command == 'finish':
            result = ledger.finish(args.attempt_id, status=args.status,
                                   actual_added_cost_cny=args.actual_added_cost_cny,
                                   cost_evidence=read_json(args.cost_evidence) if args.cost_evidence else None)
        else:
            result = ledger.settle_cost(args.attempt_id, actual_added_cost_cny=args.actual_added_cost_cny,
                                        cost_evidence=read_json(args.cost_evidence))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (LimitError, OSError, ValueError) as exc:
        print(json.dumps({'error': str(exc) if isinstance(exc, LimitError) else 'local_io_or_contract_error',
                          'dispatch_allowed': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
