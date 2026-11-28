"""Real loopback HTTP relay tests with a bounded in-memory upstream only."""
from __future__ import annotations

import copy
import hashlib
import http.client
import importlib.util
import io
import json
from pathlib import Path
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
