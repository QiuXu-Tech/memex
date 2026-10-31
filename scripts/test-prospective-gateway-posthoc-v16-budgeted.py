#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest

script = pathlib.Path(__file__).with_name('prospective-gateway-posthoc-v16-budgeted.py')
spec = importlib.util.spec_from_file_location('dayjs_posthoc', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Tests(unittest.TestCase):
    def test_only_two_valid_different_scores_trigger_adjudication(self):
        rating = lambda c, s: {'valid': True, 'rating': {'correctness': c, 'side_effects': s}}
        self.assertTrue(module.different(rating(2, 1), rating(2, 2)))
        self.assertFalse(module.different(rating(2, 1), rating(2, 1)))
        self.assertFalse(module.different(rating(2, 1), {'valid': False}))


if __name__ == '__main__':
    unittest.main()
