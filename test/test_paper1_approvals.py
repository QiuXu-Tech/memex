"""Protocol fixtures only: these tests never approve an actual host operation."""
import io
from pathlib import Path
import runpy
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'scripts/paper1/approvals.py'


class Tty(io.StringIO):
    def isatty(self):
        return True


def request(identifier=4):
    return {'id': identifier, 'method': 'item/tool/requestUserInput', 'params': {
        'threadId': 'thread', 'turnId': 'turn', 'itemId': 'item', 'isBlocking': True,
        'questions': [{'id': 'approval', 'header': 'Approval', 'question': 'Run the configured P1 test once?',
                       'options': [{'label': 'Allow once', 'description': 'Allow only this invocation.'},
                                   {'label': 'Decline', 'description': 'Do not allow this invocation.'}]}]}}


class ApprovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = runpy.run_path(str(MODULE))

    def handler(self, answer):
        records = []
        handler = self.api['InteractiveApprovals'](Tty(answer), Tty(),
                    record=lambda event, **kw: records.append((event, kw)),
                    read_line=lambda stream, timeout: stream.readline())
        return handler, records

    def test_noninteractive_stream_cannot_supply_an_approval(self):
        with self.assertRaisesRegex(ValueError, 'terminal'):
            self.api['InteractiveApprovals'](io.StringIO('1\n'), Tty())

    def test_exact_displayed_option_is_bound_to_active_request(self):
        handler, records = self.handler('1\n')
        value = handler.handle(request(), thread_id='thread', turn_id='turn', timeout=2)
        self.assertEqual(value, {'answers': {'approval': {'answers': ['Allow once']}}})
        self.assertEqual(records[-1][1]['response'], value)
        self.assertEqual(records[-1][1]['source'], 'interactive_terminal')

    def test_blank_answer_cancels_instead_of_accepting_a_default(self):
        handler, _ = self.handler('\n')
        self.assertEqual(handler.handle(request(), thread_id='thread', turn_id='turn', timeout=2), {'answers': {}})

    def test_decline_is_preserved_and_no_session_wide_grant_is_added(self):
        handler, _ = self.handler('2\n')
        self.assertEqual(handler.handle(request(), thread_id='thread', turn_id='turn', timeout=2),
                         {'answers': {'approval': {'answers': ['Decline']}}})

    def test_blocking_flag_required_and_must_be_boolean_true(self):
        for flag in (None, False, 1):
            handler, records = self.handler('1\n')
            msg = request()
            if flag is None:
                del msg['params']['isBlocking']
            else:
                msg['params']['isBlocking'] = flag
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, 'unsupported'):
                handler.handle(msg, thread_id='thread', turn_id='turn', timeout=2)
            self.assertEqual(records, [])

    def test_nullable_uint64_auto_resolution_only_shortens_wait(self):
        for millis, upper in [(None, 2), (1000, 1), (2**64 - 1, 2)]:
            handler, _ = self.handler('1\n')
            waits = []
            handler.read_line = lambda stream, timeout: waits.append(timeout) or '1'
            msg = request()
            msg['params']['autoResolutionMs'] = millis
            reply = handler.handle(msg, thread_id='thread', turn_id='turn', timeout=2)
            self.assertTrue(reply['answers'])
            self.assertGreater(waits[0], 0)
            self.assertLessEqual(waits[0], upper)
        for millis in (-1, False, 1.5, 2**64):
            handler, _ = self.handler('1\n')
            msg = request()
            msg['params']['autoResolutionMs'] = millis
            with self.subTest(millis=millis), self.assertRaisesRegex(ValueError, 'timeout'):
                handler.handle(msg, thread_id='thread', turn_id='turn', timeout=2)
        handler, _ = self.handler('1\n')
        handler.read_line = lambda *_: self.fail('expired prompt must not read an answer')
        msg = request()
        msg['params']['autoResolutionMs'] = 0
        self.assertEqual(handler.handle(msg, thread_id='thread', turn_id='turn', timeout=2), {'answers': {}})

    def test_foreign_thread_or_turn_never_reaches_the_console(self):
        for key in ('threadId', 'turnId'):
            handler, records = self.handler('1\n')
            msg = request(); msg['params'][key] = 'other'
            with self.assertRaisesRegex(ValueError, 'scope'):
                handler.handle(msg, thread_id='thread', turn_id='turn', timeout=2)
            self.assertEqual(records, [])

    def test_request_ids_cannot_replay_an_approval(self):
        handler, _ = self.handler('1\n1\n')
        handler.handle(request(), thread_id='thread', turn_id='turn', timeout=2)
        with self.assertRaisesRegex(ValueError, 'replayed'):
            handler.handle(request(), thread_id='thread', turn_id='turn', timeout=2)

    def test_secret_or_free_form_questions_are_not_supported(self):
        for key in ('isSecret', 'isOther'):
            handler, _ = self.handler('1\n')
            msg = request(); msg['params']['questions'][0][key] = True
            with self.assertRaisesRegex(ValueError, 'unsupported'):
                handler.handle(msg, thread_id='thread', turn_id='turn', timeout=2)

    def test_empty_mcp_form_does_not_establish_one_call_scope(self):
        handler, records = self.handler('accept\n')
        msg = {'id': 'form', 'method': 'mcpServer/elicitation/request', 'params': {
            'threadId': 'thread', 'turnId': 'turn', 'serverName': 'memex', 'mode': 'form',
            'message': 'Run once?', 'requestedSchema': {'type': 'object', 'properties': {}}}}
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            handler.handle(msg, thread_id='thread', turn_id='turn', timeout=2)
        self.assertEqual(records, [])

    def test_unknown_persistent_or_contradictory_options_fail_before_prompt(self):
        for label in ('Always Allow', 'acceptForSession', 'Accept', 'Yes'):
            handler, records = self.handler('1\n')
            msg = request()
            msg['params']['questions'][0]['options'][0]['label'] = label
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, 'unsupported'):
                handler.handle(msg, thread_id='thread', turn_id='turn', timeout=2)
            self.assertEqual(records, [])
        for key, value in [('question', 'Allow permanently?'), ('scope', 'session')]:
            handler, records = self.handler('1\n')
            msg = request()
            msg['params']['questions'][0][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'unsupported'):
                handler.handle(msg, thread_id='thread', turn_id='turn', timeout=2)
            self.assertEqual(records, [])

    def test_device_verification_and_permission_expansion_are_not_forged(self):
        for method, mode in [('mcpServer/elicitation/request', 'openai/userVerification'),
                             ('item/permissions/requestApproval', None)]:
            handler, _ = self.handler('accept\n')
            msg = {'id': 2, 'method': method, 'params': {'threadId': 'thread', 'turnId': 'turn',
                     'serverName': 'memex', 'mode': mode}}
            with self.assertRaisesRegex(ValueError, 'unsupported'):
                handler.handle(msg, thread_id='thread', turn_id='turn', timeout=2)


if __name__ == '__main__':
    unittest.main()
