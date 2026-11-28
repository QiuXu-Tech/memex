"""Independent diagnostic cash reservations, using temporary ledgers only."""
import importlib.util
import json
import multiprocessing
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('p1_existing_batch_fixture', ROOT / 'test/test_paper1_batch_limits.py')
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)
M = BASE.M


def binding(dispatch_id='diagnostic-dispatch-1'):
    return {'provider': 'deepseek', 'model': 'deepseek-flash',
            'endpoint': 'https://api.deepseek.com/chat/completions',
            'dispatch_id': dispatch_id, 'intent_sha256': 'a' * 64,
            'request_sha256': 'b' * 64, 'config_sha256': 'c' * 64}


def mixed_cash_worker(root, diagnostic, queue):
    root = Path(root)
    ledger = M.BatchLedger(root / M.AUTH_RELATIVE, repo_root=root)
    basis = json.loads((root / 'basis.json').read_text())
    basis['kind'] = 'priced_upper_bound'
    try:
        if diagnostic:
            ledger.reserve_diagnostic(attempt_id='d-concurrent', binding=binding(),
                                      upper_bound_cny='60.00', billing_basis=basis, run=True)
        else:
            ledger.reserve(kind='native', attempt_id='n-concurrent', upper_bound_cny='60.00',
                           billing_basis=basis, run=True)
        queue.put('reserved')
    except M.LimitError as exc:
        queue.put(str(exc))


