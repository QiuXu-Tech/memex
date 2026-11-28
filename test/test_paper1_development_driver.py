"""Selected development execution boundaries; all execution objects are offline fixtures."""
import copy
from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'scripts/paper1/development_driver.py'
if PATH.exists():
    SPEC = importlib.util.spec_from_file_location('p1_development_driver_test', PATH)
    M = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(M)
else:
    M = None


def implementation():
    if M is None:
        raise AssertionError('development_driver.py must implement an explicit A/C/D development entry')
    return M


class DevelopmentExecutionTests(unittest.TestCase):
    def setUp(self):
        self.mod = implementation()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.public = self.root / 'public'
        self.public.mkdir()
        self.output = self.root / 'output'
        self.state = self.root / 'state'
        self.task = {'task_id': 'w-101', 'project_id': 'pallets/flask', 'public_path': str(self.public),
            'public_sha256': 'a' * 64, 'taskpack_public_sha256': 'b' * 64,
            'original_request_sha256': 'c' * 64, 'shared_reader_config_sha256': 'd' * 64}
        self.context = {'task': self.task, 'replicate': 1, 'order': ('A', 'C', 'D'),
            'settings': {'fixture_only': True}, 'scope_specs': {}, 'state_root': self.state,
            'output': self.output, 'profile_path': self.root / 'profile.json',
            'input_files': {}, 'relocation': {'planned_units': 16}}
        self.report = {'dispatch_ready': True, 'status': 'eligible_for_explicit_run', 'blockers': [],
                       'model_requests': 0, 'ledger_writes': 0}
        self.backend, self.controller = Mock(), Mock()
        self.calls = []
        self.registry_bytes = b'{"fixture_only":"retained original unit registry"}\n'

    def prepared(self, task, replicate, backend, controller, output, **kwargs):
        self.calls.append(('prepare', backend, controller))
        output.mkdir()
        (output / 'checkpoint.json').write_text('{"fixture_only":true}\n')
        (output / 'unit-state').mkdir()
        (output / 'unit-state/events.jsonl').write_bytes(self.registry_bytes)
        return {'status': 'completed', 'fixture_only': True}

    def completed_unit(self, checkpoint, arm, run_id, output, backend, controller, **kwargs):
        self.calls.append((arm, backend, controller))
        self.assertEqual(checkpoint, self.output / 'block/checkpoint.json')
        self.assertEqual(run_id, 'p1-method-' + self.mod.paired.digest(
            {'task': self.task, 'replicate': 1, 'arm': arm})[:24])
        self.assertEqual(output, self.output / run_id)
        self.assertEqual(kwargs, {'execution_mode': 'live'})
        return {'status': 'completed', 'fixture_only': True}

    def boundaries(self, *, report=None, prepare=None, unit=None):
        stack = ExitStack()
        stack.enter_context(patch.object(self.mod.native, '_inspect',
            return_value=(report if report is not None else self.report, self.context)))
        self.make_controller = stack.enter_context(patch.object(self.mod.native.controller_api,
            'CanonicalPairedController', return_value=self.controller))
        self.make_backend = stack.enter_context(patch.object(self.mod.native, '_new_backend', return_value=self.backend))
        self.prepare = stack.enter_context(patch.object(self.mod.paired, 'prepare_block',
            side_effect=prepare if prepare is not None else self.prepared))
        self.unit = stack.enter_context(patch.object(self.mod.paired, 'run_unit',
            side_effect=unit if unit is not None else self.completed_unit))
        self.addCleanup(stack.close)
        return stack

    def test_read_only_default_never_constructs_backend_or_creates_outputs(self):
        self.boundaries()
        result = self.mod.run_selected()
        self.make_controller.assert_not_called()
        self.make_backend.assert_not_called()
        self.prepare.assert_not_called()
        self.unit.assert_not_called()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.state.exists())
        self.assertEqual(result['mode'], 'check')
        self.assertEqual(result['selected_arms'], ['A', 'C', 'D'])
        self.assertEqual(result['planned_block_units'], 4)
        self.assertEqual(result['planned_development_units'], 16)
        self.assertEqual(result['score_status'], 'not_scored')

    def test_one_live_lifetime_prepares_once_and_runs_only_fixed_first_attempt_identities(self):
        self.boundaries()
        result = self.mod.run_selected(run=True)
        self.assertEqual([row[0] for row in self.calls], ['prepare', 'A', 'C', 'D'])
        self.assertTrue(all(row[1] is self.backend and row[2] is self.controller for row in self.calls))
        self.make_controller.assert_called_once()
        self.make_backend.assert_called_once()
        self.backend.close.assert_called_once_with()
        self.assertTrue(result['selected_execution_complete'])
        self.assertFalse(result['execution_complete'])
        self.assertFalse(result['scientific_ready'])
        self.assertFalse(result['quality_scored'])
        self.assertEqual(set(result['execution']['arms']), set('ABCD'))
        deferred = result['execution']['arms']['B']
        self.assertEqual(deferred['status'], 'not_dispatched_dependency_blocked')
        self.assertFalse(deferred['attempt_created'])
        self.assertFalse(deferred['scope_reserved'])
        self.assertEqual(result['planned_block_units'], 4)
        self.assertEqual(result['score_status'], 'not_scored')
        self.assertIsNone(result['model_requests'])
        self.assertEqual((self.output / 'block/unit-state/events.jsonl').read_bytes(), self.registry_bytes)
        self.assertEqual(json.loads((self.output / 'development-selection-result.json').read_text()), result)

    def test_blocked_common_preflight_never_creates_attempts_or_backend(self):
        self.boundaries(report={'dispatch_ready': False, 'blockers': ['unrecognized_common_failure']})
        result = self.mod.run_selected(run=True)
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['preflight']['blockers'], ['unrecognized_common_failure'])
        self.assertEqual(result['model_requests'], 0)
        self.assertEqual(result['ledger_writes'], 0)
        self.make_controller.assert_not_called()
        self.make_backend.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_failed_native_preparation_dispatches_no_arm_and_closes(self):
        self.boundaries(prepare=lambda *args, **kwargs: {'status': 'budget_exhausted', 'fixture_only': True})
        result = self.mod.run_selected(run=True)
        self.unit.assert_not_called()
        self.backend.close.assert_called_once_with()
        self.assertFalse(result['selected_execution_complete'])
        self.assertEqual(result['execution']['preparation']['status'], 'budget_exhausted')
        self.assertTrue(all(result['execution']['arms'][arm]['status'] == 'not_dispatched_preparation_incomplete'
                            for arm in ('A', 'C', 'D')))

    def test_failed_unit_is_retained_once_without_replay_or_dropping_denominator(self):
        def unit(*args, **kwargs):
            result = self.completed_unit(*args, **kwargs)
            return {'status': 'capture_incomplete', 'usage_capture_complete': False} if args[1] == 'C' else result
        self.boundaries(unit=unit)
        result = self.mod.run_selected(run=True)
        self.assertEqual([row[0] for row in self.calls], ['prepare', 'A', 'C', 'D'])
        self.assertFalse(result['selected_execution_complete'])
        self.assertFalse(result['execution']['arms']['C']['usage_capture_complete'])
        self.assertEqual(result['planned_block_units'], 4)
        self.assertEqual(self.unit.call_count, 3)

    def test_unexpected_unit_exception_aborts_later_units_and_redacts_text(self):
        def unit(*args, **kwargs):
            if args[1] == 'C':
                raise RuntimeError('sk-private-fixture-error')
            return self.completed_unit(*args, **kwargs)
        self.boundaries(unit=unit)
        result = self.mod.run_selected(run=True)
        self.assertEqual([call.args[1] for call in self.unit.call_args_list], ['A', 'C'])
        self.assertEqual(result['execution']['arms']['D']['status'], 'not_dispatched_execution_aborted')
        self.assertNotIn('sk-private', json.dumps(result))
        self.assertIsNone(result['model_requests'])
        self.backend.close.assert_called_once_with()

    def test_input_drift_stops_before_output_backend_or_controller(self):
        path = self.root / 'settings.json'
        path.write_text('{}\n')
        self.context['input_files'][str(path)] = '0' * 64
        self.boundaries()
        result = self.mod.run_selected(run=True)
        self.assertEqual(result['error_code'], 'input_changed_after_preflight')
        self.make_controller.assert_not_called()
        self.make_backend.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_cleanup_failure_never_reports_selected_completion(self):
        self.backend.close.side_effect = RuntimeError('private-cleanup-details')
        self.boundaries()
        result = self.mod.run_selected(run=True)
        self.assertFalse(result['selected_execution_complete'])
        self.assertFalse(result['backend_closed'])
        self.assertEqual(result['cleanup_error'], 'backend_close_failed')
        self.assertNotIn('private-cleanup', json.dumps(result))

    def test_run_boolean_is_explicit_and_selection_is_not_a_public_override(self):
        with self.assertRaisesRegex(ValueError, 'explicit_run_boolean_required'):
            self.mod.run_selected(run=1)
        with self.assertRaises(TypeError):
            self.mod.run_selected(arms=('A',))


