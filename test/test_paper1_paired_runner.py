"""Source-batch preparation/admission tests; no agent or provider requests."""
import copy
import json
import os
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
API = runpy.run_path(str(ROOT / 'scripts/paper1/paired_runner.py'))
BASE = ROOT / 'docs/research/p1-evidence-verification/tasks/workflows'
PLAN = BASE / 'source-draft-plan.json'
PACKAGES = [BASE / 'packages' / name for name in ('w-101', 'w-102')]
AUTH = ROOT / 'docs/research/p1-evidence-verification/artifacts/authorized-batch1/authorization.json'


class PairedRunnerPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        # The archived approval intentionally binds its original absolute
        # locations. Exercise this legacy preparation API with an explicit
        # temporary fixture plan for this checkout, never by rewriting the
        # archived plan/authorization or weakening their identity checks.
        self.plan = self.root / 'fixture-plan.json'
        value = API['TASKPACK']['draft_plan'](PACKAGES, list('ABCD'), 2)
        self.plan.write_text(json.dumps(value))
        self.auth = self.root / 'fixture-authorization.json'
        approval = json.loads(AUTH.read_text())
        approval['source_plan']['sha256'] = API['file_sha'](self.plan)
        self.auth.write_text(json.dumps(approval))

    def tearDown(self):
        self.temp.cleanup()

    def inspect(self, **kwargs):
        return API['inspect'](self.plan, PACKAGES, environ={}, **kwargs)

    def changed_plan(self, change):
        value = json.loads(self.plan.read_text())
        change(value)
        path = self.root / 'plan.json'
        path.write_text(json.dumps(value))
        return path

    def detached_public(self):
        path = self.root / 'public'
        shutil.copytree(PACKAGES[0] / 'public', path)
        return path

    def test_actual_two_sources_are_bound_but_not_runtime_or_scientific_ready(self):
        result = self.inspect()
        self.assertEqual(result['planned_development_units'], 16)
        self.assertIsNone(result['permissions_granted'])
        self.assertFalse(result['runtime_ready'])
        self.assertFalse(result['scientific_ready'])
        self.assertEqual(result['accepted_p1_task_count'], 0)
        for source in result['sources']:
            self.assertFalse(source['source_archive_present'])
            for arm in 'ABCD':
                self.assertIn('task_bound_python_execution_not_captured', source['arms'][arm]['blocking_gates'])
                self.assertFalse(source['arms'][arm]['runtime_ready'])
            component = source['python_source_capture_component']
            self.assertTrue(component['observer_implemented'])
            self.assertEqual(component['source_executions'], 0)
            self.assertFalse(component['method_runtime_ready'])

    def test_recorded_permission_never_becomes_host_or_scientific_acceptance(self):
        result = self.inspect(authorization=self.auth)
        self.assertTrue(result['permissions_granted'])
        self.assertFalse(result['authorization_evidence']['host_approval_attested'])
        self.assertFalse(result['runtime_ready'])
        self.assertFalse(result['scientific_ready'])
        self.assertEqual(result['authorization_evidence']['added_cash_cap'], '100.00')
        self.assertEqual(result['method_attempts_reserved'], 0)

    def test_authorization_is_bound_to_exact_plan_bytes_not_just_equal_json(self):
        alternate = self.root / 'reformatted.json'
        alternate.write_text(json.dumps(json.loads(self.plan.read_text()), separators=(',', ':')))
        with self.assertRaisesRegex(ValueError, 'authorization_plan_binding'):
            API['inspect'](alternate, PACKAGES, environ={}, authorization=self.auth)

    def test_authorization_cannot_expand_the_approved_cash_limit(self):
        value = json.loads(self.auth.read_text())
        value['limits']['added_cash_total'] = '101.00'
        changed = self.root / 'authorization.json'
        changed.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'approved_limits_mismatch'):
            self.inspect(authorization=changed)

    def test_credential_presence_never_becomes_provider_verification_or_leaks_value(self):
        secret = 'FORBIDDEN-CREDENTIAL-FIXTURE'
        result = API['inspect'](self.plan, PACKAGES,
            environ={'VECTORIZE_API_KEY': secret, 'RERANK_API_KEY': secret})
        self.assertTrue(all(result['credentials_present'].values()))
        self.assertFalse(result['credential_access_verified'])
        self.assertNotIn(secret, json.dumps(result))
        self.assertIn('faithful_rawrag_provider_access_unverified', result['sources'][0]['arms']['B']['blocking_gates'])

    def test_eighty_unit_plan_is_not_admitted_under_sixteen_unit_scope(self):
        with self.assertRaisesRegex(ValueError, 'source_plan_changed'):
            API['inspect'](BASE / 'draft-plan.json', PACKAGES, environ={})

    def test_duplicate_or_relabelled_units_cannot_shrink_or_change_denominator(self):
        path = self.changed_plan(lambda x: x['units'].__setitem__(1, copy.deepcopy(x['units'][0])))
        with self.assertRaisesRegex(ValueError, 'source_plan_changed'):
            API['inspect'](path, PACKAGES)

    def test_plan_cannot_redirect_public_paths_to_controller(self):
        path = self.changed_plan(lambda x: x['experiment_spec_fragment']['tasks'][0]['public_by_replicate'].__setitem__('1', str(PACKAGES[0] / 'controller')))
        with self.assertRaisesRegex(ValueError, 'source_plan_changed'):
            API['inspect'](path, PACKAGES)

    def test_mutated_public_hash_is_not_overridden_by_authorization(self):
        path = self.changed_plan(lambda x: x['units'][0].__setitem__('public_sha256', '0' * 64))
        with self.assertRaisesRegex(ValueError, 'source_plan_changed'):
            API['inspect'](path, PACKAGES, authorization=self.auth)

    def test_foreign_or_duplicate_source_package_is_rejected(self):
        for packages in ([PACKAGES[0], PACKAGES[0]], [PACKAGES[0], BASE / 'packages/d-201']):
            with self.subTest(packages=packages), self.assertRaises(ValueError):
                API['inspect'](PLAN, packages)

    def test_initial_reader_payload_contains_original_request_not_private_mapping_or_all_code(self):
        value, size = API['public_initial_input'](PACKAGES[0] / 'public')
        self.assertEqual(set(value), {'task', 'request', 'budget'})
        self.assertEqual(value['request'], (PACKAGES[0] / 'public/request.txt').read_text())
        self.assertEqual(size, len(API['canonical'](value).encode()))
        encoded = json.dumps(value)
        for forbidden in ('source_fix_commit', 'test_patch', 'source-export.json', 'source_candidate_id'):
            self.assertNotIn(forbidden, encoded)
        self.assertNotIn((PACKAGES[0] / 'public/workspace/src/flask/app.py').read_text(), encoded)

    def test_initial_reader_wrapper_counts_against_budget_and_never_truncates(self):
        public = self.detached_public()
        budget = json.loads((public / 'budget.json').read_text())
        budget['max_initial_context_bytes'] = 1
        (public / 'budget.json').write_text(json.dumps(budget))
        with self.assertRaisesRegex(ValueError, 'payload_budget'):
            API['public_initial_input'](public)

    def test_staging_detaches_only_public_and_preserves_equal_inputs_for_all_arms(self):
        output = self.root / 'prepared'
        with mock.patch('subprocess.Popen', side_effect=AssertionError('preparation cannot launch processes')):
            result = API['stage'](self.plan, PACKAGES, output, environ={}, authorization=self.auth)
        self.assertEqual(set(p.name for p in output.iterdir()), {'public', 'controller'})
        self.assertEqual(len(result['prepared_units']), 16)
        self.assertEqual(len({u['unit_id'] for u in result['prepared_units']}), 16)
        for task in ('w-101', 'w-102'):
            public = output / 'public' / task
            self.assertEqual(API['EXPERIMENT']['public_digest'](public),
                API['EXPERIMENT']['public_digest'](BASE / 'packages' / task / 'public'))
            self.assertFalse((public / 'controller').exists())
            self.assertFalse((public / 'evaluator').exists())
            units = [u for u in result['prepared_units'] if u['task_id'] == task]
            self.assertEqual(len({u['public_sha256'] for u in units}), 1)
            self.assertEqual(len({u['public_relative_path'] for u in units}), 1)
        self.assertTrue(result['output_is_not_an_OS_sandbox'])
        self.assertFalse(result['runtime_ready'])
        self.assertEqual(result['model_requests'], 0)
        self.assertEqual(result['method_attempts_reserved'], 0)

    def test_restrictive_controller_umask_does_not_change_public_root_identity(self):
        previous = os.umask(0o077)
        try:
            result = API['stage'](self.plan, PACKAGES, self.root / 'restricted', environ={})
        finally:
            os.umask(previous)
        for source in result['sources']:
            public = self.root / 'restricted/public' / source['task_id']
            self.assertEqual(API['EXPERIMENT']['public_digest'](public), source['public_sha256'])

    def test_staging_cannot_overwrite_or_land_inside_a_source_package(self):
        for output in (self.root, PACKAGES[0] / 'new-preparation'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                API['stage'](self.plan, PACKAGES, output, environ={})
        self.assertFalse((PACKAGES[0] / 'new-preparation').exists())

    def test_symlink_destination_parent_cannot_redirect_staging(self):
        real = self.root / 'real'; real.mkdir()
        link = self.root / 'link'; link.symlink_to(real, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            API['stage'](self.plan, PACKAGES, link / 'staged', environ={})
        self.assertEqual(list(real.iterdir()), [])

    def test_archived_plan_and_authorization_are_not_silently_relocated(self):
        original_plan, original_auth = PLAN.read_bytes(), AUTH.read_bytes()
        if json.loads(original_plan) == json.loads(self.plan.read_bytes()):
            result = API['inspect'](PLAN, PACKAGES, environ={}, authorization=AUTH)
            self.assertTrue(result['permissions_granted'])
        else:
            with self.assertRaisesRegex(ValueError, 'source_plan_changed'):
                API['inspect'](PLAN, PACKAGES, environ={}, authorization=AUTH)
        self.assertEqual(PLAN.read_bytes(), original_plan)
        self.assertEqual(AUTH.read_bytes(), original_auth)

    def test_runner_abi_reports_failure_without_launching_backend(self):
        output = self.root / 'run'; output.mkdir()
        with mock.patch('subprocess.Popen', side_effect=AssertionError('no backend launch')):
            result = API['reject_dispatch'](PACKAGES[0] / 'public', 'B', 1, 'run-test', output, 300)
        self.assertEqual(result['status'], 'host_error')
        self.assertEqual(result['failure_reason'], 'source_workflow_backend_not_implemented')
        actual, error = API['EXPERIMENT']['result_metadata'](output)
        self.assertIsNone(error)
        self.assertEqual(actual, result)
        trace = json.loads((output / 'pre-dispatch-block.json').read_text())
        self.assertEqual(trace['model_requests'], 0)
        self.assertEqual(trace['provider_requests'], 0)
        self.assertIn('do not reset', trace['outer_attempt_reservation'])
        self.assertFalse((output / 'usage.jsonl').exists())

    def test_runner_rejects_unapproved_arm_replicate_timeout_and_output_overlap(self):
        output = self.root / 'run'; output.mkdir()
        for arm, replicate, timeout in [('T', 1, 300), ('B', 3, 300), ('A', 1, 301), ('A', True, 300), ('A', 1, True)]:
            with self.subTest(arm=arm, replicate=replicate, timeout=timeout), self.assertRaises(ValueError):
                API['reject_dispatch'](PACKAGES[0] / 'public', arm, replicate, 'run', output, timeout)
        public = self.detached_public()
        with self.assertRaises(ValueError):
            API['reject_dispatch'](public, 'A', 1, 'run', public, 300)
        self.assertFalse((public / 'result.json').exists())

    def test_blocked_runner_cannot_overwrite_a_prior_attempt(self):
        output = self.root / 'run'; output.mkdir()
        API['reject_dispatch'](PACKAGES[0] / 'public', 'A', 1, 'run', output, 300)
        original = (output / 'result.json').read_bytes()
        with self.assertRaises(FileExistsError):
            API['reject_dispatch'](PACKAGES[0] / 'public', 'A', 1, 'run', output, 300)
        self.assertEqual((output / 'result.json').read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
