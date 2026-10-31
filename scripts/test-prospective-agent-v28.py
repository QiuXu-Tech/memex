#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import unittest
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('agent', pathlib.Path(__file__).with_name('prospective_agent_v28.py'))
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class AgentTest(unittest.TestCase):
    def test_excess_tools_are_denied_and_all_calls_get_results(self):
        calls = [{'id': str(i), 'function': {'name': 'repo_edit', 'arguments': json.dumps({'path': str(i), 'old': 'x', 'new': 'y'})}} for i in range(6)]
        executed, logs = [], []
        pilot = SimpleNamespace(rpc=lambda worker, req: executed.append(req) or {'path': req['path']},
                                append=lambda path, event: logs.append(event), NOW=lambda: 'now')
        result = {'toolCalls': 0, 'deniedToolCalls': 0, 'publicTestCalls': 0}
        changed = set()
        messages = agent.dispatch(pilot, None, calls, changed, result, pathlib.Path('/tmp/no-write'))
        self.assertEqual(len(executed), 4)
        self.assertEqual(result['deniedToolCalls'], 2)
        self.assertEqual(len(messages), 6)
        self.assertEqual(changed, {'0', '1', '2', '3'})
        self.assertTrue(all(not log['executed'] for log in logs[4:]))
        self.assertEqual(json.loads(messages[4]['content'])['errorType'], 'ToolLimitExceeded')

    def test_invalid_tools_get_an_error_without_dispatch(self):
        logs = []
        pilot = SimpleNamespace(rpc=lambda *args: self.fail('invalid tool was dispatched'),
                                append=lambda path, event: logs.append(event), NOW=lambda: 'now')
        result = {'toolCalls': 0, 'deniedToolCalls': 0, 'publicTestCalls': 0}
        calls = [{'id': 'a', 'function': {'name': 'repo_edit', 'arguments': '{"path":"x","unexpected":1}'}}]
        messages = agent.dispatch(pilot, None, calls, set(), result, pathlib.Path('/tmp/no-write'))
        self.assertFalse(logs[0]['executed'])
        self.assertEqual(json.loads(messages[0]['content'])['errorType'], 'ValueError')


if __name__ == '__main__':
    unittest.main()
