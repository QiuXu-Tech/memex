#!/usr/bin/env python3
"""Offline checks of staged replay and fresh-session completion semantics."""
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('task_state_runner', ROOT / 'scripts/prospective-task-state-runner-20261102.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

class StagedReplay(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name)
        runner.BASE, runner.SRC = base / 'results', base / 'source'
        runner.BASE.mkdir(); runner.SRC.mkdir()
        self.task = {'id': 'task-01', 'repo': 'example/repo', 'issue': 1, 'sourceCommit': 'abc'}
        issue = {'title': 'Example', 'url': 'https://example.test/issue', 'body': 'Issue text',
                 'comments': {'nodes': [{'createdAt': '2026-01-01', 'body': f'comment {i}', 'url': f'https://example.test/{i}'} for i in range(1, 7)]}}
        (runner.SRC / 'task-01.issue.json').write_text(json.dumps(issue))
        (runner.BASE / 'task-01').mkdir()
        runner.budget = runner.Budget()
        self.observed = []
        self.duplicate_third = False
        self.original = runner.collect_client
        def collect(command, host, env, output_path, error_path):
            stage = int(output_path.name.split('-s')[1].split('-')[0])
            archive = runner.BASE / 'task-01' / 'archives' / 'baseline.json'
            self.observed.append(json.loads(archive.read_text()))
            session_id = f'session-{1 if stage == 3 and self.duplicate_third else stage}'
            event = {'type': 'result', 'subtype': 'success', 'session_id': session_id,
                     'result': f'handoff {stage}', 'total_cost_usd': 0, 'usage': {}}
            return {'events': [event], 'exitCode': 0, 'timeout': False, 'shutdownTimeoutAfterResult': False}
        runner.collect_client = collect

    def tearDown(self):
        runner.collect_client = self.original
        self.tmp.cleanup()

    def run_stages(self):
        return [runner.session(self.task, 'baseline', stage, 'unused') for stage in (1, 2, 3)]

    def test_stages_expose_later_comments_and_own_handoffs(self):
        results = self.run_stages()
        self.assertTrue(all(result['responseCompleted'] for result in results))
        self.assertEqual([[row['id'] for row in stage] for stage in self.observed],
                         [['C1', 'C2'], ['C1', 'C2', 'C3', 'C4', 'HANDOFF1'],
                          ['C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'HANDOFF1', 'HANDOFF2']])

    def test_reused_first_session_is_incomplete(self):
        self.duplicate_third = True
        results = self.run_stages()
        self.assertFalse(results[-1]['responseCompleted'])

if __name__ == '__main__':
    unittest.main()
