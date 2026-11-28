import copy
from pathlib import Path
import runpy
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/paper1/native_usage.py'


def usage(total, last=None, turn='turn', thread='thread'):
    def counts(n):
        return {'inputTokens': n - 2, 'cachedInputTokens': 0, 'cacheWriteInputTokens': 0,
                'outputTokens': 2, 'reasoningOutputTokens': 0, 'totalTokens': n}
    return {'event': 'thread/tokenUsage/updated', 'phase': 'generation', 'threadId': thread,
            'turnId': turn, 'tokenUsage': {'total': counts(total), 'last': counts(total if last is None else last)}}


class NativeUsageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = staticmethod(runpy.run_path(str(SCRIPT))['audit_events'])

    def test_duplicate_notifications_are_not_additive(self):
        result = self.audit([usage(12), usage(12)])
        self.assertEqual(result['observed_generation_totals']['totalTokens'], 12)
        self.assertEqual(result['duplicate_notifications'], 1)

    def test_second_snapshot_requires_cumulative_delta_to_match_last(self):
        a = usage(12); b = usage(25, 13)
        b['tokenUsage']['total'].update(inputTokens=21, outputTokens=4)
        result = self.audit([a, b])
        self.assertEqual(result['reconciled_generation_notifications'], 2)
        self.assertEqual(result['observed_generation_totals']['totalTokens'], 25)

    def test_compaction_context_counter_is_not_a_zero_cost_or_billable_call(self):
        row = usage(12)
        compact = copy.deepcopy(row); compact['phase'] = 'native_compaction'; compact['turnId'] = 'compact'
        compact['tokenUsage']['last'] = {k: 0 for k in row['tokenUsage']['last']}
        compact['tokenUsage']['last']['totalTokens'] = 2000
        result = self.audit([row, compact])
        self.assertEqual(result['observed_generation_totals']['totalTokens'], 12)
        self.assertEqual(result['unmetered_compaction_notifications'], 1)
        self.assertFalse(result['full_cost_available'])
        self.assertIsNone(result['standardized_cost'])

    def test_fork_counters_are_evaluated_per_thread_not_summed_as_parent_totals(self):
        result = self.audit([usage(12), usage(14, thread='fork1'), usage(15, thread='fork2')])
        self.assertEqual(result['observed_generation_totals']['totalTokens'], 41)
        inherited = usage(40, 15, thread='fork3')
        result = self.audit([inherited])
        self.assertIsNone(result['observed_generation_totals'])
        self.assertIn('unobserved_or_inherited_prefix', result['issues'])

    def test_reset_or_invalid_subset_is_preserved_as_unreconciled(self):
        for second in [usage(8), usage(15)]:
            if second['tokenUsage']['total']['totalTokens'] == 15:
                second['tokenUsage']['last']['cachedInputTokens'] = 100
            result = self.audit([usage(12), second])
            self.assertEqual(result['reconciled_generation_notifications'], 1)
            self.assertGreater(len(result['unreconciled']), 0)

    def test_completed_turn_without_usage_stays_missing(self):
        result = self.audit([{'event': 'turn/completed', 'threadId': 't', 'turnId': 'x', 'status': 'completed'}])
        self.assertEqual(result['generation_turns_without_reconciled_usage'], [{'threadId': 't', 'turnId': 'x'}])
        self.assertIsNone(result['observed_generation_totals'])


if __name__ == '__main__':
    unittest.main()
