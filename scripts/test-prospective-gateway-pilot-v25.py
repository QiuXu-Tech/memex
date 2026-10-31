#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest

script = pathlib.Path(__file__).with_name('prospective-gateway-pilot-v25.py')
spec = importlib.util.spec_from_file_location('pilot_v25', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Tests(unittest.TestCase):
    def test_balanced_arms_and_nonindependent_adjudicator(self):
        schedule = module.pilot.schedule()
        self.assertEqual(len(schedule), 6)
        for issue in module.pilot.TASKS:
            self.assertEqual({v['arm'] for v in schedule if v['issue'] == issue}, {'memex', 'keyword'})
        self.assertEqual(module.pilot.ADJUDICATOR, module.pilot.SOLVER)


if __name__ == '__main__':
    unittest.main()
