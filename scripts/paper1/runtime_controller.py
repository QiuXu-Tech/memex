#!/usr/bin/env python3
"""Durable bridge from paired operations/provider intents to the approved batch.

This trusted controller never calls a model, reads a credential, invents a price,
or increases an approval. A checked, hash-bound billing basis for the ENTIRE
scope is required before reservation. Unknown cash is never settled by tokens.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import runpy
import stat
import threading
import time

HERE = Path(__file__).resolve().parent
BATCH = runpy.run_path(str(HERE / 'batch_limits.py'))
EXPERIMENT = runpy.run_path(str(HERE / 'experiment.py'))
canonical = BATCH['canonical']
digest = BATCH['digest']
HEX = BATCH['HEX']
LABEL = BATCH['LABEL']
PROVIDERS = {
    ('deepseek', 'deepseek-flash', 'https://api.deepseek.com/responses'),
    ('deepseek', 'deepseek-flash', 'https://api.deepseek.com/chat/completions'),
    ('openai', 'text-embedding-3-small', 'https://api.openai.com/v1/embeddings'),
    ('cohere', 'rerank-v3.5', 'https://api.cohere.com/v2/rerank'),
}
SCOPE_KEYS = {'schema_version', 'scope_id', 'kind', 'operation', 'task_id',
              'project_id', 'replicate', 'arm', 'run_id', 'checkpoint_sha256',
              'sealed_checkpoint_sha256', 'dispatch_id', 'request_sha256', 'intent_sha256'}
PROVIDER_KEYS = {'schema_version', 'kind', 'attempt_id', 'scope_id', 'provider',
                 'model', 'endpoint', 'dispatch_id', 'request_sha256',
                 'request_bytes', 'config_sha256', 'checkpoint_sha256',
                 'reference_input_tokens', 'max_output_tokens',
                 'max_response_bytes', 'timeout_ms', 'intent_sha256'}
PROVIDER_KEYS.add('component')
PROVIDER_KEYS.update({'transport_id', 'relay_source_sha256'})
PROVIDER_REQUIRED = {'schema_version', 'kind', 'provider', 'model', 'endpoint',
                     'dispatch_id', 'request_sha256', 'request_bytes', 'config_sha256',
                     'component', 'reference_input_tokens', 'max_output_tokens',
                     'max_response_bytes', 'timeout_ms', 'intent_sha256'}
PROVIDER_SPEC_KEYS = {'provider', 'model', 'endpoint', 'config_sha256',
                      'checked_upper_bound_cny', 'checked_upper_bound_evidence'}
RAWRAG_CONFIG = BATCH['read_json'](HERE / 'rawrag-config.json')
RAWRAG_CONFIG_SHA256 = digest(RAWRAG_CONFIG)
DEEPSEEK_PROFILE = BATCH['read_json'](HERE / 'deepseek-reader-profile.json')
DEEPSEEK_PROFILE_SHA256 = digest(DEEPSEEK_PROFILE)
# Known prefix at official peak CNY 2/M input + 8/M output, plus one final
# unknown/overshooting request covered by the separately checked CNY 3 bound.
# This is a reservation proof, never an actual spend or billing settlement.
DEEPSEEK_PREFIX_FEN = ((65536 * 2 + 8192 * 8) * 100 + 1000000 - 1) // 1000000
DEEPSEEK_SCOPE_FEN = 300 + DEEPSEEK_PREFIX_FEN
DEEPSEEK_BOUNDS = {'request_bytes': 262144, 'reference_input_tokens': 65536,
                  'max_output_tokens': 8192, 'max_response_bytes': 4194304,
                  'timeout_ms': 30000}
# The original 16 KiB Raw-RAG limit is for its query file, not a batched HTTP
# body. Retain this separate outer wire guard; do not relabel it as an upstream
# method parameter. All other retrieval bounds come from the unchanged config.
RAWRAG_WIRE_MAX_BYTES = 2**24


class ControllerError(ValueError):
    pass


def relay_source_sha256():
    return hashlib.sha256(BATCH['regular_bytes'](HERE / 'deepseek_native_relay.py')).hexdigest()


def current_utc_date():
    return datetime.now(timezone.utc).date().isoformat()


def _guarded_provider(intent):
    return (intent.get('provider') == 'deepseek' and intent.get('model') == 'deepseek-flash'
            and intent.get('endpoint') == 'https://api.deepseek.com/responses'
            and intent.get('config_sha256') == DEEPSEEK_PROFILE_SHA256)


def _private_artifact(path, *, directory=False):
    if not isinstance(path, (str, Path)) or not Path(path).is_absolute():
        raise ControllerError('transport_absolute_private_path_required')
    value = Path(path)
    if any(part.is_symlink() for part in (value, *value.parents)):
        raise ControllerError('transport_symlink_forbidden')
    try:
        info = value.lstat()
    except OSError:
        raise ControllerError('transport_artifact_unavailable') from None
    if value != value.resolve(strict=True):
        raise ControllerError('transport_normalized_path_required')
    if (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
            or (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)):
        raise ControllerError('transport_private_artifact_required')
    return value


def _transport_json(path, expected_hash):
    value = _private_artifact(path)
    raw = BATCH['regular_bytes'](value)
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ControllerError('transport_evidence_hash_mismatch')
    return BATCH['strict_json'](raw.decode('utf-8'))


def _valid_provider_usage(value):
    return (isinstance(value, dict) and set(value) == {'input_tokens', 'cached_input_tokens', 'output_tokens'}
            and all(type(number) is int and 0 <= number <= 2**53 - 1 for number in value.values())
            and value['input_tokens'] > 0 and value['cached_input_tokens'] <= value['input_tokens'])


def _hash(value):
    return isinstance(value, str) and bool(HEX.fullmatch(value))


def _label(value):
    return isinstance(value, str) and bool(LABEL.fullmatch(value)) and not value.startswith('sk-')


def _intent(value, *, provider=False):
    if not isinstance(value, dict) or set(value) - (PROVIDER_KEYS if provider else SCOPE_KEYS):
        raise ControllerError('unexpected_intent_fields')
    required = {'dispatch_id', 'request_sha256', 'intent_sha256'}
    if not required <= set(value) or not _label(value['dispatch_id']):
        raise ControllerError('invalid_intent_identity')
    if value.get('schema_version') != 1 or type(value.get('schema_version')) is not int:
        raise ControllerError('invalid_intent_schema')
    if provider:
        if not PROVIDER_REQUIRED <= set(value):
            raise ControllerError('incomplete_provider_intent')
        if value.get('kind') not in {'p1-provider-dispatch-intent', 'p1-deepseek-extraction-intent', 'p1-deepseek-native-intent'}:
            raise ControllerError('invalid_provider_intent_kind')
        if value['component'] not in {'embedding', 'rerank', 'reader', 'extraction', 'compaction', 'prelude'}:
            raise ControllerError('invalid_provider_component')
        for name in ('request_bytes', 'reference_input_tokens', 'max_output_tokens', 'max_response_bytes', 'timeout_ms'):
            if type(value[name]) is not int or value[name] < 0:
                raise ControllerError('invalid_provider_measurement')
        if not _hash(value['config_sha256']):
            raise ControllerError('invalid_provider_config_digest')
        if ('transport_id' in value and not _label(value['transport_id'])
                or 'relay_source_sha256' in value and not _hash(value['relay_source_sha256'])):
            raise ControllerError('invalid_provider_transport_identity')
    if not all(_hash(value[k]) for k in ('request_sha256', 'intent_sha256')):
        raise ControllerError('invalid_intent_digest')
    if digest({k: v for k, v in value.items() if k != 'intent_sha256'}) != value['intent_sha256']:
        raise ControllerError('intent_digest_mismatch')
    if not provider and set(value) != SCOPE_KEYS:
        raise ControllerError('incomplete_scope_intent')
    if not provider and any(not _label(value[name]) for name in ('scope_id', 'run_id')):
        raise ControllerError('invalid_scope_identity')
    return copy.deepcopy(value)


def _receipt(intent, admission):
    return {'schema_version': 1, 'kind': 'p1-dispatch-admission-receipt',
            'decision': 'allow', 'dispatch_id': intent['dispatch_id'],
            'intent_sha256': intent['intent_sha256'],
            'request_sha256': intent['request_sha256'], 'admission_id': admission}


class _NonblockingBatchLedger(BATCH['BatchLedger']):
    """Reuse the canonical ledger and its checks, with nonblocking lock entry.

    Only the lock acquisition policy differs from BatchLedger._lock. Its
    authorization, paths, reservation, journal, counters and cash rules remain
    inherited. No alternate ledger or budget is introduced.
    """
    @contextmanager
    def _lock(self, write=False):
        self._check_auth()
        for path in (self.state_dir, *self.state_dir.parents):
            if path.is_symlink():
                raise BATCH['LimitError']('symlink_forbidden')
        if not self.state_dir.exists():
            if not write:
                yield
                return
            self.state_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
            self._fsync_dir(self.state_dir.parent)
        flags = os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0) | (os.O_CREAT if write else 0)
        fresh = write and not self.lock_path.exists()
        try:
            descriptor = os.open(self.lock_path, flags, 0o600)
        except FileNotFoundError:
            if self.journal.exists():
                raise BATCH['LimitError']('ledger_lock_missing')
            yield
            return
        except OSError as error:
            raise BATCH['LimitError']('unsafe_ledger_lock') from error
        with os.fdopen(descriptor, 'r+b') as lock:
            if not stat.S_ISREG(os.fstat(lock.fileno()).st_mode):
                raise BATCH['LimitError']('unsafe_ledger_lock')
            try:
                fcntl.flock(lock, (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ControllerError('canonical_ledger_busy') from error
            try:
                self._fresh_context = fresh
                yield
            finally:
                self._fresh_context = False
                fcntl.flock(lock, fcntl.LOCK_UN)


class CanonicalPairedController:
    """One active device owns this controller and the original canonical ledger.

    scope_specs maps scope_id to a fixed {kind, unit, public_path,
    upper_bound_cny, billing_basis, providers, max_http_dispatches} object.
    Each provider has provider/model/endpoint/config_sha256 plus a decimal
    checked_upper_bound_cny and checked_upper_bound_evidence:{ref,sha256}.
    Legacy reservations cover max_http_dispatches times the largest bound.
    The pinned Responses transport can instead prove a serial cumulative token
    envelope with independently persisted completion handshakes.
    Every provider request is bound to the latest admitted operation; native
    generation/compaction counts are reserved here, not by an optional caller.
    The caller must check price coverage, currency and service access before
    supplying these specs. Hashes attest bytes, not price truth or account access.
    """
    def __init__(self, scope_specs, *, repo_root=None, state_dir=None, run=False):
        if type(run) is not bool or not isinstance(scope_specs, dict):
            raise ControllerError('invalid_controller_options')
        self.root = Path(repo_root or HERE.parents[1]).absolute()
        self.ledger = _NonblockingBatchLedger(self.root / BATCH['AUTH_RELATIVE'], repo_root=self.root)
        self.state = Path(state_dir or self.ledger.state_dir / 'runtime-controller').absolute()
        if self.state != self.ledger.state_dir / 'runtime-controller':
            raise ControllerError('one_canonical_runtime_controller_required')
        self.run = run
        self.specs = copy.deepcopy(scope_specs)
        self._mutex = threading.RLock()
        for name, spec in self.specs.items():
            self._validate_spec(name, spec)

    def _validate_spec(self, name, spec, *, enforce_fresh=True):
        required = {'kind', 'unit', 'public_path', 'upper_bound_cny', 'billing_basis',
                    'providers', 'max_http_dispatches'}
        if not _label(name) or not isinstance(spec, dict) or set(spec) != required:
            raise ControllerError('invalid_scope_spec')
        if spec['kind'] not in ('native', 'method'):
            raise ControllerError('invalid_scope_kind')
        if (type(spec['max_http_dispatches']) is not int
                or not 1 <= spec['max_http_dispatches'] <= (20 if spec['kind'] == 'native' else 64)):
            raise ControllerError('invalid_dispatch_envelope')
        if (spec['kind'] == 'native' and (spec['unit'] is not None or spec['public_path'] is not None)
                or spec['kind'] == 'method' and not isinstance(spec['unit'], str)):
            raise ControllerError('scope_unit_mismatch')
        if (BATCH['fen'](spec['upper_bound_cny']) <= 0 or not isinstance(spec['billing_basis'], dict)
                or spec['billing_basis'].get('kind') != 'priced_upper_bound'):
            raise ControllerError('checked_priced_scope_required')
        BATCH['fields'](spec['billing_basis'], {'kind', 'evidence'})
        self.ledger._evidence(spec['billing_basis']['evidence'])
        if not isinstance(spec['providers'], list) or not spec['providers']:
            raise ControllerError('provider_envelope_required')
        seen, per_request_bounds, retrieval_bounds, envelope = set(), [], [], None
        for item in spec['providers']:
            if (not isinstance(item, dict) or not PROVIDER_SPEC_KEYS <= set(item)
                    or set(item) - PROVIDER_SPEC_KEYS - {'scope_usage_envelope'}):
                raise ControllerError('invalid_provider_envelope')
            key = tuple(item[k] for k in ('provider', 'model', 'endpoint'))
            if key not in PROVIDERS or key in seen or not _hash(item['config_sha256']):
                raise ControllerError('unapproved_provider_envelope')
            if item['provider'] != 'deepseek' and (spec['kind'] != 'method' or ':B:' not in spec['unit']):
                raise ControllerError('retrieval_provider_outside_B')
            if item['provider'] != 'deepseek' and item['config_sha256'] != RAWRAG_CONFIG_SHA256:
                raise ControllerError('rawrag_config_binding_mismatch')
            per_request = BATCH['fen'](item['checked_upper_bound_cny'])
            if item['provider'] == 'deepseek' and per_request < 300:
                raise ControllerError('deepseek_per_request_cash_floor')
            if per_request <= 0:
                raise ControllerError('positive_provider_cash_bound_required')
            self.ledger._evidence(item['checked_upper_bound_evidence'])
            per_request_bounds.append(per_request)
            if item['provider'] != 'deepseek':
                retrieval_bounds.append(per_request)
            if 'scope_usage_envelope' in item:
                expected = {'kind': 'deepseek-native-serial-envelope-v1',
                    'relay_source_sha256': relay_source_sha256(), 'max_input_tokens': 65536,
                    'max_output_tokens': 8192, 'max_http_dispatches': 8,
                    'scope_upper_bound_cny': BATCH['money'](DEEPSEEK_SCOPE_FEN)}
                if (not _guarded_provider(item) or item['scope_usage_envelope'] != expected or per_request != 300
                        or digest(BATCH['read_json'](HERE / 'deepseek-reader-profile.json')) != DEEPSEEK_PROFILE_SHA256
                        or envelope is not None):
                    raise ControllerError('invalid_deepseek_scope_usage_envelope')
                facts = BATCH['read_json'](self.root / item['checked_upper_bound_evidence']['ref'])
                price_fields = {'schema_version': 1, 'kind': 'p1-deepseek-public-price-basis',
                    'provider': 'deepseek', 'model': 'deepseek-flash', 'checked_date': DEEPSEEK_PROFILE.get('checked_date'),
                    'currency': 'CNY', 'peak_input_cny_per_million': '2.00', 'peak_output_cny_per_million': '8.00',
                    'context_token_upper_bound': 1048576, 'max_output_tokens': 8192,
                    'source_url': 'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/'}
                if (not isinstance(facts, dict) or type(facts.get('schema_version')) is not int
                        or any(facts.get(key) != value for key, value in price_fields.items())
                        or facts.get('actual_added_cash_cny') is not None):
                    raise ControllerError('deepseek_scope_price_basis_mismatch')
                if enforce_fresh and DEEPSEEK_PROFILE.get('checked_date') != current_utc_date():
                    raise ControllerError('deepseek_scope_price_verification_expired')
                envelope = expected
            seen.add(key)
        if envelope is not None:
            # No additional DeepSeek endpoint or profile may hide behind the
            # one registered transport proof. B retains its original 16 total
            # non-DeepSeek dispatch bound, independently of the 8 reader calls.
            if sum(item['provider'] == 'deepseek' for item in spec['providers']) != 1:
                raise ControllerError('ambiguous_deepseek_scope_envelope')
            floor = DEEPSEEK_SCOPE_FEN + (RAWRAG_CONFIG['limits']['max_http_dispatches'] * max(retrieval_bounds)
                                        if retrieval_bounds else 0)
        else:
            floor = spec['max_http_dispatches'] * max(per_request_bounds)
        if BATCH['fen'](spec['upper_bound_cny']) < floor:
            raise ControllerError('scope_cash_bound_insufficient')

    @contextmanager
    def _locked(self):
        if not self.run:
            raise ControllerError('explicit_run_required')
        if not self._mutex.acquire(blocking=False):
            raise ControllerError('controller_busy')
        try:
            for path in (self.state, *self.state.parents):
                if path.is_symlink():
                    raise ControllerError('controller_symlink_forbidden')
            self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(self.state / 'controller.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise ControllerError('unsafe_controller_lock')
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise ControllerError('controller_busy') from error
                path = self.state / 'events.jsonl'
                head_path = self.state / 'HEAD.json'
                journal = EXPERIMENT['Journal'](path)
                if path.exists() != head_path.exists():
                    raise ControllerError('controller_head_requires_reconciliation')
                if head_path.exists():
                    head = BATCH['read_json'](head_path)
                    if head != {'seq': len(journal.records), 'sha256': journal.previous}:
                        raise ControllerError('controller_head_mismatch')
                yield journal
            finally:
                os.close(fd)
        finally:
            self._mutex.release()

    def _append(self, journal, event):
        journal.append(event)
        head = {'seq': len(journal.records), 'sha256': journal.previous}
        temporary = self.state / ('head-' + os.urandom(12).hex() + '.tmp')
        with temporary.open('x', encoding='utf-8') as f:
            f.write(canonical(head) + '\n'); f.flush(); os.fsync(f.fileno())
        os.replace(temporary, self.state / 'HEAD.json')
        BATCH['BatchLedger']._fsync_dir(self.state)
        return 'runtime-' + journal.previous

    def register_transport(self, registration):
        """Bind one actual relay's private immutable audit root before dispatch.

        The native backend calls this after a canonical scope is reserved and
        after constructing its credential-free relay, before activating it.
        """
        required = {'schema_version', 'kind', 'transport_id', 'audit_root', 'config_sha256',
                    'relay_source_sha256', 'evidence'}
        if (not isinstance(registration, dict) or set(registration) != required
                or type(registration.get('schema_version')) is not int or registration['schema_version'] != 1
                or registration['kind'] != 'p1-deepseek-relay-registration'
                or not _label(registration['transport_id'])
                or registration['config_sha256'] != DEEPSEEK_PROFILE_SHA256
                or registration['relay_source_sha256'] != relay_source_sha256()
                or digest(BATCH['read_json'](HERE / 'deepseek-reader-profile.json')) != DEEPSEEK_PROFILE_SHA256):
            raise ControllerError('invalid_relay_transport_registration')
        root = _private_artifact(registration['audit_root'], directory=True)
        protected = [self.ledger.state_dir]
        protected += [Path(spec['public_path']) for spec in self.specs.values() if spec['public_path']]
        protected += [self.root / unit['public_relative_path'] for unit in self.ledger.auth['units']]
        if any(root == p or root.is_relative_to(p) or p.is_relative_to(root) for p in protected):
            raise ControllerError('transport_root_overlaps_protected_state')
        evidence = registration['evidence']
        if (not isinstance(evidence, dict) or set(evidence) != {'path', 'sha256'}
                or evidence['path'] != str(root / 'transport.json') or not _hash(evidence['sha256'])):
            raise ControllerError('invalid_transport_registration_evidence')
        body = {key: value for key, value in registration.items() if key != 'evidence'}
        if _transport_json(evidence['path'], evidence['sha256']) != body:
            raise ControllerError('transport_registration_evidence_mismatch')
        with self._locked() as journal:
            active = [r['scope_id'] for r in journal.records if r['event'] == 'scope_admitted'
                      and not any(e['event'] == 'scope_finished' and e['scope_id'] == r['scope_id'] for e in journal.records)]
            if not active:
                raise ControllerError('transport_requires_reserved_scope')
            for scope_id in active:
                self._active(journal, scope_id)
            matches = [r for r in journal.records if r['event'] == 'transport_registered'
                       and r['registration']['transport_id'] == registration['transport_id']]
            if matches:
                if len(matches) != 1 or matches[0]['registration'] != registration:
                    raise ControllerError('transport_registration_changed')
                return copy.deepcopy(matches[0]['receipt'])
            if any(r['event'] == 'transport_registered' and r['registration']['audit_root'] == str(root) for r in journal.records):
                raise ControllerError('transport_root_already_registered')
            # Receipt identity is independent of the containing journal row,
            # avoiding a circular hash. The row and canonical HEAD seal it.
            receipt = {'schema_version': 1, 'kind': 'p1-relay-registration-receipt',
                'transport_id': registration['transport_id'], 'config_sha256': registration['config_sha256'],
                'relay_source_sha256': registration['relay_source_sha256'], 'registration_sha256': digest(registration),
                'admission_id': 'transport-' + digest(registration)}
            self._append(journal, {'event': 'transport_registered', 'scope_id': None,
                'registration': copy.deepcopy(registration), 'receipt': receipt})
            return receipt

    def _transport(self, journal, transport_id, *, current=True):
        rows = [r for r in journal.records if r['event'] == 'transport_registered'
                and r['registration']['transport_id'] == transport_id]
        if len(rows) != 1:
            raise ControllerError('registered_relay_transport_required')
        value = rows[0]['registration']
        _private_artifact(value['audit_root'], directory=True)
        if _transport_json(value['evidence']['path'], value['evidence']['sha256']) != {
                key: item for key, item in value.items() if key != 'evidence'}:
            raise ControllerError('transport_registration_evidence_mismatch')
        if current and (value['relay_source_sha256'] != relay_source_sha256()
                        or value['config_sha256'] != digest(BATCH['read_json'](HERE / 'deepseek-reader-profile.json'))):
            raise ControllerError('registered_transport_source_or_profile_changed')
        return value

    def _completion_record(self, journal, message, intent, scope_id):
        transport = self._transport(journal, message['transport_id'], current=False)
        if (intent.get('transport_id') != message['transport_id']
                or intent.get('relay_source_sha256') != transport['relay_source_sha256']):
            raise ControllerError('completion_transport_binding_mismatch')
        directory = _private_artifact(Path(transport['audit_root']) / 'dispatches', directory=True)
        target = directory / (message['dispatch_id'] + '.json')
        value = _transport_json(target, message['record_sha256'])
        keys = {'schema_version', 'kind', 'transport_id', 'relay_source_sha256', 'config_sha256',
                'scope_id', 'dispatch_id', 'intent_sha256', 'request_sha256', 'provider_dispatch_started',
                'status', 'usage', 'usage_complete', 'terminal_event', 'response_sha256', 'response_bytes', 'error_code'}
        if (not isinstance(value, dict) or set(value) != keys or type(value['schema_version']) is not int
                or value['schema_version'] != 1 or value['kind'] != 'p1-deepseek-dispatch-result'
                or value['scope_id'] != scope_id or value['status'] not in {'completed', 'failed'}
                or type(value['provider_dispatch_started']) is not bool or type(value['usage_complete']) is not bool
                or any(value[key] != intent.get(key) for key in
                    ('transport_id', 'relay_source_sha256', 'config_sha256', 'dispatch_id', 'intent_sha256', 'request_sha256'))
                or value['terminal_event'] not in {None, 'response.completed', 'response.incomplete', 'response.failed'}
                or value['response_sha256'] is not None and not _hash(value['response_sha256'])
                or value['response_bytes'] is not None and (type(value['response_bytes']) is not int or value['response_bytes'] < 0)
                or value['usage'] is not None and not _valid_provider_usage(value['usage'])
                or value['error_code'] is not None and not _label(value['error_code'])):
            raise ControllerError('invalid_immutable_completion_record')
        # Invalid usage is retained as unknown, never coerced to a zero count.
        return value, str(target)

    def _guard_state(self, journal, scope_id, *, verify_evidence=True):
        admissions = [r for r in journal.records if r['event'] == 'provider_admitted'
                      and r['scope_id'] == scope_id and _guarded_provider(r['intent'])]
        state = {'input_tokens': 0, 'cached_input_tokens': 0, 'output_tokens': 0,
                 'reference_input_tokens': sum(r['intent']['reference_input_tokens'] for r in admissions),
                 'dispatches': len(admissions), 'pending': [], 'blocked': False, 'usage_complete': True}
        for admitted in admissions:
            intent = admitted['intent']
            endings = [r for r in journal.records if r['event'] == 'provider_completed'
                       and r['scope_id'] == scope_id and r['completion']['dispatch_id'] == intent['dispatch_id']]
            if not endings:
                state['pending'].append(intent['dispatch_id']); state['usage_complete'] = False
                continue
            if len(endings) != 1:
                raise ControllerError('duplicate_provider_completion_state')
            ended = endings[0]
            if verify_evidence:
                try:
                    observed, _ = self._completion_record(journal, ended['completion'], intent, scope_id)
                except (ValueError, OSError, UnicodeError):
                    raise ControllerError('deepseek_completion_evidence_changed') from None
                if observed != ended['record']:
                    raise ControllerError('deepseek_completion_evidence_changed')
            record = ended['record']; usage = record['usage']
            valid = (record['provider_dispatch_started'] is True and record['usage_complete'] is True
                     and _valid_provider_usage(usage))
            if valid:
                for key in ('input_tokens', 'cached_input_tokens', 'output_tokens'):
                    state[key] += usage[key]
            else:
                state['usage_complete'] = False
            if (not valid or ended['blocked'] or record['status'] != 'completed'
                    or record['terminal_event'] != 'response.completed'
                    or valid and usage['output_tokens'] > intent['max_output_tokens']):
                state['blocked'] = True
        if (state['input_tokens'] > DEEPSEEK_PROFILE['max_model_input_tokens']
                or state['output_tokens'] > DEEPSEEK_PROFILE['max_model_output_tokens']):
            state['blocked'] = True
        return state

    def _require_guard_clear(self, journal, scope_id):
        state = self._guard_state(journal, scope_id)
        if state['blocked']:
            raise ControllerError('deepseek_scope_usage_blocked')
        if state['pending']:
            raise ControllerError('deepseek_dispatch_completion_required')
        return state

    def complete_dispatch(self, completion, *, scope_id):
        """Read a bound immutable relay result, persist usage, and close in-flight.

        No caller-provided quantity is accepted. Late reports remain evidence
        and permanently block further work; they do not reopen or settle cash.
        """
        keys = {'schema_version', 'kind', 'transport_id', 'dispatch_id',
                'request_sha256', 'intent_sha256', 'record_sha256'}
        if (not isinstance(completion, dict) or set(completion) != keys
                or type(completion['schema_version']) is not int or completion['schema_version'] != 1
                or completion['kind'] != 'p1-provider-dispatch-completion'
                or not _label(scope_id) or not _label(completion['transport_id']) or not _label(completion['dispatch_id'])
                or not all(_hash(completion[key]) for key in ('request_sha256', 'intent_sha256', 'record_sha256'))):
            raise ControllerError('invalid_provider_completion')
        with self._locked() as journal:
            rows = [r for r in journal.records if r['event'] == 'provider_admitted' and r['scope_id'] == scope_id
                    and r['intent']['dispatch_id'] == completion['dispatch_id']]
            if len(rows) != 1 or not _guarded_provider(rows[0]['intent']):
                raise ControllerError('completion_requires_admitted_guarded_dispatch')
            intent = rows[0]['intent']
            if any(completion[key] != intent[key] for key in ('request_sha256', 'intent_sha256', 'transport_id')):
                raise ControllerError('completion_request_binding_mismatch')
            if any(r['event'] == 'provider_completed' and r['scope_id'] == scope_id
                   and r['completion']['dispatch_id'] == intent['dispatch_id'] for r in journal.records):
                raise ControllerError('provider_completion_already_recorded')
            value, path = self._completion_record(journal, completion, intent, scope_id)
            prior = self._guard_state(journal, scope_id)
            finished = any(r['event'] == 'scope_finished' and r['scope_id'] == scope_id for r in journal.records)
            attempts = self.ledger.status()['attempts']
            attempt = attempts.get(scope_id)
            late = (finished or not attempt or attempt['state'] != 'reserved'
                    or not 0 <= (time.time_ns() - attempt['reserved_at_unix_ns']) / 1e9 < attempt['wall_seconds']
                    or not 0 <= (time.time_ns() - rows[0]['admitted_at_unix_ns']) / 1e6 <= intent['timeout_ms'])
            drifted = (intent['relay_source_sha256'] != relay_source_sha256()
                       or intent['config_sha256'] != digest(BATCH['read_json'](HERE / 'deepseek-reader-profile.json')))
            if any('scope_usage_envelope' in provider for provider in self.specs[scope_id]['providers']):
                drifted = drifted or DEEPSEEK_PROFILE.get('checked_date') != current_utc_date()
            valid = (value['provider_dispatch_started'] is True and value['usage_complete'] is True
                     and _valid_provider_usage(value['usage']))
            totals = {key: prior[key] + (value['usage'][key] if valid else 0)
                      for key in ('input_tokens', 'cached_input_tokens', 'output_tokens')}
            blocked = (prior['blocked'] or late or drifted or not valid or value['status'] != 'completed'
                or value['terminal_event'] != 'response.completed' or value['response_sha256'] is None
                or value['response_bytes'] is None or value['response_bytes'] > intent['max_response_bytes']
                or totals['input_tokens'] > DEEPSEEK_PROFILE['max_model_input_tokens']
                or totals['output_tokens'] > DEEPSEEK_PROFILE['max_model_output_tokens']
                or valid and value['usage']['output_tokens'] > intent['max_output_tokens'])
            admission = self._append(journal, {'event': 'provider_completed', 'scope_id': scope_id,
                'completion': copy.deepcopy(completion), 'record': value, 'record_path': path,
                'blocked': bool(blocked), 'late': bool(late), 'usage_totals': totals,
                'actual_added_cost_cny': None})
            return {'schema_version': 1, 'kind': 'p1-dispatch-completion-receipt',
                'dispatch_id': completion['dispatch_id'], 'intent_sha256': completion['intent_sha256'],
                'record_sha256': completion['record_sha256'], 'decision': 'blocked' if blocked else 'continue',
                'admission_id': admission}

    def _spec(self, intent):
        spec = self.specs.get(intent['scope_id'])
        if spec is None or spec['kind'] != intent['kind']:
            raise ControllerError('scope_not_in_execution_plan')
        if intent['kind'] == 'method':
            expected = f"{intent['task_id']}:{intent['arm']}:{intent['replicate']}"
            if (expected != spec['unit'] or not _hash(intent['checkpoint_sha256'])
                    or not _hash(intent['sealed_checkpoint_sha256'])):
                raise ControllerError('method_binding_mismatch')
        elif (intent['arm'] is not None or intent['checkpoint_sha256'] is not None
              or intent['sealed_checkpoint_sha256'] is not None):
            raise ControllerError('native_scope_binding_mismatch')
        if (intent['task_id'] not in BATCH['PROJECTS']
                or intent['project_id'] != BATCH['PROJECTS'][intent['task_id']]
                or type(intent['replicate']) is not int or intent['replicate'] not in (1, 2)):
            raise ControllerError('unapproved_task_binding')
        return spec

    def _active(self, journal, scope_id, *, enforce_deadline=True):
        admissions = [r for r in journal.records if r['event'] == 'scope_admitted' and r['scope_id'] == scope_id]
        if len(admissions) != 1 or any(r['event'] == 'scope_finished' and r['scope_id'] == scope_id for r in journal.records):
            raise ControllerError('active_controller_scope_required')
        record = admissions[0]
        spec = self.specs.get(scope_id)
        if spec is None or digest(spec) != record['spec_sha256']:
            raise ControllerError('scope_spec_changed')
        self._validate_spec(scope_id, spec, enforce_fresh=enforce_deadline)
        status = self.ledger.status()
        attempt = status['attempts'].get(scope_id)
        if (status['budget_breach_observed'] or not attempt or attempt['state'] != 'reserved'
                or attempt['kind'] != spec['kind']):
            raise ControllerError('active_batch_reservation_required')
        elapsed = (time.time_ns() - attempt['reserved_at_unix_ns']) / 1e9
        if enforce_deadline and (elapsed < 0 or elapsed >= attempt['wall_seconds']):
            raise ControllerError('scope_deadline_exhausted')
        return record, spec, attempt, attempt['wall_seconds'] - elapsed

    def native_binding(self, *, task_id, project_id, replicate):
        """Bind a named native grant to the unchanged, present public source."""
        if (task_id not in BATCH['PROJECTS'] or project_id != BATCH['PROJECTS'][task_id]
                or type(replicate) is not int or replicate not in (1, 2)):
            raise ControllerError('unapproved_task_binding')
        public_sha256 = self.ledger._public_binding(f'{task_id}:A:{replicate}')
        return BATCH['validate_native_binding']({'task_id': task_id, 'project_id': project_id,
            'replicate': replicate, 'public_sha256': public_sha256}, self.ledger.auth)

    def inspect_scope(self, intent):
        intent = _intent(intent)
        spec = self._spec(intent)
        return self.ledger.reserve(kind=spec['kind'], attempt_id=intent['scope_id'],
            upper_bound_cny=spec['upper_bound_cny'], billing_basis=spec['billing_basis'],
            unit=spec['unit'], public_path=spec['public_path'],
            native_binding=self.native_binding(**{key: intent[key] for key in ('task_id', 'project_id', 'replicate')})
                           if spec['kind'] == 'native' else None, run=False)

    def admit_scope(self, intent):
        intent = _intent(intent)
        if intent['operation'] != 'admit_scope':
            raise ControllerError('scope_admission_operation_required')
        spec = self._spec(intent)
        with self._locked() as journal:
            if any(r['scope_id'] == intent['scope_id'] for r in journal.records):
                raise ControllerError('scope_already_seen_no_replay')
            result = self.ledger.reserve(kind=spec['kind'], attempt_id=intent['scope_id'],
                upper_bound_cny=spec['upper_bound_cny'], billing_basis=spec['billing_basis'],
                unit=spec['unit'], public_path=spec['public_path'],
                native_binding=self.native_binding(**{key: intent[key] for key in ('task_id', 'project_id', 'replicate')})
                               if spec['kind'] == 'native' else None, run=True)
            admission = self._append(journal, {'event': 'scope_admitted', 'scope_id': intent['scope_id'],
                'intent': intent, 'spec_sha256': digest(spec),
                'batch_reservation_sha256': result['reservation']['sha256']})
            return _receipt(intent, admission)

    def before_operation(self, intent):
        intent = _intent(intent)
        self._spec(intent)
        operations = {'native': {'capture_parent', 'prime_D', 'compact_parent'},
                      'method': {'verify_checkpoint', 'fork_parent', 'build_packet', 'continue_reader'}}
        if intent['operation'] not in operations[intent['kind']]:
            raise ControllerError('operation_outside_scope')
        with self._locked() as journal:
            admitted, _, _, _ = self._active(journal, intent['scope_id'])
            self._require_guard_clear(journal, intent['scope_id'])
            keys = ('scope_id', 'kind', 'task_id', 'project_id', 'replicate', 'arm', 'run_id',
                    'checkpoint_sha256', 'sealed_checkpoint_sha256')
            if any(intent[k] != admitted['intent'][k] for k in keys):
                raise ControllerError('operation_binding_mismatch')
            if any(r.get('intent', {}).get('dispatch_id') == intent['dispatch_id'] for r in journal.records):
                raise ControllerError('operation_already_admitted_no_replay')
            admission = self._append(journal, {'event': 'operation_admitted', 'scope_id': intent['scope_id'], 'intent': intent})
            return _receipt(intent, admission)

    def record_action(self, scope_id, kind, operation_id):
        """Reserve non-provider tools/opens; HTTP owns generation/compaction."""
        if kind in {'generation_start', 'compaction_start'}:
            raise ControllerError('provider_action_is_counted_at_dispatch')
        with self._locked() as journal:
            self._active(journal, scope_id)
            self._require_guard_clear(journal, scope_id)
            event = self.ledger.record_event(scope_id, kind, operation_id)['reservation']
            self._append(journal, {'event': 'action_admitted', 'scope_id': scope_id,
                'kind': kind, 'operation_id': operation_id, 'batch_event_sha256': event['sha256']})
            return event

    def authorize_dispatch(self, intent, *, scope_id):
        """Network-boundary admission; every adapter retry needs a fresh ID."""
        intent = _intent(intent, provider=True)
        if intent.get('attempt_id', scope_id) != scope_id or intent.get('scope_id', scope_id) != scope_id:
            raise ControllerError('provider_scope_mismatch')
        with self._locked() as journal:
            admitted, spec, attempt, remaining = self._active(journal, scope_id)
            guarded_state = self._require_guard_clear(journal, scope_id)
            envelope = {k: intent[k] for k in ('provider', 'model', 'endpoint', 'config_sha256')}
            if not any(all(item[k] == value for k, value in envelope.items()) for item in spec['providers']):
                raise ControllerError('provider_outside_checked_envelope')
            if intent.get('checkpoint_sha256', admitted['intent']['checkpoint_sha256']) != admitted['intent']['checkpoint_sha256']:
                raise ControllerError('provider_checkpoint_mismatch')
            operations = [r['intent'] for r in journal.records if r['event'] == 'operation_admitted' and r['scope_id'] == scope_id]
            if not operations:
                raise ControllerError('paired_operation_admission_required')
            operation = operations[-1]
            allowed = ({'capture_parent': {'prelude'}, 'prime_D': {'extraction'}, 'compact_parent': {'compaction'}}
                       if spec['kind'] == 'native' else
                       {'verify_checkpoint': set(), 'fork_parent': set(), 'continue_reader': {'reader'},
                        'build_packet': {'embedding', 'rerank'} if admitted['intent']['arm'] == 'B' else
                                        {'extraction'} if admitted['intent']['arm'] in {'C', 'D'} else set()})
            if intent['component'] not in allowed.get(operation['operation'], set()):
                raise ControllerError('provider_component_outside_operation')
            expected_provider = {'embedding': 'openai', 'rerank': 'cohere'}.get(intent['component'], 'deepseek')
            if intent['provider'] != expected_provider:
                raise ControllerError('provider_component_provider_mismatch')
            if intent['provider'] == 'deepseek':
                bounds = DEEPSEEK_BOUNDS
                if intent['kind'] not in {'p1-deepseek-native-intent', 'p1-deepseek-extraction-intent'} or intent['max_output_tokens'] < 1:
                    raise ControllerError('provider_request_envelope_exceeded')
                if _guarded_provider(intent):
                    transport = self._transport(journal, intent.get('transport_id'))
                    if (intent.get('relay_source_sha256') != transport['relay_source_sha256']
                            or intent['config_sha256'] != transport['config_sha256']):
                        raise ControllerError('provider_transport_binding_mismatch')
                    if (guarded_state['dispatches'] >= DEEPSEEK_PROFILE['max_http_dispatches']
                            or guarded_state['reference_input_tokens'] + intent['reference_input_tokens']
                               > DEEPSEEK_PROFILE['reference_input_token_limit']
                            or guarded_state['input_tokens'] >= DEEPSEEK_PROFILE['max_model_input_tokens']):
                        raise ControllerError('deepseek_cumulative_dispatch_or_input_budget')
                    if intent['max_output_tokens'] > DEEPSEEK_PROFILE['max_model_output_tokens'] - guarded_state['output_tokens']:
                        raise ControllerError('deepseek_remaining_output_budget')
            else:
                bounds = {'request_bytes': RAWRAG_WIRE_MAX_BYTES,
                          'reference_input_tokens': RAWRAG_CONFIG['limits']['max_processed_input_tokens'],
                          'max_output_tokens': 0, 'max_response_bytes': RAWRAG_CONFIG['limits']['max_response_bytes'],
                          'timeout_ms': min(30000, int(RAWRAG_CONFIG['runtime']['request_timeout_seconds'] * 1000))}
                if intent['kind'] != 'p1-provider-dispatch-intent':
                    raise ControllerError('provider_request_envelope_exceeded')
            if (any(intent[name] > maximum for name, maximum in bounds.items())
                    or any(intent[name] <= 0 for name in ('request_bytes', 'max_response_bytes', 'timeout_ms'))):
                raise ControllerError('provider_request_envelope_exceeded')
            if intent['timeout_ms'] > int(remaining * 1000):
                raise ControllerError('provider_timeout_exceeds_remaining_scope')
            dispatches = [r for r in journal.records if r['event'] == 'provider_admitted']
            if any(r['intent']['dispatch_id'] == intent['dispatch_id'] for r in dispatches):
                raise ControllerError('provider_dispatch_already_used')
            if sum(r['scope_id'] == scope_id for r in dispatches) >= spec['max_http_dispatches']:
                raise ControllerError('provider_dispatch_envelope_exhausted')
            if intent['provider'] != 'deepseek':
                retrieval = [r['intent'] for r in dispatches if r['scope_id'] == scope_id and r['intent']['provider'] != 'deepseek']
                if (len(retrieval) >= RAWRAG_CONFIG['limits']['max_http_dispatches']
                        or sum(r['reference_input_tokens'] for r in retrieval) + intent['reference_input_tokens']
                        > RAWRAG_CONFIG['limits']['max_processed_input_tokens']):
                    raise ControllerError('rawrag_dispatch_or_token_envelope_exhausted')
            counted_action = None
            if spec['kind'] == 'native':
                kind = 'compaction_start' if intent['component'] == 'compaction' else 'generation_start'
                operation_id = 'provider-action-' + digest({'scope_id': scope_id, 'dispatch_id': intent['dispatch_id'], 'kind': kind})[:48]
                counted = self.ledger.record_event(scope_id, kind, operation_id)['reservation']
                counted_action = {'kind': kind, 'operation_id': operation_id, 'batch_event_sha256': counted['sha256']}
            event = self.ledger.record_event(scope_id, 'public_tool_call', intent['dispatch_id'])['reservation']
            remaining_now = attempt['wall_seconds'] - (time.time_ns() - attempt['reserved_at_unix_ns']) / 1e9
            if intent['timeout_ms'] > int(remaining_now * 1000):
                raise ControllerError('provider_timeout_exceeds_remaining_scope')
            admission = self._append(journal, {'event': 'provider_admitted', 'scope_id': scope_id,
                'intent': intent, 'operation_dispatch_id': operation['dispatch_id'],
                'counted_action': counted_action, 'batch_event_sha256': event['sha256'],
                'admitted_at_unix_ns': time.time_ns()})
            return _receipt(intent, admission)

    def finish_scope(self, intent, result):
        intent = _intent(intent)
        if not isinstance(result, dict) or result.get('actual_added_cost_cny') is not None:
            raise ControllerError('billing_reconciliation_is_separate')
        with self._locked() as journal:
            admitted, _, _, _ = self._active(journal, intent['scope_id'], enforce_deadline=False)
            if admitted['intent'] != intent:
                raise ControllerError('finish_scope_binding_mismatch')
            state = result.get('status')
            terminal = state if state in BATCH['TERMINAL'] else ('completed' if state == 'completed' else 'failed')
            finished = self.ledger.finish(intent['scope_id'], status=terminal, actual_added_cost_cny=None)
            self._append(journal, {'event': 'scope_finished', 'scope_id': intent['scope_id'],
                'status': terminal, 'batch_event_sha256': finished['event']['sha256'],
                'actual_added_cost_cny': None, 'output_sha256': result.get('output_sha256')})
