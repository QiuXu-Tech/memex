#!/usr/bin/env python3
"""Exercise blind-review rescue eligibility without network calls."""
import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('rescue', ROOT / 'scripts/rescue-task-state-reviews-20261102.py')
rescue = importlib.util.module_from_spec(spec); spec.loader.exec_module(rescue)


def rating(a=1, b=1, claims=None):
    return {'rating': {'candidates': [
        {'id': 'C01', 'score': a, 'unsupportedClaims': claims or []},
        {'id': 'C02', 'score': b, 'unsupportedClaims': []}]}}


class EligibilityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.folder = pathlib.Path(self.tmp.name)
        self.models = ['review-a', 'review-b']

    def tearDown(self): self.tmp.cleanup()
    def save(self, name, value): (self.folder / name).write_text(json.dumps(value))
    def classify(self): return rescue.classify(self.folder, self.models)

    def test_reviewability_and_multiple_missing(self):
        self.assertEqual(self.classify(), 'MULTIPLE_MISSING')
        self.save('review-status.json', {'status': 'NOT_REVIEWABLE'})
        self.assertEqual(self.classify(), 'NOT_REVIEWABLE')

    def test_replace_one_missing_but_not_explicit_insufficient_evidence(self):
        self.save('review-a.json', rating())
        self.assertEqual(self.classify(), 'REPLACE_ONE')
        self.save('review-a.json', rating(None, 1))
        self.assertEqual(self.classify(), 'INSUFFICIENT_EVIDENCE')
        self.save('review-b.json', rating())
        self.assertEqual(self.classify(), 'INSUFFICIENT_EVIDENCE')

    def test_adjudication_is_retried_only_for_disagreements(self):
        self.save('review-a.json', rating())
        self.save('review-b.json', rating())
        self.assertEqual(self.classify(), 'NO_RESCUE_NEEDED')
        self.save('review-b.json', rating(2, 1))
        self.assertEqual(self.classify(), 'RETRY_ADJUDICATION')
        self.save('adjudication.json', {'rating': {'valid': True}})
        self.assertEqual(self.classify(), 'NO_RESCUE_NEEDED')

    def test_unsupported_claim_disagreement_is_adjudicated(self):
        self.save('review-a.json', rating())
        self.save('review-b.json', rating(claims=['unsupported']))
        self.assertEqual(self.classify(), 'RETRY_ADJUDICATION')

if __name__ == '__main__': unittest.main()
