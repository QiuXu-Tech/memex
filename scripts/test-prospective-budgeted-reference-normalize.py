#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import unittest

script = pathlib.Path(__file__).with_name('prospective-budgeted-reference-normalize.py')
spec = importlib.util.spec_from_file_location('normalizer', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Tests(unittest.TestCase):
    def test_known_aliases_only_and_no_other_repairs(self):
        item = {'correctness': 2, 'side_effects': 1, 'reason': 'partial',
                'references': ['issue', 'candidateDiff', 'acceptance', 'regressionControls']}
        result = module.normalize(json.dumps(item), 'stop')
        self.assertEqual(result['status'], 'POSTHOC_NORMALIZED')
        self.assertEqual(result['parsed']['rating']['references'], ['issue', 'candidate', 'checks'])
        item['references'].append('unknown')
        self.assertEqual(module.normalize(json.dumps(item), 'stop')['status'], 'INVALID')
        item['references'] = ['candidateDiff']
        item['correctness'] = True
        self.assertEqual(module.normalize(json.dumps(item), 'stop')['status'], 'INVALID')
        self.assertEqual(module.normalize(json.dumps(item), 'length')['status'], 'INVALID')


if __name__ == '__main__':
    unittest.main()
