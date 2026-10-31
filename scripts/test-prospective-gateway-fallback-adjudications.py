#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import tempfile
import unittest

script = pathlib.Path(__file__).with_name('prospective-gateway-fallback-adjudications.py')
spec = importlib.util.spec_from_file_location('fallback_many', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Tests(unittest.TestCase):
    def test_changed_packet_is_rejected_before_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory);packet = root / 'packets' / 'F01.json';packet.parent.mkdir();packet.write_text('{}')
            (root / 'manifest.json').write_text(json.dumps({'runnerSha256': module.pilot.SHA(script.read_bytes()),
                                                            'candidates': [{'blind': 'F01', 'packetSha256': 'bad'}]}))
            with self.assertRaises(SystemExit):module.run(root)
            self.assertFalse((root / 'started.json').exists())


if __name__ == '__main__':
    unittest.main()