class DevelopmentPreflightTests(unittest.TestCase):
    def setUp(self):
        self.mod = implementation()
        import test_paper1_batch_limits as batch_fixture
        self.fixture = batch_fixture.BatchLimitsTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.task_rows = []
        for task_id, project in (('w-101', 'pallets/flask'), ('w-102', 'psf/requests')):
            approved = next(u for u in self.fixture.auth['units'] if u['task_id'] == task_id)
            self.task_rows.append({'task_id': task_id, 'project_id': project,
                'public_path': str(self.root / approved['public_relative_path']),
                'public_sha256': approved['public_sha256'], 'taskpack_public_sha256': 'b' * 64})
        self.settings = {'codex': str(self.root / 'codex'), 'node': str(self.root / 'node'),
            'tokenizer_path': str(self.root / 'tokenizer.json'), 'credential_file': str(self.root / 'credential'),
            'rawrag_upstream': str(self.root / 'missing-rawrag'), 'tasks': {}}
        for task in ('w-101', 'w-102'):
            python = self.root / task / 'bin/python'
            python.parent.mkdir(parents=True)
            python.write_text('fixture only')
            self.settings['tasks'][task] = {'python': str(python), 'sandbox': {
                'kind': 'bwrap', 'executable': str(self.root / 'bwrap'), 'python': str(python),
                'dependencies': str(python.parent.parent / 'lib/python3.10/site-packages'),
                'runtime_roots': [str(self.root / 'runtime')]}}
        self.settings_path = self.root / 'settings.json'
        self.settings_path.write_text(json.dumps(self.settings))
        self.specs = self.root / 'scopes.json'
        self.specs.write_text('{}')
        self.services = {'deepseek_file_metadata_acceptable': True, 'embedding_environment_present': False,
            'reranker_environment_present': False, 'credential_file_contents_read': False,
            'provider_authentication_checked': False, 'provider_billing_checked': False}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(self.mod.native, 'ROOT', self.root))
        self.stack.enter_context(patch.object(self.mod.native.controller_api, 'CanonicalPairedController',
            return_value=Mock(ledger=self.fixture.ledger)))
        self.stack.enter_context(patch.object(self.mod.paired, 'create_relocation_receipt', return_value={
            'receipt_sha256': 'e' * 64, 'planned_units': 16, 'tasks': self.task_rows}))
        self.stack.enter_context(patch.object(self.mod.native, '_services', return_value=self.services))
        self.check_scopes = self.stack.enter_context(patch.object(self.mod.native, '_check_scopes',
            return_value={'status': 'checked', 'reservation_performed': False}))

    def inspect(self, **kwargs):
        return self.mod.native._inspect(settings_path=self.settings_path, scope_specs_path=self.specs,
            state_root=self.root / 'new-state', output=self.root / 'new-output', **kwargs)[0]

    def test_selection_removes_only_b_requirements_and_preserves_common_unknown_blocker(self):
        def common_failure(settings, tasks, profile, report, *, arms):
            self.assertEqual(tuple(arms), ('A', 'C', 'D'))
            report['blockers'].append('unrecognized_common_failure')
        with patch.object(self.mod.native, '_device', side_effect=common_failure):
            result = self.inspect(order=('A', 'C', 'D'), development_selection=('A', 'C', 'D'))
        self.assertEqual(result['blockers'], ['unrecognized_common_failure'])
        self.assertEqual(len(result['required_scope_bindings']), 4)
        self.assertEqual({spec['unit'] for spec in result['required_scope_bindings'].values()
                          if spec['kind'] == 'method'}, {'w-101:A:1', 'w-101:C:1', 'w-101:D:1'})
        self.assertFalse(self.fixture.ledger.state_dir.exists())

    def test_default_full_entry_still_requires_b_services_and_all_five_scopes(self):
        with patch.object(self.mod.native, '_device'):
            result = self.inspect()
        self.assertIn('embedding_environment_unavailable', result['blockers'])
        self.assertIn('reranker_environment_unavailable', result['blockers'])
        self.assertEqual(len(result['required_scope_bindings']), 5)

    def test_only_exact_acd_development_selection_is_allowed(self):
        with patch.object(self.mod.native, '_device'):
            for selection in (('A',), ('A', 'B', 'C'), ('A', 'C', 'D', 'D')):
                result = self.inspect(order=selection, development_selection=selection)
                self.assertIn('exact_development_selection_required', result['blockers'])
        self.assertFalse(self.fixture.ledger.state_dir.exists())

    def test_selected_device_check_skips_rawrag_but_keeps_common_native_checks(self):
        for executable in ('codex', 'node'):
            path = Path(self.settings[executable])
            path.write_text('fixture only')
            path.chmod(0o755)
        self.stack.enter_context(patch.object(self.mod.native.reader, 'ReferenceTokenizer',
            return_value=Mock(identity={'fixture_only': True})))
        self.stack.enter_context(patch.dict(self.mod.native.WORKFLOW,
            inspect=lambda *args: {'environment': {'requirements_match': True}}))
        self.stack.enter_context(patch.object(self.mod.native, 'SandboxRunner', side_effect=lambda config: Mock(config=config)))
        self.stack.enter_context(patch.object(self.mod.native.rawrag, 'dependency_report',
            side_effect=AssertionError('unused B dependency must not be inspected')))
        self.stack.enter_context(patch.object(self.mod.native.rawrag, 'verify_source_files',
            side_effect=AssertionError('unused B source must not be inspected')))
        result = self.inspect(order=('A', 'C', 'D'), development_selection=('A', 'C', 'D'))
        self.assertTrue(result['dispatch_ready'], result['blockers'])
        self.assertTrue(result['checks']['tokenizer']['verified'])
        self.assertEqual(set(result['checks']['python_workflows']), {'w-101', 'w-102'})
        self.assertEqual(result['checks']['rawrag']['status'], 'not_required_for_selected_development_arms')
        self.services['deepseek_file_metadata_acceptable'] = False
        result = self.inspect(order=('A', 'C', 'D'), development_selection=('A', 'C', 'D'))
        self.assertIn('deepseek_credential_file_metadata_unavailable', result['blockers'])
        self.assertFalse(self.fixture.ledger.state_dir.exists())

    def test_invalid_scope_error_remains_blocking_in_selection_mode(self):
        self.check_scopes.side_effect = ValueError('invalid_provider_envelope')
        with patch.object(self.mod.native, '_device'):
            result = self.inspect(order=('A', 'C', 'D'), development_selection=('A', 'C', 'D'))
        self.assertIn('invalid_provider_envelope', result['blockers'])
        self.assertFalse(result['dispatch_ready'])


if __name__ == '__main__':
    unittest.main()
