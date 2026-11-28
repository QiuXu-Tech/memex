"""Bounded clients for the pinned Codex 0.153.0 MCP approval protocol.

A protocol-valid form alone has no authority. The request must bind to exactly
one pending MCP item observed on the same native thread and turn. Only the two
bounded P1 development tools are supported. InteractiveApprovals obtains a new
terminal response. PriorChatApprovals instead records delegated execution of a
previously validated, concrete batch authorization. Neither client returns a
session/persistent grant, secret input or device-verification proof. Prior chat
authorization must never be reported as a new human terminal interaction.

Protocol source: openai/codex rust-v0.153.0, commit
41e22fee981a63b3698df7ed36bad393cda24715, core/src/mcp_tool_call.rs.
Offline fixtures do not establish that a live human approved a host operation.
"""
import hashlib
import json
import math
import re
import select
import sys
import time


UPSTREAM_COMMIT = '41e22fee981a63b3698df7ed36bad393cda24715'
QUESTION_PREFIX = 'mcp_tool_call_approval_'
TOOL_NAMES = frozenset(('run_current_tests', 'record_decision'))
OPTION_ALLOW = {'label': 'Allow', 'description': 'Run the tool and continue.'}
OPTION_SESSION = {'label': 'Allow for this session',
                  'description': 'Run the tool and remember this choice for this session.'}
OPTION_ALWAYS = {'label': "Allow and don't ask me again",
                 'description': 'Run the tool and remember this choice for future tool calls.'}
OPTION_CANCEL = {'label': 'Cancel', 'description': 'Cancel this tool call.'}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(',', ':'), allow_nan=False)


def terminal_line(stream, timeout):
    if timeout <= 0 or not select.select([stream], [], [], timeout)[0]:
        return ''
    return stream.readline(1025)


def valid_arguments(tool, arguments):
    if not isinstance(arguments, dict):
        return False
    if tool == 'run_current_tests':
        return arguments == {}
    return (tool == 'record_decision'
            and set(arguments) == {'decision', 'evidenceEventIds', 'explanation'}
            and arguments['decision'] in ('release', 'hold')
            and isinstance(arguments['evidenceEventIds'], list)
            and len(arguments['evidenceEventIds']) <= 16
            and all(isinstance(v, str) and len(v) <= 512 for v in arguments['evidenceEventIds'])
            and isinstance(arguments['explanation'], str)
            and len(arguments['explanation']) <= 4000)


def fallback_question(tool):
    return f'Allow the memex MCP server to run tool "{tool}"?'


