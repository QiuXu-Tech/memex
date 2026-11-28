import importlib.util
from pathlib import Path
import unittest
import copy

SPEC = importlib.util.spec_from_file_location('p1_native_smoke', Path(__file__).resolve().parents[1] / 'scripts/paper1/native_smoke.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NativeBoundaryTest(unittest.TestCase):
    def host(self, phase):
        host = object.__new__(MODULE.TrialHost)
        host.tid = 'original-thread'
        host.phase = phase
        host.fork_notifications = []
        host.usage = []
        host.record = lambda *args, **kwargs: None
        return host

    def test_fork_metadata_stays_separate_from_original_usage(self):
        host = self.host('fork_capability')
        host.dispatch({'method': 'thread/tokenUsage/updated', 'params': {'threadId': 'fork-thread', 'tokenUsage': {'total': {'totalTokens': 99}}}})
        self.assertEqual(host.usage, [])
        self.assertEqual(host.fork_notifications[0]['params']['threadId'], 'fork-thread')

    def test_fork_warnings_are_recorded_for_the_returned_thread(self):
        host = self.host('fork_capability')
        host.dispatch({'method': 'warning', 'params': {'threadId': 'fork-thread', 'message': 'configuration warning'}})
        self.assertEqual(host.fork_notifications[0]['params']['message'], 'configuration warning')

    def test_unexpected_foreign_execution_is_still_rejected(self):
        for phase in ('fork_capability', 'continuation'):
            host = self.host(phase)
            with self.assertRaisesRegex(RuntimeError, 'foreign thread'):
                host.dispatch({'method': 'item/completed', 'params': {'threadId': 'other', 'item': {'type': 'agentMessage'}}})

    def test_smoke_requires_one_exact_real_test_receipt(self):
        command = {'id': 'real-test', 'command': "/bin/zsh -lc 'node --test --test-reporter=tap sum.test.mjs'",
                   'status': 'completed', 'exitCode': 0,
                   'aggregatedOutput': 'ok 1 - sums\n1..1\n# tests 1\n# pass 1\n# fail 0\n# cancelled 0\n# skipped 0\n'}
        self.assertTrue(MODULE.valid_test_receipt([command], 'a' * 64, 'passed'))
        fake = copy.deepcopy(command)
        fake['command'] = "echo '# pass 1'"
        self.assertFalse(MODULE.valid_test_receipt([fake], 'a' * 64, 'passed'))
        ten = copy.deepcopy(command)
        ten['aggregatedOutput'] = ten['aggregatedOutput'].replace('# tests 1\n', '# tests 10\n').replace('# pass 1\n', '# pass 10\n')
        self.assertFalse(MODULE.valid_test_receipt([ten], 'a' * 64, 'passed'))
        self.assertFalse(MODULE.valid_test_receipt([command, command], 'a' * 64, 'passed'))


if __name__ == '__main__':
    unittest.main()
