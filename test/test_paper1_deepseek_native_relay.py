"""Real loopback HTTP relay tests with a bounded in-memory upstream only."""
from __future__ import annotations

import copy
import hashlib
import http.client
import importlib.util
import io
import json
from pathlib import Path
import socket
import stat
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import urllib.parse


ROOT = Path(__file__).resolve().parents[1]


def module():
    name = "p1_native_relay_under_test"
    if name not in sys.modules:
        path = ROOT / "scripts/paper1/deepseek_native_relay.py"
        if not path.is_file():
            return None
        spec = importlib.util.spec_from_file_location(name, path)
        value = importlib.util.module_from_spec(spec)
        sys.modules[name] = value
        spec.loader.exec_module(value)
    return sys.modules[name]


def profile():
    return {"schema_version": 1, "kind": "p1-deepseek-native-reader-profile", "provider": "deepseek",
        "model": "deepseek-flash", "endpoint": "https://api.deepseek.com/responses",
        "max_request_bytes": 262144, "max_response_bytes": 4194304, "timeout_seconds": 30,
        "max_output_tokens": 8192, "max_model_input_tokens": 65536, "max_model_output_tokens": 8192,
        "max_http_dispatches": 8, "reference_input_token_limit": 65536,
        "reasoning_effort": "none", "temperature": 0, "retries": 0,
        "tokenizer": {"kind": "fixture_reference_only", "sha256": "a" * 64}}


def receipt(intent):
    return {"schema_version": 1, "kind": "p1-dispatch-admission-receipt", "decision": "allow",
        "dispatch_id": intent["dispatch_id"], "request_sha256": intent["request_sha256"],
        "intent_sha256": intent["intent_sha256"], "admission_id": "fixture-ledger"}


