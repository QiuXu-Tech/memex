#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import tempfile
import unittest

script = pathlib.Path(__file__).with_name('prospective-gateway-pilot-v26.py')
spec = importlib.util.spec_from_file_location('pilot_v26', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Tests(unittest.TestCase):
    def test_rejects_any_started_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root / 'manifest.json').write_text(json.dumps({'schedule': [{'issue': '12191'}, {'issue': '12191'}]}))
            (root / 'solver-calls.jsonl').write_text(json.dumps({'operationLabel': '01:0', 'status': 'started'}) + '\n')
            for slot in (1, 2):
                path = root / 'runs' / f'{slot:02d}' / 'result.json'
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps({'status': 'NOT_RUN_AFTER_STOP'}))
            with self.assertRaises(SystemExit):
                module.unstarted(root)


if __name__ == '__main__':
    unittest.main()