class DiagnosticLimitsTests(unittest.TestCase):
    # Reuse the existing temporary public-source/authorization fixture; no real
    # ledger, service account, credential or network is touched by these tests.
    setUp = BASE.BatchLimitsTests.setUp
    save_auth = BASE.BatchLimitsTests.save_auth
    reserve_native = BASE.BatchLimitsTests.reserve

    def reserve_diagnostic(self, identifier='d1', amount='3.00', dispatch_id='diagnostic-dispatch-1', **kw):
        self.assertTrue(callable(getattr(self.ledger, 'reserve_diagnostic', None)),
                        'independent diagnostic cash reservation is not implemented')
        return self.ledger.reserve_diagnostic(attempt_id=identifier, binding=binding(dispatch_id),
                                             upper_bound_cny=amount,
                                             billing_basis={'kind': 'priced_upper_bound', 'evidence': self.evidence},
                                             **kw)

    def test_diagnostic_dry_run_does_not_create_state_or_allow_dispatch(self):
        result = self.reserve_diagnostic()
        self.assertTrue(result['dry_run'])
        self.assertFalse(result['dispatch_allowed'])
        self.assertTrue(result['reservation_would_fit'])
        self.assertEqual(result['proposed']['binding'], binding())
        self.assertEqual(result['proposed']['wall_seconds'], 30)
        self.assertFalse(self.ledger.state_dir.exists())

    def test_diagnostics_share_cash_with_both_original_attempt_kinds_without_using_their_quotas(self):
        self.reserve_native('n1', '70.00')
        self.ledger.reserve(kind='method', attempt_id='m1', unit='w-101:A:1',
                            upper_bound_cny='20.00',
                            billing_basis={'kind': 'priced_upper_bound', 'evidence': self.evidence}, run=True)
        result = self.reserve_diagnostic(run=True)['status']
        self.assertEqual(result['committed_cash_upper_bound'], '93.00')
        self.assertEqual(result['native_attempts_remaining'], 1)
        self.assertEqual(result['method_units_remaining'], 15)
        self.assertEqual(result['diagnostic_attempts_reserved'], 1)
        self.reserve_native('n2', '7.00')
        with self.assertRaisesRegex(M.LimitError, 'added_cash_budget_exhausted'):
            self.reserve_diagnostic('d2', '0.01', 'dispatch-2', run=True)
        with self.assertRaisesRegex(M.LimitError, 'native_attempt_budget_exhausted'):
            self.reserve_native('n3')
        with self.assertRaisesRegex(M.LimitError, 'method_unit_already_reserved'):
            self.ledger.reserve(kind='method', attempt_id='m2', unit='w-101:A:1',
                                upper_bound_cny='0.00', billing_basis=self.basis, run=True)

    def test_finished_unknown_diagnostic_holds_cash_and_cannot_reuse_dispatch_under_new_attempt_id(self):
        self.reserve_diagnostic(amount='100.00', run=True)
        result = self.ledger.finish('d1', status='failed')['status']
        self.assertIsNone(result['actual_added_cash_total'])
        self.assertEqual(result['committed_cash_upper_bound'], '100.00')
        self.assertEqual(result['attempts_with_unsettled_cost'], ['d1'])
        changed = binding()
        changed['request_sha256'] = 'd' * 64
        with self.assertRaisesRegex(M.LimitError, 'diagnostic_dispatch_already_reserved'):
            self.ledger.reserve_diagnostic(attempt_id='relabelled', binding=changed,
                                          upper_bound_cny='1.00',
                                          billing_basis={'kind': 'priced_upper_bound', 'evidence': self.evidence}, run=True)
        with self.assertRaisesRegex(M.LimitError, 'added_cash_budget_exhausted'):
            self.reserve_diagnostic('d2', '0.01', 'new-dispatch', run=True)

    def test_binding_is_exact_fixed_provider_and_hash_bound_before_any_state_is_created(self):
        self.assertTrue(callable(getattr(self.ledger, 'reserve_diagnostic', None)))
        mutations = [dict(provider='openai'), dict(model='deepseek-chat'),
                     dict(endpoint='https://other.invalid/chat/completions'),
                     dict(dispatch_id='sk-fixture-not-an-identifier'), dict(dispatch_id='bad\nheader'),
                     dict(intent_sha256='a' * 63), dict(request_sha256='B' * 64),
                     dict(config_sha256=None), dict(extra='not allowed')]
        for changes in mutations:
            with self.subTest(changes=changes):
                value = binding()
                value.update(changes)
                with self.assertRaises(M.LimitError):
                    self.ledger.reserve_diagnostic(attempt_id='d1', binding=value, upper_bound_cny='3.00',
                                                  billing_basis={'kind': 'priced_upper_bound', 'evidence': self.evidence}, run=True)
                self.assertFalse(self.ledger.state_dir.exists())

    def test_priced_evidence_is_required_and_zero_or_subscription_cannot_admit_paid_diagnostic(self):
        self.assertTrue(callable(getattr(self.ledger, 'reserve_diagnostic', None)))
        for amount, basis in [('0.00', {'kind': 'priced_upper_bound', 'evidence': self.evidence}),
                              ('3.00', self.basis),
                              ('3.00', {'kind': 'priced_upper_bound',
                                        'evidence': {'ref': self.evidence['ref'], 'sha256': '0' * 64}})]:
            with self.assertRaises(M.LimitError):
                self.ledger.reserve_diagnostic(attempt_id='d1', binding=binding(), upper_bound_cny=amount,
                                              billing_basis=basis, run=True)
            self.assertFalse(self.ledger.state_dir.exists())
        with self.assertRaisesRegex(M.LimitError, 'invalid_attempt_identity'):
            self.ledger.reserve(kind='diagnostic', attempt_id='d1', upper_bound_cny='3.00',
                                billing_basis={'kind': 'priced_upper_bound', 'evidence': self.evidence}, run=True)

    def test_provider_event_is_one_use_request_bound_and_expires_after_thirty_seconds(self):
        self.reserve_diagnostic(run=True)
        with self.assertRaisesRegex(M.LimitError, 'diagnostic_operation_binding_mismatch'):
            self.ledger.record_event('d1', 'provider_request', 'another-dispatch')
        with self.assertRaisesRegex(M.LimitError, 'unsupported_counted_operation'):
            self.ledger.record_event('d1', 'generation_start', 'diagnostic-dispatch-1')
        event = self.ledger.record_event('d1', 'provider_request', 'diagnostic-dispatch-1')
        self.assertTrue(event['dispatch_allowed'])
        self.assertGreater(event['remaining_wall_seconds'], 0)
        self.assertLessEqual(event['remaining_wall_seconds'], 30)
        with self.assertRaisesRegex(M.LimitError, 'operation_already_reserved'):
            self.ledger.record_event('d1', 'provider_request', 'diagnostic-dispatch-1')
        self.reserve_diagnostic('d2', dispatch_id='dispatch-2', run=True)
        started = self.ledger.status()['attempts']['d2']['reserved_at_unix_ns']
        with patch.object(M.time, 'time_ns', return_value=started + 30 * 10**9):
            with self.assertRaisesRegex(M.LimitError, 'attempt_wall_budget_exhausted'):
                self.ledger.record_event('d2', 'provider_request', 'dispatch-2')

    def test_actual_cost_settlement_releases_only_cash_and_overrun_stops_all_new_kinds(self):
        self.reserve_diagnostic(run=True)
        self.ledger.finish('d1', status='timeout')
        self.ledger.settle_cost('d1', actual_added_cost_cny='0.01', cost_evidence=self.evidence)
        status = self.ledger.status()
        self.assertEqual(status['remaining_cash_capacity'], '99.99')
        self.assertEqual(status['diagnostic_attempts_reserved'], 1)
        self.assertEqual(status['native_attempts_remaining'], 2)
        self.assertEqual(status['method_units_remaining'], 16)
        self.reserve_diagnostic('d2', '1.00', 'dispatch-2', run=True)
        self.ledger.finish('d2', status='failed', actual_added_cost_cny='1.01', cost_evidence=self.evidence)
        for action in (lambda: self.reserve_diagnostic('d3', dispatch_id='dispatch-3', run=True),
                       lambda: self.reserve_native('n1')):
            with self.assertRaisesRegex(M.LimitError, 'previous_budget_breach'):
                action()

    def test_real_historical_prefix_and_authorization_remain_byte_identical_after_diagnostic_append(self):
        # Copy the published history into a disposable root; do not mutate it.
        self.auth_path.write_bytes(BASE.REAL_AUTH.read_bytes())
        self.ledger = M.BatchLedger(self.auth_path, repo_root=self.root)
        self.ledger.state_dir.mkdir(parents=True)
        for name in ('events.jsonl', 'HEAD.json', 'ledger.lock'):
            shutil.copyfile(ROOT / M.LEDGER_RELATIVE / name, self.ledger.state_dir / name)
        original = self.ledger.journal.read_bytes()
        auth_before = self.auth_path.read_bytes()
        before = self.ledger.status()
        self.reserve_diagnostic(run=True)
        after = self.ledger.status()
        self.assertTrue(self.ledger.journal.read_bytes().startswith(original))
        self.assertEqual(self.auth_path.read_bytes(), auth_before)
        self.assertEqual(after['journal_events'], before['journal_events'] + 1)
        self.assertEqual(after['native_attempts_reserved'], 2)
        self.assertEqual(after['native_attempts_remaining'], 0)
        self.assertEqual(after['method_units_reserved'], 0)
        self.assertEqual(after['method_units_remaining'], 16)
        self.assertEqual(after['committed_cash_upper_bound'], '3.00')

    def test_concurrent_diagnostic_and_native_reservations_share_same_cash_lock(self):
        self.assertTrue(callable(getattr(self.ledger, 'reserve_diagnostic', None)))
        ctx = multiprocessing.get_context('fork')
        queue = ctx.Queue()
        processes = [ctx.Process(target=mixed_cash_worker, args=(str(self.root), diagnostic, queue))
                     for diagnostic in (False, True)]
        for process in processes:
            process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        self.assertEqual(sorted(queue.get(timeout=2) for _ in processes),
                         ['added_cash_budget_exhausted', 'reserved'])
        self.assertEqual(self.ledger.status()['committed_cash_upper_bound'], '60.00')

    def test_cli_reserve_diagnostic_and_bound_event_use_the_same_canonical_ledger(self):
        args = [sys.executable, '-B', str(ROOT / 'scripts/paper1/batch_limits.py'), '--repo-root', str(self.root)]
        (self.root / 'binding.json').write_text(json.dumps(binding()))
        (self.root / 'priced-basis.json').write_text(json.dumps({'kind': 'priced_upper_bound', 'evidence': self.evidence}))
        command = args + ['reserve-diagnostic', '--attempt-id', 'd1', '--binding', str(self.root / 'binding.json'),
                          '--upper-bound-cny', '3.00', '--billing-basis', str(self.root / 'priced-basis.json')]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(json.loads(result.stdout)['dispatch_allowed'])
        self.assertFalse(self.ledger.state_dir.exists())
        result = subprocess.run(command + ['--run'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['reservation']['data']['binding'], binding())
        result = subprocess.run(args + ['event', '--attempt-id', 'd1', '--kind', 'provider_request',
                                        '--operation-id', 'diagnostic-dispatch-1'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['dispatch_allowed'])
        self.assertEqual(self.ledger.status()['journal_events'], 2)


if __name__ == '__main__':
    unittest.main()
