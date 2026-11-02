#!/usr/bin/env python3
import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent

class StreamUsageTest(unittest.TestCase):
    def test_recovery_mismatch_is_reported_without_imputation(self):
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory); (base / 'registration.json').write_text(json.dumps({'tasks': [{'id': 'task-01'}]}))
            folder = base / 'task-01'; (folder / 'results').mkdir(parents=True); (folder / 'traces').mkdir()
            usage = {'input_tokens': 1, 'cache_read_input_tokens': 2, 'cache_creation_input_tokens': 3}
            for arm in ('baseline', 'memex'):
                for stage in (1, 2, 3):
                    name = f'{arm}-s{stage}'; recovery = name == 'memex-s1'
                    summary = {'responseCompleted': True, 'recovery': {'usage': usage} if recovery else None,
                               'initialAttempt': {'usage': {'input_tokens': 1, 'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0}}}
                    (folder / 'results' / f'{name}.json').write_text(json.dumps(summary))
                    event = {'type': 'assistant', 'message': {'id': name, 'usage': usage}}
                    (folder / 'traces' / f'{name}-events.jsonl').write_text(json.dumps(event) + '\n')
                    if recovery:
                        event['message']['id'] += '-recovery'
                        (folder / 'traces' / f'{name}-recovery-events.jsonl').write_text(json.dumps(event) + '\n')
            output = base / 'result.json'
            subprocess.run(['python3', '-B', str(ROOT / 'scripts/summarize-task-state-stream-usage-20261102.py'), str(base), str(output)], check=True, capture_output=True)
            result = json.loads(output.read_text())
            self.assertEqual(result['distinctAssistantMessageIds'], 7)
            self.assertEqual(result['recoveredInitialSummaryComparison']['initialDiffers'], 1)
            self.assertEqual(result['completePairsWithAllStreamedInput'], 1)
            self.assertEqual(result['streamedInputByArmForThosePairs'], {'baseline': 18, 'memex': 24})
            self.assertNotIn('output_tokens', result['streamedInputTotals'])

if __name__ == '__main__': unittest.main()