class _NativeApprovalRequests:
    origin = None

    def __init__(self, *, record=None):
        self.record = record if record is not None else (lambda event, **fields: None)
        self.seen = set()
        self.pending = {}
        self.observed = set()
        self.consumed_items = set()
        self.resolved = set()

    def _audit_fields(self):
        return {'origin': self.origin, 'identityAttested': False}

    def observe(self, message, *, thread_id, turn_id):
        """Observe native notifications; this method never creates an approval.

        The caller first updates its active turn from the real turn/started
        notification, then forwards notifications here before dispatching.
        Model text and tool results must never be passed as host notifications.
        """
        if not isinstance(message, dict) or 'id' in message:
            return
        params = message.get('params')
        if (not isinstance(params, dict) or params.get('threadId') != thread_id
                or not isinstance(thread_id, str) or not thread_id):
            return
        method = message.get('method')
        if method == 'serverRequest/resolved':
            identifier = params.get('requestId')
            if isinstance(identifier, (str, int)) and not isinstance(identifier, bool):
                self.resolved.add((type(identifier).__name__, identifier))
            return
        if method == 'turn/completed':
            turn = params.get('turn', {})
            finished = turn.get('id') if isinstance(turn, dict) else None
            self.pending = {k: v for k, v in self.pending.items() if k[:2] != (thread_id, finished)}
            return
        if params.get('turnId') != turn_id or not isinstance(turn_id, str) or not turn_id:
            return
        item = params.get('item')
        if not isinstance(item, dict) or item.get('type') != 'mcpToolCall':
            return
        identifier = item.get('id')
        if not isinstance(identifier, str) or not identifier:
            return
        key = (thread_id, turn_id, identifier)
        if method == 'item/completed':
            self.pending.pop(key, None)
            self.observed.add(key)
            return
        if method != 'item/started':
            return
        # Never let a repeated start update an already observed invocation.
        if key in self.observed:
            self.pending.pop(key, None)
            raise ValueError('replayed or mutated MCP item start')
        if len(self.observed) >= 20:
            raise ValueError('observed MCP item budget exhausted')
        self.observed.add(key)
        if (item.get('status') != 'inProgress' or item.get('server') != 'memex'
                or item.get('tool') not in TOOL_NAMES
                or not valid_arguments(item.get('tool'), item.get('arguments'))):
            return
        binding = {'itemId': identifier, 'server': 'memex', 'tool': item['tool'],
                   'arguments': item['arguments']}
        encoded = canonical(binding)
        if len(encoded.encode()) > 16384:
            return
        self.pending[key] = json.loads(encoded)  # Snapshot, not a shared mutable dict.

    def _bound_item(self, params, *, thread_id, turn_id, tool, item_id=None):
        candidates = [(k, v) for k, v in self.pending.items()
                      if k[:2] == (thread_id, turn_id) and v['tool'] == tool
                      and (item_id is None or k[2] == item_id)
                      and k not in self.consumed_items]
        if len(candidates) != 1:
            raise ValueError('approval has no unique pending MCP item binding')
        return candidates[0]

    def _mcp_form(self, params, *, thread_id, turn_id):
        required = {'threadId', 'turnId', 'serverName', 'mode', 'message', 'requestedSchema', '_meta'}
        if (set(params) != required or params['serverName'] != 'memex' or params['mode'] != 'form'):
            raise ValueError('unsupported MCP approval form fields')
        schema = params['requestedSchema']
        if (not isinstance(schema, dict) or set(schema) - {'type', 'properties', 'required', '$schema'}
                or schema.get('type') != 'object' or schema.get('properties') != {}
                or schema.get('required') not in (None, [])
                or schema.get('$schema') not in (None, 'http://json-schema.org/draft-07/schema#')):
            raise ValueError('unsupported MCP approval form schema')
        meta = params['_meta']
        allowed = {'codex_approval_kind', 'persist', 'tool_name', 'tool_title', 'tool_description',
                   'tool_params', 'tool_params_display', 'codex_request_type',
                   'codex_strict_auto_review', 'codex_sensitive_action', 'approvals_reviewer'}
        if (not isinstance(meta, dict) or set(meta) - allowed
                or meta.get('codex_approval_kind') != 'mcp_tool_call'):
            raise ValueError('unsupported MCP approval metadata')
        persistence = meta.get('persist')
        if persistence not in (None, 'session', 'always', ['session', 'always']):
            raise ValueError('unsupported MCP persistence advertisement')
        if ('codex_request_type' in meta and meta['codex_request_type'] != 'approval_request'):
            raise ValueError('unsupported MCP request type')
        for field in ('codex_strict_auto_review', 'codex_sensitive_action'):
            if field in meta and type(meta[field]) is not bool:
                raise ValueError('unsupported MCP approval flag')
        if 'approvals_reviewer' in meta and meta['approvals_reviewer'] != 'user':
            raise ValueError('unsupported MCP approval reviewer')
        for field in ('tool_title', 'tool_description'):
            if field in meta and not isinstance(meta[field], str):
                raise ValueError('unsupported MCP display metadata')
        tools = [t for t in TOOL_NAMES if params['message'] == fallback_question(t)]
        if len(tools) != 1:
            raise ValueError('unsupported MCP tool question')
        tool = tools[0]
        key, binding = self._bound_item(params, thread_id=thread_id, turn_id=turn_id, tool=tool)
        if ('tool_name' in meta and meta['tool_name'] != tool
                or meta.get('tool_params') != binding['arguments']):
            raise ValueError('MCP approval arguments differ from the pending item')
        display = meta.get('tool_params_display')
        if display is not None:
            expected = [{'name': k, 'value': v, 'display_name': k}
                        for k, v in sorted(binding['arguments'].items())]
            # RenderedMcpToolApprovalParam has no serde camelCase rename.
            if display != expected:
                raise ValueError('MCP approval displayed arguments differ from the pending item')
        return key, binding, None, None, 'mcp_form'

    def _question(self, params, *, thread_id, turn_id):
        required = {'threadId', 'turnId', 'itemId', 'questions', 'isBlocking'}
        if (not required <= set(params) or set(params) - required - {'autoResolutionMs'}
                or params['isBlocking'] is not True or not isinstance(params['itemId'], str)
                or not params['itemId']):
            raise ValueError('unsupported approval request fields')
        auto_ms = params.get('autoResolutionMs')
        if auto_ms is not None and (type(auto_ms) is not int or not 0 <= auto_ms < 2**64):
            raise ValueError('unsupported auto-resolution timeout')
        questions = params['questions']
        if not isinstance(questions, list) or len(questions) != 1 or not isinstance(questions[0], dict):
            raise ValueError('unsupported approval question count')
        question = questions[0]
        if (set(question) - {'id', 'header', 'question', 'options', 'isSecret', 'isOther'}
                or question.get('id') != QUESTION_PREFIX + params['itemId']
                or question.get('header') != 'Approve app tool call?'
                or question.get('isSecret', False) is not False
                or question.get('isOther', False) is not False):
            raise ValueError('unsupported native MCP question identity')
        options = question.get('options')
        if options not in ([OPTION_ALLOW, OPTION_CANCEL],
                           [OPTION_ALLOW, OPTION_SESSION, OPTION_CANCEL],
                           [OPTION_ALLOW, OPTION_ALWAYS, OPTION_CANCEL],
                           [OPTION_ALLOW, OPTION_SESSION, OPTION_ALWAYS, OPTION_CANCEL]):
            raise ValueError('unsupported MCP question options')
        tools = [t for t in TOOL_NAMES if question.get('question') == fallback_question(t)]
        if len(tools) != 1:
            raise ValueError('unsupported MCP tool question')
        key, binding = self._bound_item(params, thread_id=thread_id, turn_id=turn_id,
                                       tool=tools[0], item_id=params['itemId'])
        return key, binding, question['id'], auto_ms, 'request_user_input'

    def _prepare(self, message, *, thread_id, turn_id, timeout):
        received_at = time.monotonic()
        if (not isinstance(message, dict) or set(message) - {'jsonrpc', 'id', 'method', 'params'}
                or message.get('jsonrpc', '2.0') != '2.0'):
            raise ValueError('unsupported approval request envelope')
        params = message.get('params', {})
        identifier, method = message.get('id'), message.get('method')
        if (not isinstance(identifier, (str, int)) or isinstance(identifier, bool)
                or identifier == '' or not isinstance(params, dict)
                or not isinstance(thread_id, str) or not thread_id
                or not isinstance(turn_id, str) or not turn_id
                or params.get('threadId') != thread_id or params.get('turnId') != turn_id):
            raise ValueError('approval request scope does not match the active turn')
        request_key = (type(identifier).__name__, identifier)
        if request_key in self.seen or request_key in self.resolved:
            raise ValueError('replayed or already resolved approval request identifier')
        if len(self.seen) >= 8:
            raise ValueError('approval request budget exhausted')
        encoded = canonical(message)
        if len(encoded.encode()) > 16384:
            raise ValueError('unsupported oversized approval request')
        if type(timeout) not in (int, float) or not math.isfinite(timeout):
            raise ValueError('unsupported approval timeout')
        if method == 'mcpServer/elicitation/request':
            item_key, binding, question_id, auto_ms, variant = self._mcp_form(
                params, thread_id=thread_id, turn_id=turn_id)
        elif method == 'item/tool/requestUserInput':
            item_key, binding, question_id, auto_ms, variant = self._question(
                params, thread_id=thread_id, turn_id=turn_id)
        else:
            raise ValueError('unsupported approval method')
        wait_seconds = min(timeout, 120)
        if auto_ms is not None:
            wait_seconds = min(wait_seconds, auto_ms / 1000)
        deadline = received_at + max(0, wait_seconds)
        self.seen.add(request_key)
        self.consumed_items.add(item_key)
        arguments_sha = hashlib.sha256(canonical(binding['arguments']).encode()).hexdigest()
        self.record('approval/request', requestId=identifier, method=method,
                    threadId=thread_id, turnId=turn_id, itemId=binding['itemId'],
                    tool=binding['tool'], argumentsSha256=arguments_sha, variant=variant,
                    requestSha256=hashlib.sha256(encoded.encode()).hexdigest(),
                    **self._audit_fields())
        return {'requestId': identifier, 'method': method, 'threadId': thread_id,
                'turnId': turn_id, 'binding': binding, 'request_key': request_key,
                'item_key': item_key, 'question_id': question_id, 'variant': variant,
                'encoded': encoded, 'deadline': deadline, 'arguments_sha': arguments_sha}

    def _finish(self, context, value):
        active = (time.monotonic() < context['deadline']
                  and context['request_key'] not in self.resolved
                  and context['item_key'] in self.pending)
        if context['variant'] == 'mcp_form':
            response = {'action': 'accept', 'content': {}} if active and value == '1' else {
                'action': 'decline' if active and value == '2' else 'cancel', 'content': None}
        else:
            answers = {}
            if active and value in ('1', '2'):
                answers[context['question_id']] = {'answers': ['Allow' if value == '1' else 'Cancel']}
            response = {'answers': answers}
        self.record('approval/response', requestId=context['requestId'], method=context['method'],
                    threadId=context['threadId'], turnId=context['turnId'],
                    itemId=context['binding']['itemId'], tool=context['binding']['tool'],
                    argumentsSha256=context['arguments_sha'], response=response,
                    source=self.origin, **self._audit_fields())
        return response


