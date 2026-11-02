#!/usr/bin/env python3
"""Test blind rescue score verification and event tamper detection."""
import importlib.util
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('rescue_aggregate', ROOT / 'scripts/aggregate-task-state-rescue-20261102.py')
agg = importlib.util.module_from_spec(spec); spec.loader.exec_module(agg)

def rating(a, b, adjudication=False):
    row = {'candidates': [{'id': 'C01', 'score': a, 'reason': 'supported', 'references': ['final:C01'], 'unsupportedClaims': []},
                          {'id': 'C02', 'score': b, 'reason': 'supported', 'references': ['final:C02'], 'unsupportedClaims': []}]}
    if adjudication: row['materialDisagreement'] = True
    return row

def event(label, value):
    return {'operationLabel': label, 'status': 'ok', 'finishReason': 'stop', 'message': {'content': json.dumps(value)}}

class RescueAggregationTest(unittest.TestCase):
    def setUp(self):
        self.task = {'task': 'task-1', 'reason': 'REPLACE_ONE'}
        self.plan = {'reviewers': ['orig-a', 'orig-b'], 'adjudicator': 'gemini-3.8-flash'}
        self.packet = {'evidence': {'final:C01': {}, 'final:C02': {}}}; self.key = {'C01': 'baseline', 'C02': 'memex'}
        a, b, final = rating(1, 1), rating(2, 1), rating(2, 1, True)
        self.original = [event('task-1:orig-b', b)]
        self.extra = [event('task-1:fallback', a), event('task-1:adjudication', final)]
        self.result = {'task': 'task-1', 'replacedModels': ['orig-a'],
                       'reviews': [{'model': 'gpt-6.1-terra', 'rating': a}, {'model': 'orig-b', 'rating': b}],
                       'adjudication': {'model': 'gemini-3.8-flash', 'status': 'ok', 'rating': final}}

    def evaluate(self):
        return agg.evaluate_one(self.task, self.result, self.plan, self.original, self.extra, self.packet, self.key)

    def test_independent_unblinding_and_adjudication(self):
        result = self.evaluate()
        self.assertEqual(result['scores'], {'baseline': 2, 'memex': 1})
        self.assertTrue(result['numericReviewerDisagreement'])
        self.assertTrue(result['adjudicated'])

    def test_changed_gateway_rating_is_rejected(self):
        self.extra[0]['message']['content'] = json.dumps(rating(2, 2))
        with self.assertRaises(AssertionError): self.evaluate()

    def test_invalid_evidence_is_not_converted_to_a_score(self):
        bad = rating(1, 1); bad['candidates'][0]['references'] = ['made-up']
        self.extra[0] = event('task-1:fallback', bad)
        self.result['reviews'][0]['rating'] = None
        self.assertIsNone(self.evaluate())

    def test_insufficient_evidence_stays_missing(self):
        empty = rating(None, 1); self.extra[0] = event('task-1:fallback', empty)
        self.result['reviews'][0]['rating'] = empty
        self.assertIsNone(self.evaluate())

if __name__ == '__main__': unittest.main()
