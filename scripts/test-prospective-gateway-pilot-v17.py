#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest
from unittest import mock

script = pathlib.Path(__file__).with_name('prospective-gateway-pilot-v17.py')
spec = importlib.util.spec_from_file_location('pilot_v17', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Tests(unittest.TestCase):
    def test_balanced_schedule_and_review_budgets(self):
        schedule = module.pilot.schedule()
        self.assertEqual(len(schedule), 8)
        for issue in module.pilot.TASKS:
            self.assertEqual({v['arm'] for v in schedule if v['issue'] == issue}, {'memex', 'keyword'})
        with mock.patch.object(module.prospective_gateway, 'call') as call:
            for model, expected in (('gpt-6-astra', 1000), ('deepseek-flash', 700), ('qwen3.8-flash', 2048), ('gemini-3.8-flash', 2048)):
                limit = 1000 if model == 'gpt-6-astra' else 700
                module.budgeted_api('key', model, [], limit, 'trace', 'label')
                self.assertEqual(call.call_args.args[3], expected)


if __name__ == '__main__':
    unittest.main()