class InteractiveApprovals(_NativeApprovalRequests):
    origin = 'interactive_terminal'

    def __init__(self, input_stream=None, output_stream=None, *, record=None, read_line=None):
        self.input = input_stream or sys.stdin
        self.output = output_stream or sys.stderr
        if not self.input.isatty() or not self.output.isatty():
            raise ValueError('interactive approval requires a human-operated terminal')
        super().__init__(record=record)
        self.read_line = read_line or terminal_line

    def handle(self, message, *, thread_id, turn_id, timeout):
        context = self._prepare(message, thread_id=thread_id, turn_id=turn_id, timeout=timeout)
        # Escaped JSON prevents request-controlled terminal escape sequences.
        self.output.write('\nP1 native host approval (this invocation only):\n' + context['encoded'] + '\n')
        self.output.write('Observed native invocation: ' + canonical(context['binding']) + '\n')
        self.output.write('1=Allow this invocation once, 2=Decline. Empty/timeout cancels. '
                          'Session/persistent options are not supported: ')
        self.output.flush()
        remaining = context['deadline'] - time.monotonic()
        value = self.read_line(self.input, remaining).strip() if remaining > 0 else ''
        return self._finish(context, value)


class PriorChatApprovals(_NativeApprovalRequests):
    """Exercise one concrete, controller-validated prior authorization.

    The controller must validate the authorization's contents, reserve this
    attempt in the durable budget ledger and verify the referenced reservation
    BEFORE constructing this client. Digests here are immutable audit references,
    not self-authenticating permission. A model must not supply or read the
    controller's permit. The controller owns attempt lifetime and budget checks.

    A known native pending invocation is still required for every response.
    Neither generic consent, a recognized tool name nor a form alone suffices.
    Unknown flows and explicit sensitive/strict-review signals fail closed for
    human handoff; this client never claims fresh human or device presence.
    """
    origin = 'prior_chat_authorization'

    def __init__(self, *, grant_reference, record):
        required = {'authorization_sha256', 'attempt_id', 'reservation_sha256'}
        if not isinstance(grant_reference, dict) or set(grant_reference) != required:
            raise ValueError('validated controller grant reference required')
        for name in ('authorization_sha256', 'reservation_sha256'):
            value = grant_reference[name]
            if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value):
                raise ValueError('invalid controller grant digest')
        attempt = grant_reference['attempt_id']
        if not isinstance(attempt, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', attempt):
            raise ValueError('invalid controller grant attempt identity')
        if not callable(record):
            raise ValueError('prior authorization requires an audit recorder')
        self._grant_reference = tuple(sorted(grant_reference.items()))
        super().__init__(record=record)

    def _audit_fields(self):
        return dict(super()._audit_fields(), grantReference=dict(self._grant_reference))

    def handle(self, message, *, thread_id, turn_id, timeout):
        # These recognized flags are not evidence of delegated prior consent.
        # Do not convert any fresh review/presence requirement into a grant.
        params = message.get('params') if isinstance(message, dict) else None
        meta = params.get('_meta') if isinstance(params, dict) else None
        if isinstance(meta, dict) and (meta.get('codex_strict_auto_review') is True
                                      or meta.get('codex_sensitive_action') is True):
            raise ValueError('approval requires separate human review or handoff')
        context = self._prepare(message, thread_id=thread_id, turn_id=turn_id, timeout=timeout)
        # Protocol-level one-invocation approval only. Never echo _meta.persist
        # or select either remembered option from the original request.
        return self._finish(context, '1')
