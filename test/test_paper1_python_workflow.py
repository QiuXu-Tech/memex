"""Controller capture tests. Only owned tiny Python fixtures are executed here."""
import copy
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
API = runpy.run_path(str(ROOT / 'scripts/paper1/python_workflow.py'))
CHILD = ROOT / 'scripts/paper1/python_workflow_child.py'
PUBLIC = ROOT / 'docs/research/p1-evidence-verification/tasks/workflows/packages'
OLD_RUNTIME = ROOT.parent / 'p1-real-repros'


class PythonWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fixture_workspace(self, module='fixture'):
        workspace = self.root / 'workspace'
        (workspace / module).mkdir(parents=True)
        (workspace / module / '__init__.py').write_text('VALUE = 42\n')
        (workspace / 'tests').mkdir()
        return workspace

    def run_owned_fixture(self, content, *, module='fixture', initialization=None, task='w-101'):
        project = {'w-101': 'pallets__flask-5014', 'w-102': 'psf__requests-6028'}[task]
        python = OLD_RUNTIME / project / 'venv310/bin/python'
        if not python.exists():
            self.skipTest('existing pinned local Python fixture runtime unavailable; no installation attempted')
        recipe = API['profile'](PUBLIC / task / 'public')
        environment = API['runtime'](python, recipe)
        workspace = self.fixture_workspace(module)
        if initialization is not None:
            (workspace / module / '__init__.py').write_text(initialization)
        (workspace / 'tests/test_example.py').write_text(content)
        # A parent conftest would fail if pytest crossed the snapshot boundary.
        (self.root / 'conftest.py').write_text('raise RuntimeError("parent conftest must never load")\n')
        output = self.root / 'run'
        output.mkdir()
        config = {'nonce': 'owned-fixture-nonce', 'workspace': str(workspace),
                  'dependencies': str(environment['site']), 'module': module, 'import_root': '.',
                  'requirements': recipe['requirements'], 'python_version': [3, 10, 16],
                  'tests': ['tests/test_example.py'], 'plugins': recipe['plugins'],
                  'temporary': str(output / 'tmp'), 'junit': str(output / 'junit.xml'),
                  'result': str(output / 'observation.json')}
        API['write_json'](output / 'config.json', config)
        before = API['snapshot'](workspace)
        process = API['run_process']([python, '-I', '-S', '-B', CHILD, output / 'config.json'],
            cwd=workspace, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8',
                               'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}, timeout=20, directory=output)
        observation = json.loads((output / 'observation.json').read_text())
        evaluation = API['summarize'](process, observation, before, API['snapshot'](workspace),
            nonce=config['nonce'], tests=config['tests'], module=module,
            dependencies=environment['dependency_snapshot']['files'])
        return process, observation, evaluation

    def test_actual_clean_sources_have_exact_fixed_public_profiles(self):
        for task, expected in [('w-101', 'tests/test_blueprints.py'), ('w-102', 'tests/test_utils.py')]:
            report = API['inspect'](PUBLIC / task / 'public')
            self.assertEqual(report['fixed_tests'], [expected])
            self.assertEqual(report['source_executions'], 0)
            self.assertFalse(report['method_runtime_ready'])
            self.assertTrue(report['observer_implemented'])

    def test_prepare_copies_only_public_bytes_and_rejects_changed_seed(self):
        session = self.root / 'session'
        result = API['prepare'](PUBLIC / 'w-101/public', session)
        self.assertEqual(result['source_executions'], 0)
        self.assertFalse((session / 'public/evaluator').exists())
        self.assertEqual(API['profile'](session / 'public')['task_id'], 'w-101')
        target = session / 'public/workspace/src/flask/app.py'
        target.write_text(target.read_text() + '\n# changed\n')
        with self.assertRaisesRegex(ValueError, 'clean_public_seed_hash'):
            API['profile'](session / 'public')

    def test_prepare_refuses_existing_session_and_source_symlinks(self):
        with self.assertRaisesRegex(ValueError, 'session_already_exists'):
            API['prepare'](PUBLIC / 'w-101/public', self.root)
        workspace = self.fixture_workspace()
        (workspace / 'link').symlink_to(workspace / 'fixture/__init__.py')
        with self.assertRaisesRegex(ValueError, 'nonregular_or_symlink'):
            API['snapshot'](workspace)

    def test_snapshot_records_modes_empty_dirs_and_exact_source_bytes(self):
        workspace = self.fixture_workspace()
        original = API['snapshot'](workspace)
        (workspace / 'empty').mkdir()
        second = API['snapshot'](workspace)
        self.assertNotEqual(original['version'], second['version'])
        (workspace / 'fixture/__init__.py').chmod(0o600)
        self.assertNotEqual(second['version'], API['snapshot'](workspace)['version'])

    def test_real_fixture_uses_pinned_pytest_without_site_or_parent_conftest(self):
        _, observation, result = self.run_owned_fixture(
            'import os,sys,pytest,fixture\n'
            'def test_observed():\n'
            ' assert fixture.VALUE == 42\n'
            ' assert "FORBIDDEN_KEY" not in os.environ\n'
            ' assert not any(p.endswith("/repo") or p.endswith("/repo/src") for p in sys.path)\n'
            ' assert sys.dont_write_bytecode\n'
            '@pytest.mark.skip(reason="owned fixture skip")\n'
            'def test_skipped(): pass\n')
        self.assertEqual(result['status'], 'tests_passed', observation)
        self.assertEqual(result['test_counts'], {'collected': 2, 'passed': 1, 'failed': 0, 'errors': 0, 'skipped': 1})
        self.assertTrue(observation['pth_processing_disabled'])
        self.assertFalse(list((self.root / 'workspace').rglob('*.pyc')))

    def test_real_fixture_teardown_failure_is_not_overwritten_by_passing_call(self):
        process, observation, result = self.run_owned_fixture(
            'import pytest\n'
            '@pytest.fixture\n'
            'def cleanup():\n'
            ' yield\n'
            ' assert False, "owned teardown failure"\n'
            'def test_body(cleanup): assert True\n')
        self.assertEqual(process['returncode'], 1)
        self.assertEqual(result['status'], 'tests_failed', observation)
        self.assertEqual(result['test_counts']['errors'], 1)

    def test_real_fixture_collection_error_and_all_xfail_never_count_as_success(self):
        process, observation, result = self.run_owned_fixture('raise RuntimeError("owned collection failure")\n')
        self.assertEqual(process['returncode'], 2)
        self.assertTrue(observation['collection_errors'])
        self.assertEqual(result['status'], 'capture_incomplete')

    def test_real_fixture_all_xfail_is_not_a_passing_test(self):
        _, observation, result = self.run_owned_fixture(
            'import pytest\n@pytest.mark.xfail(reason="owned")\ndef test_xfail(): assert False\n')
        self.assertEqual(result['reason'], 'no_non_skipped_passing_tests', observation)

    def test_real_fixture_requests_dependency_aliases_are_not_mistaken_for_source_imports(self):
        initialization = (
            'import sys,urllib3,idna,charset_normalizer\n'
            'for name in list(sys.modules):\n'
            ' if name == "urllib3" or name.startswith("urllib3.") or name == "idna" or name.startswith("idna."):\n'
            '  sys.modules["requests.packages." + name] = sys.modules[name]\n'
            'sys.modules["requests.packages.chardet"] = charset_normalizer\n'
            'VALUE=42\n')
        _, observation, result = self.run_owned_fixture('def test_owned(): assert True\n',
            module='requests', initialization=initialization, task='w-102')
        self.assertEqual(result['status'], 'tests_passed', observation)

    def test_real_fixture_import_outside_workspace_is_rejected(self):
        _, observation, result = self.run_owned_fixture('def test_owned(): assert True\n',
            initialization='import sys,os\nsys.modules["fixture.other"] = os\n')
        self.assertEqual(observation['error']['code'], 'project_import_outside_current_workspace')
        self.assertEqual(result['status'], 'capture_incomplete')

    def test_real_fixture_network_guard_retains_failed_attempt(self):
        process, observation, result = self.run_owned_fixture(
            'import socket\ndef test_network_denied(): socket.getaddrinfo("example.invalid",80)\n')
        self.assertEqual(process['returncode'], 1)
        self.assertEqual(observation['network_attempts_blocked'], 1)
        self.assertEqual(result['reason'], 'network_operation_blocked')

    def test_process_capture_keeps_exact_binary_streams_and_nonzero_exit(self):
        result = API['run_process']([sys.executable, '-I', '-S', '-c',
            'import os,sys;os.write(1,b"out\\x00\\xff");os.write(2,b"err\\n");sys.exit(7)'],
            cwd=self.root, env={}, timeout=5, directory=self.root)
        self.assertEqual(result['returncode'], 7)
        self.assertEqual((self.root / 'stdout.raw').read_bytes(), b'out\x00\xff')
        self.assertEqual((self.root / 'stderr.raw').read_bytes(), b'err\n')
        self.assertEqual(result['streams']['stdout']['sha256'], API['sha'](b'out\x00\xff'))

    def test_process_timeout_keeps_partial_output_and_signal(self):
        result = API['run_process']([sys.executable, '-I', '-S', '-u', '-c',
            'import time;print("started");time.sleep(20)'],
            cwd=self.root, env={}, timeout=0.2, directory=self.root)
        self.assertTrue(result['timed_out'])
        self.assertIsNotNone(result['signal'])
        self.assertIn(b'started', (self.root / 'stdout.raw').read_bytes())
        self.assertLess(result['elapsed_seconds'], 3)

    def test_process_output_cap_is_not_silent_truncation(self):
        result = API['run_process']([sys.executable, '-I', '-S', '-c',
            'import os;os.write(1,b"x"*1000000)'],
            cwd=self.root, env={}, timeout=5, directory=self.root, output_limit=32)
        self.assertTrue(result['output_limit_exceeded'])
        self.assertFalse(result['output_complete'])
        self.assertEqual((self.root / 'stdout.raw').stat().st_size, 32)

    def test_failed_spawn_keeps_real_error_without_fabricating_exit(self):
        result = API['run_process'](['/no/such/owned-fixture-command'],
            cwd=self.root, env={}, timeout=5, directory=self.root)
        self.assertFalse(result['spawned'])
        self.assertIsNone(result['returncode'])
        self.assertEqual(result['error']['type'], 'FileNotFoundError')

    def test_redaction_preserves_raw_hash_separately_from_published_output(self):
        original = b'/private/attempt/workspace/test.py\n/private/attempt/log\n'
        published = API['redact'](original, {'/private/attempt': '<controller>',
                                             '/private/attempt/workspace': '<workspace>'})
        self.assertEqual(published, b'<workspace>/test.py\n<controller>/log\n')
        self.assertNotEqual(API['sha'](original), API['sha'](published))

    def test_junit_redaction_preserves_valid_xml_with_path_in_parameterized_name(self):
        raw = b'<testsuites><testcase name="test[/private/deps/test.py]">/private/deps/log</testcase></testsuites>'
        published = API['redact_xml'](raw, {'/private/deps': '<dependencies>'})
        element = ET.fromstring(published).find('testcase')
        self.assertEqual(element.attrib['name'], 'test[<dependencies>/test.py]')
        self.assertEqual(element.text, '<dependencies>/log')
        self.assertIn(b'&lt;dependencies&gt;', published)

    def test_execute_preflight_creates_no_attempt_and_never_spawns(self):
        python = OLD_RUNTIME / 'pallets__flask-5014/venv310/bin/python'
        if not python.exists():
            self.skipTest('pinned local environment unavailable')
        session = self.root / 'session'
        API['prepare'](PUBLIC / 'w-101/public', session)
        output = self.root / 'export'
        before = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*'))
        with mock.patch.object(API['subprocess'], 'Popen', side_effect=AssertionError('must not spawn')):
            report = API['execute'](session, python, output)
        self.assertEqual(report['source_executions'], 0)
        self.assertEqual(before, sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob('*')))

    def test_controller_exception_retains_numbered_attempt_without_claiming_source_success(self):
        python = OLD_RUNTIME / 'pallets__flask-5014/venv310/bin/python'
        if not python.exists():
            self.skipTest('pinned local environment unavailable')
        session = self.root / 'session'
        API['prepare'](PUBLIC / 'w-101/public', session)
        # Failure before a process launches, injected at the runtime call seam.
        globals_ = API['_execute'].__globals__
        with mock.patch.dict(globals_, {'run_process': mock.Mock(side_effect=RuntimeError('owned failure'))}):
            report = API['execute'](session, python, self.root / 'export', run=True)
        self.assertEqual(report['evaluation']['status'], 'capture_incomplete')
        self.assertIsNone(report['source_executions'])
        self.assertEqual(report['method_attempts_reserved'], 0)
        self.assertTrue((session / 'controller/attempts/001/controller-failure.json').exists())
        self.assertTrue((self.root / 'export/capture.json').exists())


if __name__ == '__main__':
    unittest.main()
