"""Driver boundary tests only; no provider, human label, or research result."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'scripts/paper1/native_driver.py'
if PATH.exists():
    SPEC = importlib.util.spec_from_file_location('p1_native_driver_test', PATH)
    M = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(M)
else:
    M = None


def implementation():
    if M is None:
        raise AssertionError('native_driver.py must implement a zero-call preflight and explicit run entry')
    return M


def snapshot(paths):
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.is_file()}


class NativeDriverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.state = self.directory / 'new-backend'
        self.output = self.directory / 'new-output'
        # Exercise the original exhausted two-attempt state in a disposable
        # historical fixture. A later explicitly activated supplement in the
        # real canonical ledger must not alter or be written by these tests.
        self.fixture_root = self.directory / 'historical-repo-fixture'
        base_relative = Path('docs/research/p1-evidence-verification')
        for relative in (implementation().controller_api.BATCH['AUTH_RELATIVE'],
                         str(base_relative / 'tasks/workflows/shared-budget.json'),
                         str(base_relative / 'tasks/workflows/source-draft-plan.json')):
            target = self.fixture_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / relative).read_bytes())
        for task in ('w-101', 'w-102'):
            relative = base_relative / 'tasks/workflows/packages' / task
            shutil.copytree(ROOT / relative, self.fixture_root / relative)
        ledger_relative = implementation().controller_api.BATCH['LEDGER_RELATIVE']
        history = b''.join((ROOT / ledger_relative / 'events.jsonl').read_bytes().splitlines(keepends=True)[:7])
        rows = [json.loads(line) for line in history.splitlines()]
        self.assertEqual(len(rows), 7)
        self.assertEqual(sum(row['event'] == 'reserved' and row['data']['kind'] == 'native' for row in rows), 2)
        ledger = self.fixture_root / ledger_relative
        ledger.mkdir(parents=True)
        (ledger / 'events.jsonl').write_bytes(history)
        (ledger / 'HEAD.json').write_text(json.dumps({'authorization_sha256': rows[-1]['authorization_sha256'],
            'seq': 7, 'sha256': rows[-1]['sha256']}) + '\n')
        (ledger / 'ledger.lock').touch(mode=0o600)
        root_patch = patch.object(implementation(), 'ROOT', self.fixture_root)
        root_patch.start(); self.addCleanup(root_patch.stop)
        base = self.fixture_root / base_relative
        self.protected = [base / 'artifacts/authorized-batch1/authorization.json',
            base / 'tasks/workflows/shared-budget.json', base / 'tasks/workflows/source-draft-plan.json']
        self.protected += list((base / 'artifacts/authorized-batch1/ledger').glob('*'))

    def settings(self):
        values = {'codex': str(self.directory / 'codex'), 'node': str(self.directory / 'node'),
            'tokenizer_path': str(self.directory / 'tokenizer.json'),
            'credential_file': str(self.directory / 'credential-file'),
            'rawrag_upstream': str(self.directory / 'upstream'), 'tasks': {}}
        for task in ('w-101', 'w-102'):
            values['tasks'][task] = {'python': str(self.directory / task / 'bin/python'),
                'sandbox': {'kind': 'bwrap', 'executable': str(self.directory / 'bwrap'),
                    'python': str(self.directory / 'python3.10'),
                    'dependencies': str(self.directory / task / 'site-packages'),
                    'runtime_roots': [str(self.directory / 'runtime')]}}
        return values

    def save(self, name, value):
        path = self.directory / name
        path.write_text(json.dumps(value))
        return path

    def test_default_preflight_reads_original_quota_without_process_network_or_writes(self):
        mod = implementation()
        before = snapshot(self.protected)
        with (patch.object(subprocess, 'run', side_effect=AssertionError('no process')),
                patch.object(subprocess, 'Popen', side_effect=AssertionError('no process')),
                patch.object(socket, 'socket', side_effect=AssertionError('no network'))):
            result = mod.preflight(state_root=self.state, output=self.output)
        self.assertEqual(result['mode'], 'check')
        self.assertFalse(result['dispatch_ready'])
        self.assertIn('native_attempt_budget_exhausted', result['blockers'])
        self.assertEqual(result['checks']['ledger']['native_attempts_remaining'], 0)
        self.assertEqual(result['checks']['relocation']['status'], 'verified')
        self.assertEqual(result['model_requests'], 0)
        self.assertEqual(result['ledger_writes'], 0)
        self.assertFalse(self.state.exists())
        self.assertFalse(self.output.exists())
        self.assertEqual(before, snapshot(self.protected))

    def test_explicit_run_with_current_exhausted_quota_never_constructs_backend(self):
        mod = implementation()
        before = snapshot(self.protected)
        with patch.object(mod, '_new_backend', side_effect=AssertionError('backend must stay absent')):
            result = mod.run_block(run=True, state_root=self.state, output=self.output)
        self.assertEqual(result['status'], 'blocked')
        self.assertFalse(result['dispatch_ready'])
        self.assertEqual(result['model_requests'], 0)
        self.assertFalse(self.state.exists())
        self.assertFalse(self.output.exists())
        self.assertEqual(before, snapshot(self.protected))

    def test_settings_are_strict_and_never_echo_secret_fields(self):
        mod = implementation()
        settings = self.settings()
        settings['api_key'] = 'sk-do-not-echo-this-fixture-value'
        result = mod.preflight(settings_path=self.save('bad-settings.json', settings))
        self.assertIn('invalid_settings_fields', result['blockers'])
        self.assertNotIn(settings['api_key'], json.dumps(result))

    def test_duplicate_settings_keys_are_rejected(self):
        mod = implementation()
        path = self.directory / 'duplicate.json'
        path.write_text('{"codex":"/one","codex":"/two"}')
        result = mod.preflight(settings_path=path)
        self.assertIn('settings_invalid_json', result['blockers'])

    def test_credential_preflight_stats_file_without_reading_its_contents(self):
        mod = implementation()
        settings = self.settings()
        credential = Path(settings['credential_file'])
        credential.write_text('sk-fixture-private-never-read')
        credential.chmod(0o600)
        original = mod.controller_api.BATCH['regular_bytes']
        def guarded(path):
            self.assertNotEqual(Path(path), credential, 'credential bytes must not be read')
            return original(path)
        with patch.dict(mod.controller_api.BATCH, regular_bytes=guarded), patch.dict(os.environ,
                {'VECTORIZE_API_KEY': 'sk-fixture-vector-secret', 'RERANK_API_KEY': 'fixture-rerank-secret'}):
            result = mod.preflight(settings_path=self.save('settings.json', settings))
        self.assertTrue(result['checks']['services']['deepseek_file_metadata_acceptable'])
        self.assertTrue(result['checks']['services']['embedding_environment_present'])
        self.assertTrue(result['checks']['services']['reranker_environment_present'])
        self.assertFalse(result['credential_file_contents_read'])
        self.assertFalse(result['environment_credential_values_reported'])
        self.assertNotIn('sk-fixture', json.dumps(result))
        self.assertFalse(result['dispatch_ready'])

    def test_bad_tokenizer_is_not_replaced_by_a_byte_estimate_or_alternate_runtime(self):
        mod = implementation()
        settings = self.settings()
        Path(settings['tokenizer_path']).write_text('{"fixture":"wrong tokenizer"}')
        result = mod.preflight(settings_path=self.save('settings.json', settings))
        self.assertIn('tokenizer_digest_mismatch', result['blockers'])
        self.assertFalse(result['checks']['tokenizer']['verified'])

    def test_service_preflight_checks_environment_names_without_fetching_values(self):
        mod = implementation()
        class NamesOnly:
            def __contains__(self, name):
                return name in {'VECTORIZE_API_KEY', 'RERANK_API_KEY'}
            def get(self, *args):
                raise AssertionError('No environment credential values may be fetched')
            def __getitem__(self, key):
                raise AssertionError('No environment credential values may be fetched')
        with patch.object(mod.os, 'environ', NamesOnly()):
            result = mod._services(None)
        self.assertTrue(result['embedding_environment_present'])
        self.assertTrue(result['reranker_environment_present'])
        self.assertFalse(result['provider_authentication_checked'])

    def test_existing_or_overlapping_output_state_paths_do_not_create_artifacts(self):
        mod = implementation()
        self.state.mkdir()
        result = mod.preflight(state_root=self.state, output=self.output)
        self.assertIn('fresh_backend_state_required', result['blockers'])
        result = mod.preflight(state_root=self.output / 'backend', output=self.output)
        self.assertIn('output_state_paths_overlap', result['blockers'])
        result = mod.preflight(state_root=self.output / '..' / 'backend', output=self.output)
        self.assertIn('explicit_absolute_local_path_required', result['blockers'])
        self.assertFalse(self.output.exists())

    def test_required_scope_ids_bind_selected_replicate_and_four_arms(self):
        mod = implementation()
        one = mod.preflight(task_id='w-101', replicate=1)
        two = mod.preflight(task_id='w-101', replicate=2)
        bindings = one['required_scope_bindings']
        self.assertEqual(len(bindings), 5)
        self.assertEqual({v['unit'] for v in bindings.values() if v['kind'] == 'method'},
                         {'w-101:' + arm + ':1' for arm in 'ABCD'})
        self.assertTrue(set(bindings).isdisjoint(two['required_scope_bindings']))
        self.assertTrue(all('upper_bound_cny' not in v for v in bindings.values()))

    def test_all_arm_order_is_required_and_no_single_unit_cli_is_invented(self):
        mod = implementation()
        result = mod.preflight(order=('A', 'B', 'C', 'C'))
        self.assertIn('exact_four_arm_order_required', result['blockers'])
        self.assertFalse(result['dispatch_ready'])

    def fixture_context(self):
        task = {'task_id': 'w-101', 'project_id': 'pallets/flask', 'public_path': '/fixture/public',
            'public_sha256': 'a' * 64, 'taskpack_public_sha256': 'b' * 64,
            'original_request_sha256': 'c' * 64, 'shared_reader_config_sha256': 'd' * 64}
        return {'task': task, 'replicate': 1, 'order': ('D', 'A', 'B', 'C'),
            'settings': self.settings(), 'scope_specs': {}, 'state_root': self.state,
            'output': self.output, 'profile_path': Path('/fixture/profile.json'),
            'input_files': {}, 'relocation': {'fixture_only': True}}

    def test_run_uses_one_backend_one_controller_and_closes_after_failed_preparation(self):
        mod = implementation()
        context = self.fixture_context()
        backend = Mock()
        controller = Mock()
        report = {'status': 'eligible_for_explicit_run', 'dispatch_ready': True, 'blockers': []}
        failed = {'kind': 'paired_runtime_component_execution', 'preparation': {'status': 'host_timeout'},
                  'arms': {}, 'scientific_ready': False}
        with (patch.object(mod, '_inspect', return_value=(report, context)),
                patch.object(mod.controller_api, 'CanonicalPairedController', return_value=controller) as make_controller,
                patch.object(mod, '_new_backend', return_value=backend) as make_backend,
                patch.object(mod.paired, 'run_paired_block', return_value=failed) as execute):
            result = mod.run_block(run=True)
        make_controller.assert_called_once()
        make_backend.assert_called_once()
        execute.assert_called_once_with(context['task'], 1, backend, controller, self.output,
                                        order=context['order'], execution_mode='live')
        backend.close.assert_called_once_with()
        self.assertFalse(result['execution_complete'])
        self.assertFalse(result['scientific_ready'])
        self.assertFalse((self.output / 'block/checkpoint.json').exists())

    def test_wrapper_completion_never_becomes_quality_or_research_readiness(self):
        mod = implementation()
        completed = {'preparation': {'status': 'completed'},
            'arms': {arm: {'status': 'completed'} for arm in 'ABCD'}, 'scientific_ready': False}
        context = self.fixture_context()
        with (patch.object(mod, '_inspect', return_value=({'dispatch_ready': True, 'blockers': []}, context)),
                patch.object(mod.controller_api, 'CanonicalPairedController', return_value=Mock()),
                patch.object(mod, '_new_backend', return_value=Mock()),
                patch.object(mod.paired, 'run_paired_block', return_value=completed)):
            result = mod.run_block(run=True)
        self.assertTrue(result['execution_complete'])
        self.assertFalse(result['scientific_ready'])
        self.assertFalse(result['quality_scored'])
        self.assertIsNone(result['model_requests'])

    def test_backend_is_closed_and_arbitrary_exception_text_is_redacted(self):
        mod = implementation()
        backend = Mock()
        with (patch.object(mod, '_inspect', return_value=({'dispatch_ready': True, 'blockers': []}, self.fixture_context())),
                patch.object(mod.controller_api, 'CanonicalPairedController', return_value=Mock()),
                patch.object(mod, '_new_backend', return_value=backend),
                patch.object(mod.paired, 'run_paired_block', side_effect=RuntimeError('sk-private-provider-response'))):
            result = mod.run_block(run=True)
        backend.close.assert_called_once_with()
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn('sk-private', json.dumps(result))

    def test_changed_input_after_preflight_stops_before_backend_or_controller_creation(self):
        mod = implementation()
        context = self.fixture_context()
        path = self.save('changed-settings.json', {'fixture': 'changed after check'})
        context['input_files'] = {str(path): '0' * 64}
        with (patch.object(mod, '_inspect', return_value=({'dispatch_ready': True, 'blockers': []}, context)),
                patch.object(mod, '_new_backend', side_effect=AssertionError('must not construct')),
                patch.object(mod.controller_api, 'CanonicalPairedController', side_effect=AssertionError('must not construct'))):
            result = mod.run_block(run=True)
        self.assertEqual(result['error_code'], 'input_changed_after_preflight')
        self.assertFalse(self.state.exists())
        self.assertFalse(self.output.exists())


class NativeDriverScopeTests(unittest.TestCase):
    """Cash and identity tests use the existing disposable ledger fixture only."""
    def setUp(self):
        self.mod = implementation()
        import test_paper1_batch_limits as batch_fixture
        self.fixture = batch_fixture.BatchLimitsTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        approved = next(row for row in self.fixture.auth['units'] if row['task_id'] == 'w-101')
        self.task = {'task_id': 'w-101', 'project_id': 'pallets/flask',
            'public_path': str(self.fixture.root / approved['public_relative_path']),
            'public_sha256': approved['public_sha256'], 'taskpack_public_sha256': 'b' * 64,
            'original_request_sha256': 'c' * 64, 'shared_reader_config_sha256': 'd' * 64}
        self.required = self.mod._required_scopes(self.task, 1, 'd' * 64)

    def scopes(self, *, dispatches=None):
        specs = copy.deepcopy(self.required)
        for spec in specs.values():
            n = dispatches if dispatches is not None else (3 if spec['kind'] == 'native' or ':B:' in (spec['unit'] or '') else 1)
            spec.update(max_http_dispatches=n, upper_bound_cny=f'{n * 3}.00',
                billing_basis={'kind': 'priced_upper_bound', 'evidence': self.fixture.evidence})
            for provider in spec['providers']:
                provider.update(checked_upper_bound_cny='3.00', checked_upper_bound_evidence=self.fixture.evidence)
        return specs

    def check(self, specs):
        with patch.object(self.mod, 'ROOT', self.fixture.root):
            return self.mod._check_scopes(specs, self.required, self.task, 1, self.fixture.ledger.status())

    def test_whole_block_cash_is_checked_without_reserving_any_attempt(self):
        with self.assertRaisesRegex(ValueError, 'whole_block_cash_envelope_does_not_fit'):
            self.check(self.scopes(dispatches=8))
        self.assertFalse(self.fixture.ledger.state_dir.exists())
        checked = self.check(self.scopes())
        self.assertEqual(checked['selected_total_upper_bound_cny'], '27.00')
        self.assertFalse(checked['reservation_performed'])
        self.assertFalse(checked['pricing_truth_independently_verified'])
        self.assertFalse(self.fixture.ledger.state_dir.exists())

    def test_wrong_scope_unit_and_incomplete_native_components_are_rejected(self):
        specs = self.scopes()
        name = next(name for name, spec in specs.items() if spec['unit'] == 'w-101:A:1')
        specs[name]['unit'] = 'w-101:A:2'
        with self.assertRaisesRegex(ValueError, 'selected_block_scope_binding_mismatch'):
            self.check(specs)
        with self.assertRaisesRegex(ValueError, 'scope_dispatch_envelope_below_required_components'):
            self.check(self.scopes(dispatches=1))
        self.assertFalse(self.fixture.ledger.state_dir.exists())

    def test_wrong_common_reader_config_and_missing_price_evidence_are_rejected(self):
        specs = self.scopes()
        first = next(iter(specs.values()))
        first['providers'][0]['config_sha256'] = 'e' * 64
        with self.assertRaisesRegex(ValueError, 'selected_block_provider_binding_mismatch'):
            self.check(specs)
        specs = self.scopes()
        next(iter(specs.values()))['providers'][0].pop('checked_upper_bound_evidence')
        with self.assertRaisesRegex(ValueError, 'invalid_provider_envelope'):
            self.check(specs)
        self.assertFalse(self.fixture.ledger.state_dir.exists())

    def test_pinned_serial_scope_envelope_passes_through_without_legacy_repricing(self):
        # Prices and ledger here are synthetic fixture data, never a live basis.
        api = self.mod.controller_api
        profile_hash = api.DEEPSEEK_PROFILE_SHA256
        pricing = self.fixture.root / 'fixture-deepseek-public-price.json'
        pricing.write_text(api.canonical({'schema_version': 1, 'kind': 'p1-deepseek-public-price-basis',
            'provider': 'deepseek', 'model': 'deepseek-flash', 'checked_date': api.DEEPSEEK_PROFILE['checked_date'],
            'currency': 'CNY', 'peak_input_cny_per_million': '2.00', 'peak_output_cny_per_million': '8.00',
            'context_token_upper_bound': 1048576, 'max_output_tokens': 8192,
            'source_url': 'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/',
            'fixture': 'offline contract test only; not a live price or account observation',
            'actual_added_cash_cny': None}) + '\n')
        price_evidence = {'ref': pricing.name, 'sha256': hashlib.sha256(pricing.read_bytes()).hexdigest()}
        self.task['shared_reader_config_sha256'] = profile_hash
        self.required = self.mod._required_scopes(self.task, 1, profile_hash)
        specs = self.scopes(dispatches=8)
        for spec in specs.values():
            is_B = ':B:' in (spec['unit'] or '')
            spec.update(upper_bound_cny='7.20' if is_B else '3.20', max_http_dispatches=24 if is_B else 8)
            for provider in spec['providers']:
                if provider['provider'] == 'deepseek':
                    provider['checked_upper_bound_evidence'] = price_evidence
                    provider['scope_usage_envelope'] = {
                        'kind': 'deepseek-native-serial-envelope-v1',
                        'relay_source_sha256': self.mod.controller_api.relay_source_sha256(),
                        'max_input_tokens': 65536, 'max_output_tokens': 8192,
                        'max_http_dispatches': 8, 'scope_upper_bound_cny': '3.20'}
                else:
                    provider['checked_upper_bound_cny'] = '0.25'
        with patch.object(api, 'current_utc_date', return_value=api.DEEPSEEK_PROFILE['checked_date']):
            checked = self.check(specs)
        self.assertEqual(checked['selected_total_upper_bound_cny'], '20.00')
        self.assertFalse(checked['reservation_performed'])
        self.assertFalse(checked['pricing_truth_independently_verified'])
        self.assertFalse(self.fixture.ledger.state_dir.exists())


if __name__ == '__main__':
    unittest.main()
