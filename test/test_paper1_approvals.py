"""Pinned native protocol fixtures; never approve an actual host operation."""
import copy
import io
from pathlib import Path
import runpy
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'scripts/paper1/approvals.py'


class Tty(io.StringIO):
    def isatty(self):
        return True


def start(item_id='item', tool='run_current_tests', arguments=None):
    return {'method': 'item/started', 'params': {'threadId': 'thread', 'turnId': 'turn',
        'item': {'type': 'mcpToolCall', 'id': item_id, 'server': 'memex', 'tool': tool,
                 'arguments': {} if arguments is None else arguments, 'status': 'inProgress'}}}


def request(identifier=4, item_id='item', tool='run_current_tests'):
    return {'id': identifier, 'method': 'item/tool/requestUserInput', 'params': {
        'threadId': 'thread', 'turnId': 'turn', 'itemId': item_id, 'isBlocking': True,
        'questions': [{'id': 'mcp_tool_call_approval_' + item_id, 'header': 'Approve app tool call?',
            'question': f'Allow the memex MCP server to run tool "{tool}"?',
            'options': [{'label': 'Allow', 'description': 'Run the tool and continue.'},
                        {'label': 'Cancel', 'description': 'Cancel this tool call.'}]}]}}


def form(identifier=4, tool='run_current_tests', arguments=None):
    return {'id': identifier, 'method': 'mcpServer/elicitation/request', 'params': {
        'threadId': 'thread', 'turnId': 'turn', 'serverName': 'memex', 'mode': 'form',
        'message': f'Allow the memex MCP server to run tool "{tool}"?',
        'requestedSchema': {'type': 'object', 'properties': {}},
        '_meta': {'codex_approval_kind': 'mcp_tool_call',
                  'tool_params': {} if arguments is None else arguments}}}


class ApprovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = runpy.run_path(str(MODULE))

    def handler(self, answer='1\n', event=None, bind=True):
        records = []
        handler = self.api['InteractiveApprovals'](Tty(answer), Tty(),
            record=lambda event, **kw: records.append((event, kw)),
            read_line=lambda stream, timeout: stream.readline())
        if bind:
            handler.observe(start() if event is None else event, thread_id='thread', turn_id='turn')
        return handler, records

    def call(self, handler, message, timeout=2):
        return handler.handle(message, thread_id='thread', turn_id='turn', timeout=timeout)

    def test_noninteractive_input_or_output_cannot_supply_an_approval(self):
        for a, b in ((io.StringIO('1\n'), Tty()), (Tty('1\n'), io.StringIO())):
            with self.assertRaisesRegex(ValueError, 'terminal'):
                self.api['InteractiveApprovals'](a, b)

    def test_official_question_allow_is_bound_to_observed_native_item(self):
        handler, records = self.handler()
        response = self.call(handler, request())
        self.assertEqual(response, {'answers': {'mcp_tool_call_approval_item': {'answers': ['Allow']}}})
        self.assertEqual(records[-1][1]['response'], response)
        self.assertEqual(records[-1][1]['source'], 'interactive_terminal')
        self.assertFalse(records[-1][1]['identityAttested'])
        self.assertEqual(records[0][1]['itemId'], 'item')
        self.assertIn('argumentsSha256', records[0][1])

    def test_official_empty_form_requires_privileged_metadata_and_pending_call(self):
        handler, _ = self.handler()
        self.assertEqual(self.call(handler, form()), {'action': 'accept', 'content': {}})
        for remove in ('_meta',):
            handler, records = self.handler()
            message = form(); del message['params'][remove]
            with self.assertRaisesRegex(ValueError, 'unsupported'):
                self.call(handler, message)
            self.assertEqual(records, [])
        handler, records = self.handler(bind=False)
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.call(handler, form())
        self.assertEqual(records, [])

    def test_decline_blank_eof_and_invalid_input_never_accept(self):
        for value, action in [('2\n', 'decline'), ('\n', 'cancel'), ('', 'cancel'), ('3\n', 'cancel'), ('Allow\n', 'cancel')]:
            with self.subTest(value=value):
                handler, _ = self.handler(value)
                self.assertEqual(self.call(handler, form()), {'action': action, 'content': None})
        handler, _ = self.handler('2\n')
        self.assertEqual(self.call(handler, request()),
                         {'answers': {'mcp_tool_call_approval_item': {'answers': ['Cancel']}}})

    def test_session_and_persistent_advertisements_are_never_forwarded(self):
        for persist in ('session', 'always', ['session', 'always']):
            handler, _ = self.handler()
            message = form(); message['params']['_meta']['persist'] = persist
            self.assertEqual(self.call(handler, message), {'action': 'accept', 'content': {}})
        handler, _ = self.handler()
        message = request()
        message['params']['questions'][0]['options'].insert(1, self.api['OPTION_SESSION'])
        message['params']['questions'][0]['options'].insert(2, self.api['OPTION_ALWAYS'])
        self.assertEqual(self.call(handler, message),
                         {'answers': {'mcp_tool_call_approval_item': {'answers': ['Allow']}}})

    def test_only_two_authorized_tool_argument_shapes_are_supported(self):
        arguments = {'decision': 'hold', 'evidenceEventIds': ['receipt'], 'explanation': 'Observed failure.'}
        handler, _ = self.handler(event=start(tool='record_decision', arguments=arguments))
        self.assertEqual(self.call(handler, form(tool='record_decision', arguments=arguments)),
                         {'action': 'accept', 'content': {}})
        cases = [('run_current_tests', {'command': 'something'}),
                 ('record_decision', dict(arguments, path='/elsewhere')),
                 ('record_decision', dict(arguments, decision='deploy')),
                 ('record_decision', dict(arguments, evidenceEventIds=['x'] * 17)),
                 ('record_decision', dict(arguments, explanation='x' * 4001)),
                 ('arbitrary_tool', {})]
        for tool, args in cases:
            handler, _ = self.handler(event=start(tool=tool, arguments=args))
            with self.subTest(tool=tool, args=repr(args)[:80]), self.assertRaises(ValueError):
                self.call(handler, form(tool=tool, arguments=args))

    def test_form_arguments_must_equal_native_item_even_with_same_tool_name(self):
        handler, records = self.handler()
        message = form(); message['params']['_meta']['tool_params'] = {'extra': 'value'}
        with self.assertRaisesRegex(ValueError, 'arguments differ'):
            self.call(handler, message)
        self.assertEqual(records, [])

    def test_native_observation_is_snapshotted_before_caller_can_mutate_it(self):
        event = start()
        handler, _ = self.handler(event=event)
        event['params']['item']['arguments']['extra'] = 'value'
        self.assertEqual(self.call(handler, form()), {'action': 'accept', 'content': {}})

    def test_foreign_thread_turn_or_server_never_reaches_console(self):
        for key, value in [('threadId', 'other'), ('turnId', 'other'), ('turnId', None), ('serverName', 'other')]:
            handler, records = self.handler()
            message = form(); message['params'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.call(handler, message)
            self.assertEqual(records, [])
        handler, _ = self.handler(bind=False)
        message = start(); message['params']['turnId'] = 'other'
        handler.observe(message, thread_id='thread', turn_id='turn')
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.call(handler, form())

    def test_request_id_and_item_cannot_be_reapproved(self):
        handler, _ = self.handler('1\n1\n')
        self.call(handler, form())
        with self.assertRaisesRegex(ValueError, 'replayed'):
            self.call(handler, form())
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.call(handler, form(identifier=5))

    def test_replayed_native_start_is_not_an_update_of_authorized_arguments(self):
        handler, _ = self.handler()
        with self.assertRaisesRegex(ValueError, 'replayed'):
            handler.observe(start(), thread_id='thread', turn_id='turn')
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.call(handler, form())

    def test_completed_item_or_turn_invalidates_pending_binding(self):
        events = [dict(start(), method='item/completed'),
                  {'method': 'turn/completed', 'params': {'threadId': 'thread', 'turn': {'id': 'turn'}}}]
        for event in events:
            handler, records = self.handler()
            handler.observe(event, thread_id='thread', turn_id='turn')
            with self.subTest(event=event), self.assertRaisesRegex(ValueError, 'binding'):
                self.call(handler, form())
            self.assertEqual(records, [])

    def test_resolved_request_and_resolution_during_prompt_cannot_accept(self):
        resolved = {'method': 'serverRequest/resolved', 'params': {'threadId': 'thread', 'requestId': 4}}
        handler, _ = self.handler()
        handler.observe(resolved, thread_id='thread', turn_id='turn')
        with self.assertRaisesRegex(ValueError, 'resolved'):
            self.call(handler, form())
        handler, _ = self.handler()
        def answer(*_):
            handler.observe(resolved, thread_id='thread', turn_id='turn')
            return '1'
        handler.read_line = answer
        self.assertEqual(self.call(handler, form()), {'action': 'cancel', 'content': None})

    def test_two_same_tool_pending_items_are_ambiguous_for_an_unidentified_form(self):
        handler, records = self.handler()
        handler.observe(start('item2'), thread_id='thread', turn_id='turn')
        with self.assertRaisesRegex(ValueError, 'unique'):
            self.call(handler, form())
        self.assertEqual(records, [])
        self.assertTrue(self.call(handler, request())['answers'])

    def test_generic_or_secret_forms_and_device_verification_are_rejected(self):
        cases = []
        for mode in ('url', 'openai/form', 'openaiForm', 'openai/userVerification'):
            message = form(); message['params']['mode'] = mode; cases.append(message)
        message = form(); message['params']['requestedSchema']['properties'] = {'secret': {'type': 'string'}}; cases.append(message)
        message = form(); message['params']['_meta']['codex_approval_kind'] = 'tool_suggestion'; cases.append(message)
        message = form(); message['params']['_meta']['persist'] = 'forever'; cases.append(message)
        message = form(); message['params']['_meta']['connector_id'] = 'other'; cases.append(message)
        message = form(); message['method'] = 'item/permissions/requestApproval'; cases.append(message)
        for message in cases:
            handler, records = self.handler()
            with self.subTest(method=message['method'], mode=message['params']['mode']), self.assertRaises(ValueError):
                self.call(handler, message)
            self.assertEqual(records, [])

    def test_form_display_metadata_cannot_disagree_with_native_arguments(self):
        arguments = {'decision': 'hold', 'evidenceEventIds': ['r'], 'explanation': 'checked'}
        handler, _ = self.handler(event=start(tool='record_decision', arguments=arguments))
        message = form(tool='record_decision', arguments=arguments)
        message['params']['_meta']['tool_params_display'] = [
            {'name': k, 'value': v, 'display_name': k} for k, v in sorted(arguments.items())]
        self.assertEqual(self.call(handler, message), {'action': 'accept', 'content': {}})
        handler, _ = self.handler(event=start(tool='record_decision', arguments=arguments))
        message['params']['_meta']['tool_params_display'][0]['value'] = 'release'
        with self.assertRaisesRegex(ValueError, 'displayed arguments differ'):
            self.call(handler, message)
        handler, _ = self.handler(event=start(tool='record_decision', arguments=arguments))
        message['params']['_meta']['tool_params_display'] = [
            {'name': k, 'value': v, 'displayName': k} for k, v in sorted(arguments.items())]
        with self.assertRaisesRegex(ValueError, 'displayed arguments differ'):
            self.call(handler, message)

    def test_original_request_and_arguments_are_escaped_for_terminal_display(self):
        arguments = {'decision': 'hold', 'evidenceEventIds': [], 'explanation': '\x1b[2J'}
        handler, _ = self.handler(event=start(tool='record_decision', arguments=arguments))
        self.call(handler, form(tool='record_decision', arguments=arguments))
        shown = handler.output.getvalue()
        self.assertNotIn('\x1b', shown)
        self.assertIn('\\u001b', shown)

    def test_question_must_match_native_call_identity_and_options(self):
        cases = []
        for field, value in [('id', 'other'), ('header', 'Approval'), ('isSecret', True), ('isOther', True),
                             ('question', 'Run the configured P1 test once?')]:
            message = request(); message['params']['questions'][0][field] = value; cases.append(message)
        message = request(); message['params']['itemId'] = 'wrong'; cases.append(message)
        message = request(); message['params']['questions'][0]['options'][0]['label'] = 'Always Allow'; cases.append(message)
        message = request(); message['params']['questions'][0]['options'][0]['description'] = 'Run forever'; cases.append(message)
        for message in cases:
            handler, records = self.handler()
            with self.subTest(message=message), self.assertRaises(ValueError):
                self.call(handler, message)
            self.assertEqual(records, [])

    def test_blocking_flag_required_and_boolean_true(self):
        for flag in (None, False, 1):
            handler, _ = self.handler()
            message = request()
            if flag is None: del message['params']['isBlocking']
            else: message['params']['isBlocking'] = flag
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, 'unsupported'):
                self.call(handler, message)

    def test_deadline_and_nullable_uint64_auto_timeout_can_only_shorten_wait(self):
        for millis, upper in [(None, 2), (1000, 1), (2**64 - 1, 2)]:
            handler, _ = self.handler()
            waits = []
            handler.read_line = lambda stream, timeout: waits.append(timeout) or '1'
            message = request(); message['params']['autoResolutionMs'] = millis
            self.assertTrue(self.call(handler, message)['answers'])
            self.assertGreater(waits[0], 0)
            self.assertLessEqual(waits[0], upper)
        for millis in (-1, False, 1.5, 2**64):
            handler, _ = self.handler()
            message = request(); message['params']['autoResolutionMs'] = millis
            with self.subTest(millis=millis), self.assertRaisesRegex(ValueError, 'timeout'):
                self.call(handler, message)
        handler, _ = self.handler()
        handler.read_line = lambda *_: self.fail('expired prompt must not read an answer')
        message = request(); message['params']['autoResolutionMs'] = 0
        self.assertEqual(self.call(handler, message), {'answers': {}})
        handler, _ = self.handler()
        self.assertEqual(self.call(handler, form(), timeout=0), {'action': 'cancel', 'content': None})

    def test_nonfinite_timeouts_and_malformed_envelopes_are_rejected(self):
        for timeout in (float('nan'), float('inf'), True, '2'):
            handler, _ = self.handler()
            with self.subTest(timeout=timeout), self.assertRaisesRegex(ValueError, 'timeout'):
                self.call(handler, form(), timeout=timeout)
        for identifier in (True, '', None):
            handler, _ = self.handler()
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                self.call(handler, form(identifier=identifier))

    def test_eight_approval_limit_and_oversized_request_fail_before_prompt(self):
        handler, records = self.handler('1\n' * 9, bind=False)
        for i in range(8):
            handler.observe(start(str(i)), thread_id='thread', turn_id='turn')
            self.call(handler, request(i, str(i)))
        handler.observe(start('9'), thread_id='thread', turn_id='turn')
        with self.assertRaisesRegex(ValueError, 'budget'):
            self.call(handler, request(9, '9'))
        self.assertEqual(len(records), 16)
        handler, records = self.handler()
        message = form(); message['params']['message'] = 'x' * 17000
        with self.assertRaisesRegex(ValueError, 'oversized'):
            self.call(handler, message)
        self.assertEqual(records, [])


class PriorChatApprovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = runpy.run_path(str(MODULE))

    def grant(self):
        # Fixture references only; these are not an actual experiment permit.
        return {'authorization_sha256': 'a' * 64, 'attempt_id': 'native-fixture-01',
                'reservation_sha256': 'b' * 64}

    def handler(self, *, event=None, bind=True, grant=None):
        records = []
        handler = self.api['PriorChatApprovals'](
            grant_reference=self.grant() if grant is None else grant,
            record=lambda event, **kw: records.append((event, kw)))
        if bind:
            handler.observe(start() if event is None else event, thread_id='thread', turn_id='turn')
        return handler, records

    def call(self, handler, message, timeout=2):
        return handler.handle(message, thread_id='thread', turn_id='turn', timeout=timeout)

    def test_two_known_tools_and_two_protocol_paths_return_one_call_only(self):
        for tool, args in [('run_current_tests', {}), ('record_decision', {
                'decision': 'hold', 'evidenceEventIds': ['r'], 'explanation': 'Checked receipt.'})]:
            for variant in ('form', 'question'):
                with self.subTest(tool=tool, variant=variant):
                    handler, records = self.handler(event=start(tool=tool, arguments=args))
                    message = form(tool=tool, arguments=args) if variant == 'form' else request(tool=tool)
                    response = self.call(handler, message)
                    expected = {'action': 'accept', 'content': {}} if variant == 'form' else {
                        'answers': {'mcp_tool_call_approval_item': {'answers': ['Allow']}}}
                    self.assertEqual(response, expected)
                    self.assertEqual(len(records), 2)
                    for _, fields in records:
                        self.assertEqual(fields['origin'], 'prior_chat_authorization')
                        self.assertEqual(fields['grantReference'], self.grant())
                        self.assertFalse(fields['identityAttested'])
                    self.assertEqual(records[-1][1]['source'], 'prior_chat_authorization')
                    self.assertFalse(hasattr(handler, 'input'))

    def test_missing_or_invalid_grant_and_missing_audit_recorder_are_rejected(self):
        ctor = self.api['PriorChatApprovals']
        with self.assertRaises(TypeError):
            ctor(record=lambda *_: None)
        bad = [None, {}, self.grant() | {'persist': 'always'}]
        for name in self.grant():
            altered = self.grant(); del altered[name]; bad.append(altered)
        for name in ('authorization_sha256', 'reservation_sha256'):
            for value in ('x' * 64, 'A' * 64, 'a' * 63, None, 3):
                bad.append(self.grant() | {name: value})
        for attempt in ('', '../other', 'n\n', 'n' * 129, None, 1):
            bad.append(self.grant() | {'attempt_id': attempt})
        for reference in bad:
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                ctor(grant_reference=reference, record=lambda *_: None)
        for recorder in (None, {}, False):
            with self.subTest(recorder=recorder), self.assertRaisesRegex(ValueError, 'recorder'):
                ctor(grant_reference=self.grant(), record=recorder)

    def test_grant_reference_is_snapshotted_and_cannot_be_widened_by_caller_mutation(self):
        reference = self.grant()
        handler, records = self.handler(grant=reference)
        reference['attempt_id'] = 'different-attempt'
        self.call(handler, form())
        self.assertEqual(records[0][1]['grantReference'], self.grant())
        records[0][1]['grantReference']['attempt_id'] = 'mutated-audit-copy'
        self.assertEqual(records[1][1]['grantReference'], self.grant())

    def test_context_and_native_pending_call_are_mandatory(self):
        handler, records = self.handler(bind=False)
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.call(handler, form())
        self.assertEqual(records, [])
        for field, value in [('threadId', 'foreign'), ('turnId', 'foreign'), ('turnId', None),
                             ('serverName', 'foreign')]:
            handler, records = self.handler()
            message = form(); message['params'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.call(handler, message)
            self.assertEqual(records, [])
        handler, records = self.handler(event=start(tool='unapproved_tool'))
        with self.assertRaises(ValueError):
            self.call(handler, form(tool='unapproved_tool'))
        self.assertEqual(records, [])
        handler, records = self.handler()
        message = form(); message['params']['_meta']['tool_params'] = {'unexpected': 'argument'}
        with self.assertRaisesRegex(ValueError, 'arguments differ'):
            self.call(handler, message)
        self.assertEqual(records, [])

    def test_request_and_item_replay_cannot_create_another_grant(self):
        handler, records = self.handler()
        self.call(handler, form())
        with self.assertRaisesRegex(ValueError, 'replayed'):
            self.call(handler, form())
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.call(handler, form(identifier=5))
        self.assertEqual(len(records), 2)

    def test_persistence_choices_are_never_granted_and_persistence_only_forms_fail(self):
        handler, _ = self.handler()
        message = form(); message['params']['_meta']['persist'] = ['session', 'always']
        self.assertEqual(self.call(handler, message), {'action': 'accept', 'content': {}})
        handler, _ = self.handler()
        message = request()
        message['params']['questions'][0]['options'][1:1] = [
            self.api['OPTION_SESSION'], self.api['OPTION_ALWAYS']]
        self.assertEqual(self.call(handler, message), {
            'answers': {'mcp_tool_call_approval_item': {'answers': ['Allow']}}})
        cases = []
        message = request(); message['params']['questions'][0]['options'] = [
            self.api['OPTION_ALWAYS'], self.api['OPTION_CANCEL']]; cases.append(message)
        message = form(); message['params']['requestedSchema']['properties'] = {
            'persist': {'const': 'always'}}; cases.append(message)
        message = form(); message['params']['_meta']['persist'] = 'forever'; cases.append(message)
        for message in cases:
            handler, records = self.handler()
            with self.assertRaises(ValueError):
                self.call(handler, message)
            self.assertEqual(records, [])

    def test_device_human_presence_review_and_unknown_flows_require_handoff(self):
        cases = []
        for field in ('requiresHumanApproval', 'requiredHumanApproval', 'humanPresenceRequired',
                      'deviceVerificationRequired', 'codex_strict_auto_review', 'codex_sensitive_action'):
            message = form(); message['params']['_meta'][field] = True; cases.append(message)
        for mode in ('url', 'openai/form', 'openai/userVerification'):
            message = form(); message['params']['mode'] = mode; cases.append(message)
        for method in ('item/commandExecution/requestApproval', 'item/permissions/requestApproval',
                       'attestation/generate', 'account/chatgptAuthTokens/refresh'):
            message = form(); message['method'] = method; cases.append(message)
        message = request(); message['params']['questions'][0]['isSecret'] = True; cases.append(message)
        for message in cases:
            handler, records = self.handler()
            with self.subTest(message=message), self.assertRaises(ValueError):
                self.call(handler, message)
            self.assertEqual(records, [])

    def test_expiry_and_resolved_or_completed_invocations_never_accept(self):
        handler, _ = self.handler()
        self.assertEqual(self.call(handler, form(), timeout=0), {'action': 'cancel', 'content': None})
        handler, _ = self.handler()
        message = request(); message['params']['autoResolutionMs'] = 0
        self.assertEqual(self.call(handler, message), {'answers': {}})
        events = [{'method': 'serverRequest/resolved', 'params': {'threadId': 'thread', 'requestId': 4}},
                  dict(start(), method='item/completed')]
        for event in events:
            handler, records = self.handler()
            handler.observe(event, thread_id='thread', turn_id='turn')
            with self.assertRaises(ValueError):
                self.call(handler, form())
            self.assertEqual(records, [])

    def test_failed_audit_write_cannot_return_an_accept(self):
        class BrokenRecorder:
            def __bool__(self):
                return False

            def __call__(self, *_, **__):
                raise OSError('fixture audit writer failed')
        handler = self.api['PriorChatApprovals'](grant_reference=self.grant(), record=BrokenRecorder())
        handler.observe(start(), thread_id='thread', turn_id='turn')
        with self.assertRaises(OSError):
            self.call(handler, form())
        with self.assertRaisesRegex(ValueError, 'replayed'):
            self.call(handler, form())

    def test_native_arguments_and_display_values_are_exactly_bound(self):
        arguments = {'decision': 'hold', 'evidenceEventIds': ['r'], 'explanation': 'checked'}
        for mutation in ('argument', 'display', 'unknown_meta'):
            handler, records = self.handler(event=start(tool='record_decision', arguments=arguments))
            message = form(tool='record_decision', arguments=copy.deepcopy(arguments))
            if mutation == 'argument':
                message['params']['_meta']['tool_params']['decision'] = 'release'
            elif mutation == 'display':
                message['params']['_meta']['tool_params_display'] = [
                    {'name': 'decision', 'value': 'release', 'display_name': 'decision'}]
            else:
                message['params']['_meta']['humanApprovalEvidence'] = 'fabricated'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.call(handler, message)
            self.assertEqual(records, [])


if __name__ == '__main__':
    unittest.main()
