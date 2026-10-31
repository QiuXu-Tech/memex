#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest
from unittest import mock

script = pathlib.Path(__file__).with_name('prospective-gateway-posthoc-v15-budgeted.py')
spec = importlib.util.spec_from_file_location('budgeted_posthoc', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Tests(unittest.TestCase):
    def test_only_reasoning_reviewer_budgets_are_increased(self):
        with mock.patch.object(module.prospective_gateway, 'call') as call:
            for model, expected in (('deepseek-flash', 700), ('qwen3.8-flash', 2048), ('gemini-3.8-flash', 2048)):
                module.budgeted_api('key', model, [], 700, 'trace', 'label')
                self.assertEqual(call.call_args.args[3], expected)


if __name__ == '__main__':
    unittest.main()
