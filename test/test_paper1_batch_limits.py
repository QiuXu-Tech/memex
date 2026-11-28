import copy
import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('p1_batch_limits_test', ROOT / 'scripts/paper1/batch_limits.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
REAL_AUTH = ROOT / M.AUTH_RELATIVE


def reserve_worker(root, identifier, queue, amount='0.00', die=False):
    root = Path(root)
    basis = json.loads((root / 'basis.json').read_text())
    if amount != '0.00':
        basis['kind'] = 'priced_upper_bound'
    try:
        ledger = M.BatchLedger(root / M.AUTH_RELATIVE, repo_root=root)
        ledger.reserve(kind='native', attempt_id=identifier, upper_bound_cny=amount, billing_basis=basis, run=True)
        if die:
            os._exit(7)
        queue.put('reserved')
    except M.LimitError as exc:
        queue.put(str(exc))


class BatchLimitsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.auth = copy.deepcopy(json.loads(REAL_AUTH.read_text()))
        plan = {'schema_version': 1, 'units': []}
        for task in ('w-101', 'w-102'):
            relative = next(u['public_relative_path'] for u in self.auth['units'] if u['task_id'] == task)
            public = self.root / relative
            public.mkdir(parents=True)
            (public / 'request.txt').write_text('Public source request for ' + task)
            digest = M.public_digest(public)
            for unit in self.auth['units']:
                if unit['task_id'] == task:
                    unit['public_sha256'] = digest
                    plan['units'].append({k: v for k, v in unit.items() if k != 'public_relative_path'})
        plan_path = self.root / self.auth['source_plan']['relative_path']
        plan_path.write_text(json.dumps(plan))
        budget_path = self.root / self.auth['source_plan']['shared_budget_relative_path']
        budget_path.write_text('{"frozen":false}')
        self.auth['source_plan']['sha256'] = hashlib.sha256(plan_path.read_bytes()).hexdigest()
        self.auth['source_plan']['shared_budget_sha256'] = hashlib.sha256(budget_path.read_bytes()).hexdigest()
        self.auth_path = self.root / M.AUTH_RELATIVE
        self.auth_path.parent.mkdir(parents=True, exist_ok=True)
        self.save_auth()
        evidence = self.root / 'billing-observation.json'
        evidence.write_text('{"fixture":"no live provider was called"}')
        self.evidence = {'ref': 'billing-observation.json', 'sha256': hashlib.sha256(evidence.read_bytes()).hexdigest()}
        self.basis = {'kind': 'included_subscription', 'evidence': self.evidence}
        (self.root / 'basis.json').write_text(json.dumps(self.basis))
        self.ledger = M.BatchLedger(self.auth_path, repo_root=self.root)

    def save_auth(self):
        self.auth_path.write_text(json.dumps(self.auth))

    def reserve(self, identifier='n1', amount='0.00', **kw):
        basis = self.basis if amount == '0.00' else {'kind': 'priced_upper_bound', 'evidence': self.evidence}
        return self.ledger.reserve(kind='native', attempt_id=identifier, upper_bound_cny=amount,
                                   billing_basis=basis, run=True, **kw)

    def test_status_and_default_dryrun_create_no_state(self):
        self.assertEqual(self.ledger.status()['native_attempts_remaining'], 2)
        result = self.ledger.reserve(kind='native', attempt_id='n1', upper_bound_cny='0.00', billing_basis=self.basis)
        self.assertFalse(result['dispatch_allowed'])
        self.assertTrue(result['dry_run'])
        self.assertFalse(self.ledger.state_dir.exists())

    def test_same_batch_cannot_select_new_ledger_to_reset_limits(self):
        with self.assertRaisesRegex(M.LimitError, 'one_canonical_ledger'):
            M.BatchLedger(self.auth_path, self.root / 'another-ledger', self.root)

    def test_limits_and_unaccepted_state_cannot_be_widened(self):
        for update in ({'native_attempts': 3}, {'added_cash_total': '1000.00'}):
            value = copy.deepcopy(self.auth)
            value['limits'].update(update)
            with self.assertRaisesRegex(M.LimitError, 'approved_limits_mismatch'):
                M.validate_authorization(value)
        value = copy.deepcopy(self.auth)
        value['scientific_state']['frozen'] = True
        with self.assertRaisesRegex(M.LimitError, 'not_scientific_acceptance'):
            M.validate_authorization(value)

    def test_authorization_mutation_after_start_is_rejected(self):
        self.reserve()
        self.auth['allowed_scope'].append('changed wording')
        self.save_auth()
        with self.assertRaisesRegex(M.LimitError, 'authorization_changed'):
            self.ledger.status()
        other = M.BatchLedger(self.auth_path, repo_root=self.root)
        with self.assertRaisesRegex(M.LimitError, 'journal_integrity'):
            other.status()

    def test_two_native_attempts_include_failures_and_no_retry_relabel(self):
        self.reserve('n1')
        self.ledger.finish('n1', status='host_blocked')
        self.reserve('n2')
        self.ledger.finish('n2', status='failed')
        with self.assertRaisesRegex(M.LimitError, 'native_attempt_budget'):
            self.reserve('n3')
        with self.assertRaisesRegex(M.LimitError, 'attempt_already_reserved'):
            self.reserve('n1')
        self.assertEqual(self.ledger.status()['native_attempts_remaining'], 0)

    def test_native_operation_reservations_enforce_counts_and_replay(self):
        self.reserve()
        for i in range(5):
            self.ledger.record_event('n1', 'generation_start', f'g{i}')
        with self.assertRaisesRegex(M.LimitError, 'operation_budget_exhausted'):
            self.ledger.record_event('n1', 'generation_start', 'g5')
        with self.assertRaisesRegex(M.LimitError, 'already_reserved'):
            self.ledger.record_event('n1', 'generation_start', 'g0')
        for i in range(2):
            self.ledger.record_event('n1', 'compaction_start', f'c{i}')
        with self.assertRaisesRegex(M.LimitError, 'operation_budget_exhausted'):
            self.ledger.record_event('n1', 'compaction_start', 'c2')

    def test_wall_deadline_and_clock_rollback_block_operations(self):
        self.reserve()
        started = self.ledger.status()['attempts']['n1']['reserved_at_unix_ns']
        for now in (started - 1, started + 600 * 10**9):
            with patch.object(M.time, 'time_ns', return_value=now):
                with self.assertRaisesRegex(M.LimitError, 'wall_budget'):
                    self.ledger.record_event('n1', 'generation_start', 'expired')

    def test_known_unit_requires_fixed_plan_and_actual_public_bytes(self):
        result = self.ledger.reserve(kind='method', attempt_id='m1', unit='w-101:A:1',
                                     upper_bound_cny='0.00', billing_basis=self.basis, run=True)
        self.assertTrue(result['dispatch_allowed'])
        with self.assertRaisesRegex(M.LimitError, 'method_unit_already_reserved'):
            self.ledger.reserve(kind='method', attempt_id='m2', unit='w-101:A:1',
                                upper_bound_cny='0.00', billing_basis=self.basis, run=True)
        with self.assertRaisesRegex(M.LimitError, 'outside_approval'):
            self.ledger.reserve(kind='method', attempt_id='m3', unit='w-101:T:1',
                                upper_bound_cny='0.00', billing_basis=self.basis, run=True)
        public = self.root / self.auth['units'][0]['public_relative_path']
        (public / 'request.txt').write_text('Mutated inputs')
        with self.assertRaisesRegex(M.LimitError, 'public_snapshot_drift'):
            self.ledger.reserve(kind='method', attempt_id='m4', unit='w-101:B:1',
                                upper_bound_cny='0.00', billing_basis=self.basis, run=True)

    def test_plan_drift_does_not_reserve_a_run(self):
        (self.root / M.PLAN_RELATIVE).write_text('{"different":"plan"}')
        with self.assertRaisesRegex(M.LimitError, 'source_plan_drift'):
            self.ledger.reserve(kind='method', attempt_id='m1', unit='w-101:A:1',
                                upper_bound_cny='0.00', billing_basis=self.basis, run=True)
        self.assertFalse(self.ledger.state_dir.exists())

    def test_unknown_cost_remains_reserved_after_failure(self):
        self.reserve('n1', '75.00')
        result = self.ledger.finish('n1', status='failed')
        self.assertIsNone(result['status']['actual_added_cash_total'])
        self.assertEqual(result['status']['committed_cash_upper_bound'], '75.00')
        with self.assertRaisesRegex(M.LimitError, 'cash_budget_exhausted'):
            self.reserve('n2', '25.01')
        self.reserve('n2', '25.00')
        self.assertEqual(self.ledger.status()['committed_cash_upper_bound'], '100.00')

    def test_verified_known_cost_releases_money_but_not_attempt_count(self):
        self.reserve('n1', '75.00')
        self.ledger.finish('n1', status='capture_incomplete')
        self.ledger.settle_cost('n1', actual_added_cost_cny='5.00', cost_evidence=self.evidence)
        self.assertEqual(self.ledger.status()['remaining_cash_capacity'], '95.00')
        self.assertEqual(self.ledger.status()['native_attempts_remaining'], 1)
        with self.assertRaisesRegex(M.LimitError, 'cost_already_settled'):
            self.ledger.settle_cost('n1', actual_added_cost_cny='0.00', cost_evidence=self.evidence)

    def test_actual_overrun_is_preserved_and_stops_further_dispatch(self):
        self.reserve('n1', '10.00')
        result = self.ledger.finish('n1', status='failed', actual_added_cost_cny='12.00', cost_evidence=self.evidence)
        self.assertTrue(result['status']['budget_breach_observed'])
        self.assertEqual(result['status']['actual_added_cash_total'], '12.00')
        with self.assertRaisesRegex(M.LimitError, 'previous_budget_breach'):
            self.reserve('n2')

    def test_unknown_price_and_false_zero_are_not_paid_reservations(self):
        for amount in (None, 0, -1, 'NaN', '-1.00', '0.001'):
            with self.assertRaises(M.LimitError):
                self.ledger.reserve(kind='native', attempt_id='n1', upper_bound_cny=amount, billing_basis=self.basis)
        with self.assertRaisesRegex(M.LimitError, 'billing_basis_amount_mismatch'):
            self.ledger.reserve(kind='native', attempt_id='n1', upper_bound_cny='0.00',
                                billing_basis={'kind': 'priced_upper_bound', 'evidence': self.evidence})
        with self.assertRaisesRegex(M.LimitError, 'run_must_be_boolean'):
            self.ledger.reserve(kind='native', attempt_id='n1', upper_bound_cny='0.00', billing_basis=self.basis, run='yes')

    def test_evidence_binding_is_required_and_verified(self):
        wrong = copy.deepcopy(self.basis)
        wrong['evidence']['sha256'] = '0' * 64
        with self.assertRaisesRegex(M.LimitError, 'evidence_hash_mismatch'):
            self.ledger.reserve(kind='native', attempt_id='n1', upper_bound_cny='0.00', billing_basis=wrong)
        self.reserve('n1', '10.00')
        with self.assertRaisesRegex(M.LimitError, 'schema_fields'):
            self.ledger.finish('n1', status='failed', actual_added_cost_cny='0.00')
        self.assertIsNone(self.ledger.status()['actual_added_cash_total'])

    def test_partial_or_tampered_journal_never_resets_counts(self):
        self.reserve()
        original = self.ledger.journal.read_bytes()
        self.ledger.journal.write_bytes(original + b'{"partial":')
        with self.assertRaisesRegex(M.LimitError, 'partial_journal'):
            self.reserve('n2')
        self.ledger.journal.write_bytes(original.replace(b'"upper_bound_fen":0', b'"upper_bound_fen":1'))
        with self.assertRaisesRegex(M.LimitError, 'journal_integrity'):
            self.ledger.status()

    def test_deleted_truncated_and_valid_prefix_journal_fail_closed(self):
        self.reserve()
        first = self.ledger.journal.read_bytes()
        self.ledger.record_event('n1', 'generation_start', 'g1')
        full = self.ledger.journal.read_bytes()
        self.ledger.journal.write_bytes(first)
        with self.assertRaisesRegex(M.LimitError, 'journal_head_mismatch'):
            self.ledger.status()
        self.ledger.journal.write_bytes(b'')
        with self.assertRaisesRegex(M.LimitError, 'empty_journal'):
            self.ledger.status()
        self.ledger.journal.unlink()
        with self.assertRaisesRegex(M.LimitError, 'journal_missing'):
            self.reserve('n2')
        self.ledger.journal.write_bytes(full)
        self.assertEqual(self.ledger.status()['native_attempts_reserved'], 1)

    def test_operation_or_finish_without_reservation_creates_no_state(self):
        with self.assertRaisesRegex(M.LimitError, 'active_reservation_required'):
            self.ledger.record_event('none', 'generation_start', 'g1')
        with self.assertRaisesRegex(M.LimitError, 'reservation_required'):
            self.ledger.finish('none', status='failed')
        self.assertFalse(self.ledger.state_dir.exists())

    def test_symlink_state_and_public_inputs_fail_closed(self):
        outside = self.root / 'outside'
        outside.mkdir()
        self.ledger.state_dir.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(M.LimitError, 'symlink_forbidden'):
            self.reserve()

    def test_concurrent_controllers_cannot_exceed_native_limit(self):
        ctx = multiprocessing.get_context('fork')
        queue = ctx.Queue()
        processes = [ctx.Process(target=reserve_worker, args=(str(self.root), f'n{i}', queue)) for i in range(6)]
        for p in processes: p.start()
        for p in processes:
            p.join(10)
            self.assertEqual(p.exitcode, 0)
        results = [queue.get(timeout=2) for _ in processes]
        self.assertEqual(results.count('reserved'), 2, results)
        self.assertEqual(results.count('native_attempt_budget_exhausted'), 4, results)
        self.assertEqual(self.ledger.status()['native_attempts_reserved'], 2)

    def test_concurrent_paid_reservations_share_one_cash_limit(self):
        ctx = multiprocessing.get_context('fork')
        queue = ctx.Queue()
        processes = [ctx.Process(target=reserve_worker, args=(str(self.root), f'n{i}', queue, '60.00')) for i in range(2)]
        for p in processes: p.start()
        for p in processes:
            p.join(10)
            self.assertEqual(p.exitcode, 0)
        results = [queue.get(timeout=2) for _ in processes]
        self.assertEqual(sorted(results), ['added_cash_budget_exhausted', 'reserved'])
        self.assertEqual(self.ledger.status()['committed_cash_upper_bound'], '60.00')

    def test_process_death_after_reservation_preserves_count_and_money(self):
        ctx = multiprocessing.get_context('fork')
        queue = ctx.Queue()
        process = ctx.Process(target=reserve_worker, args=(str(self.root), 'crashed', queue, '90.00', True))
        process.start(); process.join(10)
        self.assertEqual(process.exitcode, 7)
        recovered = M.BatchLedger(self.auth_path, repo_root=self.root)
        self.assertEqual(recovered.status()['native_attempts_reserved'], 1)
        self.assertEqual(recovered.status()['committed_cash_upper_bound'], '90.00')
        self.assertEqual(recovered.status()['attempts']['crashed']['state'], 'reserved')
        with self.assertRaisesRegex(M.LimitError, 'attempt_already_reserved'):
            self.reserve('crashed', '90.00')

    def test_real_authorization_matches_exact_source_material_plan(self):
        actual = M.validate_authorization(json.loads(REAL_AUTH.read_text()))
        plan_path = ROOT / actual['source_plan']['relative_path']
        plan = json.loads(plan_path.read_text())
        self.assertEqual(hashlib.sha256(plan_path.read_bytes()).hexdigest(), actual['source_plan']['sha256'])
        stripped = [{k: v for k, v in u.items() if k != 'public_relative_path'} for u in actual['units']]
        self.assertEqual(stripped, plan['units'])
        self.assertEqual(len({M.unit_key(u) for u in actual['units']}), 16)

    def test_cli_status_is_read_only_and_has_no_dispatch(self):
        result = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/paper1/batch_limits.py'),
                                 '--repo-root', str(self.root), 'status'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertFalse(value['host_approval_attested'])
        self.assertFalse(value['scientific_ready'])
        self.assertFalse(self.ledger.state_dir.exists())


if __name__ == '__main__':
    unittest.main()
