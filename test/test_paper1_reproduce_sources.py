"""Boundary tests for source qualification; these are not research runs."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/paper1/reproduce_sources.py'
spec = importlib.util.spec_from_file_location('reproduce_sources', SCRIPT)
repro = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repro)


class ReproductionBoundaryTests(unittest.TestCase):
    def fixture(self):
        row = {'instance_id': 'org__project-1', 'repo': 'org/project',
               'base_commit': 'a' * 40, 'patch': 'diff --git a/src/a.py b/src/a.py\n',
               'test_patch': 'diff --git a/tests/test_a.py b/tests/test_a.py\n',
               'FAIL_TO_PASS': '["private-test"]', 'PASS_TO_PASS': '[]'}
        candidate = {'candidate_id': row['instance_id'], 'project_id': row['repo'],
                     'repository_url': 'https://github.com/org/project',
                     'upstream': {'base_commit': row['base_commit']},
                     'source_dataset': {'canonical_row_sha256': repro.canonical_digest(row)},
                     'changed_files': {'benchmark_source_patch': ['src/a.py'],
                                       'benchmark_test_patch': ['tests/test_a.py']},
                     'official_benchmark_labels_evaluator_only': {
                         'patch_sha256': repro.digest(row['patch'].encode()),
                         'test_patch_sha256': repro.digest(row['test_patch'].encode())}}
        return candidate, row

    def test_row_requires_exact_content_pin(self):
        c, row = self.fixture()
        repro.validate_row(c, row)
        row['FAIL_TO_PASS'] = '["different"]'
        with self.assertRaisesRegex(ValueError, 'row_hash'):
            repro.validate_row(c, row)

    def test_patch_cannot_target_other_files_or_escape(self):
        c, row = self.fixture()
        for path in ['../secret', 'unlisted.py']:
            changed = copy.deepcopy(row)
            changed['patch'] = f'diff --git a/{path} b/{path}\n'
            c['source_dataset']['canonical_row_sha256'] = repro.canonical_digest(changed)
            c['official_benchmark_labels_evaluator_only']['patch_sha256'] = repro.digest(changed['patch'].encode())
            with self.assertRaisesRegex(ValueError, 'patch_paths'):
                repro.validate_row(c, changed)

    def test_candidate_identity_and_official_origin_required(self):
        c, row = self.fixture()
        c['repository_url'] = 'https://example.invalid/org/project'
        with self.assertRaisesRegex(ValueError, 'origin'):
            repro.validate_row(c, row)

    def test_all_dependency_requirements_must_be_pinned(self):
        for requirement in ['pytest', 'pytest>=7', '-r private.txt', 'x @ https://x.invalid/a.whl']:
            with self.assertRaisesRegex(ValueError, 'pin'):
                repro.validate_profile({'requirements': [requirement], 'test_runner': 'pytest', 'plugins': []})

    def test_missing_junit_is_unknown_not_zero(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(repro.junit_metrics(Path(d) / 'missing.xml'))

    def test_junit_counts_actual_testcases_without_nested_double_count(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'junit.xml'
            p.write_text('<testsuites><testsuite tests="3"><testcase name="a"/>'
                         '<testcase name="b"><failure/></testcase>'
                         '<testcase name="c"><skipped/></testcase></testsuite></testsuites>')
            self.assertEqual(repro.junit_metrics(p), {'tests': 3, 'passed': 1, 'failures': 1,
                                                     'errors': 0, 'skipped': 1})

    def test_minimal_environment_never_forwards_model_keys_or_home(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'do-not-copy', 'HOME': '/private',
                                     'HTTPS_PROXY': 'transport-only'}, clear=True):
            env = repro.install_environment()
        self.assertNotIn('OPENAI_API_KEY', env)
        self.assertNotIn('HOME', env)
        self.assertEqual(env['HTTPS_PROXY'], 'transport-only')
        self.assertEqual(env['GIT_CONFIG_GLOBAL'], '/dev/null')

    def test_dry_run_creates_nothing_and_launches_nothing(self):
        c, _ = self.fixture()
        with tempfile.TemporaryDirectory() as d, patch.object(repro, 'run_command') as run:
            root = Path(d) / 'private'
            public = Path(d) / 'report'
            result = repro.qualify(c, {}, root, public, Path(sys.executable), run=False)
            self.assertEqual(result['status'], 'dry_run')
            run.assert_not_called()
            self.assertFalse(root.exists())
            self.assertFalse(public.exists())

    def test_attempt_reservation_prevents_automatic_retry(self):
        c, _ = self.fixture()
        with tempfile.TemporaryDirectory() as d, patch.object(repro, 'run_command') as run:
            root, public = Path(d) / 'private', Path(d) / 'public'
            (root / c['candidate_id']).mkdir(parents=True)
            (root / c['candidate_id'] / 'attempt.json').write_text('{}')
            result = repro.qualify(c, {}, root, public, Path(sys.executable), run=True)
            self.assertEqual(result['status'], 'already_attempted')
            run.assert_not_called()

    def test_command_timeout_is_preserved_as_failure(self):
        with tempfile.TemporaryDirectory() as d:
            result = repro.run_command([sys.executable, '-c', 'import time;time.sleep(20)'],
                                       Path(d), {}, .05, Path(d), 'timeout-test')
            self.assertTrue(result['timed_out'])
            self.assertNotEqual(result['returncode'], 0)
            self.assertTrue((Path(d) / 'timeout-test.stdout.txt').exists())

    def test_public_receipt_has_no_raw_official_values(self):
        c, row = self.fixture()
        report = repro.initial_receipt(c, row)
        serialized = json.dumps(report)
        self.assertNotIn('private-test', serialized)
        self.assertNotIn('diff --git', serialized)
        self.assertFalse(report['formal_task'])
        self.assertEqual(report['model_requests'], 0)

    def test_setup_budget_is_total_remaining_not_reset_for_each_command(self):
        with patch.object(repro.time, 'monotonic', return_value=102):
            self.assertEqual(repro.remaining_budget(100, 6), 4)
        with patch.object(repro.time, 'monotonic', return_value=107):
            with self.assertRaisesRegex(TimeoutError, 'setup_budget'):
                repro.remaining_budget(100, 6)

    def test_pinned_parser_retains_its_module_constants(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = "FLAG = re.compile('skip')\ndef parse_log_pytest(log, spec):\n    return bool(FLAG.match(log))\n"
            constants = "class TestStatus(Enum):\n    PASSED = 'PASSED'\n"
            (root / 'official-log-parsers-python.py').write_text(source)
            (root / 'official-harness-constants.py').write_text(constants)
            with patch.object(repro, 'PARSER_SHA256', repro.digest(source.encode())), \
                    patch.object(repro, 'CONSTANTS_SHA256', repro.digest(constants.encode())):
                self.assertTrue(repro.load_official_parser(root, 'parse_log_pytest')('skip', None))

    def test_one_explicit_setup_followup_preserves_cumulative_budget(self):
        previous = {'status': 'setup_or_acquisition_failure', 'base_result': None,
                    'attempt_number': 1, 'total_elapsed_seconds': 80}
        self.assertEqual(repro.retry_setup_budget(previous, 360), 280)
        previous['base_result'] = {'returncode': 1}
        with self.assertRaisesRegex(ValueError, 'setup_only'):
            repro.retry_setup_budget(previous, 360)
        previous.update(base_result=None, attempt_number=2)
        with self.assertRaisesRegex(ValueError, 'one_followup'):
            repro.retry_setup_budget(previous, 360)

    def test_sandbox_account_file_is_generated_without_host_identity_or_resolver(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cmd = repro.sandbox_command(Path(sys.executable), root / 'venv', root / 'repo', root, ['true'])
            account = (root / 'sandbox.passwd').read_text()
            self.assertIn('qualification:', account)
            self.assertIn('/tmp:/bin/sh', account)
            self.assertNotIn('/etc/resolv.conf', cmd)
            self.assertNotIn('HOME', cmd)
            self.assertNotIn('CODEX_HOME', cmd)

    def test_candidate_directory_cannot_escape_root(self):
        c, row = self.fixture()
        c['candidate_id'] = '../../elsewhere'
        with self.assertRaisesRegex(ValueError, 'candidate_id'):
            repro.qualify(c, {}, Path('/tmp/private'), Path('/tmp/public'), Path(sys.executable), run=False)

    def test_official_error_is_a_reproduced_regression_but_skip_is_not(self):
        for status, expected in [('ERROR', True), ('FAILED', True), ('SKIPPED', False), ('PASSED', False)]:
            checks = repro.transition_checks({'bad': status, 'old': 'PASSED'},
                                             {'bad': 'PASSED', 'old': 'PASSED'}, ['bad'], ['old'])
            self.assertEqual(checks['base_failed_matches_official_f2p'], expected)
        self.assertFalse(repro.transition_checks({}, {'bad': 'PASSED'}, ['bad'], [])['base_failed_matches_official_f2p'])

    def test_fixed_process_cannot_qualify_after_mutating_its_test_file(self):
        candidate, row = self.fixture()
        profile = {'requirements': ['pytest==6.2.5'], 'test_runner': 'pytest', 'plugins': []}
        with tempfile.TemporaryDirectory() as d:
            private, public = Path(d) / 'private', Path(d) / 'public'
            private.mkdir()
            (private / (candidate['candidate_id'] + '.official-row.json')).write_text(json.dumps(row))

            def fake_command(argv, cwd, env, timeout, logs, name):
                # A synthetic runner contract test. No source project or model is run.
                repo = cwd / 'repo'
                if name == 'git-init':
                    (repo / 'src').mkdir(parents=True)
                    (repo / 'tests').mkdir()
                    (repo / 'src/a.py').write_text('original source')
                    (repo / 'tests/test_a.py').write_text('frozen evaluation test')
                stdout = ''
                if name == 'git-head':
                    stdout = row['base_commit']
                elif name == 'install-dependencies':
                    (logs / 'dependency-install-report.json').write_text('{"install": []}')
                elif name == 'dependencies-freeze':
                    stdout = 'pytest==6.2.5\n'
                elif name == 'python-version':
                    stdout = '{"version": "synthetic-test-runtime"}'
                elif name == 'patch-apply':
                    (repo / 'src/a.py').write_text('fixed source')
                elif name == 'fixed':
                    (repo / 'tests/test_a.py').write_text('changed during fixed test process')
                (logs / (name + '.stdout.txt')).write_text(stdout)
                (logs / (name + '.stderr.txt')).write_text('')
                return {'phase': name, 'returncode': 1 if name == 'base' else 0,
                        'timed_out': False, 'elapsed_seconds': 0.001}

            with patch.object(repro, 'run_command', side_effect=fake_command), \
                    patch.object(repro, 'label_coverage', return_value={'all_expected_transitions_verified': True}):
                report = repro.qualify(candidate, profile, private, public, Path(sys.executable), run=True)
            self.assertFalse(report['test_file_unchanged_between_phases'])
            self.assertEqual(report['status'], 'evidence_integrity_failure')


if __name__ == '__main__':
    unittest.main()
