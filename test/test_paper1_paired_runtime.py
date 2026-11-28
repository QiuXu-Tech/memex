"""Offline runtime contracts. Fixtures never become research observations."""
import copy
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'scripts/paper1/paired_runtime.py'
API = runpy.run_path(str(MODULE)) if MODULE.exists() else {}
BASE = ROOT / 'docs/research/p1-evidence-verification/tasks/workflows'
PLAN = BASE / 'source-draft-plan.json'
PACKAGES = [BASE / 'packages' / task for task in ('w-101', 'w-102')]
AUTH = ROOT / 'docs/research/p1-evidence-verification/artifacts/authorized-batch1/authorization.json'
RECORDED = ROOT / 'docs/research/p1-evidence-verification/artifacts/readonly-native/attempt-01'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value) + '\n')


def load_api(name):
    if not callable(API.get(name)):
        raise AssertionError(name + ' must implement the runtime contract')
    return API[name]


class FixtureController:
    """Local durable admission fixture, never a real authorization issuer."""
    def __init__(self, deny=False):
        self.deny = deny
        self.scopes = []
        self.finished = []

    def receipt(self, intent):
        if self.deny:
            raise ValueError('fixture_denied')
        without = {k: v for k, v in intent.items() if k != 'intent_sha256'}
        if intent['intent_sha256'] != API['digest'](without):
            raise AssertionError('intent binding invalid')
        return {'schema_version': 1, 'kind': 'p1-dispatch-admission-receipt', 'decision': 'allow',
                'dispatch_id': intent['dispatch_id'], 'request_sha256': intent['request_sha256'],
                'intent_sha256': intent['intent_sha256'], 'admission_id': 'fixture-admission'}

    def admit_scope(self, intent):
        self.scopes.append(intent)
        return self.receipt(intent)

    def before_operation(self, intent):
        return self.receipt(intent)

    def finish_scope(self, intent, result):
        self.finished.append((intent, result))


