import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/paper1'))
import native_backend as backend


def captured_history():
    return {'thread': {'id': 'parent-1', 'modelProvider': 'memex_deepseek_p1', 'ephemeral': False,
        'turns': [{'id': 'turn-1', 'status': 'completed', 'error': None, 'items': [
            {'id': 'u1', 'type': 'userMessage', 'content': [{'type': 'text', 'text': 'Fix local code.'}]},
            {'id': 'a1', 'type': 'agentMessage', 'text': 'A recorded draft.'}]},
            {'id': 'turn-2', 'status': 'completed', 'error': None, 'items': [{'id': 'compact-1', 'type': 'contextCompaction'}]}]}}


class NativeBackendTest(unittest.TestCase):
    def test_actual_history_binding_rejects_changed_retained_parent(self):
        response = captured_history()
        before = backend.stable_thread_state(response, 'parent-1', compaction_item='compact-1', original_request='Fix local code.')
        response['thread']['updatedAt'] = 999
        self.assertEqual(before, backend.stable_thread_state(response, 'parent-1', compaction_item='compact-1', original_request='Fix local code.'))
        response['thread']['turns'][0]['items'][1]['text'] = 'Changed.'
        after = backend.stable_thread_state(response, 'parent-1', compaction_item='compact-1', original_request='Fix local code.')
        self.assertNotEqual(before['history_sha256'], after['history_sha256'])

    def test_summary_or_foreign_or_partial_history_is_not_native_parent(self):
        mutations = [lambda x: x['thread'].update(id='foreign'), lambda x: x['thread'].update(turns=[]),
                     lambda x: x['thread'].update(modelProvider='other'), lambda x: x['thread'].update(ephemeral=True),
                     lambda x: x['thread']['turns'][0].update(status='inProgress'),
                     lambda x: x['thread']['turns'][1].update(items=[])]
        for mutate in mutations:
            response = captured_history(); mutate(response)
            with self.assertRaises(backend.BackendError):
                backend.stable_thread_state(response, 'parent-1', compaction_item='compact-1', original_request='Fix local code.')

    def test_actual_fork_lineage_and_inherited_content_are_independently_checked(self):
        parent = captured_history()
        child = copy.deepcopy(parent); child['thread'].update(id='child-1', forkedFromId='parent-1')
        p = backend.stable_thread_state(parent, 'parent-1', compaction_item='compact-1')
        c = backend.stable_thread_state(child, 'child-1', compaction_item='compact-1', expected_parent='parent-1')
        self.assertEqual(p['content_sha256'], c['content_sha256'])
        self.assertNotEqual(p['history_sha256'], c['history_sha256'])
        child['thread']['forkedFromId'] = 'other-parent'
        with self.assertRaisesRegex(backend.BackendError, 'actual_fork_lineage_required'):
            backend.stable_thread_state(child, 'child-1', compaction_item='compact-1', expected_parent='parent-1')

    def test_failed_operation_preserves_known_usage_without_claiming_completeness(self):
        instance = backend.NativeBackend.__new__(backend.NativeBackend); instance._scope = lambda _: 'scope-1'
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            backend.save(output / 'provider-operation-audit.json', {'scope_id': 'scope-1', 'component': 'reader', 'records': [
                {'dispatch_id': 'request-1', 'provider_dispatch_started': True, 'usage_complete': True,
                 'usage': {'input_tokens': 19, 'cached_input_tokens': 3, 'output_tokens': 2}},
                {'dispatch_id': 'request-2', 'provider_dispatch_started': True, 'usage_complete': False, 'usage': None}]})
            rows = instance.capture_failure_usage({}, output=output)
            self.assertEqual(rows[0]['values'], {'input_tokens': 19, 'cached_input_tokens': 3, 'output_tokens': 2})
            self.assertEqual(rows[0]['component'], 'model')
            self.assertEqual(rows[-1]['coverage'], 'incomplete')
            self.assertEqual(len(list(output.iterdir())), 1)

    def test_interrupted_baseline_tail_keeps_known_usage_prefix_incomplete(self):
        instance = backend.NativeBackend.__new__(backend.NativeBackend); instance._scope = lambda _: 'scope-1'
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder); (output / 'rawrag').mkdir()
            known = {'event': 'usage', 'usage_id': 'embed-1', 'measurement_id': 'embed-1', 'operation_id': 'embed-call-1',
                     'component': 'embedding', 'counter_kind': 'delta', 'values': {'quantity': 23}, 'source_ref': 'ledger.json'}
            (output / 'rawrag/usage.jsonl').write_text(json.dumps(known) + '\n{"event":')
            rows = instance.capture_failure_usage({}, output=output)
            self.assertEqual(rows[0]['values']['quantity'], 23)
            self.assertEqual(rows[0]['source_ref'], 'rawrag/ledger.json')
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(row['coverage'] == 'incomplete' for row in rows if row['event'] == 'component_end'))

    def test_private_credential_is_lazy_and_requires_owner_only_regular_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fake-key'; path.write_text('sk-this-is-only-a-unit-test-value'); path.chmod(0o600)
            provider = backend.private_credential_provider(path)
            path.write_text('sk-this-is-another-unit-test-value')
            self.assertEqual(provider(), 'sk-this-is-another-unit-test-value')
            path.chmod(0o644)
            with self.assertRaises(backend.BackendError):
                provider()
            path.chmod(0o600); link = Path(folder) / 'alias'; link.symlink_to(path)
            with self.assertRaises(backend.BackendError.__bases__[0]):
                backend.private_credential_provider(link)

    def test_native_test_action_keeps_public_receipt_contract(self):
        instance = backend.NativeBackend.__new__(backend.NativeBackend)
        instance.controller = Mock()
        instance._scope = lambda _: 'scope-1'
        intent = {'kinds': ['public_tool_call'], 'observable_kind': 'test_execution', 'operation_id': 'tool-1'}
        result = instance._tool_admission({})(intent)
        self.assertEqual(result['admitted_kinds'], ['public_tool_call'])
        self.assertEqual(instance.controller.record_action.call_count, 2)
        instance.controller.record_action.assert_any_call('scope-1', 'test_execution', 'tool-1:test_execution')

    def test_method_test_action_never_widens_native_authorization(self):
        instance = backend.NativeBackend.__new__(backend.NativeBackend)
        instance.controller = Mock(); instance._scope = lambda _: 'scope-1'
        instance._tool_admission({'checkpoint': {}})({'kinds': ['public_tool_call'],
            'observable_kind': 'test_execution', 'operation_id': 'tool-1'})
        self.assertEqual(instance.controller.record_action.call_count, 1)

    def test_source_admission_binds_request_epoch_and_unit_before_ledger_write(self):
        instance = backend.NativeBackend.__new__(backend.NativeBackend)
        instance.controller = Mock(); instance._scope = lambda _: 'scope-1'
        instance.evidence_identities = {'scope-1': {'archive_epoch': 'actual-epoch'}}
        context = {'task': {'task_id': 'w-101', 'original_request_sha256': 'a' * 64},
                   'parent': {'source_archive_sha256': 'b' * 64}}
        intent = {'kind': 'source_open', 'archive_sha256': 'b' * 64, 'task_id': 'w-101',
                  'original_request_sha256': 'a' * 64, 'archive_epoch': 'actual-epoch', 'unit_id': 'prime',
                  'source_bytes_upper_bound': 42, 'operation_id': 'open-1'}
        admit = instance._source_admission(context)
        for changes in ({'archive_epoch': 'foreign'}, {'unit_id': 'other-unit'}, {'original_request_sha256': 'f' * 64}):
            with self.assertRaises(backend.BackendError):
                admit({**intent, **changes})
        instance.controller.record_action.assert_not_called()
        admit(intent)
        instance.controller.record_action.assert_called_once_with('scope-1', 'public_tool_call', 'open-1:tool')

    def test_unbound_dynamic_tool_never_reaches_workspace(self):
        host = backend.PublicNativeHost.__new__(backend.PublicNativeHost)
        host.deadline = time.monotonic() + 10
        host.broker = Mock(); host.tid = 'parent-1'; host.active_turn_id = 'turn-1'
        host.answered = set(); host.public_calls = []; host.record = Mock(); host.send = Mock()
        valid = {'id': 1, 'method': 'item/tool/call', 'params': {'threadId': 'parent-1',
            'turnId': 'turn-1', 'callId': 'call-1', 'tool': 'list_files', 'arguments': {}}}
        for changes in ({'threadId': 'other'}, {'turnId': 'other'}, {'tool': 'exec_command'}, {'namespace': 'foreign'}):
            message = copy.deepcopy(valid); message['params'].update(changes)
            with self.assertRaises(backend.BackendError):
                host.dispatch(message)
        host.broker.call.assert_not_called()
        host.broker.call.return_value = {'ok': True, 'result': {'files': []}, 'receipt': {}}
        host.dispatch(valid)
        host.broker.call.assert_called_once_with('list_files', {})
        with self.assertRaises(backend.BackendError):
            host.dispatch(valid)

    def test_usage_never_substitutes_reference_tokens_or_cash(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            rows = backend.usage_rows([{'dispatch_id': 'request-1', 'provider_dispatch_started': True,
                'usage_complete': False, 'usage': None, 'reference_input_tokens': 100, 'held_cash': 3}], output, 'model')
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['coverage'], 'incomplete')
            self.assertEqual(rows[0]['usage_ids'], [])

    def _archive_events(self, status='passed', observed=True):
        time = '2026-11-28T10:00:00+00:00'; version = 'a' * 64
        receipt = {'event_id': 'test-receipt-1'}
        result = {'completed': observed, 'executed': True, 'status': status, 'testCount': 2,
            'workspace_before_sha256': version, 'workspace_after_sha256': version,
            'executed_snapshot_after_sha256': version, 'observation_sha256': 'b' * 64,
            'command': 'pytest tests/test_blueprints.py', 'exitCode': 0 if status == 'passed' else 1}
        return [
            {'event': 'item/completed', 'utc': time, 'item': {'id': 'u1', 'type': 'userMessage',
             'content': [{'type': 'text', 'text': 'Fix local code.'}]}},
            {'event': 'item/completed', 'utc': time, 'item': {'id': 'a0', 'type': 'agentMessage', 'text': 'I will inspect.'}},
            {'event': 'public_tool/request', 'utc': time, 'callId': 'c1', 'tool': 'run_current_tests', 'arguments': {}},
            {'event': 'public_tool/response', 'utc': time, 'callId': 'c1', 'tool': 'run_current_tests',
             'result': {'ok': True, 'result': result, 'receipt': receipt}},
            {'event': 'item/completed', 'utc': time, 'item': {'id': 'a1', 'type': 'agentMessage', 'text': 'A recorded draft.'}},
            {'event': 'public_workspace/snapshot', 'utc': time, 'version': version}]

    def _archive(self, events):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'events.jsonl'
            source.write_text(''.join(json.dumps(event) + '\n' for event in events))
            return backend.archive_from_observations('w-101', 'Fix local code.', 'A recorded draft.', source, 'a' * 64)

    def test_archive_retains_intermediate_messages_actual_tests_and_readback(self):
        archive = self._archive(self._archive_events())
        self.assertEqual(len(archive['sources']), 5)
        self.assertEqual([row['type'] for row in archive['sources']], ['request', 'draft', 'test_result', 'draft', 'current_version'])
        self.assertTrue(archive['sources'][2]['complete'])
        api = backend.runpy.run_path(str(backend.HERE / 'rawrag_adapter.py'))
        api['validate_archive'](archive, api['load_config']()['limits'])

    def test_bare_zero_exit_is_an_observation_not_a_passed_test_source(self):
        archive = self._archive(self._archive_events(observed=False))
        self.assertFalse(any(row['type'] == 'test_result' for row in archive['sources']))

    def test_missing_tool_response_or_public_item_fails_archive_capture(self):
        events = self._archive_events(); events.pop(3)
        with self.assertRaises(backend.BackendError):
            self._archive(events)

    def test_real_python_node_protocol_binds_admission_and_preserves_prime_epoch(self):
        """Real local L2/IPC, explicitly fixture extraction; zero model/provider calls."""
        node = backend.shutil.which('node')
        self.assertIsNotNone(node)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); archive_path = root / 'archive.json'; request_path = root / 'request.txt'
            archive_path.write_text(json.dumps(self._archive(self._archive_events())) + '\n')
            request_path.write_text('Fix local code.')
            output = root / 'process'; output.mkdir()
            context = 'Scope w-101. Test command pytest tests/test_blueprints.py; current workspace ' + 'a' * 64
            helper = backend.EvidenceProcess(node, {'schema_version': 1, 'archivePath': str(archive_path),
                'archiveSha256': backend.sha_file(archive_path), 'requestPath': str(request_path),
                'requestSha256': backend.sha_file(request_path), 'taskId': 'w-101', 'output': str(root / 'l2'),
                'publicInput': {'draft': 'A recorded draft.', 'context': context, 'toolDescriptions': []}}, output)
            deadline = time.monotonic() + 20
            admissions = []
            def admit(intent):
                admissions.append(intent)
                return {'operation_id': intent['operation_id'], 'fixture_only': True}
            try:
                prepared = helper.call({'op': 'prepare'}, deadline=deadline)
                self.assertEqual(prepared['input']['request'], 'Fix local code.')
                extracted = helper.call({'op': 'install', 'rawOutput': json.dumps({'claims': [
                    {'type': 'test_result', 'scope': 'w-101', 'entity': 'pytest tests/test_blueprints.py',
                     'version': 'a' * 64, 'basis': {'field': 'context', 'quote': 'pytest tests/test_blueprints.py'},
                     'uncertainty': []}], 'unresolved': []})}, deadline=deadline)
                self.assertTrue(extracted['ok'])
                common = {'maxPacketBytes': 12000, 'maxEvidenceBytes': 4000, 'maxReferenceBytes': 4000,
                          'limits': {'maxSourceOpens': 6, 'maxSourceBytes': 96000, 'maxSourceBytesPerOpen': 4000}}
                prime = helper.call({'op': 'prime', **common}, deadline=deadline, authorize_open=admit)
                always = helper.call({'op': 'verify', 'unitId': 'fixture-C', 'mode': 'always', **common},
                                     deadline=deadline, authorize_open=admit)
                selective = helper.call({'op': 'verify', 'unitId': 'fixture-D', 'mode': 'selective', **common},
                                        deadline=deadline, authorize_open=admit)
                self.assertEqual(prime['counts']['source_open_calls'], 1)
                self.assertEqual(always['counts']['source_open_calls'], 1)
                self.assertEqual(selective['counts']['source_open_calls'], 0)
                self.assertEqual(selective['counts']['reused_receipts'], 1)
                self.assertEqual(len(admissions), 2)
                self.assertEqual(len({r['operation_id'] for r in admissions}), 2)
                self.assertEqual(prime['archive_epoch'], selective['archive_epoch'])
            finally:
                helper.close()
        events = self._archive_events(); events[1]['item']['type'] = 'commandExecution'
        with self.assertRaises(backend.BackendError):
            self._archive(events)


if __name__ == '__main__':
    unittest.main()
