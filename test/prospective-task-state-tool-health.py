#!/usr/bin/env python3
import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent

class ToolHealthTest(unittest.TestCase):
    def test_counts_outcomes_repeats_and_invalid_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory); (base / 'registration.json').write_text(json.dumps({'tasks': [{'id': 'task-01'}]}))
            trace = base / 'task-01/traces'; trace.mkdir(parents=True)
            name = 'mcp__memex__memory_write'; args = {'title': 'x'}
            events = [{'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': 'a', 'name': name, 'input': args}, {'type': 'tool_use', 'id': 'b', 'name': name, 'input': args}]}},
                      {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'a', 'is_error': True}, {'type': 'tool_result', 'tool_use_id': 'b'}]}}]
            (trace / 'memex-s1-events.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in events))
            rows = [{'name': 'repo_search', 'status': 'error', 'error': 'invalid query', 'arguments': {'limit': 50}},
                    {'name': 'repo_search', 'status': 'ok', 'result': {'limitAdjustment': {'requested': 50, 'applied': 30}}}]
            (trace / 'memex-s1-tools.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
            output = base / 'result.json'
            subprocess.run(['python3', '-B', str(ROOT / 'scripts/summarize-task-state-tool-health-20261102.py'), str(base), str(output)], check=True, capture_output=True)
            result = json.loads(output.read_text())
            self.assertEqual(result['exactRepeatedCallsByArm']['memex'], 1)
            self.assertEqual(result['toolOutcomesByArm']['memex'][name], {'error': 1, 'success': 1})
            self.assertEqual(result['tasksWithSuccessfulTool']['memex:' + name], 1)
            self.assertEqual(result['pilotErrors']['searchAboveMaximum'], 1)
            self.assertEqual(result['pilotErrors']['searchLimitsAdjusted'], 1)

if __name__ == '__main__': unittest.main()
