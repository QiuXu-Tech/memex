#!/usr/bin/env python3
import importlib.util
import pathlib
import tempfile
import unittest

script = pathlib.Path(__file__).with_name('prospective-gateway-posthoc-v15.py')
spec = importlib.util.spec_from_file_location('posthoc_v15', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Tests(unittest.TestCase):
    def test_modified_candidate_is_rejected_before_review(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            path = root / 'candidate.diff'
            path.write_text('original')
            manifest = {'runHashes': {'candidate.diff': module.pilot.SHA(path.read_bytes())}}
            module.check_run_hashes(root, manifest)
            path.write_text('changed')
            with self.assertRaises(SystemExit):
                module.check_run_hashes(root, manifest)


if __name__ == '__main__':
    unittest.main()
