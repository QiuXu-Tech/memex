#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import tempfile
import unittest

script = pathlib.Path(__file__).with_name('prospective-gateway-adjudication-v16-fallback.py')
spec = importlib.util.spec_from_file_location('fallback', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Tests(unittest.TestCase):
    def test_modified_packet_is_rejected_before_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            packet = root / 'packets' / 'A01.json'
            packet.parent.mkdir()
            packet.write_text('{}')
            manifest = {'runnerSha256': module.pilot.SHA(script.read_bytes()),
                        'candidates': [{'blind': 'A01', 'packetSha256': 'bad'}]}
            (root / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaises(SystemExit):
                module.run(root)
            self.assertFalse((root / 'started.json').exists())


if __name__ == '__main__':
    unittest.main()
