"""Public tools and OS-sandbox construction; no third-party source execution."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'scripts/paper1/public_workspace.py'
API = runpy.run_path(str(MODULE)) if MODULE.exists() else {}
PUBLIC = ROOT / 'docs/research/p1-evidence-verification/tasks/workflows/packages/w-101/public'


def require(name):
    if not callable(API.get(name)):
        raise AssertionError(name + ' must implement the workspace contract')
    return API[name]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PublicWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.intents = []

    def tearDown(self):
        self.temp.cleanup()

    def admit(self, intent):
        self.intents.append(intent)
        return {'operation_id': intent['operation_id'], 'admitted_kinds': intent['kinds']}

    def workspace(self, **kwargs):
        return require('PublicWorkspace')(PUBLIC, self.root / 'workspace', self.root / 'controller',
                                          authorize_operation=self.admit, **kwargs)

    def test_only_public_workspace_is_copied_and_tool_schemas_have_exact_arguments(self):
        workspace = self.workspace()
        self.assertEqual((workspace.workdir / 'src/flask/__init__.py').read_bytes(),
                         (PUBLIC / 'workspace/src/flask/__init__.py').read_bytes())
        self.assertFalse((workspace.workdir / 'controller').exists())
        self.assertFalse((workspace.workdir / 'evaluator').exists())
        names = {row['name'] for row in workspace.tool_descriptions}
        self.assertEqual(names, {'read_file', 'write_file', 'list_files', 'run_current_tests', 'record_review'})
        self.assertTrue(all(row['inputSchema']['additionalProperties'] is False for row in workspace.tool_descriptions))

    def test_reads_are_byte_bounded_and_charge_failed_source_open_attempts(self):
        workspace = self.workspace(limits={'max_source_open_bytes_per_call': 4,
            'max_source_open_bytes_total': 8, 'max_source_open_calls': 2, 'max_tool_calls': 5})
        result = workspace.call('read_file', {'path': 'src/flask/__init__.py', 'offset': 0, 'limit': 4})
        self.assertTrue(result['ok'])
        self.assertEqual(result['result']['bytes'], 4)
        self.assertEqual(result['result']['next_offset'], 4)
        failed = workspace.call('read_file', {'path': '../controller/private.json', 'offset': 0, 'limit': 4})
        self.assertFalse(failed['ok'])
        self.assertEqual(workspace.counters['source_open_calls'], 2)
        denied = workspace.call('read_file', {'path': 'src/flask/__init__.py', 'offset': 4, 'limit': 4})
        self.assertFalse(denied['ok'])
        self.assertEqual(workspace.counters['source_open_bytes'], 4)

    def test_write_is_hash_bound_and_changes_detached_snapshot_only(self):
        workspace = self.workspace()
        before = workspace.snapshot()['version']
        source = PUBLIC / 'workspace/src/flask/__init__.py'
        original = source.read_bytes()
        result = workspace.call('write_file', {'path': 'src/flask/__init__.py', 'content': '# observed edit\n',
            'expected_sha256': sha(source), 'range': {'start': 0, 'end': 0}})
        self.assertTrue(result['ok'])
        self.assertEqual(source.read_bytes(), original)
        self.assertNotEqual(workspace.snapshot()['version'], before)
        stale = workspace.call('write_file', {'path': 'src/flask/__init__.py', 'content': '', 'expected_sha256': sha(source)})
        self.assertFalse(stale['ok'])

    def test_new_tests_are_allowed_but_private_paths_and_symlinks_are_denied(self):
        workspace = self.workspace()
        result = workspace.call('write_file', {'path': 'tests/test_new_local_case.py',
            'content': 'def test_new_case():\n    assert True\n', 'expected_sha256': None})
        self.assertTrue(result['ok'])
        for path in ('/etc/passwd', '../outside.txt', 'controller/receipt.json', '.env', '.git/config', 'tests/../../escape.py'):
            with self.subTest(path=path):
                denied = workspace.call('write_file', {'path': path, 'content': 'blocked', 'expected_sha256': None})
                self.assertFalse(denied['ok'])
        (workspace.workdir / 'external-link').symlink_to(self.root / 'controller', target_is_directory=True)
        self.assertFalse(workspace.call('read_file', {'path': 'external-link/session.json', 'offset': 0, 'limit': 100})['ok'])

    def test_real_test_execution_requires_live_sandbox_verification(self):
        workspace = self.workspace()
        with mock.patch('subprocess.Popen', side_effect=AssertionError('unverified code cannot execute')):
            outcome = workspace.call('run_current_tests', {})
        self.assertFalse(outcome['ok'])
        self.assertEqual(outcome['result']['error'], 'verified_os_sandbox_required')
        self.assertEqual(workspace.counters['test_executions'], 0)

    def test_bad_tool_admission_cannot_apply_an_edit(self):
        workspace = self.workspace()
        workspace.authorize_operation = lambda intent: {'operation_id': 'foreign', 'admitted_kinds': intent['kinds']}
        outcome = workspace.call('write_file', {'path': 'tests/test_denied.py', 'content': 'x=1\n', 'expected_sha256': None})
        self.assertFalse(outcome['ok'])
        self.assertFalse((workspace.workdir / 'tests/test_denied.py').exists())
        self.assertEqual(workspace.counters['tool_calls'], 1)

    def test_reviews_bind_current_snapshot_and_actual_prior_receipts(self):
        workspace = self.workspace()
        read = workspace.call('read_file', {'path': 'src/flask/__init__.py', 'offset': 0, 'limit': 30})
        review = workspace.call('record_review', {'text': 'Read the current source; no test has been run.',
            'evidence_event_ids': [read['receipt']['event_id']]})
        self.assertTrue(review['ok'])
        self.assertEqual(review['result']['workspace_sha256'], workspace.snapshot()['version'])
        self.assertFalse(review['result']['correctness_judged'])
        self.assertFalse(workspace.call('record_review', {'text': 'Unobserved claim', 'evidence_event_ids': ['invented']})['ok'])

    def test_existing_controller_session_cannot_be_restarted_to_reset_budgets(self):
        self.workspace()
        with self.assertRaises(ValueError):
            self.workspace()

    def test_controller_deadline_can_only_shorten_the_tool_session(self):
        workspace = self.workspace()
        original = workspace.constrain_deadline(float('1e12'))
        self.assertEqual(workspace.constrain_deadline(original + 100), original)
        self.assertEqual(workspace.constrain_deadline(0), 0)
        result = workspace.call('write_file', {'path': 'tests/too_late.py', 'content': 'pass\n', 'expected_sha256': None})
        self.assertFalse(result['ok'])
        self.assertEqual(result['result']['error'], 'public_workspace_deadline_exhausted')
        self.assertFalse((workspace.workdir / 'tests/too_late.py').exists())
        for invalid in (True, float('nan'), float('inf')):
            with self.subTest(deadline=invalid), self.assertRaises(ValueError):
                workspace.constrain_deadline(invalid)


class SandboxConstructionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.executable = self.root / 'bwrap'; self.executable.write_text('#!/bin/sh\nexit 88\n'); self.executable.chmod(0o700)
        self.dependencies = self.root / 'dependencies'; self.dependencies.mkdir()
        (self.dependencies / 'marker.txt').write_text('fixture dependency bytes')
        self.config = {'kind': 'bwrap', 'executable': str(self.executable), 'python': str(Path(sys.executable).resolve()),
                       'dependencies': str(self.dependencies), 'runtime_roots': [str(Path(sys.executable).resolve().parent.parent)]}

    def tearDown(self):
        self.temp.cleanup()

    def test_no_saved_boolean_or_config_can_skip_actual_probe(self):
        runner = require('SandboxRunner')(self.config)
        self.assertFalse(runner.verified)
        with self.assertRaisesRegex(ValueError, 'verified_os_sandbox_required'):
            runner.run_observer(workspace=self.root, bootstrap=self.executable, config=self.executable,
                                output=self.root, timeout=10)

    def test_linux_command_hides_host_root_and_unshares_network(self):
        runner = require('SandboxRunner')(self.config)
        workspace = self.root / 'workspace'; workspace.mkdir()
        output = self.root / 'output'; output.mkdir()
        bootstrap = self.root / 'observer.py'; bootstrap.write_text('pass\n')
        cfg = self.root / 'config.json'; cfg.write_text('{}\n')
        command = runner.command(workspace=workspace, bootstrap=bootstrap, config=cfg, output=output)
        self.assertIn('--unshare-net', command['argv'])
        self.assertIn('--unshare-all', command['argv'])
        self.assertIn('--die-with-parent', command['argv'])
        self.assertNotIn('--share-net', command['argv'])
        self.assertNotIn('--not-a-security-boundary', command['argv'])
        for index, token in enumerate(command['argv']):
            if token in ('--bind', '--ro-bind'):
                self.assertNotEqual(command['argv'][index + 1], '/')
        self.assertEqual(command['paths']['workspace'], '/p1/workspace')

    def test_overbroad_runtime_mounts_are_rejected(self):
        for unsafe in ('/', '/home', '/Users', '/workspace', '/tmp', '/etc'):
            with self.subTest(root=unsafe), self.assertRaises(ValueError):
                require('SandboxRunner')({**self.config, 'runtime_roots': [unsafe]})

    def test_precise_dependency_runtime_below_config_does_not_grant_config_root(self):
        config_root = self.root / '.config'; runtime_root = config_root / 'dependencies/python-runtime'
        runtime_root.mkdir(parents=True)
        python = runtime_root / 'python'; python.write_text('# fixture only\n'); python.chmod(0o700)
        narrow = {**self.config, 'python': str(python), 'runtime_roots': [str(runtime_root)]}
        runner = require('SandboxRunner')(narrow)
        self.assertEqual(runner.config['runtime_roots'], [str(runtime_root)])
        with self.assertRaises(ValueError):
            require('SandboxRunner')({**narrow, 'runtime_roots': [str(config_root)]})

    def test_macos_profile_is_default_deny_and_writes_only_bound_paths(self):
        config = {**self.config, 'kind': 'sandbox-exec'}
        executable = self.root / 'sandbox-exec'; executable.write_text('#!/bin/sh\nexit 88\n'); executable.chmod(0o700)
        config['executable'] = str(executable)
        runner = require('SandboxRunner')(config)
        workspace = self.root / 'workspace'; workspace.mkdir()
        output = self.root / 'output'; output.mkdir()
        bootstrap = self.root / 'observer.py'; bootstrap.write_text('pass\n')
        cfg = self.root / 'config.json'; cfg.write_text('{}\n')
        command = runner.command(workspace=workspace, bootstrap=bootstrap, config=cfg, output=output)
        self.assertEqual(command['argv'][1], '-f')
        profile = Path(command['argv'][2]).read_text()
        self.assertIn('(deny default)', profile)
        self.assertIn('(deny network*)', profile)
        self.assertNotIn('(allow file-read*)', profile)
        self.assertNotIn('(allow network', profile)
        # macOS getcwd requires the root directory itself, not its children.
        self.assertIn('(allow file-read* (literal "/"))', profile)
        self.assertNotIn('(allow file-read* (subpath "/"))', profile)
        self.assertEqual(command['paths']['workspace'], str(workspace))

    def fake_probe_process(self, argv, *, cwd, env, timeout, directory, **kwargs):
        cfg = json.loads((directory.parent.parent / 'probe-config.json').read_text())
        report = {'nonce': cfg['nonce'], 'checks': {key: True for key in
            ('allowed_read', 'allowed_write', 'private_read_denied', 'private_write_denied', 'loopback_connection_denied')}}
        (directory / 'stdout.raw').write_text(json.dumps(report) + '\n')
        (directory / 'stderr.raw').write_text('')
        (directory.parent / 'sandbox-output/allowed-write.txt').write_text(cfg['nonce'])
        return {'spawned': True, 'returncode': 0, 'signal': None, 'error': None, 'timed_out': False, 'output_limit_exceeded': False}

    def test_probe_binding_expires_when_dependency_bytes_change(self):
        runner = require('SandboxRunner')(self.config)
        with mock.patch.dict(API['WORKFLOW'], {'run_process': self.fake_probe_process}):
            receipt = runner.probe(self.root / 'probe')
        self.assertEqual(receipt['status'], 'passed')
        self.assertTrue(runner.verified)
        (self.dependencies / 'marker.txt').write_text('changed dependency bytes')
        self.assertFalse(runner.verified)

    def test_claimed_probe_success_without_controller_observed_write_stays_failed(self):
        runner = require('SandboxRunner')(self.config)
        def false_report(*args, **kwargs):
            result = self.fake_probe_process(*args, **kwargs)
            (kwargs['directory'].parent / 'sandbox-output/allowed-write.txt').unlink()
            return result
        with mock.patch.dict(API['WORKFLOW'], {'run_process': false_report}):
            receipt = runner.probe(self.root / 'probe')
        self.assertEqual(receipt['status'], 'failed')
        self.assertTrue(receipt['private_sentinel_unchanged'])
        self.assertFalse(runner.verified)
        self.assertTrue((self.root / 'probe/probe-receipt.json').is_file())

    def test_test_exit_zero_without_observer_is_not_a_passing_test(self):
        runner = require('SandboxRunner')(self.config)
        with mock.patch.dict(API['WORKFLOW'], {'run_process': self.fake_probe_process}):
            runner.probe(self.root / 'probe')
        workspace = require('PublicWorkspace')(PUBLIC, self.root / 'workspace', self.root / 'controller',
            authorize_operation=lambda intent: {'operation_id': intent['operation_id'], 'admitted_kinds': intent['kinds']},
            sandbox=runner, python=sys.executable)
        dependency_snapshot = API['WORKFLOW']['snapshot'](self.dependencies)
        runtime = {'target': Path(sys.executable).resolve(), 'site': self.dependencies, 'venv': self.dependencies.parent,
                   'report': {'requirements_match': True, 'dependency_tree_sha256': dependency_snapshot['version']},
                   'dependency_snapshot': dependency_snapshot}
        def zero_without_observer(argv, *, directory, **kwargs):
            (directory / 'stdout.raw').write_text('exit zero is not a pytest observation\n')
            (directory / 'stderr.raw').write_text('')
            return {'spawned': True, 'returncode': 0, 'signal': None, 'error': None, 'timed_out': False, 'output_limit_exceeded': False}
        with mock.patch.dict(API['WORKFLOW'], {'runtime': lambda *args: runtime, 'run_process': zero_without_observer}):
            outcome = workspace.call('run_current_tests', {})
        self.assertTrue(outcome['ok'])
        self.assertEqual(outcome['result']['status'], 'unknown')
        self.assertFalse(outcome['result']['completed'])
        self.assertEqual(outcome['result']['exitCode'], 0)
        self.assertIsNone(outcome['result']['testCount'])
        self.assertEqual(outcome['result']['reason'], 'missing_or_unbound_pytest_observation')


if __name__ == '__main__':
    unittest.main()
