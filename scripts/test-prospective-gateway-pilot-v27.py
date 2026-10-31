#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('pilot_v27', pathlib.Path(__file__).with_name('prospective-gateway-pilot-v27.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PilotTest(unittest.TestCase):
    def test_no_history_and_identical_ids_are_not_eligible(self):
        self.assertFalse(module.distinct_history({'keywordIds': [], 'memexIds': []}))
        self.assertFalse(module.distinct_history({'keywordIds': ['a', 'b'], 'memexIds': ['b', 'a']}))
        self.assertTrue(module.distinct_history({'keywordIds': ['a'], 'memexIds': ['a', 'b']}))

    def test_each_issue_has_both_arms(self):
        schedule = module.pilot.schedule()
        self.assertEqual(len(schedule), 2 * len(module.pilot.TASKS))
        for issue in module.pilot.TASKS:
            self.assertEqual({x['arm'] for x in schedule if x['issue'] == issue}, {'keyword', 'memex'})

    def test_registered_model_output_limits_are_used(self):
        with patch.object(module.prospective_gateway, 'call', return_value={'status': 'ok'}) as call:
            module.api('key', 'qwen3.8-flash', [], 700, None, 'x')
            self.assertEqual(call.call_args.args[3], 2048)
            module.api('key', 'gpt-6.1-sol', [], 700, None, 'x')
            self.assertEqual(call.call_args.args[3], 1200)
            module.api('key', 'deepseek-flash', [], 700, None, 'x')
            self.assertEqual(call.call_args.args[3], 700)


if __name__ == '__main__':
    unittest.main()
