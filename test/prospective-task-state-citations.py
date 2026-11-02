#!/usr/bin/env python3
import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent

class CitationTest(unittest.TestCase):
    def test_citation_requires_earlier_record_and_successful_open(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory); (base / 'registration.json').write_text(json.dumps({'tasks': [{'id': 'task-01'}]}))
            folder = base / 'task-01'; (folder / 'results').mkdir(parents=True); (folder / 'traces').mkdir()
            for arm in ('baseline', 'memex'):
                for stage in (1, 2, 3):
                    name = f'{arm}-s{stage}'; row = {'responseCompleted': True, 'sessionId': name, 'final': 'See mem_1234567890' if name == 'memex-s3' else 'Earlier answer'}
                    (folder / 'results' / f'{name}.json').write_text(json.dumps(row))
            def trace(stage, tool, input_data, returned):
                events = [{'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': tool, 'name': 'mcp__memex__memory_' + tool, 'input': input_data}]}},
                          {'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': tool, 'content': [{'type': 'text', 'text': returned}]}]}}]
                (folder / 'traces' / f'memex-s{stage}-events.jsonl').write_text(''.join(json.dumps(x) + '\n' for x in events))
            trace(1, 'write', {}, 'Stored mem_1234567890')
            trace(2, 'open', {'id': 'mem_1234567890'}, 'mem_1234567890: saved')
            output = base / 'result.json'; command = ['python3', '-B', str(ROOT / 'scripts/summarize-task-state-citations-20261102.py'), str(base), str(output)]
            subprocess.run(command, check=True, capture_output=True); result = json.loads(output.read_text())
            self.assertEqual(result['finalCitesEarlierRecord'], 1)
            self.assertEqual(result['finalCitesEarlierOpenedRecord'], 1)
            self.assertEqual(result['finalCitesEarlierRecalledRecord'], 0)
            trace(2, 'open', {'id': 'mem_9999999999'}, 'mem_9999999999: unrelated')
            subprocess.run(command, check=True, capture_output=True); result = json.loads(output.read_text())
            self.assertEqual(result['finalCitesEarlierRecord'], 1)
            self.assertEqual(result['finalCitesEarlierOpenedRecord'], 0)
            first = folder / 'traces' / 'memex-s1-events.jsonl'; first.unlink()
            events = [{'type': 'assistant', 'message': {'content': [
                {'type': 'tool_use', 'id': 'w2', 'name': 'mcp__memex__memory_write', 'input': {}},
                {'type': 'tool_use', 'id': 'o2', 'name': 'mcp__memex__memory_open', 'input': {'id': 'mem_1234567890'}}]}},
                {'type': 'user', 'message': {'content': [
                    {'type': 'tool_result', 'tool_use_id': 'w2', 'content': [{'type': 'text', 'text': 'Stored mem_1234567890'}]},
                    {'type': 'tool_result', 'tool_use_id': 'o2', 'content': [{'type': 'text', 'text': 'mem_1234567890: saved'}]}]}}]
            (folder / 'traces' / 'memex-s2-events.jsonl').write_text(''.join(json.dumps(x) + '\n' for x in events))
            subprocess.run(command, check=True, capture_output=True); result = json.loads(output.read_text())
            self.assertEqual(result['finalCitesEarlierRecord'], 1)
            self.assertEqual(result['finalCitesEarlierOpenedRecord'], 0)

if __name__ == '__main__': unittest.main()
