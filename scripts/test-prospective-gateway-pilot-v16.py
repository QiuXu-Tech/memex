#!/usr/bin/env python3
import contextlib
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from unittest import mock

script = pathlib.Path(__file__).with_name('prospective-gateway-pilot-v16.py')
spec = importlib.util.spec_from_file_location('gateway_pilot_v16', script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Tests(unittest.TestCase):
    def test_registration_freezes_six_paired_issues_and_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            paths = {}
            for number in module.pilot.TASKS:
                paths[number] = {}
                for name in ('public', 'acceptance', 'regressionControls'):
                    path = root / f'{number}-{name}.js'
                    path.write_text(name)
                    paths[number][name] = path
            issues = {n: {'number': int(n), 'url': 'https://github.com/iamkun/dayjs/issues/' + n,
                          'state': 'OPEN', 'comments': {'nodes': [], 'totalCount': 0,
                                                       'pageInfo': {'hasNextPage': False}}}
                      for n in module.pilot.TASKS}
            snapshot = root / 'snapshot.json'
            snapshot.write_text(json.dumps({'data': {'repository': issues}}))
            context = {'keywordIds': [], 'memexIds': [], 'memexTokens': 0}
            with mock.patch.object(module.pilot, 'check_paths', side_effect=lambda n, _: paths[n]), \
                 mock.patch.object(module.pilot, 'store_context', return_value=context), \
                 contextlib.redirect_stdout(io.StringIO()):
                module.prepare(root / 'run', snapshot)
                manifest = module.pilot.integrity(root / 'run')
                self.assertEqual(manifest['runtime']['nodeBinarySha256'], module.NODE_SHA256)
                self.assertEqual(manifest['gatewayPolicy']['retryOnly'], 'explicit HTTP 503')
                self.assertEqual(manifest['reviewers'], ['deepseek-flash', 'qwen3.8-flash'])
                self.assertEqual(manifest['adjudicator'], 'gemini-3.8-flash')
                self.assertEqual({(x['issue'], x['arm']) for x in manifest['schedule']},
                                 {(n, arm) for n in issues for arm in ('keyword', 'memex')})
                paths['2951']['acceptance'].write_text('changed')
                with self.assertRaises(SystemExit):
                    module.pilot.integrity(root / 'run')


if __name__ == '__main__':
    unittest.main()
