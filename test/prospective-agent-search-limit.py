#!/usr/bin/env python3
"""Agent tool calls that exceed the documented search cap remain useful."""
import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRIDGE = ROOT / 'scripts/prospective-agent-mcp-v5.mjs'

class SearchLimitTest(unittest.TestCase):
    def test_over_limit_search_is_bounded_and_reports_adjustment(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = pathlib.Path(directory) / 'worker.py'
            worker.write_text("import json,sys\nfor line in sys.stdin:\n r=json.loads(line); limit=r.get('limit',20)\n if not 1 <= limit <= 30: print(json.dumps({'ok':False,'error':'invalid query'}),flush=True)\n else: print(json.dumps({'ok':True,'result':{'matches':[],'actualLimit':limit}}),flush=True)\n")
            process = subprocess.Popen(['node', str(BRIDGE), '--read-only', '--', 'python3', str(worker)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            def search(identifier, limit):
                request = {'jsonrpc': '2.0', 'id': identifier, 'method': 'tools/call', 'params': {'name': 'repo_search', 'arguments': {'query': 'example', 'limit': limit}}}
                process.stdin.write(json.dumps(request) + '\n');process.stdin.flush()
                response = json.loads(process.stdout.readline())['result']
                self.assertFalse(response['isError'], response['content'])
                return json.loads(response['content'][0]['text'])
            try:
                adjusted = search(1, 50)
                self.assertEqual(adjusted['actualLimit'], 30)
                self.assertEqual(adjusted['limitAdjustment'], {'requested': 50, 'applied': 30})
                adjusted = search(2, 40)
                self.assertEqual(adjusted['actualLimit'], 30)
                self.assertEqual(adjusted['limitAdjustment'], {'requested': 40, 'applied': 30})
                within = search(3, 20)
                self.assertEqual(within['actualLimit'], 20)
                self.assertNotIn('limitAdjustment', within)
            finally:
                process.stdin.close();process.wait(timeout=10);process.stdout.close();process.stderr.close()

if __name__ == '__main__': unittest.main()