class FixtureBackend:
    """Writes complete local protocol fixtures for boundary tests only."""
    evidence_origin = 'contract_fixture'

    def __init__(self, fail_reader=False, parent_drift=False, excess_tools=False):
        self.fail_reader, self.parent_drift, self.excess_tools = fail_reader, parent_drift, excess_tools
        self.forks = []
        self.reader_inputs = []

    def wrap(self, value, usage_rows=None, trace_refs=None):
        return {'value': value, 'usage_rows': usage_rows or [], 'trace_refs': trace_refs or []}

    def capture_parent(self, context, *, output, deadline):
        workspace = output / 'workspace'; workspace.mkdir()
        (workspace / 'program.txt').write_text('fixture current source\n')
        task, replicate = context['task'], context['replicate']
        self.parent = 'fixture-parent-' + task['task_id'] + '-' + str(replicate)
        self.capture = output / 'events.jsonl'
        rows = [{'event': 'thread/start', 'threadId': self.parent, 'model': 'fixture-reader', 'provider': 'fixture'},
                {'event': 'item/completed', 'threadId': self.parent, 'turnId': 'fixture-prelude',
                 'item': {'type': 'userMessage', 'id': 'fixture-request', 'content':
                          [{'type': 'text', 'text': context['original_request']}]}},
                {'event': 'turn/completed', 'threadId': self.parent, 'turnId': 'fixture-prelude', 'status': 'completed'}]
        self.capture.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        source = {'eventId': 'fixture-event', 'sourceId': 'fixture-source', 'sourceSequence': 1,
                  'observedAt': '2026-11-28T00:00:00Z', 'role': 'tool', 'type': 'test_result',
                  'scope': task['task_id'], 'entity': 'fixture-test', 'text': 'Fixture receipt only.'}
        archive = {'schema': 1, 'taskId': task['task_id'], 'snapshot': {'cutoff': source['observedAt'],
                    'watermark': 'fixture-watermark', 'complete': True}, 'sources': [source]}
        save(output / 'archive.json', archive)
        return self.wrap({'task_binding': {key: (replicate if key == 'replicate' else task[key]) for key in
            ('task_id', 'replicate', 'public_sha256', 'original_request_sha256', 'shared_reader_config_sha256')},
            'native_parent_thread_id': self.parent, 'workspace_path': 'workspace',
            'source_archive_path': 'archive.json', 'native_capture_path': 'events.jsonl'})

    def prime_D(self, context, *, output, deadline):
        extraction = {'ok': True, 'claims': [{'type': 'test_result', 'scope': context['task']['task_id'],
                       'entity': 'fixture-test', 'version': 'fixture-version'}], 'rawOutput': '{"claims":[]}',
                      'coverageEstablished': False, 'promptSha256': 'a' * 64}
        save(output / 'extraction.json', extraction)
        save(output / 'receipts.json', {'extraction_sha256': sha(output / 'extraction.json'),
             'source_archive_sha256': context['parent']['source_archive_sha256'], 'receipts': [{'fixture': True}]})
        return self.wrap({'extraction_path': 'extraction.json', 'receipts_path': 'receipts.json'})

    def compact_parent(self, context, *, output, deadline):
        rows = [json.loads(row) for row in self.capture.read_text().splitlines()]
        rows += [{'event': 'turn/started', 'threadId': self.parent, 'turnId': 'fixture-compaction', 'status': 'inProgress'},
                 {'event': 'item/started', 'threadId': self.parent, 'turnId': 'fixture-compaction',
                  'kind': 'contextCompaction', 'itemId': 'fixture-compaction-item'},
                 {'event': 'item/completed', 'threadId': self.parent, 'turnId': 'fixture-compaction',
                  'item': {'type': 'contextCompaction', 'id': 'fixture-compaction-item'}},
                 {'event': 'turn/completed', 'threadId': self.parent, 'turnId': 'fixture-compaction', 'status': 'completed'}]
        (output / 'events.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
        return self.wrap({'native_parent_thread_id': self.parent, 'turn_id': 'fixture-compaction',
                          'item_id': 'fixture-compaction-item', 'native_capture_path': 'events.jsonl'})

    def verify_checkpoint(self, context, *, output, deadline):
        binding = {key: context['checkpoint'][key] for key in API['CHECKPOINT_IDENTITY_FIELDS']}
        if self.parent_drift and self.forks:
            binding['native_capture_sha256'] = '0' * 64
        return self.wrap({'binding': binding})

    def fork_parent(self, context, *, output, deadline):
        checkpoint = context['checkpoint']
        source = Path(context['checkpoint_root']) / checkpoint['artifacts']['workspace']['path']
        shutil.copytree(source, output / 'workspace')
        thread_id = 'fixture-child-' + context['arm']
        save(output / 'fork.json', {'method': 'thread/fork',
             'request': {'threadId': checkpoint['native_parent_thread_id']},
             'response': {'thread': {'id': thread_id}, 'model': 'fixture-reader', 'modelProvider': 'fixture'}})
        self.forks.append((checkpoint['native_parent_thread_id'], thread_id, str(output / 'workspace')))
        return self.wrap({'native_parent_thread_id': checkpoint['native_parent_thread_id'],
                          'thread_id': thread_id, 'workspace_path': 'workspace', 'fork_response_path': 'fork.json'})

    def build_packet(self, context, *, output, deadline):
        cp, arm = context['checkpoint'], context['arm']
        return self.wrap({'packet': {'evidence': 'fixture-only'}, 'checkpoint_sha256': cp['checkpoint_sha256'],
            'source_archive_sha256': cp['source_archive_sha256'], 'original_request_sha256': cp['original_request_sha256'],
            'shared_reader_config_sha256': cp['shared_reader_config_sha256'],
            'extraction_sha256': cp['extraction_sha256'] if arm in 'CD' else None,
            'd_prime_sha256': cp['d_prime_sha256'] if arm == 'D' else None})

    def continue_reader(self, context, *, output, deadline):
        self.reader_inputs.append((context['arm'], context['packet'], context['original_request']))
        (output / 'final.txt').write_text('Fixture answer, not a model observation.\n')
        if self.fail_reader:
            raise RuntimeError('fixture_reader_disconnected')
        uid = 'fixture-model-' + context['arm']
        usage = [{'event': 'usage', 'usage_id': uid, 'measurement_id': uid, 'operation_id': uid,
                  'component': 'model', 'counter_kind': 'delta', 'values':
                  {'input_tokens': 10, 'cached_input_tokens': 0, 'output_tokens': 2}, 'source_ref': 'final.txt'},
                 {'event': 'component_end', 'component': 'model', 'coverage': 'measured',
                  'usage_ids': [uid], 'reason': 'fixture-only', 'evidence_ref': 'final.txt'}]
        return self.wrap({'result': {'status': 'completed', 'host_version': 'fixture-host',
            'model_version': 'fixture-reader', 'trace_ref': 'final.txt'},
            'budget_usage': {'model_input_tokens': 10, 'model_output_tokens': 2,
             'tool_calls': 65 if self.excess_tools else 0, 'source_open_calls': 0, 'source_open_bytes': 0}}, usage)


class NativeReceiptTests(unittest.TestCase):
    def test_saved_native_compaction_requires_completed_item_and_turn(self):
        validate = load_api('validate_native_compaction')
        summary = json.loads((RECORDED / 'summary.json').read_text())
        shared = summary['shared_prefix']
        kwargs = {'parent_thread_id': shared['parent_thread_id'], 'turn_id': shared['compaction']['turnId'],
                  'item_id': shared['compaction']['itemId']}
        events = RECORDED / 'main-host/events.jsonl'
        checked = validate(events, **kwargs)
        self.assertEqual(checked['native_capture_sha256'], sha(events))
        self.assertFalse(checked['authenticity_attested'])
        with tempfile.TemporaryDirectory() as folder:
            incomplete = Path(folder) / 'events.jsonl'
            rows = [json.loads(row) for row in events.read_text().splitlines()]
            incomplete.write_text(''.join(json.dumps(row) + '\n' for row in rows if not
                (row.get('event') == 'turn/completed' and row.get('turnId') == kwargs['turn_id'])))
            with self.assertRaisesRegex(ValueError, 'compaction'):
                validate(incomplete, **kwargs)

    def test_summary_alone_and_wrong_thread_do_not_establish_native_receipt(self):
        validate = load_api('validate_native_compaction')
        for file in ('summary.json', 'main-host/events.jsonl'):
            with self.subTest(file=file), self.assertRaises(ValueError):
                validate(RECORDED / file, parent_thread_id='different-task-parent', turn_id='turn', item_id='item')


class PairedRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.controller = FixtureController()
        self.backend = FixtureBackend()
        receipt = API['create_relocation_receipt'](PLAN, PACKAGES, AUTH)
        row = receipt['tasks'][0]
        self.task = {key: row[key] for key in ('task_id', 'project_id', 'public_path', 'public_sha256', 'taskpack_public_sha256')}
        self.task.update(original_request_sha256=sha(PACKAGES[0] / 'public/request.txt'), shared_reader_config_sha256='1' * 64)

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self):
        return load_api('prepare_block')(self.task, 1, self.backend, self.controller, self.root / 'block', execution_mode='contract_test')

    def test_four_arm_pipeline_forks_one_parent_and_retains_real_abi_files(self):
        block = self.prepare()
        checkpoint = self.root / 'block/checkpoint.json'
        outcomes = {}
        for arm in 'ABCD':
            output = self.root / ('run-' + arm)
            outcomes[arm] = load_api('run_unit')(checkpoint, arm, 'fixture-' + arm, output,
                self.backend, self.controller, execution_mode='contract_test')
            actual, error = API['EXPERIMENT']['result_metadata'](output)
            self.assertIsNone(error)
            self.assertEqual(actual['status'], 'completed')
            self.assertTrue((output / actual['trace_ref']).is_file())
            usage = [json.loads(row) for row in (output / 'usage.jsonl').read_text().splitlines()]
            self.assertEqual([r['values']['input_tokens'] for r in usage if r['event'] == 'usage'], [10])
            self.assertTrue(all((output / r.get('source_ref', r.get('evidence_ref'))).is_file() for r in usage))
        self.assertEqual(len({row[0] for row in self.backend.forks}), 1)
        self.assertEqual(len({row[1] for row in self.backend.forks}), 4)
        self.assertEqual(len({row[2] for row in self.backend.forks}), 4)
        self.assertIsNone(next(packet for arm, packet, _ in self.backend.reader_inputs if arm == 'A'))
        self.assertEqual(len({request for _, _, request in self.backend.reader_inputs}), 1)
        self.assertFalse(block['scientific_ready'])
        self.assertTrue(all(entry[1]['actual_added_cost_cny'] is None for entry in self.controller.finished))

    def test_native_admission_denial_never_launches_parent(self):
        self.controller.deny = True
        outcome = self.prepare()
        self.assertEqual(outcome['status'], 'capture_incomplete')
        self.assertFalse(hasattr(self.backend, 'parent'))
        self.assertFalse((self.root / 'block/checkpoint.json').exists())

    def test_failed_backend_known_usage_is_retained_before_terminal_failure(self):
        def fail(context, *, output, deadline):
            save(output / 'observed.json', {'fixture_only': True, 'input_tokens': 3, 'output_tokens': 2})
            raise RuntimeError('fixture interruption after observed request')
        def recover(context, *, output):
            return [{'event': 'usage', 'usage_id': 'fixture-known', 'measurement_id': 'fixture-known',
                     'operation_id': 'fixture-request', 'component': 'prelude', 'counter_kind': 'delta',
                     'values': {'input_tokens': 3, 'cached_input_tokens': 0, 'output_tokens': 2},
                     'source_ref': 'observed.json'},
                    {'event': 'component_end', 'component': 'prelude', 'coverage': 'incomplete',
                     'usage_ids': ['fixture-known'], 'reason': 'fixture_failed_after_known_request', 'evidence_ref': 'observed.json'}]
        self.backend.capture_parent = fail
        self.backend.capture_failure_usage = recover
        result = self.prepare()
        self.assertEqual(result['status'], 'capture_incomplete')
        rows = [json.loads(line) for line in (self.root / 'block/usage.jsonl').read_text().splitlines()]
        self.assertEqual(rows[0]['values']['input_tokens'], 3)
        self.assertEqual(rows[-1]['coverage'], 'incomplete')
        self.assertFalse((self.root / 'block/checkpoint.json').exists())

    def test_fixture_backend_cannot_be_used_as_a_live_native_host(self):
        with self.assertRaisesRegex(ValueError, 'evidence_origin'):
            load_api('prepare_block')(self.task, 1, self.backend, self.controller, self.root / 'block')
        self.assertEqual(self.controller.scopes, [])

    def test_parent_drift_blocks_completed_method_and_replay(self):
        self.prepare()
        self.backend.parent_drift = True
        checkpoint = self.root / 'block/checkpoint.json'
        outcome = load_api('run_unit')(checkpoint, 'A', 'fixture-A', self.root / 'run-A',
            self.backend, self.controller, execution_mode='contract_test')
        self.assertEqual(outcome['status'], 'capture_incomplete')
        with self.assertRaisesRegex(ValueError, 'already_reserved'):
            API['run_unit'](checkpoint, 'A', 'another-A', self.root / 'another-A',
                self.backend, self.controller, execution_mode='contract_test')

    def test_interruption_preserves_partial_trace_and_unknown_cost(self):
        self.prepare(); self.backend.fail_reader = True
        outcome = load_api('run_unit')(self.root / 'block/checkpoint.json', 'D', 'fixture-D', self.root / 'run-D',
            self.backend, self.controller, execution_mode='contract_test')
        self.assertEqual(outcome['status'], 'capture_incomplete')
        self.assertEqual(len(list((self.root / 'run-D').rglob('final.txt'))), 1)
        self.assertIsNone(self.controller.finished[-1][1]['actual_added_cost_cny'])
        journal = API['EXPERIMENT']['read_ledger'](self.root / 'run-D/operations.jsonl')
        started = [r for r in journal if r['event'] == 'operation_started' and r['operation'] == 'continue_reader']
        completed = [r for r in journal if r['event'] == 'operation_completed' and r['operation'] == 'continue_reader']
        self.assertEqual(len(started), 1)
        self.assertEqual(completed, [])

    def test_tool_limit_excess_is_retained_as_budget_exhausted(self):
        self.prepare(); self.backend.excess_tools = True
        outcome = load_api('run_unit')(self.root / 'block/checkpoint.json', 'A', 'fixture-A', self.root / 'run-A',
            self.backend, self.controller, execution_mode='contract_test')
        self.assertEqual(outcome['status'], 'budget_exhausted')
        self.assertTrue((self.root / 'run-A/usage.jsonl').read_text())

    def test_recorded_other_scenario_cannot_be_imported_as_authorized_source_task(self):
        with self.assertRaises(ValueError):
            load_api('import_checkpoint')(RECORDED / 'summary.json', self.task, 1, self.root / 'imported')

    def test_checkpoint_identity_and_full_artifact_seal_are_distinct(self):
        self.prepare()
        checkpoint = json.loads((self.root / 'block/checkpoint.json').read_text())
        keys = ('task_id', 'replicate', 'public_sha256', 'workspace_snapshot_sha256', 'native_parent_thread_id',
                'native_capture_sha256', 'native_compaction_item_id', 'source_archive_sha256',
                'shared_reader_config_sha256', 'original_request_sha256')
        expected = hashlib.sha256(json.dumps({k: checkpoint[k] for k in keys}, sort_keys=True,
            ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(checkpoint['checkpoint_sha256'], expected)
        self.assertNotEqual(checkpoint['sealed_checkpoint_sha256'], expected)
        self.assertEqual(load_api('load_checkpoint')(self.root / 'block/checkpoint.json')['checkpoint_sha256'], expected)

    def test_operations_are_durable_before_backend_calls_and_bad_admission_stops_call(self):
        original = self.backend.capture_parent
        def inspect_before(context, *, output, deadline):
            records = API['EXPERIMENT']['read_ledger'](output.parents[1] / 'operations.jsonl')
            self.assertEqual(records[-2]['event'], 'operation_started')
            self.assertEqual(records[-1]['event'], 'operation_admitted')
            self.assertTrue((output / 'admission.json').is_file())
            return original(context, output=output, deadline=deadline)
        self.backend.capture_parent = inspect_before
        self.assertEqual(self.prepare()['status'], 'completed')
        old = self.controller.before_operation
        def wrong_request(intent):
            receipt = old(intent); receipt['request_sha256'] = '0' * 64
            return receipt
        self.controller.before_operation = wrong_request
        outcome = API['run_unit'](self.root / 'block/checkpoint.json', 'A', 'fixture-A', self.root / 'run-A',
            self.backend, self.controller, execution_mode='contract_test')
        self.assertEqual(outcome['status'], 'capture_incomplete')
        self.assertEqual(self.backend.forks, [])

    def test_unrelated_recorded_native_prelude_cannot_be_relabelled(self):
        original = self.backend.capture_parent
        def unrelated(context, *, output, deadline):
            response = original(context, output=output, deadline=deadline)
            shutil.copyfile(RECORDED / 'main-host/events.jsonl', output / 'events.jsonl')
            return response
        self.backend.capture_parent = unrelated
        self.assertEqual(self.prepare()['status'], 'capture_incomplete')
        self.assertFalse((self.root / 'block/checkpoint.json').exists())

    def test_compaction_capture_must_preserve_admitted_prelude_prefix(self):
        original = self.backend.compact_parent
        def discard_prefix(context, *, output, deadline):
            response = original(context, output=output, deadline=deadline)
            rows = (output / 'events.jsonl').read_text().splitlines()
            (output / 'events.jsonl').write_text('\n'.join(rows[-4:]) + '\n')
            return response
        self.backend.compact_parent = discard_prefix
        self.assertEqual(self.prepare()['status'], 'capture_incomplete')

    def test_checkpoint_copy_keeps_first_attempt_reservations(self):
        self.prepare()
        API['run_unit'](self.root / 'block/checkpoint.json', 'A', 'fixture-A', self.root / 'run-A',
            self.backend, self.controller, execution_mode='contract_test')
        imported = load_api('import_checkpoint')(self.root / 'block/checkpoint.json', self.task, 1, self.root / 'imported')
        self.assertTrue(imported['copied_attempt_registry'])
        with self.assertRaisesRegex(ValueError, 'already_reserved'):
            API['run_unit'](self.root / 'imported/checkpoint.json', 'A', 'retry-A', self.root / 'retry-A',
                self.backend, self.controller, execution_mode='contract_test')

    def test_unreferenced_checkpoint_sidecar_cannot_follow_an_external_symlink(self):
        self.prepare()
        private = self.root / 'outside'; private.mkdir()
        (private / 'only-fixture.txt').write_text('This is not an input artifact.')
        sidecar = self.root / 'block/sidecar'; sidecar.mkdir()
        (sidecar / 'external').symlink_to(private, target_is_directory=True)
        with self.assertRaises(ValueError):
            API['import_checkpoint'](self.root / 'block/checkpoint.json', self.task, 1, self.root / 'imported')
        self.assertFalse((self.root / 'imported/sidecar/external/only-fixture.txt').exists())

    def test_run_paired_block_preserves_explicit_order_and_four_scopes(self):
        result = load_api('run_paired_block')(self.task, 1, self.backend, self.controller, self.root / 'paired',
            order=('D', 'A', 'C', 'B'), execution_mode='contract_test')
        self.assertEqual(list(result['arms']), ['D', 'A', 'C', 'B'])
        self.assertEqual([intent['kind'] for intent in self.controller.scopes], ['native', 'method', 'method', 'method', 'method'])
        self.assertTrue(all(result['arms'][arm]['status'] == 'completed' for arm in 'ABCD'))

    def test_unconfirmed_terminal_cannot_publish_or_import_candidate_checkpoint(self):
        def failed_finish(intent, result):
            raise RuntimeError('fixture_finish_unknown')
        self.controller.finish_scope = failed_finish
        outcome = self.prepare()
        self.assertEqual(outcome['status'], 'capture_incomplete')
        self.assertFalse((self.root / 'block/checkpoint.json').exists())
        with self.assertRaisesRegex(ValueError, 'checkpoint'):
            API['load_checkpoint'](self.root / 'block/checkpoint-candidate.json')

    def test_malformed_usage_retains_failure_receipt_without_inventing_counters(self):
        self.prepare()
        original = self.backend.continue_reader
        def malformed(context, *, output, deadline):
            response = original(context, output=output, deadline=deadline)
            response['usage_rows'][1]['usage_ids'] = None
            return response
        self.backend.continue_reader = malformed
        outcome = API['run_unit'](self.root / 'block/checkpoint.json', 'A', 'fixture-A', self.root / 'run-A',
            self.backend, self.controller, execution_mode='contract_test')
        self.assertEqual(outcome['status'], 'capture_incomplete')
        usage = [json.loads(row) for row in (self.root / 'run-A/usage.jsonl').read_text().splitlines()]
        self.assertEqual(len(usage), 1)
        self.assertEqual(usage[0]['values']['input_tokens'], 10)


class RelocationTests(unittest.TestCase):
    def function(self, name):
        self.assertTrue(callable(API.get(name)), name + ' must implement the runtime contract')
        return API[name]

    def test_relocation_keeps_authorized_plan_bytes_and_maps_only_public_locations(self):
        original = PLAN.read_bytes(), AUTH.read_bytes()
        receipt = self.function('create_relocation_receipt')(PLAN, PACKAGES, AUTH)
        admitted = self.function('admit_relocation')(receipt, PLAN, PACKAGES, AUTH)
        self.assertEqual((PLAN.read_bytes(), AUTH.read_bytes()), original)
        self.assertEqual(admitted['planned_units'], 16)
        self.assertEqual(admitted['native_attempts_created'], 0)
        self.assertEqual(admitted['method_attempts_reserved'], 0)
        self.assertEqual(set(row['task_id'] for row in admitted['tasks']), {'w-101', 'w-102'})
        self.assertEqual(admitted['tasks'][0]['public_path'], str(PACKAGES[0] / 'public'))
        self.assertFalse(admitted['scientific_ready'])

    def test_relocation_receipt_cannot_change_an_approved_public_digest(self):
        receipt = self.function('create_relocation_receipt')(PLAN, PACKAGES, AUTH)
        receipt['tasks'][0]['public_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'relocation'):
            self.function('admit_relocation')(receipt, PLAN, PACKAGES, AUTH)

    def test_relocation_cannot_hide_nonpath_changes_to_original_plan(self):
        self.function('create_relocation_receipt')
        value = json.loads(PLAN.read_text())
        value['experiment_spec_fragment']['arms'] = ['A', 'C', 'D']
        with tempfile.TemporaryDirectory() as folder:
            changed = Path(folder) / 'plan.json'
            changed.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                API['create_relocation_receipt'](changed, PACKAGES, AUTH)


if __name__ == '__main__':
    unittest.main()
