"""Actual in-process dispatcher seam, with explicitly nonresearch backend fixtures."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/paper1'))
import paired_dispatch as dispatch
import paired_runtime as paired
import experiment
import test_paper1_paired_runtime as runtime_fixtures
import test_paper1_experiment as experiment_fixtures


class PairedDispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.controller, self.backend = runtime_fixtures.FixtureController(), runtime_fixtures.FixtureBackend()
        relocation = paired.create_relocation_receipt(runtime_fixtures.PLAN, runtime_fixtures.PACKAGES, runtime_fixtures.AUTH)
        row = relocation['tasks'][0]
        self.task = {k: row[k] for k in ('task_id', 'project_id', 'public_path', 'public_sha256', 'taskpack_public_sha256')}
        self.task.update(original_request_sha256=paired.file_sha(Path(self.task['public_path']) / 'request.txt'),
                         shared_reader_config_sha256='1' * 64)
        result = paired.prepare_block(self.task, 1, self.backend, self.controller, self.root / 'checkpoint', execution_mode='contract_test')
        self.assertEqual(result['status'], 'completed')
        self.binding = dispatch.create_binding(self.root / 'bound-runner')
        measurement = experiment_fixtures.ExperimentTests().measurement()
        spec = {'schema_version': 1, 'study_phase': 'development',
            'tasks': [{'task_id': self.task['task_id'], 'project_id': self.task['project_id'],
                       'public_by_replicate': {'1': self.task['public_path']}}],
            'arms': ['A', 'C', 'D'], 'replicates': 1, 'seed': 7,
            'runner': self.binding['runner'], 'env_allowlist': ['PATH'],
            'budgets': {'max_runs': 3, 'max_wall_seconds': 60, 'per_run_seconds': 20}, 'measurement': measurement}
        (self.root / 'spec.json').write_text(json.dumps(spec))
        experiment.freeze_study(self.root / 'spec.json', self.root / 'frozen')
        self.launcher = dispatch.PairedLauncher(plan=self.root / 'frozen', state=self.root / 'state',
            checkpoints={(self.task['task_id'], 1): self.root / 'checkpoint/checkpoint.json'},
            backend=self.backend, controller=self.controller, execution_mode='contract_test')

    def test_one_existing_backend_runs_each_scheduled_unit_and_keeps_original_seals(self):
        result = experiment.dispatch(self.root / 'frozen', self.root / 'state', run=True, launcher=self.launcher)
        self.assertEqual(result['launcher_invocations'], 3)
        self.assertEqual(result['external_processes_started'], 0)
        self.assertEqual(len(self.backend.forks), 3)
        rows = experiment.read_ledger(self.root / 'state/run-ledger.jsonl')
        started = [r for r in rows if r['event'] == 'run_started']
        finished = [r for r in rows if r['event'] == 'run_finished']
        self.assertEqual(len(started), 3)
        self.assertEqual(len(finished), 3)
        self.assertTrue(all(r['status'] == 'completed' for r in finished))
        frozen = experiment.load_frozen(self.root / 'frozen')
        _, attempts, terminals = experiment.state_snapshot(frozen, rows)
        self.assertEqual(len(experiment.sealed_score_rows(frozen, self.root / 'state', attempts, terminals)), 3)
        again = experiment.dispatch(self.root / 'frozen', self.root / 'state', run=True, launcher=self.launcher)
        self.assertEqual(again['launcher_invocations'], 0)
        self.assertEqual(len(self.backend.forks), 3)

    def test_default_dispatch_preflight_creates_no_attempts(self):
        result = experiment.dispatch(self.root / 'frozen', self.root / 'state', launcher=self.launcher)
        self.assertEqual(result['model_requests'], 0)
        self.assertFalse((self.root / 'state').exists())
        self.assertEqual(len(self.backend.forks), 0)

    def test_core_entrypoint_is_in_actual_implementation_binding(self):
        binding = dispatch.load_binding(self.binding['runner'])
        self.assertIn('packages/memex-core/index.js', binding['sources'])
        changed = copy.deepcopy(binding['sources'])
        changed['packages/memex-core/index.js'] = '0' * 64
        with patch.object(dispatch, 'implementation_sources', return_value=changed):
            with self.assertRaisesRegex(ValueError, 'actual_runner_implementation_changed'):
                dispatch.load_binding(self.binding['runner'])

    def test_existing_study_rejects_changed_launcher_binding_before_new_attempt(self):
        experiment.dispatch(self.root / 'frozen', self.root / 'state', run=True, launcher=self.launcher)
        ledger = self.root / 'state/run-ledger.jsonl'; before = ledger.read_bytes()
        binding = copy.deepcopy(self.launcher.initial_binding)
        binding['checkpoint_bindings_sha256'] = '0' * 64
        with patch.object(self.launcher, 'validate_frozen', return_value=binding):
            with self.assertRaisesRegex(ValueError, 'launcher_binding_changed_within_study'):
                experiment.dispatch(self.root / 'frozen', self.root / 'state', run=True, launcher=self.launcher)
        self.assertEqual(ledger.read_bytes(), before)
        self.assertEqual(len(self.backend.forks), 3)

    def test_launcher_instance_locks_initial_checkpoint_identity(self):
        self.launcher.initial_binding['checkpoint_bindings_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'launcher_checkpoint_bindings_changed'):
            self.launcher.validate_frozen(self.launcher.frozen, self.root / 'state')

    def test_bound_wrapper_and_fixture_cannot_be_misrepresented_as_live_host(self):
        with self.assertRaisesRegex(ValueError, 'evidence_origin'):
            dispatch.PairedLauncher(plan=self.root / 'frozen', state=self.root / 'other-state',
                checkpoints={(self.task['task_id'], 1): self.root / 'checkpoint/checkpoint.json'},
                backend=self.backend, controller=self.controller)
        binding = Path(self.binding['runner'])
        binding.write_text(binding.read_text().replace('same_live_backend_and_evidence_process', 'summary_replay'))
        with self.assertRaisesRegex(ValueError, 'implementation_changed'):
            self.launcher.validate_frozen(self.launcher.frozen, self.root / 'state')

    def test_direct_unit_call_without_experiment_reservation_is_rejected(self):
        unit = self.launcher.frozen['schedule']['units'][0]; out = self.root / 'state/runs' / unit['run_id']
        args = [self.binding['runner'], '--public', unit['public'], '--arm', unit['key']['arm'], '--replicate', '1',
                '--run-id', unit['run_id'], '--output', str(out), '--timeout-seconds', '20']
        import io, os
        with self.assertRaisesRegex(ValueError, 'first_attempt_reservation_required'):
            self.launcher(args, cwd=out, env={'PATH': os.environ['PATH']}, timeout=20, stdout=io.BytesIO(), stderr=io.BytesIO())
        self.assertEqual(len(self.backend.forks), 0)

    def test_launcher_exception_is_sealed_as_incomplete_not_retried_or_success(self):
        self.backend.continue_reader = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('fixture interruption'))
        experiment.dispatch(self.root / 'frozen', self.root / 'state', run=True, launcher=self.launcher)
        rows = experiment.read_ledger(self.root / 'state/run-ledger.jsonl')
        finished = [r for r in rows if r['event'] == 'run_finished']
        self.assertEqual(len(finished), 3)
        self.assertTrue(all(r['status'] == 'capture_incomplete' for r in finished))
        self.assertTrue(all(r['usage_capture_complete'] is False for r in finished))
        with self.assertRaisesRegex(ValueError, 'launcher_binding_changed_within_study'):
            experiment.dispatch(self.root / 'frozen', self.root / 'state', run=True)


if __name__ == '__main__':
    unittest.main()
