"""Only temporary fixture ledgers: no real activation, provider or host calls."""
import copy
import hashlib
import importlib.util
import json
import multiprocessing
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


FIXTURE = module('p1_native_supplement_fixture', ROOT / 'test/test_paper1_batch_limits.py')
CONTROLLER = module('p1_native_supplement_controller_fixture', ROOT / 'test/test_paper1_runtime_controller.py')
M = FIXTURE.M


def activation_worker(root, sha, outcomes):
    try:
        ledger = M.BatchLedger(Path(root) / M.AUTH_RELATIVE, repo_root=Path(root))
        ledger.activate_native_supplement(expected_sha256=sha, run=True)
        outcomes.put('activated')
    except M.LimitError as error:
        outcomes.put(str(error))


class NativeSupplementTests(unittest.TestCase):
    save_auth = FIXTURE.BatchLimitsTests.save_auth
    reserve = FIXTURE.BatchLimitsTests.reserve

    def setUp(self):
        FIXTURE.BatchLimitsTests.setUp(self)
        binding = {'provider': 'deepseek', 'model': 'deepseek-flash',
            'endpoint': 'https://api.deepseek.com/chat/completions', 'dispatch_id': 'fixture-diagnostic-http',
            'intent_sha256': 'a' * 64, 'request_sha256': 'b' * 64, 'config_sha256': 'c' * 64}
        self.ledger.reserve_diagnostic(attempt_id='fixture-diagnostic', binding=binding,
            upper_bound_cny='3.00', billing_basis={'kind': 'priced_upper_bound', 'evidence': self.evidence}, run=True)
        self.ledger.record_event('fixture-diagnostic', 'provider_request', binding['dispatch_id'])
        self.ledger.finish('fixture-diagnostic', status='completed')
        for name, status in (('original-native-1', 'host_blocked'), ('original-native-2', 'failed')):
            self.reserve(name)
            self.ledger.finish(name, status=status)
        self.historical = self.ledger.journal.read_bytes()
        self.assertEqual(len(self.historical.splitlines()), 7)
        self.original_files = {path: (self.root / path).read_bytes() for path in
            (M.AUTH_RELATIVE, self.auth['source_plan']['relative_path'], self.auth['source_plan']['shared_budget_relative_path'])}
        grants = []
        for task in M.PROJECTS:
            approved = next(unit for unit in self.auth['units'] if unit['task_id'] == task)
            for replicate in (1, 2):
                grants.append({'scope_id': 'p1-native-' + M.digest({'fixture': True, 'task': task, 'replicate': replicate})[:24],
                    'task_id': task, 'project_id': M.PROJECTS[task], 'replicate': replicate,
                    'public_sha256': approved['public_sha256'], 'taskpack_public_sha256': approved['taskpack_public_sha256']})
        self.supplement = {'schema_version': 1, 'kind': 'p1-native-preparation-supplement',
            'supplement_id': M.NATIVE_SUPPLEMENT_ID, 'batch_id': M.BATCH_ID,
            'approval': {'date': '2026-11-29', 'timezone': 'Asia/Shanghai', 'user_quote': M.NATIVE_SUPPLEMENT_QUOTE},
            'authorization': {'relative_path': M.AUTH_RELATIVE, 'sha256': self.ledger.auth_sha256},
            'source_plan': copy.deepcopy(self.auth['source_plan']), 'ledger_relative_path': M.LEDGER_RELATIVE,
            'prior_journal': {'events': 7, 'head_sha256': self.ledger.status()['journal_head_sha256'],
                              'sha256': hashlib.sha256(self.historical).hexdigest()},
            'additional_native_attempts': 4, 'unchanged_limits': copy.deepcopy(self.auth['limits']),
            'native_scope_limits': {'wall_seconds': 600, **M.EVENT_LIMITS['native']}, 'grants': grants}
        self.supplement_path = self.root / M.NATIVE_SUPPLEMENT_RELATIVE
        self.supplement_sha = self.write_supplement(self.supplement)

    def write_supplement(self, value):
        self.supplement_path.write_text(M.canonical(value) + '\n')
        return hashlib.sha256(self.supplement_path.read_bytes()).hexdigest()

    def activate(self):
        return self.ledger.activate_native_supplement(expected_sha256=self.supplement_sha, run=True)

    @staticmethod
    def binding(grant):
        return {key: grant[key] for key in ('task_id', 'project_id', 'replicate', 'public_sha256')}

    def reserve_grant(self, ordinal=0, amount='3.20', *, run=True, **changes):
        grant = self.supplement['grants'][ordinal]
        args = {'kind': 'native', 'attempt_id': grant['scope_id'], 'upper_bound_cny': amount,
                'billing_basis': {'kind': 'priced_upper_bound', 'evidence': self.evidence},
                'native_binding': self.binding(grant), 'run': run}
        args.update(changes)
        return self.ledger.reserve(**args)

    def test_presence_and_read_only_activation_cannot_grant_permission(self):
        self.assertEqual(M.NATIVE_SUPPLEMENT_QUOTE, '确认追加\n真人如无必要尽可能由你代劳')
        self.assertEqual(self.ledger.status()['native_attempts_remaining'], 0)
        self.assertFalse(self.ledger.status()['native_supplement_active'])
        with self.assertRaisesRegex(M.LimitError, 'native_attempt_budget_exhausted'):
            self.reserve_grant()
        head = self.ledger.head_path.read_bytes()
        result = self.ledger.activate_native_supplement(expected_sha256=self.supplement_sha)
        self.assertTrue(result['activation_would_fit'])
        self.assertFalse(result['activation_performed'])
        self.assertFalse(result['dispatch_allowed'])
        self.assertEqual(self.ledger.journal.read_bytes(), self.historical)
        self.assertEqual(self.ledger.head_path.read_bytes(), head)

    def test_activation_cannot_bootstrap_a_new_ledger(self):
        # An activation is an append to the historical ledger, never a reset or
        # an initialization path. This second root is still a temporary fixture.
        other = self.root / 'unused-fixture-root'
        auth_path = other / M.AUTH_RELATIVE
        auth_path.parent.mkdir(parents=True)
        auth_path.write_bytes(self.auth_path.read_bytes())
        ledger = M.BatchLedger(auth_path, repo_root=other)
        with self.assertRaisesRegex(M.LimitError, 'requires_existing_journal'):
            ledger.activate_native_supplement(expected_sha256=self.supplement_sha, run=True)
        self.assertFalse(ledger.state_dir.exists())

    def test_activation_appends_one_event_preserving_original_bytes_and_limits(self):
        result = self.activate()
        self.assertEqual(result['event']['seq'], 8)
        self.assertEqual(result['event']['event'], M.NATIVE_SUPPLEMENT_EVENT)
        self.assertFalse(result['dispatch_allowed'])
        self.assertTrue(self.ledger.journal.read_bytes().startswith(self.historical))
        for path, before in self.original_files.items():
            self.assertEqual((self.root / path).read_bytes(), before)
        status = result['status']
        self.assertEqual(status['native_original_attempts_reserved'], 2)
        self.assertEqual(status['native_original_attempts_remaining'], 0)
        self.assertEqual(status['native_supplemental_attempts_remaining'], 4)
        self.assertEqual(status['native_attempts_remaining'], 4)
        self.assertEqual(status['method_units_remaining'], 16)
        self.assertEqual(status['added_cash_cap'], '100.00')
        self.assertEqual(status['committed_cash_upper_bound'], '3.00')
        self.assertIsNone(status['actual_added_cash_total'])

    def test_exact_four_grants_failures_count_and_cannot_relabel_or_replay(self):
        self.activate()
        for ordinal, terminal in enumerate(('failed', 'host_blocked', 'timeout', 'capture_incomplete')):
            self.reserve_grant(ordinal)
            self.ledger.finish(self.supplement['grants'][ordinal]['scope_id'], status=terminal)
        status = self.ledger.status()
        self.assertEqual(status['native_attempts_reserved'], 6)
        self.assertEqual(status['native_original_attempts_reserved'], 2)
        self.assertEqual(status['native_supplemental_attempts_reserved'], 4)
        self.assertEqual(status['native_attempts_remaining'], 0)
        self.assertEqual(status['committed_cash_upper_bound'], '15.80')
        with self.assertRaisesRegex(M.LimitError, 'attempt_already_reserved'):
            self.reserve_grant(0)
        with self.assertRaisesRegex(M.LimitError, 'outside_supplemental_grants'):
            self.reserve_grant(0, attempt_id='p1-native-' + 'f' * 24)
        with self.assertRaisesRegex(M.LimitError, 'native_attempt_budget_exhausted'):
            self.reserve('legacy-cannot-borrow')

    def test_grant_id_alone_and_cross_task_or_replicate_binding_are_rejected(self):
        self.activate()
        with self.assertRaisesRegex(M.LimitError, 'native_attempt_budget_exhausted'):
            self.reserve_grant(native_binding=None)
        for ordinal in (1, 2, 3):
            with self.subTest(ordinal=ordinal), self.assertRaisesRegex(M.LimitError, 'outside_supplemental_grants'):
                self.reserve_grant(native_binding=self.binding(self.supplement['grants'][ordinal]))
        changed = self.binding(self.supplement['grants'][0]); changed['public_sha256'] = 'f' * 64
        with self.assertRaisesRegex(M.LimitError, 'public_binding_mismatch'):
            self.reserve_grant(native_binding=changed)
        self.assertEqual(self.ledger.status()['journal_events'], 8)

    def test_dryrun_does_not_consume_grant_and_restart_does_not_reset_it(self):
        self.activate()
        self.assertTrue(self.reserve_grant(run=False)['reservation_would_fit'])
        self.assertEqual(self.ledger.status()['native_supplemental_attempts_remaining'], 4)
        self.reserve_grant()
        reopened = M.BatchLedger(self.auth_path, repo_root=self.root)
        self.assertEqual(reopened.status()['native_supplemental_attempts_remaining'], 3)
        with self.assertRaisesRegex(M.LimitError, 'attempt_already_reserved'):
            reopened.reserve(kind='native', attempt_id=self.supplement['grants'][0]['scope_id'], upper_bound_cny='3.20',
                billing_basis={'kind': 'priced_upper_bound', 'evidence': self.evidence},
                native_binding=self.binding(self.supplement['grants'][0]), run=True)

    def test_duplicate_activation_and_replacement_cannot_expand_grants(self):
        self.activate()
        after = self.ledger.journal.read_bytes()
        with self.assertRaisesRegex(M.LimitError, 'already_activated'):
            self.activate()
        changed = copy.deepcopy(self.supplement)
        changed['grants'][0]['scope_id'] = 'p1-native-' + 'd' * 24
        replacement_sha = self.write_supplement(changed)
        for operation in (lambda: self.ledger.status(), lambda: self.reserve_grant(1),
                          lambda: self.ledger.activate_native_supplement(expected_sha256=replacement_sha, run=True)):
            with self.assertRaisesRegex(M.LimitError, 'supplement_hash_mismatch'):
                operation()
        self.assertEqual(self.ledger.journal.read_bytes(), after)

    def test_missing_active_grant_file_blocks_without_releasing_cash(self):
        self.activate(); self.reserve_grant()
        before = self.ledger.journal.read_bytes()
        self.supplement_path.unlink()
        with self.assertRaisesRegex(M.LimitError, 'file_unavailable'):
            self.reserve_grant(1)
        self.assertEqual(self.ledger.journal.read_bytes(), before)
        self.write_supplement(self.supplement)
        self.assertEqual(self.ledger.status()['committed_cash_upper_bound'], '6.20')

    def test_expected_hash_and_canonical_file_location_are_mandatory(self):
        for expected in ('', 'not-a-sha', 'f' * 64):
            with self.subTest(expected=expected), self.assertRaises(M.LimitError):
                self.ledger.activate_native_supplement(expected_sha256=expected, run=True)
        self.supplement_path.rename(self.root / 'renamed-supplement.json')
        with self.assertRaisesRegex(M.LimitError, 'file_unavailable'):
            self.activate()
        self.assertEqual(self.ledger.journal.read_bytes(), self.historical)

    def test_widened_limits_changed_approval_or_fifth_grant_are_rejected(self):
        changes = [lambda x: x.update(additional_native_attempts=5),
                   lambda x: x['unchanged_limits'].update(added_cash_total='101.00'),
                   lambda x: x['unchanged_limits'].update(method_units=17),
                   lambda x: x['unchanged_limits'].update(native_attempts=6),
                   lambda x: x['native_scope_limits'].update(generation_start=6),
                   lambda x: x['native_scope_limits'].update(wall_seconds=601),
                   lambda x: x['approval'].update(date='2026-11-28'),
                   lambda x: x['approval'].update(timezone='UTC'),
                   lambda x: x['approval'].update(user_quote='全部批准'),
                   lambda x: x['grants'].append(copy.deepcopy(x['grants'][0])),
                   lambda x: x.update(ledger_relative_path='alternate-ledger'),
                   lambda x: x.update(private_path='/fixture/private/path')]
        for ordinal, change in enumerate(changes):
            value = copy.deepcopy(self.supplement); change(value)
            sha = self.write_supplement(value)
            with self.subTest(ordinal=ordinal), self.assertRaises(M.LimitError):
                self.ledger.activate_native_supplement(expected_sha256=sha, run=True)
        self.assertEqual(self.ledger.journal.read_bytes(), self.historical)

    def test_duplicate_identity_public_and_taskpack_substitution_are_rejected(self):
        for field, replacement in (('scope_id', self.supplement['grants'][1]['scope_id']),
                                   ('replicate', 2), ('project_id', 'other/project'),
                                   ('public_sha256', 'd' * 64), ('taskpack_public_sha256', 'd' * 64)):
            value = copy.deepcopy(self.supplement); value['grants'][0][field] = replacement
            sha = self.write_supplement(value)
            with self.subTest(field=field), self.assertRaises(M.LimitError):
                self.ledger.activate_native_supplement(expected_sha256=sha, run=True)
        self.assertEqual(self.ledger.journal.read_bytes(), self.historical)

    def test_parent_authorization_plan_and_exact_journal_anchor_cannot_be_swapped(self):
        for change in (lambda x: x['authorization'].update(sha256='e' * 64),
                       lambda x: x['source_plan'].update(sha256='e' * 64),
                       lambda x: x['prior_journal'].update(head_sha256='e' * 64),
                       lambda x: x['prior_journal'].update(sha256='e' * 64),
                       lambda x: x['prior_journal'].update(events=6)):
            value = copy.deepcopy(self.supplement); change(value)
            sha = self.write_supplement(value)
            with self.assertRaises(M.LimitError):
                self.ledger.activate_native_supplement(expected_sha256=sha, run=True)
        self.assertEqual(self.ledger.journal.read_bytes(), self.historical)

    def test_new_event_since_review_refuses_stale_activation_anchor(self):
        self.ledger.reserve(kind='method', attempt_id='fixture-method', unit='w-101:A:1',
            upper_bound_cny='0.00', billing_basis=self.basis, run=True)
        before = self.ledger.journal.read_bytes()
        with self.assertRaisesRegex(M.LimitError, 'journal_anchor_mismatch'):
            self.activate()
        self.assertEqual(self.ledger.journal.read_bytes(), before)

    def test_source_or_actual_public_drift_blocks_activation_or_reservation(self):
        self.activate()
        source = self.root / self.auth['source_plan']['relative_path']
        original = source.read_bytes(); source.write_text('{}')
        with self.assertRaisesRegex(M.LimitError, 'source_plan_drift'):
            self.reserve_grant()
        source.write_bytes(original)
        public = self.root / self.auth['units'][0]['public_relative_path']
        (public / 'request.txt').write_text('changed fixture source')
        with self.assertRaisesRegex(M.LimitError, 'public_snapshot_drift'):
            self.reserve_grant()
        self.assertEqual(self.ledger.status()['native_supplemental_attempts_remaining'], 4)

    def test_supplement_does_not_increase_cash_or_release_unknown_failure_hold(self):
        self.activate()
        self.reserve_grant(amount='97.00')
        self.ledger.finish(self.supplement['grants'][0]['scope_id'], status='failed')
        self.assertEqual(self.ledger.status()['committed_cash_upper_bound'], '100.00')
        with self.assertRaisesRegex(M.LimitError, 'cash_budget_exhausted'):
            self.reserve_grant(1, amount='0.01')
        self.assertEqual(self.ledger.status()['native_supplemental_attempts_remaining'], 3)
        self.assertIsNone(self.ledger.status()['actual_added_cash_total'])

    def test_original_sixteen_method_units_remain_exact_and_independent(self):
        self.activate()
        for ordinal, unit in enumerate(self.auth['units']):
            self.ledger.reserve(kind='method', attempt_id=f'fixture-method-{ordinal}', unit=M.unit_key(unit),
                upper_bound_cny='0.00', billing_basis=self.basis, run=True)
        status = self.ledger.status()
        self.assertEqual(status['method_units_reserved'], 16)
        self.assertEqual(status['method_units_remaining'], 0)
        self.assertEqual(status['native_supplemental_attempts_remaining'], 4)
        with self.assertRaisesRegex(M.LimitError, 'method_unit_already_reserved'):
            self.ledger.reserve(kind='method', attempt_id='fixture-method-extra', unit='w-101:A:1',
                upper_bound_cny='0.00', billing_basis=self.basis, run=True)

    def test_original_per_native_operation_and_wall_limits_are_unchanged(self):
        self.activate(); self.reserve_grant()
        scope = self.supplement['grants'][0]['scope_id']
        for kind, limit in M.EVENT_LIMITS['native'].items():
            for ordinal in range(limit):
                self.ledger.record_event(scope, kind, f'{kind}-{ordinal}')
            with self.assertRaisesRegex(M.LimitError, 'operation_budget_exhausted'):
                self.ledger.record_event(scope, kind, f'{kind}-extra')
        started = self.ledger.status()['attempts'][scope]['reserved_at_unix_ns']
        with patch.object(M.time, 'time_ns', return_value=started + 600 * 10**9):
            with self.assertRaisesRegex(M.LimitError, 'wall_budget_exhausted'):
                self.ledger.record_event(scope, 'generation_start', 'after-deadline')

    def test_concurrent_activation_appends_only_one_canonical_event(self):
        context = multiprocessing.get_context('fork')
        queue = context.Queue()
        workers = [context.Process(target=activation_worker, args=(str(self.root), self.supplement_sha, queue)) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(10)
            self.assertEqual(worker.exitcode, 0)
        self.assertEqual(sorted(queue.get(timeout=2) for _ in workers), ['activated', 'native_supplement_already_activated'])
        self.assertEqual(self.ledger.status()['journal_events'], 8)
        self.assertTrue(self.ledger.journal.read_bytes().startswith(self.historical))

    def test_controller_inspection_and_admission_supply_actual_task_binding(self):
        self.activate()
        scope = self.supplement['grants'][0]['scope_id']
        spec = CONTROLLER.RuntimeControllerTests.spec(self)
        controller = CONTROLLER.M.CanonicalPairedController({scope: spec}, repo_root=self.root, run=True)
        intent = CONTROLLER.RuntimeControllerTests.intent(self, scope=scope)
        self.assertTrue(controller.inspect_scope(intent)['reservation_would_fit'])
        self.assertEqual(self.ledger.status()['native_supplemental_attempts_reserved'], 0)
        controller.admit_scope(intent)
        record = self.ledger.status()['attempts'][scope]
        self.assertEqual(record['native_binding'], self.binding(self.supplement['grants'][0]))
        self.assertEqual(record['native_supplement_sha256'], self.supplement_sha)
        self.assertEqual(record['public_sha256'], self.supplement['grants'][0]['public_sha256'])

    def test_cli_requires_explicit_run_and_reviewed_hash(self):
        command = [sys.executable, str(ROOT / 'scripts/paper1/batch_limits.py'), '--repo-root', str(self.root),
                   'activate-native-supplement', '--expected-sha256', self.supplement_sha]
        dry = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertFalse(json.loads(dry.stdout)['activation_performed'])
        self.assertEqual(self.ledger.journal.read_bytes(), self.historical)
        active = subprocess.run(command + ['--run'], capture_output=True, text=True, check=True)
        self.assertTrue(json.loads(active.stdout)['activation_performed'])
        self.assertEqual(self.ledger.status()['journal_events'], 8)


if __name__ == '__main__':
    unittest.main()