def sse(*, usage=True, text="fixture answer", input_tokens=7, output_tokens=3):
    response = {"id": "resp_fixture", "object": "response", "model": "deepseek-flash", "status": "completed",
        "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": text}]}],
        "store": False}
    if usage:
        response["usage"] = {"input_tokens": input_tokens, "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "input_tokens_details": {"cached_tokens": 2}, "output_tokens_details": {"reasoning_tokens": 0}}
    values = [
        {"type": "response.created", "sequence_number": 0,
         "response": {"id": "resp_fixture", "model": "deepseek-flash", "status": "in_progress"}},
        {"type": "response.output_text.delta", "sequence_number": 1, "delta": text},
        {"type": "response.completed", "sequence_number": 2, "response": response}]
    return "".join("event: " + v["type"] + "\ndata: " + json.dumps(v) + "\n\n" for v in values).encode()


def codex_source_request(*, history=False, compaction=False):
    """Source-derived shape, NOT a captured host turn or provider observation.

    openai/codex 41e22fee981a63b3698df7ed36bad393cda24715:
    core/src/{client,responses_metadata}.rs, protocol/src/models.rs,
    tools/src/responses_api.rs, analytics/src/facts.rs.
    """
    names = ('read_file', 'write_file', 'list_files', 'run_current_tests', 'record_review')
    turn = {'installation_id': 'fixture-installation', 'session_id': 'fixture-session',
        'thread_id': 'fixture-thread', 'turn_id': 'fixture-turn', 'window_id': 'fixture-window',
        'window_number': 0, 'context_window_id': '11111111-1111-4111-8111-111111111111',
        'request_kind': 'compaction' if compaction else 'turn', 'thread_source': 'user',
        'turn_trigger': 'user', 'sandbox': 'read-only', 'sandbox_mode': 'read-only',
        'auto_review_enabled': False, 'node_repl_auto_review_required': False,
        'node_repl_disabled': True, 'turn_started_at_unix_ms': 1795824000000,
        'history_ingest_requested': False,
        'workspaces': {'/fixture/public-workspace': {'associated_remote_urls': {
            'origin': 'https://example.invalid/public.git'}, 'latest_git_commit_hash': 'a' * 40,
            'has_changes': False}},
        'tool_namespaces_info': {'functions': {'name': 'functions', 'functions': {
            name: {'name': name, 'direct': True, 'code_mode_name': None, 'deferred': False,
                   'source': {'kind': 'harness'}} for name in names}}}}
    if compaction:
        turn['compaction'] = {'trigger': 'manual', 'reason': 'user_requested',
            'implementation': 'responses', 'phase': 'standalone_turn', 'strategy': 'memento'}
    value = {'model': 'deepseek-flash', 'instructions': 'fixture public instructions',
        'input': [{'type': 'message', 'role': 'developer', 'content': [
            {'type': 'input_text', 'text': 'fixture public developer context'}]},
            {'type': 'message', 'role': 'user', 'content': [
                {'type': 'input_text', 'text': 'fixture public original request'}]}],
        'tools': [{'type': 'function', 'name': name, 'description': 'fixture public tool',
            'strict': False, 'parameters': {'type': 'object', 'properties': {}}} for name in names],
        'tool_choice': 'auto', 'parallel_tool_calls': False, 'reasoning': {'effort': 'none'},
        'store': False, 'stream': True, 'include': ['reasoning.encrypted_content'],
        'prompt_cache_key': 'fixture-session', 'client_metadata': {
            'x-codex-installation-id': 'fixture-installation', 'session_id': 'fixture-session',
            'thread_id': 'fixture-thread', 'x-codex-window-id': 'fixture-window',
            'turn_id': 'fixture-turn', 'x-codex-turn-metadata': json.dumps(turn)}}
    if history:
        value['input'].extend([
            {'type': 'function_call', 'call_id': 'call_public_1', 'name': 'read_file',
                'arguments': '{"path":"public.txt"}'},
            {'type': 'function_call_output', 'call_id': 'call_public_1', 'output': [
                {'type': 'input_text', 'text': 'fixture public tool result'}]},
            {'type': 'message', 'role': 'assistant', 'phase': 'final_answer', 'content': [
                {'type': 'output_text', 'text': 'fixture prior final answer'}]},
            {'type': 'message', 'role': 'user', 'content': [
                {'type': 'input_text', 'text': 'fixture public continuation'}]}])
    return value


class UpstreamResponse:
    status = 200
    def __init__(self, body):
        self.data = io.BytesIO(body)
        self.headers = {"content-type": "text/event-stream", "content-length": str(len(body)), "x-request-id": "fixture"}
    def read(self, maximum):
        return self.data.read(maximum)
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.data.close()


class NativeRelayTests(unittest.TestCase):
    def setUp(self):
        self.m = module()
        self.assertIsNotNone(self.m, "native Responses relay is missing")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.calls, self.admissions, self.credentials, self.completions = [], [], [], []
        self.response = sse()
        def open_upstream(request, timeout):
            self.calls.append({"url": request.full_url, "body": json.loads(request.data), "timeout": timeout})
            return UpstreamResponse(self.response)
        self.opener = type("FixtureOpener", (), {"open": staticmethod(open_upstream)})()
        self.patcher = mock.patch.object(self.m.urllib.request, "build_opener", return_value=self.opener)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.relay = None

    def start(self, *, custom_profile=None, authorize=None, complete=None, registration=None,
              component='reader', checkpoint='b' * 64):
        def credential():
            self.credentials.append(True)
            return "offline-provider-fixture-secret"
        def admit(intent, *, scope_id):
            self.admissions.append({"intent": copy.deepcopy(intent), "scope_id": scope_id})
            return receipt(intent)
        def finish(message, *, scope_id):
            self.completions.append(copy.deepcopy(message))
            record_path = Path(self.temp.name) / 'relay/dispatches' / (message['dispatch_id'] + '.json')
            self.assertEqual(hashlib.sha256(record_path.read_bytes()).hexdigest(), message['record_sha256'])
            record = json.loads(record_path.read_text())
            return {'schema_version': 1, 'kind': 'p1-dispatch-completion-receipt',
                'dispatch_id': message['dispatch_id'], 'intent_sha256': message['intent_sha256'],
                'record_sha256': message['record_sha256'], 'admission_id': 'fixture-completion-ledger',
                'decision': 'continue' if record['status'] == 'completed' else 'blocked'}
        self.relay = self.m.DeepSeekRelay(profile=custom_profile or profile(), output=Path(self.temp.name) / "relay",
            credential_provider=credential, authorize_dispatch=authorize or admit,
            complete_dispatch=complete or finish, token_counter=lambda text: len(text) // 4 + 1)
        self.addCleanup(self.relay.close)
        identity = self.relay.registration
        registered = registration(identity) if registration else {
            'schema_version': 1, 'kind': 'p1-relay-registration-receipt',
            'transport_id': identity['transport_id'], 'config_sha256': identity['config_sha256'],
            'relay_source_sha256': identity['relay_source_sha256'],
            'registration_sha256': self.m.digest(identity), 'admission_id': 'fixture-registration-ledger'}
        self.relay.bind_transport(registered)
        self.relay.activate(scope_id="scope-1", component=component, checkpoint_sha256=checkpoint,
                            deadline=time.monotonic() + 30)
        return self.relay

    def post(self, body=None, *, token=None):
        target = urllib.parse.urlsplit(self.relay.base_url)
        connection = http.client.HTTPConnection(target.hostname, target.port, timeout=5)
        data = json.dumps(body or {"model": "deepseek-flash", "input": "fixture public history", "stream": True}).encode()
        try:
            connection.request("POST", target.path.rstrip("/") + "/responses", body=data,
                headers={"Authorization": "Bearer " + (token or self.relay.local_token), "Content-Type": "application/json"})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_real_loopback_request_is_admitted_and_returns_only_reviewed_sse(self):
        self.start()
        status, body = self.post()
        self.assertEqual(status, 200)
        self.assertEqual(body, self.response)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.admissions), 1)
        self.assertEqual(len(self.completions), 1)
        self.assertEqual(self.calls[0]["url"], "https://api.deepseek.com/responses")
        self.assertEqual(self.calls[0]["body"]["reasoning"], {"effort": "none"})
        self.assertIs(self.calls[0]["body"]["store"], False)
        self.assertEqual(self.calls[0]["body"]["max_output_tokens"], 8192)
        record = self.relay.records[0]
        self.assertEqual(record["usage"], {"input_tokens": 7, "cached_input_tokens": 2, "output_tokens": 3})
        self.assertEqual(record["component"], "reader")
        self.assertEqual(record["checkpoint_sha256"], "b" * 64)
        public = json.dumps(self.relay.records) + (Path(self.temp.name) / "relay/relay-state.json").read_text()
        self.assertNotIn("offline-provider-fixture-secret", public)
        self.assertNotIn("fixture public history", public)
        self.assertNotIn("fixture answer", public)

    def test_pinned_codex_shapes_preserve_full_history_and_flat_tools(self):
        self.start()
        for history, compaction in ((False, False), (True, False), (True, True)):
            with self.subTest(history=history, compaction=compaction):
                request = codex_source_request(history=history, compaction=compaction)
                status, response = self.post(request)
                self.assertEqual(status, 200, response)
                sent = self.calls[-1]['body']
                for key in ('input', 'instructions', 'tools', 'tool_choice', 'parallel_tool_calls'):
                    self.assertEqual(sent[key], request[key])
                for key in ('prompt_cache_key', 'client_metadata', 'include'):
                    self.assertNotIn(key, sent)
                self.assertEqual(sent['reasoning'], {'effort': 'none'})
                record = self.relay.records[-1]
                self.assertEqual(record['wire_request_sha256'], hashlib.sha256(json.dumps(request).encode()).hexdigest())
                self.assertEqual(record['request_sha256'], self.m.digest(sent))
                self.assertEqual(self.admissions[-1]['intent']['request_sha256'], self.m.digest(sent))
        audit = (Path(self.temp.name) / 'relay/relay-state.json').read_text()
        self.assertNotIn('fixture-installation', audit)
        self.assertNotIn('fixture-session', audit)
        self.assertNotIn('/fixture/public-workspace', audit)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(len(self.completions), 3)

    def test_client_metadata_must_match_bounded_typed_source_schema(self):
        valid = codex_source_request()
        cases = [
            {'prompt_cache_key': 'bad\ncache-key'}, {'prompt_cache_key': 'x' * 257},
            {'client_metadata': {'unrecognized': 'private-value'}},
            {'client_metadata': {'session_id': {'not': 'a string'}}},
            {'client_metadata': {'session_id': 'x' * 257}},
            {'client_metadata': {'x-codex-turn-metadata': '[]'}},
            {'client_metadata': {'x-codex-turn-metadata': '{"request_kind":"turn","request_kind":"turn"}'}},
            {'client_metadata': {'x-codex-turn-metadata': json.dumps({'unexpected_extra': 'private'})}},
            {'client_metadata': {'x-codex-turn-metadata': json.dumps({'window_number': True})}},
            {'client_metadata': {'x-codex-turn-metadata': json.dumps({'workspaces': {'/fixture': {'unknown': True}}})}},
            {'client_metadata': {'x-codex-turn-metadata': json.dumps({'tool_namespaces_info': {
                'functions': {'name': 'functions', 'functions': {'read_file': {'name': 'read_file'}}}}})}},
            {'client_metadata': {'x-codex-turn-metadata': json.dumps({'compaction': {
                'trigger': 'manual', 'reason': 'user_requested', 'implementation': 'unknown',
                'phase': 'standalone_turn', 'strategy': 'memento'}})}},
            {'client_metadata': {'x-codex-turn-metadata': ' ' * 16385}},
        ]
        # Establish the source-shaped valid case before rejecting its mutations.
        self.m.prepare_request(json.dumps(valid).encode(), profile(), 8192)
        for change in cases:
            with self.subTest(change=change):
                with self.assertRaises(self.m.RelayError):
                    self.m.prepare_request(json.dumps({**valid, **change}).encode(), profile(), 8192)

    def test_metadata_compatibility_does_not_admit_tools_tiers_or_incomplete_history(self):
        valid = codex_source_request(history=True)
        self.m.prepare_request(json.dumps(valid).encode(), profile(), 8192)
        cases = [
            {**valid, 'service_tier': 'priority'}, {**valid, 'service_tier': 'default'},
            {**valid, 'unknown_field': 'private-value'}, {**valid, 'stream_options': {'include_usage': True}},
            {**valid, 'reasoning': {'effort': 'none', 'summary': 'auto'}},
            {**valid, 'include': ['reasoning.encrypted_content', 'web_search_call.action.sources']},
            {**valid, 'tools': [{'type': 'namespace', 'name': 'functions', 'tools': valid['tools']}]},
            {**valid, 'tools': valid['tools'] + [{'type': 'function', 'name': 'request_user_input', 'parameters': {}}]},
            {**valid, 'input': [item for item in valid['input'] if item['type'] != 'function_call_output']},
            {**valid, 'input': valid['input'] + [valid['input'][2]]},
            {**valid, 'input': valid['input'] + [valid['input'][3]]},
            {**valid, 'input': [{**item, 'name': 'shell'} if item['type'] == 'function_call' else item for item in valid['input']]},
            {**valid, 'input': [{**item, 'call_id': 'unknown_call'} if item['type'] == 'function_call_output' else item for item in valid['input']]},
            {**valid, 'input': valid['input'] + [{'type': 'reasoning', 'encrypted_content': 'forbidden'}]},
        ]
        for candidate in cases:
            with self.subTest(candidate=candidate):
                with self.assertRaises(self.m.RelayError):
                    self.m.prepare_request(json.dumps(candidate).encode(), profile(), 8192)

    def test_prerecord_rejections_are_immutable_private_and_bound_to_each_lease(self):
        self.start()
        secret = 'private-rejected-payload-marker'
        request = {'model': 'deepseek-flash', 'input': secret, 'stream': True, secret: secret}
        wire = json.dumps(request).encode()
        old_token = self.relay.local_token
        released = threading.Event()
        release = self.relay._release
        def observe_release(lease):
            release(lease)
            released.set()
        self.relay._release = observe_release
        self.assertEqual(self.post(request)[0], 400)
        self.assertTrue(released.wait(timeout=2), 'handler must release its real lease before activation')
        self.relay.activate(scope_id='scope-2', component='compaction', checkpoint_sha256='c' * 64,
            deadline=time.monotonic() + 30)
        self.assertEqual(self.post(request, token=old_token)[0], 401)
        self.assertEqual(self.post(request)[0], 400)
        files = sorted((Path(self.temp.name) / 'relay/rejections').glob('*.json'))
        self.assertEqual(len(files), 2)
        rows = [json.loads(path.read_text()) for path in files]
        self.assertEqual([(row['scope_id'], row['component'], row['checkpoint_sha256'], row['epoch'])
            for row in rows], [('scope-1', 'reader', 'b' * 64, 1), ('scope-2', 'compaction', 'c' * 64, 2)])
        for path, row in zip(files, rows):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(row['error_code'], 'unsupported_request_fields')
            self.assertEqual(row['request_bytes_received'], len(wire))
            self.assertEqual(row['request_bytes_sha256'], hashlib.sha256(wire).hexdigest())
            self.assertTrue(row['request_body_complete'])
            self.assertIs(row['provider_dispatch_started'], False)
            with self.assertRaises(FileExistsError):
                self.relay._write_immutable(str(path.relative_to(self.relay.output)), {'overwrite': True})
        audit = ''.join(path.read_text() for path in self.relay.output.rglob('*.json'))
        for private in (secret, old_token, self.relay.local_token, 'offline-provider-fixture-secret'):
            self.assertNotIn(private, audit)
        self.assertEqual(self.relay.records, [])
        self.assertEqual(self.credentials + self.admissions + self.calls + self.completions, [])
        self.assertEqual(self.relay.scope_states['scope-1']['dispatches'], 0)

    def test_header_and_partial_body_rejections_count_only_actually_read_bytes(self):
        self.start()
        target = urllib.parse.urlsplit(self.relay.base_url)
        connection = http.client.HTTPConnection(target.hostname, target.port, timeout=5)
        try:
            connection.request('POST', '/responses', body=b'private-unread-body', headers={
                'Authorization': 'Bearer ' + self.relay.local_token, 'Content-Type': 'text/plain'})
            response = connection.getresponse()
            self.assertEqual(response.status, 400)
            response.read()
        finally:
            connection.close()
        # Real truncated local HTTP body: Content-Length is a promise, not an observation.
        partial = b'{"private":"partial'
        with socket.create_connection((target.hostname, target.port), timeout=5) as connection:
            header = ('POST /responses HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer ' +
                self.relay.local_token + '\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n').encode()
            connection.sendall(header + partial)
            connection.shutdown(socket.SHUT_WR)
            while connection.recv(65536):
                pass
        rows = [json.loads(path.read_text()) for path in sorted((self.relay.output / 'rejections').glob('*.json'))]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['error_code'], 'json_request_required')
        self.assertEqual(rows[0]['request_bytes_received'], 0)
        self.assertIsNone(rows[0]['request_bytes_sha256'])
        self.assertFalse(rows[0]['request_body_complete'])
        self.assertEqual(rows[1]['error_code'], 'request_body_incomplete')
        self.assertEqual(rows[1]['request_bytes_received'], len(partial))
        self.assertEqual(rows[1]['request_bytes_sha256'], hashlib.sha256(partial).hexdigest())
        self.assertFalse(rows[1]['request_body_complete'])
        self.assertEqual(self.relay.records, [])
        self.assertEqual(self.credentials + self.admissions + self.calls + self.completions, [])

    def test_prerecord_callback_failure_has_fixed_code_and_no_exception_text(self):
        self.start()
        def broken_counter(text):
            raise ValueError('private-callback-message')
        self.relay.token_counter = broken_counter
        status, body = self.post()
        self.assertEqual(status, 400)
        files = list((self.relay.output / 'rejections').glob('*.json'))
        self.assertEqual(len(files), 1)
        self.assertEqual(json.loads(files[0].read_text())['error_code'], 'reference_token_measurement_failed')
        self.assertNotIn(b'private-callback-message', body)
        self.assertNotIn('private-callback-message', files[0].read_text())
        self.assertEqual(self.relay.records, [])
        self.assertEqual(self.credentials + self.admissions + self.calls, [])

    def test_completion_receipt_mismatch_withholds_reviewed_body_and_blocks_scope(self):
        def wrong(message, *, scope_id):
            return {'schema_version': 1, 'kind': 'p1-dispatch-completion-receipt',
                'dispatch_id': message['dispatch_id'], 'intent_sha256': message['intent_sha256'],
                'record_sha256': 'f' * 64, 'admission_id': 'fixture-bad-proof', 'decision': 'continue'}
        self.start(complete=wrong)
        status, body = self.post()
        self.assertGreaterEqual(status, 400)
        self.assertNotIn(b'fixture answer', body)
        self.assertTrue(self.relay.scope_states['scope-1']['blocked'])
        self.assertGreaterEqual(self.post()[0], 400)
        self.assertEqual(len(self.calls), 1)
        records = list((Path(self.temp.name) / 'relay/dispatches').glob('*.json'))
        self.assertEqual(len(records), 1)
        self.assertEqual(json.loads(records[0].read_text())['usage']['input_tokens'], 7)

    def test_actual_canonical_controller_observes_prefix_and_unknown_terminal_without_cash_settlement(self):
        spec = importlib.util.spec_from_file_location('relay_controller_fixture', ROOT / 'test/test_paper1_runtime_controller.py')
        suite = importlib.util.module_from_spec(spec); spec.loader.exec_module(suite)
        fixture = suite.RuntimeControllerTests(methodName='runTest'); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        controller = suite.M.CanonicalPairedController({'scope-1': fixture.envelope_spec()}, repo_root=fixture.root, run=True)
        controller.admit_scope(fixture.intent(scope='scope-1'))
        controller.before_operation(fixture.intent(scope='scope-1', operation='capture_parent', ordinal=1))
        actual = json.loads((ROOT / 'scripts/paper1/deepseek-reader-profile.json').read_text())
        self.start(custom_profile=actual, authorize=controller.authorize_dispatch,
            complete=controller.complete_dispatch, registration=controller.register_transport,
            component='prelude', checkpoint=None)
        self.assertEqual(self.post()[0], 200)
        self.response = sse(usage=False)
        self.assertGreaterEqual(self.post()[0], 400)
        journal = [json.loads(line)['record'] for line in (controller.state / 'events.jsonl').read_text().splitlines()]
        completed = [row for row in journal if row['event'] == 'provider_completed']
        self.assertEqual(len(completed), 2)
        self.assertTrue(completed[-1]['blocked'])
        self.assertEqual(completed[-1]['usage_totals']['input_tokens'], 7)
        self.assertEqual(fixture.ledger.status()['committed_cash_upper_bound'], '3.20')
        self.assertIsNone(fixture.ledger.status()['actual_added_cash_total'])
        self.assertEqual(len(self.calls), 2)

    def test_wrong_admission_stops_before_upstream_and_locks_scope(self):
        self.start(authorize=lambda intent, scope_id: {**receipt(intent), "request_sha256": "f" * 64})
        status, _ = self.post()
        self.assertGreaterEqual(status, 400)
        self.assertEqual(self.calls, [])
        status, _ = self.post()
        self.assertGreaterEqual(status, 400)
        self.assertEqual(self.calls, [])

    def test_unsupported_history_or_server_tools_do_not_access_credentials(self):
        self.start()
        for change in ({"previous_response_id": "resp_old"},
                       {"tools": [{"type": "web_search"}]},
                       {"input": [{"role": "user", "content": [{"type": "input_image", "image_url": "https://example.invalid/image"}]}]}):
            with self.subTest(change=change):
                status, _ = self.post({"model": "deepseek-flash", "input": "history", "stream": True, **change})
                self.assertGreaterEqual(status, 400)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.admissions, [])
        self.assertEqual(self.credentials, [])

    def test_missing_usage_blocks_same_scope_even_after_component_switch(self):
        self.start()
        self.response = sse(usage=False)
        status, _ = self.post()
        self.assertGreaterEqual(status, 400)
        self.assertFalse(self.relay.records[0]["usage_complete"])
        with self.assertRaises(self.m.RelayError):
            self.relay.activate(scope_id="scope-1", component="compaction", checkpoint_sha256="b" * 64,
                                deadline=time.monotonic() + 30)
        self.assertEqual(len(self.calls), 1)

    def test_real_profile_metadata_is_accepted_and_hashed(self):
        actual = json.loads((ROOT / "scripts/paper1/deepseek-reader-profile.json").read_text())
        relay = self.start(custom_profile=actual)
        self.assertEqual(relay.config_sha256, self.m.digest(actual))
        self.assertEqual(self.post()[0], 200)

    def test_only_public_dynamic_tools_are_admitted(self):
        self.start()
        for name in ("shell", "exec_command", "apply_patch", "functions.run_current_tests"):
            with self.subTest(name=name):
                status, _ = self.post({"model": "deepseek-flash", "input": "history", "stream": True,
                    "tools": [{"type": "function", "name": name, "parameters": {"type": "object"}}]})
                self.assertGreaterEqual(status, 400)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.credentials, [])
        status, _ = self.post({"model": "deepseek-flash", "input": "history", "stream": True,
            "tools": [{"type": "function", "name": "run_current_tests", "parameters": {"type": "object"}}]})
        self.assertEqual(status, 200)

    def test_request_deadline_is_not_reset_after_admission(self):
        def admit(intent, *, scope_id):
            self.relay._inflight["request_deadline"] = time.monotonic() - 1
            return receipt(intent)
        self.start(authorize=admit)
        status, _ = self.post()
        self.assertGreaterEqual(status, 400)
        self.assertEqual(self.calls, [])
        self.assertTrue(self.relay.scope_states["scope-1"]["blocked"])

    def test_credential_callback_exception_is_never_reflected(self):
        self.start()
        def unavailable():
            raise self.m.RelayError("offline-provider-fixture-secret")
        self.relay.credential_provider = unavailable
        status, body = self.post()
        self.assertGreaterEqual(status, 400)
        public = body.decode() + json.dumps(self.relay.records) + (Path(self.temp.name) / "relay/relay-state.json").read_text()
        self.assertNotIn("offline-provider-fixture-secret", public)
        self.assertEqual(self.calls, [])

    def test_rotation_preserves_scope_dispatch_budget_and_invalidates_old_token(self):
        limited = profile()
        limited["max_http_dispatches"] = 2
        self.start(custom_profile=limited)
        old = self.relay.local_token
        self.assertEqual(self.post()[0], 200)
        self.relay.activate(scope_id="scope-1", component="compaction", checkpoint_sha256="b" * 64,
                            deadline=time.monotonic() + 30)
        self.assertNotEqual(old, self.relay.local_token)
        self.assertEqual(self.post(token=old)[0], 401)
        self.assertEqual(self.post()[0], 200)
        self.assertGreaterEqual(self.post()[0], 400)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.relay.scope_states["scope-1"]["input_tokens"], 14)
        self.assertEqual([r["component"] for r in self.relay.records], ["reader", "compaction"])

    def test_deactivation_locks_inflight_scope_and_withholds_late_sse(self):
        self.start()
        entered, release = threading.Event(), threading.Event()
        def delayed_open(request, timeout):
            entered.set()
            if not release.wait(timeout=3):
                raise TimeoutError("fixture wait")
            return UpstreamResponse(self.response)
        self.relay._opener = type("DelayedOpener", (), {"open": staticmethod(delayed_open)})()
        result = []
        worker = threading.Thread(target=lambda: result.append(self.post()))
        worker.start()
        self.assertTrue(entered.wait(timeout=2))
        try:
            self.relay.deactivate()
            with self.assertRaises(self.m.RelayError):
                self.relay.activate(scope_id="scope-2", component="reader", checkpoint_sha256="c" * 64,
                                    deadline=time.monotonic() + 30)
        finally:
            release.set()
            worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertGreaterEqual(result[0][0], 400)
        self.assertNotIn(b"fixture answer", result[0][1])
        old = self.relay.scope_states["scope-1"]
        self.assertTrue(old["blocked"])
        self.assertFalse(old["usage_complete"])
        self.relay.activate(scope_id="scope-2", component="reader", checkpoint_sha256="c" * 64,
                            deadline=time.monotonic() + 30)
        self.assertTrue(self.relay.scope_states["scope-1"]["blocked"])

    def test_actual_usage_over_limit_blocks_later_dispatches(self):
        limited = profile()
        limited["max_model_input_tokens"] = 6
        self.start(custom_profile=limited)
        self.assertGreaterEqual(self.post()[0], 400)
        self.assertEqual(self.relay.records[0]["usage"]["input_tokens"], 7)
        self.assertTrue(self.relay.records[0]["usage_complete"])
        self.assertGreaterEqual(self.post()[0], 400)
        self.assertEqual(len(self.calls), 1)

    def test_oversize_response_is_not_replayed_or_retried(self):
        limited = profile()
        limited["max_response_bytes"] = 100
        self.start(custom_profile=limited)
        status, body = self.post()
        self.assertGreaterEqual(status, 400)
        self.assertNotIn(b"fixture answer", body)
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(self.relay.records[0]["usage_complete"])

    def test_secret_reflection_blocks_the_whole_sse_and_audit(self):
        self.start()
        self.response = sse(text="".join("\\u%04x" % ord(c) for c in "offline-provider-fixture-secret"))
        status, body = self.post()
        self.assertGreaterEqual(status, 400)
        self.assertNotIn(b"offline-provider-fixture-secret", body)
        audit = (Path(self.temp.name) / "relay/relay-state.json").read_text()
        self.assertNotIn("offline-provider-fixture-secret", audit)
        self.assertNotIn("\\\\u006f", audit)
        self.assertEqual(self.relay.records[0]["error_code"], "credential_reflection_rejected")

    def test_sse_sequence_terminal_model_and_tool_constraints(self):
        body = sse()
        cases = {
            "missing_terminal": body[:body.rfind(b"event: response.completed")],
            "duplicate_sequence": body.replace(b'"sequence_number": 2', b'"sequence_number": 1'),
            "wrong_model": body.replace(b'"deepseek-flash"', b'"another-model"'),
            "reasoning_event": body.replace(b'response.output_text.delta', b'response.reasoning_text.delta'),
            "no_terminal_status": body.replace(b'"status": "completed"', b'"status": "in_progress"'),
            "undeclared_tool": body.replace(b'"type": "message", "role": "assistant"',
                b'"type": "function_call", "name": "shell", "role": "assistant"'),
        }
        for name, candidate in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(self.m.RelayError):
                    self.m.parse_sse(candidate, tool_names=set(), credential="fixture-secret-123", local_token="fixture-local-123")


if __name__ == "__main__":
    unittest.main()
