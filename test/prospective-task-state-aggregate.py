#!/usr/bin/env python3
"""Offline reconciliation and tamper-detection checks for the replay report."""
import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('task_state_aggregate', ROOT / 'scripts/aggregate-task-state-20261102.py')
agg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agg)

def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')

def lines(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))

class AggregateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = pathlib.Path(self.tmp.name)
        agg.BASE, agg.PUBLISHED = root / 'private', root / 'published'
        base, pub = agg.BASE, agg.PUBLISHED
        task = {'id': 'task-01', 'issueUrl': 'https://example.test/1', 'sourceCommit': 'abc', 'discussionSpanDays': 30}
        registration = {'memexCommit': 'abc', 'tasks': [task]}
        plan = {'reviewers': ['gpt-6.1-sol', 'deepseek-flash']}
        save(base / 'registration.json', registration); save(pub / 'registration.json', registration)
        save(base / 'reviews/plan.json', plan); save(pub / 'review-plan.json', plan)
        folder = base / 'reviews/task-01'; key = {'C01': 'baseline', 'C02': 'memex'}; salt = 'fixture-salt'
        packet = {'evidence': {'final:C01': {}, 'final:C02': {}}}
        save(folder / 'key.json', key); save(folder / 'salt.json', {'nonce': salt}); save(folder / 'packet.json', packet)
        encoded = json.dumps(key, sort_keys=True, separators=(',', ':'))
        commitments = {'packets': [{'task': 'task-01', 'packetSha256': agg.audit.digest(folder / 'packet.json'),
                                    'saltedKeyCommitmentSha256': hashlib.sha256((salt + '\0' + encoded).encode()).hexdigest()}]}
        save(base / 'reviews/commitments.json', commitments); save(pub / 'packet-commitments.json', commitments)
        rating = {'candidates': [{'id': 'C01', 'score': 2, 'references': ['final:C01'], 'unsupportedClaims': []},
                                 {'id': 'C02', 'score': 1, 'references': ['final:C02'], 'unsupportedClaims': []}]}
        gateway = []
        for model in plan['reviewers']:
            save(folder / f'{model}.json', {'model': model, 'rating': rating})
            gateway.append({'operationLabel': f'task-01:{model}', 'status': 'ok', 'model': model,
                            'message': {'content': json.dumps(rating)}, 'usage': {'prompt_tokens': 10, 'completion_tokens': 3}})
        lines(folder / 'gateway.jsonl', gateway)
        usage = {'input_tokens': 3, 'cache_creation_input_tokens': 1, 'cache_read_input_tokens': 2, 'output_tokens': 2}
        for arm in ('baseline', 'memex'):
            for stage in (1, 2, 3):
                name = f'{arm}-s{stage}'; session_id = f'{arm}-{stage}'
                row = {'arm': arm, 'stage': stage, 'status': 'success', 'sessionId': session_id,
                       'responseCompleted': True, 'usage': usage, 'clientListPriceUsd': 0.01, 'final': 'answer'}
                save(base / 'task-01/results' / f'{name}.json', row)
                parts = []
                if name == 'memex-s1':
                    parts = [{'type': 'tool_use', 'id': 'write', 'name': 'mcp__memex__memory_write', 'input': {}}]
                if name == 'memex-s2':
                    parts = [{'type': 'tool_use', 'id': 'open', 'name': 'mcp__memex__memory_open', 'input': {'id': 'mem_abcd123456'}}]
                events = [{'type': 'assistant', 'message': {'id': name, 'usage': usage, 'content': parts}}]
                if parts:
                    result = 'Stored mem_abcd123456' if stage == 1 else 'mem_abcd123456: saved context'
                    events.append({'type': 'user', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': parts[0]['id'], 'content': [{'type': 'text', 'text': result}]}]}})
                events.append({'type': 'result', 'subtype': 'success', 'result': 'answer', 'session_id': session_id})
                lines(base / 'task-01/traces' / f'{name}-events.jsonl', events)

    def tearDown(self):
        self.tmp.cleanup()

    def test_recounts_blind_scores_tokens_and_cross_session_open(self):
        result, unblinded = agg.reconcile()
        self.assertEqual((result['completePairs'], result['validRatedPairs']), (1, 1))
        self.assertEqual(result['scoreDirections'], {'memexHigher': 0, 'tie': 0, 'baselineHigher': 1})
        self.assertEqual(result['verifiedTokenPairs'], 1)
        self.assertEqual(result['verifiedTokens']['baseline']['input'], 18)
        self.assertEqual(result['memoryEvents']['agentWriteThenSuccessfulOpen'], 1)
        self.assertEqual(result['clientListPriceKnownUsd'], 0.06)
        self.assertEqual(len(unblinded), 1)

    def test_changed_raw_completion_is_rejected(self):
        path = agg.BASE / 'task-01/results/baseline-s3.json'; row = json.loads(path.read_text())
        row['final'] = 'changed'; save(path, row)
        with self.assertRaises(AssertionError): agg.reconcile()

if __name__ == '__main__':
    unittest.main()
