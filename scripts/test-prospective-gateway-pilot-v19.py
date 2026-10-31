#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest

script = pathlib.Path(__file__).with_name('prospective-gateway-pilot-v19.py')
spec = importlib.util.spec_from_file_location('pilot_v19', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Tests(unittest.TestCase):
    def test_all_issues_have_both_arms(self):
        schedule = module.pilot.schedule()
        self.assertEqual(len(schedule), 4)
        for issue in module.pilot.TASKS:
            self.assertEqual({v['arm'] for v in schedule if v['issue'] == issue}, {'memex', 'keyword'})


if __name__ == '__main__':
    unittest.main()
