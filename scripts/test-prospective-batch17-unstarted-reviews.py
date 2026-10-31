#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('followup', pathlib.Path(__file__).with_name('prospective-batch17-unstarted-reviews.py'))
followup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(followup)


class UnstartedReviewsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        (self.root / 'blind-key.json').write_text(json.dumps({'B04': 6, 'B05': 5, 'B06': 3}))
        (self.root / 'review-calls.jsonl').write_text(json.dumps({'label': 'B04:qwen3.8-flash#attempt-1', 'status': 'error'}) + '\n')
        (self.root / 'reviews').mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_selects_only_never_started_candidates(self):
        self.assertEqual(followup.check_unstarted(self.root), [('B05', 5), ('B06', 3)])

    def test_rejects_even_an_unfinished_started_request(self):
        with (self.root / 'review-calls.jsonl').open('a') as out:
            out.write(json.dumps({'label': 'B05:deepseek-flash#attempt-1', 'status': 'started'}) + '\n')
        with self.assertRaises(ValueError):
            followup.check_unstarted(self.root)

    def test_rejects_existing_output(self):
        (self.root / 'reviews' / 'B06-qwen3.8-flash.json').write_text('{}')
        with self.assertRaises(ValueError):
            followup.check_unstarted(self.root)

    def test_rejects_changed_blind_mapping(self):
        (self.root / 'blind-key.json').write_text(json.dumps({'B05': 3, 'B06': 5}))
        with self.assertRaises(ValueError):
            followup.check_unstarted(self.root)


if __name__ == '__main__':
    unittest.main()
