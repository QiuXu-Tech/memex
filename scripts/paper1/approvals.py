"""Narrow, interactive approval client for the P1 development host.

No unattended accept path, remembered grants, credential entry, permission
expansion or device-verification proof is implemented. Protocol tests use
in-memory fixtures; a live run requires an actual interactive terminal.
"""
import hashlib
import json
import select
import sys
import time


def terminal_line(stream, timeout):
    if timeout <= 0 or not select.select([stream], [], [], timeout)[0]:
        return ''
    return stream.readline(1025)


class InteractiveApprovals:
    def __init__(self, input_stream=None, output_stream=None, *, record=None, read_line=None):
        self.input = input_stream or sys.stdin
        self.output = output_stream or sys.stderr
        if not self.input.isatty() or not self.output.isatty():
            raise ValueError('interactive approval requires a human-operated terminal')
        self.record = record or (lambda event, **fields: None)
        self.read_line = read_line or terminal_line
        self.seen = set()

    def handle(self, message, *, thread_id, turn_id, timeout):
        received_at = time.monotonic()
        params = message.get('params', {})
        identifier, method = message.get('id'), message.get('method')
        if (not isinstance(identifier, (str, int)) or isinstance(identifier, bool)
                or not isinstance(params, dict) or not thread_id or not turn_id
                or params.get('threadId') != thread_id or params.get('turnId') != turn_id):
            raise ValueError('approval request scope does not match the active turn')
        key = (type(identifier).__name__, identifier)
        if key in self.seen:
            raise ValueError('replayed approval request identifier')
        if len(self.seen) >= 8:
            raise ValueError('interactive approval request budget exhausted')
        encoded = json.dumps(message, sort_keys=True, ensure_ascii=True)
        if len(encoded.encode()) > 16384:
            raise ValueError('unsupported oversized approval request')
        if method not in ('item/tool/requestUserInput', 'tool/requestUserInput'):
            raise ValueError('unsupported approval method; a generic form has no one-call scope')
        required = {'threadId', 'turnId', 'itemId', 'questions', 'isBlocking'}
        if (not required <= set(params) or set(params) - required - {'autoResolutionMs'}
                or params['isBlocking'] is not True or not isinstance(params['itemId'], str) or not params['itemId']):
            raise ValueError('unsupported approval request fields')
        auto_ms = params.get('autoResolutionMs')
        if auto_ms is not None and (type(auto_ms) is not int or not 0 <= auto_ms < 2**64):
            raise ValueError('unsupported auto-resolution timeout')
        wait_seconds = min(timeout, 120)
        if auto_ms is not None:
            wait_seconds = min(wait_seconds, auto_ms / 1000)
        deadline = received_at + max(0, wait_seconds)
        questions = params['questions']
        if not isinstance(questions, list) or len(questions) != 1 or not isinstance(questions[0], dict):
            raise ValueError('unsupported approval question count')
        question = questions[0]
        options = [{'label': 'Allow once', 'description': 'Allow only this invocation.'},
                   {'label': 'Decline', 'description': 'Do not allow this invocation.'}]
        if (set(question) - {'id', 'header', 'question', 'options', 'isSecret', 'isOther'}
                or question.get('id') != 'approval' or question.get('header') != 'Approval'
                or question.get('question') not in ('Run the configured P1 test once?',
                                                     'Record this simulated P1 decision once?')
                or question.get('isSecret', False) is not False or question.get('isOther', False) is not False
                or question.get('options') != options):
            raise ValueError('unsupported approval scope or options; use the host UI')
        self.seen.add(key)
        self.record('approval/request', requestId=identifier, method=method,
                    threadId=thread_id, turnId=turn_id,
                    requestSha256=hashlib.sha256(encoded.encode()).hexdigest())
        # JSON escaping prevents source-controlled terminal escape sequences.
        self.output.write('\nP1 host approval request (only this request):\n' + encoded + '\n')
        self.output.flush()
        self.output.write('1=Allow once, 2=Decline. Empty/timeout cancels: ')
        self.output.flush()
        remaining = deadline - time.monotonic()
        value = self.read_line(self.input, remaining).strip() if remaining > 0 else ''
        answers = {}
        if time.monotonic() < deadline and value in ('1', '2'):
            answers[question['id']] = {'answers': [options[int(value) - 1]['label']]}
        response = {'answers': answers}
        self.record('approval/response', requestId=identifier, method=method,
                    threadId=thread_id, turnId=turn_id, response=response,
                    source='interactive_terminal', identityAttested=False)
        return response
