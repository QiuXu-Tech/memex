import copy
import fcntl
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import queue
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


M = module('p1_runtime_controller_test', ROOT / 'scripts/paper1/runtime_controller.py')
FIXTURE = module('p1_batch_fixture_controller', ROOT / 'test/test_paper1_batch_limits.py')


def admission_probe(root, specs, intent, outcomes):
    try:
        controller = M.CanonicalPairedController(specs, repo_root=Path(root), run=True)
        controller.admit_scope(intent)
        outcomes.put('allowed')
    except Exception as error:
        outcomes.put(str(error))


class RuntimeControllerTests(unittest.TestCase):
    save_auth = FIXTURE.BatchLimitsTests.save_auth

    def setUp(self):
        FIXTURE.BatchLimitsTests.setUp(self)
        clock = patch.object(M, 'current_utc_date', return_value=M.DEEPSEEK_PROFILE['checked_date'])
        clock.start(); self.addCleanup(clock.stop)

    def spec(self, kind='native', unit=None, **changes):
        value = {'kind': kind, 'unit': unit, 'public_path': None,
                 'upper_bound_cny': f"{changes.get('max_http_dispatches', 2) * 3}.00",
                 'billing_basis': {'kind': 'priced_upper_bound', 'evidence': self.evidence},
                 'max_http_dispatches': 2,
                 'providers': [{'provider': 'deepseek', 'model': 'deepseek-flash',
                                'endpoint': 'https://api.deepseek.com/responses',
                                'config_sha256': 'c' * 64,
                                'checked_upper_bound_cny': '3.00',
                                'checked_upper_bound_evidence': self.evidence}]}
        return {**value, **changes}

    def intent(self, scope='test-native', operation='admit_scope', kind='native', arm=None, ordinal=0):
        value = {'schema_version': 1, 'scope_id': scope, 'kind': kind, 'operation': operation,
                 'task_id': 'w-101', 'project_id': 'pallets/flask', 'replicate': 1,
                 'arm': arm, 'run_id': scope, 'checkpoint_sha256': None if arm is None else 'd' * 64,
                 'sealed_checkpoint_sha256': None if arm is None else 'f' * 64,
                 'dispatch_id': scope + ':' + str(ordinal) + ':' + operation,
                 'request_sha256': 'a' * 64}
        return {**value, 'intent_sha256': M.digest(value)}

    def provider(self, identifier='http-1', **changes):
        value = {'schema_version': 1, 'kind': 'p1-deepseek-native-intent',
                 'provider': 'deepseek', 'model': 'deepseek-flash',
                 'endpoint': 'https://api.deepseek.com/responses', 'dispatch_id': identifier,
                 'request_sha256': 'b' * 64, 'request_bytes': 432,
                 'config_sha256': 'c' * 64, 'component': 'prelude',
                 'reference_input_tokens': 100, 'max_output_tokens': 1024,
                 'max_response_bytes': 65536, 'timeout_ms': 30000}
        value.update(changes)
        return {**value, 'intent_sha256': M.digest(value)}

    def controller(self, **kw):
        return M.CanonicalPairedController({'test-native': self.spec()}, repo_root=self.root, **kw)

    def retrieval_spec(self, **changes):
        providers = []
        for provider, model, endpoint in (
                ('openai', 'text-embedding-3-small', 'https://api.openai.com/v1/embeddings'),
                ('cohere', 'rerank-v3.5', 'https://api.cohere.com/v2/rerank')):
            providers.append({'provider': provider, 'model': model, 'endpoint': endpoint,
                'config_sha256': M.RAWRAG_CONFIG_SHA256, 'checked_upper_bound_cny': '3.00',
                'checked_upper_bound_evidence': self.evidence})
        return self.spec('method', 'w-101:B:1', providers=providers, **changes)

    def retrieval_provider(self, identifier='retrieval-1', component='embedding', **changes):
        provider = self.retrieval_spec()['providers'][0 if component == 'embedding' else 1]
        return self.provider(identifier, **{**{k: provider[k] for k in
            ('provider', 'model', 'endpoint', 'config_sha256')},
            'kind': 'p1-provider-dispatch-intent', 'component': component,
            'checkpoint_sha256': 'd' * 64, 'max_output_tokens': 0,
            'max_response_bytes': 8388608, **changes})

    def admitted_retrieval(self, **changes):
        controller = M.CanonicalPairedController({'m1': self.retrieval_spec(**changes)},
                                                repo_root=self.root, run=True)
        controller.admit_scope(self.intent('m1', kind='method', arm='B'))
        controller.before_operation(self.intent('m1', 'build_packet', 'method', 'B', 1))
        return controller

    def admitted(self):
        controller = self.controller(run=True)
        admission = self.intent()
        receipt = controller.admit_scope(admission)
        self.assertEqual(receipt['decision'], 'allow')
        controller.before_operation(self.intent(operation='capture_parent', ordinal=1))
        return controller, admission

    def envelope_spec(self, kind='native', unit=None, **changes):
        value = self.spec(kind, unit, max_http_dispatches=8, upper_bound_cny='3.20')
        pricing = self.root / 'fixture-deepseek-public-price.json'
        if not pricing.exists():
            pricing.write_text(M.canonical({'schema_version': 1, 'kind': 'p1-deepseek-public-price-basis',
                'provider': 'deepseek', 'model': 'deepseek-flash', 'checked_date': M.DEEPSEEK_PROFILE['checked_date'],
                'currency': 'CNY', 'peak_input_cny_per_million': '2.00', 'peak_output_cny_per_million': '8.00',
                'context_token_upper_bound': 1048576, 'max_output_tokens': 8192,
                'source_url': 'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/',
                'fixture': 'offline test only; not a live account observation', 'actual_added_cash_cny': None}) + '\n')
        value['providers'][0].update(config_sha256=M.DEEPSEEK_PROFILE_SHA256,
            checked_upper_bound_evidence={'ref': pricing.name, 'sha256': M.hashlib.sha256(pricing.read_bytes()).hexdigest()},
            scope_usage_envelope={'kind': 'deepseek-native-serial-envelope-v1',
                'relay_source_sha256': M.relay_source_sha256(), 'max_input_tokens': 65536,
                'max_output_tokens': 8192, 'max_http_dispatches': 8, 'scope_upper_bound_cny': '3.20'})
        return {**value, **changes}

    def register_transport(self, controller, name='fixture-transport'):
        root = self.root / name
        root.mkdir(mode=0o700)
        body = {'schema_version': 1, 'kind': 'p1-deepseek-relay-registration', 'transport_id': name,
            'audit_root': str(root), 'config_sha256': M.DEEPSEEK_PROFILE_SHA256,
            'relay_source_sha256': M.relay_source_sha256()}
        target = root / 'transport.json'
        target.write_text(M.canonical(body) + '\n'); target.chmod(0o600)
        request = {**body, 'evidence': {'path': str(target), 'sha256': M.hashlib.sha256(target.read_bytes()).hexdigest()}}
        receipt = controller.register_transport(request)
        self.assertEqual(receipt['registration_sha256'], M.digest(request))
        self.transport = request
        return request

    def envelope_provider(self, identifier='guarded-1', **changes):
        return self.provider(identifier, config_sha256=M.DEEPSEEK_PROFILE_SHA256,
            transport_id=self.transport['transport_id'], relay_source_sha256=M.relay_source_sha256(), **changes)

    def admitted_envelope(self):
        controller = M.CanonicalPairedController({'test-native': self.envelope_spec()}, repo_root=self.root, run=True)
        admission = self.intent()
        controller.admit_scope(admission)
        controller.before_operation(self.intent(operation='capture_parent', ordinal=1))
        self.register_transport(controller)
        return controller, admission

    def complete_provider(self, controller, intent, *, usage=None, status='completed', terminal='response.completed', scope='test-native'):
        if usage is None and status == 'completed':
            usage = {'input_tokens': 100, 'cached_input_tokens': 20, 'output_tokens': 10}
        value = {'schema_version': 1, 'kind': 'p1-deepseek-dispatch-result',
            'transport_id': self.transport['transport_id'], 'relay_source_sha256': M.relay_source_sha256(),
            'config_sha256': M.DEEPSEEK_PROFILE_SHA256, 'scope_id': scope,
            'dispatch_id': intent['dispatch_id'], 'intent_sha256': intent['intent_sha256'],
            'request_sha256': intent['request_sha256'], 'provider_dispatch_started': True,
            'status': status, 'usage': usage, 'usage_complete': usage is not None,
            'terminal_event': terminal, 'response_sha256': 'a' * 64 if usage else None,
            'response_bytes': 1000 if usage else None, 'error_code': None if status == 'completed' else 'fixture_failure'}
        directory = Path(self.transport['audit_root']) / 'dispatches'; directory.mkdir(exist_ok=True, mode=0o700)
        path = directory / (intent['dispatch_id'] + '.json')
        path.write_text(M.canonical(value) + '\n'); path.chmod(0o600)
        message = {'schema_version': 1, 'kind': 'p1-provider-dispatch-completion',
            'transport_id': self.transport['transport_id'], 'dispatch_id': intent['dispatch_id'],
            'request_sha256': intent['request_sha256'], 'intent_sha256': intent['intent_sha256'],
            'record_sha256': M.hashlib.sha256(path.read_bytes()).hexdigest()}
        return controller.complete_dispatch(message, scope_id=scope), path, message

    def test_guarded_scope_requires_registration_and_durable_completion_before_next_dispatch(self):
        controller = M.CanonicalPairedController({'test-native': self.envelope_spec()}, repo_root=self.root, run=True)
        controller.admit_scope(self.intent())
        controller.before_operation(self.intent(operation='capture_parent', ordinal=1))
        with self.assertRaisesRegex(M.ControllerError, 'transport'):
            controller.authorize_dispatch(self.provider(config_sha256=M.DEEPSEEK_PROFILE_SHA256), scope_id='test-native')
        self.register_transport(controller)
        first = self.envelope_provider()
        controller.authorize_dispatch(first, scope_id='test-native')
        reopened = M.CanonicalPairedController({'test-native': self.envelope_spec()}, repo_root=self.root, run=True)
        with self.assertRaisesRegex(M.ControllerError, 'completion_required'):
            reopened.authorize_dispatch(self.envelope_provider('guarded-2'), scope_id='test-native')
        with self.assertRaisesRegex(M.ControllerError, 'completion_required'):
            reopened.before_operation(self.intent(operation='prime_D', ordinal=2))
        receipt, _, _ = self.complete_provider(reopened, first)
        self.assertEqual(receipt['decision'], 'continue')
        reopened.authorize_dispatch(self.envelope_provider('guarded-2'), scope_id='test-native')
        self.assertEqual(self.ledger.status()['committed_cash_upper_bound'], '3.20')

    def test_guarded_unknown_usage_permanently_blocks_and_never_settles_cash(self):
        controller, admission = self.admitted_envelope()
        first = self.envelope_provider()
        controller.authorize_dispatch(first, scope_id='test-native')
        receipt, _, _ = self.complete_provider(controller, first, usage=None, status='failed', terminal=None)
        self.assertEqual(receipt['decision'], 'blocked')
        with self.assertRaisesRegex(M.ControllerError, 'usage_blocked'):
            controller.authorize_dispatch(self.envelope_provider('guarded-2'), scope_id='test-native')
        controller.finish_scope(admission, {'status': 'failed', 'actual_added_cost_cny': None})
        self.assertEqual(self.ledger.status()['committed_cash_upper_bound'], '3.20')
        self.assertIsNone(self.ledger.status()['actual_added_cash_total'])

    def test_guarded_actual_overshoot_is_preserved_and_blocks_next_request(self):
        controller, _ = self.admitted_envelope()
        first = self.envelope_provider()
        controller.authorize_dispatch(first, scope_id='test-native')
        receipt, path, _ = self.complete_provider(controller, first,
            usage={'input_tokens': 65537, 'cached_input_tokens': 0, 'output_tokens': 10})
        self.assertEqual(receipt['decision'], 'blocked')
        self.assertEqual(json.loads(path.read_text())['usage']['input_tokens'], 65537)
        with self.assertRaisesRegex(M.ControllerError, 'usage_blocked'):
            controller.authorize_dispatch(self.envelope_provider('guarded-2'), scope_id='test-native')

    def test_guarded_completion_reads_actual_immutable_file_and_rejects_replacement(self):
        controller, _ = self.admitted_envelope()
        first = self.envelope_provider()
        controller.authorize_dispatch(first, scope_id='test-native')
        _, path, message = self.complete_provider(controller, first)
        with self.assertRaisesRegex(M.ControllerError, 'completion_already'):
            controller.complete_dispatch(message, scope_id='test-native')
        path.write_text('{}\n')
        with self.assertRaisesRegex(M.ControllerError, 'completion_evidence'):
            controller.authorize_dispatch(self.envelope_provider('guarded-2'), scope_id='test-native')

    def test_guarded_output_budget_is_checked_independently_of_relay(self):
        controller, _ = self.admitted_envelope()
        first = self.envelope_provider(max_output_tokens=8000)
        controller.authorize_dispatch(first, scope_id='test-native')
        self.complete_provider(controller, first, usage={'input_tokens': 100, 'cached_input_tokens': 0, 'output_tokens': 8000})
        with self.assertRaisesRegex(M.ControllerError, 'remaining_output'):
            controller.authorize_dispatch(self.envelope_provider('guarded-2', max_output_tokens=193), scope_id='test-native')
        controller.authorize_dispatch(self.envelope_provider('guarded-2', max_output_tokens=192), scope_id='test-native')

    def test_guarded_late_completion_is_retained_but_cannot_reopen_scope(self):
        controller, admission = self.admitted_envelope()
        first = self.envelope_provider()
        controller.authorize_dispatch(first, scope_id='test-native')
        controller.finish_scope(admission, {'status': 'failed', 'actual_added_cost_cny': None})
        receipt, path, _ = self.complete_provider(controller, first)
        self.assertEqual(receipt['decision'], 'blocked')
        self.assertEqual(json.loads(path.read_text())['usage']['input_tokens'], 100)
        with self.assertRaises(M.ControllerError):
            controller.authorize_dispatch(self.envelope_provider('guarded-2'), scope_id='test-native')

    def test_guarded_scope_cash_proof_cannot_change_source_profile_or_terminal_bound(self):
        for changed in ('source', 'profile', 'single_bound', 'scope_bound'):
            value = self.envelope_spec()
            provider = value['providers'][0]
            if changed == 'source': provider['scope_usage_envelope']['relay_source_sha256'] = 'e' * 64
            elif changed == 'profile': provider['config_sha256'] = 'e' * 64
            elif changed == 'single_bound': provider['checked_upper_bound_cny'] = '5.00'
            else: value['upper_bound_cny'] = '3.19'
            with self.subTest(changed=changed), self.assertRaises(M.ControllerError):
                M.CanonicalPairedController({'test-native': value}, repo_root=self.root)

    def test_mixed_B_adds_only_non_deepseek_sixteen_dispatch_bounds(self):
        value = self.envelope_spec('method', 'w-101:B:1', max_http_dispatches=24, upper_bound_cny='4.00')
        retrieval = self.retrieval_spec()['providers']
        retrieval[0]['checked_upper_bound_cny'] = '0.02'
        retrieval[1]['checked_upper_bound_cny'] = '0.05'
        value['providers'].extend(retrieval)
        controller = M.CanonicalPairedController({'m1': value}, repo_root=self.root)
        self.assertTrue(controller.inspect_scope(self.intent('m1', kind='method', arm='B'))['reservation_would_fit'])
        value['upper_bound_cny'] = '3.99'
        with self.assertRaisesRegex(M.ControllerError, 'cash_bound'):
            M.CanonicalPairedController({'m1': value}, repo_root=self.root)

    def test_guarded_fresh_price_date_is_required_again_before_dispatch(self):
        controller, admission = self.admitted_envelope()
        with patch.object(M, 'current_utc_date', return_value='2099-01-01'):
            with self.assertRaisesRegex(M.ControllerError, 'price_verification_expired'):
                M.CanonicalPairedController({'test-native': self.envelope_spec()}, repo_root=self.root)
            with self.assertRaisesRegex(M.ControllerError, 'price_verification_expired'):
                controller.authorize_dispatch(self.envelope_provider(), scope_id='test-native')
            with self.assertRaisesRegex(M.ControllerError, 'price_verification_expired'):
                controller.register_transport(self.transport)
            controller.finish_scope(admission, {'status': 'failed', 'actual_added_cost_cny': None})
        self.assertEqual(self.ledger.status()['committed_cash_upper_bound'], '3.20')

    def test_guarded_completion_after_its_admitted_timeout_cannot_allow_another_request(self):
        controller, _ = self.admitted_envelope()
        first = self.envelope_provider(timeout_ms=1)
        controller.authorize_dispatch(first, scope_id='test-native')
        real_now = M.time.time_ns()
        with patch.object(M.time, 'time_ns', return_value=real_now + 2_000_000_000):
            receipt, _, _ = self.complete_provider(controller, first)
        self.assertEqual(receipt['decision'], 'blocked')
        with self.assertRaisesRegex(M.ControllerError, 'usage_blocked'):
            controller.authorize_dispatch(self.envelope_provider('guarded-2'), scope_id='test-native')

    def test_guarded_price_evidence_must_match_current_profile_date_and_official_bounds(self):
        for field, replacement in (('checked_date', '2000-01-01'), ('peak_input_cny_per_million', '0.01')):
            value = self.envelope_spec()
            provider = value['providers'][0]
            target = self.root / provider['checked_upper_bound_evidence']['ref']
            original = target.read_bytes()
            facts = json.loads(original); facts[field] = replacement
            target.write_text(M.canonical(facts))
            provider['checked_upper_bound_evidence']['sha256'] = M.hashlib.sha256(target.read_bytes()).hexdigest()
            with self.subTest(field=field), self.assertRaisesRegex(M.ControllerError, 'price_basis_mismatch'):
                M.CanonicalPairedController({'test-native': value}, repo_root=self.root)
            target.write_bytes(original)

    def test_default_inspection_does_not_reserve_or_dispatch(self):
        controller = self.controller()
        self.assertTrue(controller.inspect_scope(self.intent())['reservation_would_fit'])
        with self.assertRaisesRegex(M.ControllerError, 'explicit_run'):
            controller.admit_scope(self.intent())
        self.assertFalse(self.ledger.state_dir.exists())

    def test_cash_reservation_real_operations_and_unknown_finish(self):
        controller, intent = self.admitted()
        receipt = controller.authorize_dispatch(self.provider(), scope_id='test-native')
        self.assertEqual(receipt['request_sha256'], 'b' * 64)
        status = self.ledger.status()
        self.assertEqual(status['committed_cash_upper_bound'], '6.00')
        self.assertEqual(status['attempts']['test-native']['counters']['public_tool_call'], 1)
        controller.finish_scope(intent, {'status': 'completed', 'actual_added_cost_cny': None})
        self.assertEqual(self.ledger.status()['committed_cash_upper_bound'], '6.00')
        self.assertIsNone(self.ledger.status()['actual_added_cash_total'])
        with self.assertRaises(M.ControllerError):
            controller.authorize_dispatch(self.provider('later'), scope_id='test-native')

    def test_replay_across_controller_restart_is_denied(self):
        controller, _ = self.admitted()
        controller.authorize_dispatch(self.provider(), scope_id='test-native')
        reopened = self.controller(run=True)
        with self.assertRaisesRegex(M.ControllerError, 'already_used'):
            reopened.authorize_dispatch(self.provider(), scope_id='test-native')
        with self.assertRaisesRegex(M.ControllerError, 'scope_already_seen'):
            reopened.admit_scope(self.intent())

    def test_allocation_does_not_reset_two_native_limit(self):
        for name in ('old-1', 'old-2'):
            self.ledger.reserve(kind='native', attempt_id=name, upper_bound_cny='3.00',
                billing_basis={'kind': 'priced_upper_bound', 'evidence': self.evidence}, run=True)
            self.ledger.finish(name, status='failed')
        with self.assertRaisesRegex(Exception, 'native_attempt_budget_exhausted'):
            self.controller(run=True).admit_scope(self.intent())
        self.assertEqual(self.ledger.status()['native_attempts_reserved'], 2)

    def test_method_cannot_create_native_checkpoint(self):
        controller = M.CanonicalPairedController({'m1': self.spec('method', 'w-101:A:1')}, repo_root=self.root, run=True)
        controller.admit_scope(self.intent('m1', kind='method', arm='A'))
        with self.assertRaisesRegex(M.ControllerError, 'operation_outside_scope'):
            controller.before_operation(self.intent('m1', 'capture_parent', 'method', 'A', 1))
        self.assertEqual(self.ledger.status()['native_attempts_reserved'], 0)
        self.assertEqual(self.ledger.status()['method_units_reserved'], 1)

    def test_wrong_provider_config_scope_and_tampered_intent_rejected(self):
        controller, _ = self.admitted()
        for changed in ({'endpoint': 'https://example.com/responses'}, {'config_sha256': 'e' * 64},
                        {'attempt_id': 'different'}, {'checkpoint_sha256': 'e' * 64}):
            with self.assertRaises(M.ControllerError):
                controller.authorize_dispatch(self.provider(**changed), scope_id='test-native')
        changed = self.provider(); changed['request_bytes'] = 433
        with self.assertRaisesRegex(M.ControllerError, 'digest_mismatch'):
            controller.authorize_dispatch(changed, scope_id='test-native')
        self.assertEqual(self.ledger.status()['attempts']['test-native']['counters'], {})

    def test_dispatch_limit_is_shared_after_reopen(self):
        controller, _ = self.admitted()
        controller.authorize_dispatch(self.provider('http-a'), scope_id='test-native')
        self.controller(run=True).authorize_dispatch(self.provider('http-b'), scope_id='test-native')
        with self.assertRaisesRegex(M.ControllerError, 'envelope_exhausted'):
            controller.authorize_dispatch(self.provider('http-c'), scope_id='test-native')

    def test_journal_prefix_truncation_cannot_reset_dispatches(self):
        controller, _ = self.admitted()
        path = controller.state / 'events.jsonl'
        path.write_bytes(path.read_bytes().splitlines(keepends=True)[0])
        with self.assertRaisesRegex(M.ControllerError, 'head_mismatch'):
            self.controller(run=True).authorize_dispatch(self.provider(), scope_id='test-native')

    def test_expired_attempt_cannot_dispatch_but_can_finish_unknown(self):
        controller, intent = self.admitted()
        reservation = self.ledger.status()['attempts']['test-native']['reserved_at_unix_ns']
        with patch.object(M.time, 'time_ns', return_value=reservation + 601 * 10**9):
            with self.assertRaisesRegex(M.ControllerError, 'deadline'):
                controller.authorize_dispatch(self.provider(), scope_id='test-native')
            controller.finish_scope(intent, {'status': 'timeout', 'actual_added_cost_cny': None})
        self.assertEqual(self.ledger.status()['attempts']['test-native']['state'], 'timeout')

    def test_price_or_scope_spec_drift_refuses_later_dispatch(self):
        controller, _ = self.admitted()
        specs = {'test-native': self.spec(max_http_dispatches=3)}
        other = M.CanonicalPairedController(specs, repo_root=self.root, run=True)
        with self.assertRaisesRegex(M.ControllerError, 'spec_changed'):
            other.authorize_dispatch(self.provider(), scope_id='test-native')

    def test_provider_callback_without_operation_admission_refuses(self):
        controller = self.controller(run=True)
        controller.admit_scope(self.intent())
        with self.assertRaisesRegex(M.ControllerError, 'operation_admission_required'):
            controller.authorize_dispatch(self.provider(), scope_id='test-native')

    def test_generic_metadata_cannot_write_secret_fields(self):
        controller, _ = self.admitted()
        with self.assertRaisesRegex(M.ControllerError, 'unexpected_intent_fields'):
            controller.authorize_dispatch(self.provider(api_key='fixture-not-a-real-secret'), scope_id='test-native')

    def test_sixth_native_generation_is_denied_without_optional_record_action(self):
        controller = M.CanonicalPairedController({'test-native': self.spec(max_http_dispatches=8, upper_bound_cny='24.00')},
                                                repo_root=self.root, run=True)
        controller.admit_scope(self.intent())
        controller.before_operation(self.intent(operation='capture_parent', ordinal=1))
        for i in range(5):
            controller.authorize_dispatch(self.provider('generation-' + str(i)), scope_id='test-native')
        with self.assertRaisesRegex(Exception, 'operation_budget_exhausted'):
            controller.authorize_dispatch(self.provider('generation-six'), scope_id='test-native')
        counters = self.ledger.status()['attempts']['test-native']['counters']
        self.assertEqual(counters['generation_start'], 5)
        self.assertEqual(counters['public_tool_call'], 5)

    def test_third_native_compaction_is_denied_and_not_counted_as_generation(self):
        controller = M.CanonicalPairedController({'test-native': self.spec(max_http_dispatches=8, upper_bound_cny='24.00')},
                                                repo_root=self.root, run=True)
        controller.admit_scope(self.intent())
        controller.before_operation(self.intent(operation='compact_parent', ordinal=1))
        for i in range(2):
            controller.authorize_dispatch(self.provider('compaction-' + str(i), component='compaction'), scope_id='test-native')
        with self.assertRaisesRegex(Exception, 'operation_budget_exhausted'):
            controller.authorize_dispatch(self.provider('compaction-three', component='compaction'), scope_id='test-native')
        counters = self.ledger.status()['attempts']['test-native']['counters']
        self.assertEqual(counters['compaction_start'], 2)
        self.assertNotIn('generation_start', counters)

    def test_method_scope_cannot_admit_prelude_or_compaction_http(self):
        controller = M.CanonicalPairedController({'m1': self.spec('method', 'w-101:A:1')}, repo_root=self.root, run=True)
        controller.admit_scope(self.intent('m1', kind='method', arm='A'))
        controller.before_operation(self.intent('m1', 'continue_reader', 'method', 'A', 1))
        for component in ('prelude', 'compaction'):
            with self.assertRaisesRegex(M.ControllerError, 'provider_component_outside_operation'):
                controller.authorize_dispatch(self.provider(component=component), scope_id='m1')
        self.assertEqual(self.ledger.status()['attempts']['m1']['counters'], {})

    def test_provider_must_match_latest_operation_not_any_historical_operation(self):
        controller, _ = self.admitted()
        controller.before_operation(self.intent(operation='compact_parent', ordinal=2))
        with self.assertRaisesRegex(M.ControllerError, 'provider_component_outside_operation'):
            controller.authorize_dispatch(self.provider(), scope_id='test-native')

    def test_request_timeout_cannot_exceed_remaining_scope(self):
        controller, _ = self.admitted()
        reservation = self.ledger.status()['attempts']['test-native']['reserved_at_unix_ns']
        with patch.object(M.time, 'time_ns', return_value=reservation + 599 * 10**9):
            with self.assertRaisesRegex(M.ControllerError, 'provider_timeout_exceeds_remaining_scope'):
                controller.authorize_dispatch(self.provider(timeout_ms=30000), scope_id='test-native')
        self.assertEqual(self.ledger.status()['attempts']['test-native']['counters'], {})

    def test_deepseek_numeric_envelope_and_required_fields_are_enforced(self):
        controller, _ = self.admitted()
        changes = ({'timeout_ms': 30001}, {'timeout_ms': 0}, {'max_output_tokens': 8193},
                   {'reference_input_tokens': 65537}, {'request_bytes': 262145}, {'max_response_bytes': 4194305})
        for i, changed in enumerate(changes):
            with self.subTest(changed=changed), self.assertRaisesRegex(M.ControllerError, 'provider_request_envelope_exceeded'):
                controller.authorize_dispatch(self.provider('bad-bounds-' + str(i), **changed), scope_id='test-native')
        missing = self.provider()
        del missing['max_response_bytes']
        missing['intent_sha256'] = M.digest({k: v for k, v in missing.items() if k != 'intent_sha256'})
        with self.assertRaisesRegex(M.ControllerError, 'incomplete_provider_intent'):
            controller.authorize_dispatch(missing, scope_id='test-native')
        self.assertEqual(self.ledger.status()['attempts']['test-native']['counters'], {})

    def test_generation_and_compaction_record_action_are_not_double_counted(self):
        controller, _ = self.admitted()
        for kind in ('generation_start', 'compaction_start'):
            with self.assertRaisesRegex(M.ControllerError, 'provider_action_is_counted_at_dispatch'):
                controller.record_action('test-native', kind, 'duplicate-count')

    def test_controller_and_canonical_file_locks_fail_without_waiting(self):
        for which in ('controller', 'canonical'):
            with self.subTest(which=which):
                controller = self.controller(run=True)
                path = (controller.state / 'controller.lock' if which == 'controller'
                        else self.ledger.state_dir / 'ledger.lock')
                path.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                outcomes = multiprocessing.Queue()
                process = multiprocessing.Process(target=admission_probe, args=(str(self.root),
                    {'test-native': self.spec()}, self.intent(), outcomes))
                try:
                    process.start()
                    try:
                        outcome = outcomes.get(timeout=1)
                    except queue.Empty:
                        outcome = 'blocked_waiting_for_lock'
                    self.assertEqual(outcome, 'controller_busy' if which == 'controller' else 'canonical_ledger_busy')
                finally:
                    if process.is_alive():
                        process.terminate()
                    process.join(timeout=2)
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                    os.close(descriptor)
                    outcomes.close()

    def test_entire_dispatch_envelope_requires_covered_cash_reservation(self):
        specs = {'test-native': self.spec(max_http_dispatches=8, upper_bound_cny='23.99')}
        with self.assertRaisesRegex(M.ControllerError, 'scope_cash_bound_insufficient'):
            M.CanonicalPairedController(specs, repo_root=self.root)
        controller = M.CanonicalPairedController({'test-native': self.spec(max_http_dispatches=8, upper_bound_cny='24.00')},
                                                repo_root=self.root)
        self.assertEqual(controller.inspect_scope(self.intent())['proposed']['upper_bound_fen'], 2400)
        self.assertFalse(self.ledger.state_dir.exists())

    def test_deepseek_floor_and_evidence_binding_cannot_be_omitted(self):
        spec = self.spec()
        spec['providers'][0]['checked_upper_bound_cny'] = '2.99'
        with self.assertRaisesRegex(M.ControllerError, 'deepseek_per_request_cash_floor'):
            M.CanonicalPairedController({'test-native': spec}, repo_root=self.root)
        spec = self.spec()
        spec['providers'][0].pop('checked_upper_bound_evidence')
        with self.assertRaisesRegex(M.ControllerError, 'invalid_provider_envelope'):
            M.CanonicalPairedController({'test-native': spec}, repo_root=self.root)

    def test_changed_provider_bound_evidence_blocks_dispatch_without_releasing_cash(self):
        controller, _ = self.admitted()
        (self.root / self.evidence['ref']).write_text('Changed fixture pricing evidence')
        with self.assertRaisesRegex(Exception, 'evidence'):
            controller.authorize_dispatch(self.provider(), scope_id='test-native')
        self.assertEqual(self.ledger.status()['committed_cash_upper_bound'], '6.00')

    def test_B_fixed_retrieval_bounds_allow_batched_wire_body_and_eight_mib_response(self):
        controller = self.admitted_retrieval()
        for i, component in enumerate(('embedding', 'rerank')):
            receipt = controller.authorize_dispatch(self.retrieval_provider(
                'retrieval-' + str(i), component, request_bytes=262145), scope_id='m1')
            self.assertEqual(receipt['decision'], 'allow')
        counters = self.ledger.status()['attempts']['m1']['counters']
        self.assertEqual(counters, {'public_tool_call': 2})

    def test_B_retrieval_config_and_provider_scope_are_fixed(self):
        for kind, unit, error in (('native', None, 'retrieval_provider_outside_B'),
                                 ('method', 'w-101:A:1', 'retrieval_provider_outside_B')):
            spec = self.retrieval_spec()
            spec.update(kind=kind, unit=unit)
            with self.subTest(kind=kind), self.assertRaisesRegex(M.ControllerError, error):
                M.CanonicalPairedController({'m1': spec}, repo_root=self.root)
        spec = self.retrieval_spec()
        spec['providers'][0]['config_sha256'] = 'e' * 64
        with self.assertRaisesRegex(M.ControllerError, 'rawrag_config_binding_mismatch'):
            M.CanonicalPairedController({'m1': spec}, repo_root=self.root)
        self.assertFalse(self.ledger.state_dir.exists())

    def test_B_cumulative_processed_tokens_cannot_exceed_fixed_config(self):
        controller = self.admitted_retrieval(max_http_dispatches=3)
        controller.authorize_dispatch(self.retrieval_provider(
            'first', reference_input_tokens=200000), scope_id='m1')
        reopened = M.CanonicalPairedController({'m1': self.retrieval_spec(max_http_dispatches=3)},
                                               repo_root=self.root, run=True)
        with self.assertRaisesRegex(M.ControllerError, 'rawrag_dispatch_or_token_envelope_exhausted'):
            reopened.authorize_dispatch(self.retrieval_provider(
                'second', reference_input_tokens=100001), scope_id='m1')
        self.assertEqual(self.ledger.status()['attempts']['m1']['counters']['public_tool_call'], 1)

    def test_B_seventeenth_retrieval_request_denied_even_if_scope_envelope_larger(self):
        controller = self.admitted_retrieval(max_http_dispatches=17)
        for i in range(16):
            controller.authorize_dispatch(self.retrieval_provider('retrieval-' + str(i)), scope_id='m1')
        with self.assertRaisesRegex(M.ControllerError, 'rawrag_dispatch_or_token_envelope_exhausted'):
            controller.authorize_dispatch(self.retrieval_provider('retrieval-17'), scope_id='m1')
        self.assertEqual(self.ledger.status()['attempts']['m1']['counters']['public_tool_call'], 16)

    def test_B_wire_output_response_and_timeout_limits_fail_before_reservation(self):
        controller = self.admitted_retrieval()
        changes = ({'request_bytes': 2**24 + 1}, {'max_output_tokens': 1},
                   {'max_response_bytes': 8388609}, {'timeout_ms': 30001},
                   {'reference_input_tokens': 300001})
        for i, changed in enumerate(changes):
            with self.subTest(changed=changed), self.assertRaisesRegex(M.ControllerError, 'provider_request_envelope_exceeded'):
                controller.authorize_dispatch(self.retrieval_provider('bad-' + str(i), **changed), scope_id='m1')
        self.assertEqual(self.ledger.status()['attempts']['m1']['counters'], {})

    def test_B_retrieval_does_not_borrow_reader_operation_or_wrong_provider(self):
        controller = self.admitted_retrieval()
        with self.assertRaisesRegex(M.ControllerError, 'provider_component_provider_mismatch'):
            controller.authorize_dispatch(self.retrieval_provider(component='rerank',
                provider='openai', model='text-embedding-3-small',
                endpoint='https://api.openai.com/v1/embeddings'), scope_id='m1')
        controller.before_operation(self.intent('m1', 'continue_reader', 'method', 'B', 2))
        with self.assertRaisesRegex(M.ControllerError, 'provider_component_outside_operation'):
            controller.authorize_dispatch(self.retrieval_provider(), scope_id='m1')
        self.assertEqual(self.ledger.status()['attempts']['m1']['counters'], {})


if __name__ == '__main__':
    unittest.main()
