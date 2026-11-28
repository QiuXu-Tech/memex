"""Safety and experiment-contract tests; no learned-model inference is mocked as a result.

Run: python -B -m unittest discover -s test -p 'test_paper1_rawrag.py' -v
"""
from __future__ import annotations

import contextlib
import copy
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "scripts" / "paper1" / "rawrag_adapter.py"
CONFIG = ROOT / "scripts" / "paper1" / "rawrag-config.json"


class CharacterEncoding:
    """Only tests text packing; never an embedding or production tokenizer."""
    name = "unit-test-characters"

    def encode(self, value, **kwargs):
        return list(value)

    def decode(self, values, **kwargs):
        return "".join(values)


def public_archive():
    return {
        "schema": 1,
        "taskId": "dev-01",
        "snapshot": {
            "cutoff": "2026-11-27T10:30:00Z",
            "watermark": "visible-snapshot-01",
            "complete": True,
        },
        "sources": [{
            "eventId": "evt-1", "sourceId": "runner", "sourceSequence": 1,
            "observedAt": "2026-11-27T10:00:00Z", "role": "tool",
            "type": "test_result", "scope": "repo", "entity": "unit",
            "kind": "command_execution", "command": "python -m unittest",
            "status": "failed", "complete": True, "exitCode": 1,
            "text": "AssertionError: expected 42, received 41.\n",
        }],
    }


def fixture_admission(intent):
    """A test callback only; never a production cash reservation."""
    return {"schema_version": 1, "kind": "p1-dispatch-admission-receipt", "decision": "allow",
            "dispatch_id": intent["dispatch_id"], "intent_sha256": intent["intent_sha256"],
            "request_sha256": intent["request_sha256"], "admission_id": "fixture-ledger"}


class RawRagContractTests(unittest.TestCase):
    def module(self):
        self.assertTrue(ADAPTER.is_file(), "Raw-RAG adapter implementation is missing")
        name = "paper1_rawrag_contract_under_test"
        if name not in sys.modules:
            spec = importlib.util.spec_from_file_location(name, ADAPTER)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        return sys.modules[name]

    def config(self):
        module = self.module()
        self.assertTrue(CONFIG.is_file(), "Pinned Raw-RAG configuration is missing")
        return module.load_config(CONFIG)

    def shared_source_archive(self, source_setup):
        """Exercise real JS ingestion/verifiers before passing the same source to B."""
        script = r"""
import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { EvidenceArchive } from './scripts/paper1/archive.mjs'
import { normalizeNodeTestEvent } from './scripts/paper1/normalize-node.mjs'
import { verifyEvidence } from './scripts/paper1/verification.mjs'
""" + source_setup + r"""
const now = '2026-11-27T10:30:00Z'
const root = mkdtempSync(join(tmpdir(), 'p1-cross-arm-'))
const archive = new EvidenceArchive({ root, cwd: root, sessionId: 'cross-arm' })
try {
  archive.ingest([source])
  archive.setSynchronized(true)
  const claim = Object.fromEntries(['type', 'scope', 'entity', 'version', 'actor', 'action']
    .filter(key => source[key] !== undefined).map(key => [key, source[key]]))
  for (const mode of ['always', 'selective']) {
    const result = await verifyEvidence({ claim, now, mode }, archive)
    assert.equal(result.outcome, 'supported', result.reason)
    assert.deepEqual(result.source, source)
  }
  const view = await archive.readView(claim)
  process.stdout.write(JSON.stringify({ schema: 1, taskId: 'cross-arm',
    snapshot: { cutoff: now, watermark: view.watermark, complete: view.complete },
    sources: [source] }))
} finally {
  archive.close()
  rmSync(root, { recursive: true, force: true })
}
"""
        result = subprocess.run(["node", "--input-type=module", "-e", script],
                                cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_real_node_normalizer_source_is_preserved_across_arms(self):
        document = self.shared_source_archive(r"""
const event = { type: 'commandExecution', id: 'node-execution',
  command: 'node --test --test-reporter=tap unit.test.mjs', status: 'completed', exitCode: 0,
  aggregatedOutput: 'TAP version 13\n1..3\n# tests 3\n# pass 1\n# fail 0\n# cancelled 0\n# skipped 1\n# todo 1\n' }
const normalized = normalizeNodeTestEvent(event, { threadId: 'thread-public', scope: 'demo',
  observedAt: '2026-11-27T10:00:00Z', sourceSequence: 1,
  artifactBefore: 'a'.repeat(64), artifactAfter: 'a'.repeat(64) })
assert.equal(normalized.issue, null)
assert.equal(normalized.invalidatesView, false)
const source = normalized.source
assert.equal(source.text, event.aggregatedOutput)
""")
        source = document["sources"][0]
        self.assertEqual({key: source[key] for key in
                          ["testCount", "skippedCount", "todoCount", "parserVersion"]},
                         {"testCount": 1, "skippedCount": 1, "todoCount": 1,
                          "parserVersion": "native-node-tap-v1"})
        original = copy.deepcopy(document)
        self.assertEqual(self.module().validate_archive(document, self.config()["limits"]),
                         original)

    def test_authorization_source_is_preserved_across_arms(self):
        document = self.shared_source_archive(r"""
const source = { eventId: 'grant', sourceId: 'decisions', sourceSequence: 7,
  observedAt: '2026-11-27T10:00:00Z', effectiveAt: '2026-11-27T10:15:00Z',
  expiresAt: '2026-11-27T11:00:00Z', type: 'operation_authorization',
  scope: 'demo', entity: 'release', version: 'c1', role: 'user', kind: 'user_decision',
  actor: 'maintainer', action: 'publish', status: 'granted', complete: true,
  text: 'I approve publishing release c1 in demo until 11:00 UTC.' }
""")
        original = copy.deepcopy(document)
        self.assertEqual(self.module().validate_archive(document, self.config()["limits"]),
                         original)
        for field in ["gold", "claims", "answer"]:
            private = copy.deepcopy(document)
            private["sources"][0][field] = "private evaluation metadata"
            with self.subTest(private_field=field):
                with self.assertRaises(self.module().ContractError):
                    self.module().validate_archive(private, self.config()["limits"])

    def test_turn_expansion_cannot_be_silently_disabled(self):
        module = self.module()
        config = self.config()
        config["retrieval"]["expand_turns_on_display"] = False
        with self.assertRaises(module.ContractError):
            module.validate_config(config)

    def test_retrieval_model_substitution_is_rejected(self):
        module = self.module()
        config = self.config()
        config["models"]["embedding"]["model"] = "bm25-or-fake-embedding"
        with self.assertRaises(module.ContractError):
            module.validate_config(config)

    def test_wrong_window_size_is_not_labeled_official(self):
        module = self.module()
        config = self.config()
        config["retrieval"]["chunk_size"] = 512
        with self.assertRaises(module.ContractError):
            module.validate_config(config)

    def test_supervision_fields_are_rejected_at_all_structured_levels(self):
        module = self.module()
        limits = self.config()["limits"]
        cases = []
        top = public_archive()
        top["gold"] = {"source": "evt-1"}
        cases.append(top)
        nested = public_archive()
        nested["sources"][0]["transport"] = {"claims": [{"answer": "passed"}]}
        cases.append(nested)
        target = public_archive()
        target["sources"][0]["expected_source"] = "runner"
        cases.append(target)
        for document in cases:
            with self.subTest(document=document):
                with self.assertRaises(module.ContractError):
                    module.validate_archive(document, limits)

    def test_raw_test_output_is_preserved_even_when_it_mentions_expected(self):
        module = self.module()
        document = public_archive()
        valid = module.validate_archive(document, self.config()["limits"])
        self.assertEqual(valid["sources"][0]["text"],
                         "AssertionError: expected 42, received 41.\n")
        self.assertEqual(valid["sources"][0]["observedAt"], "2026-11-27T10:00:00Z")

    def test_same_day_future_source_fails_before_retrieval(self):
        module = self.module()
        document = public_archive()
        document["sources"][0]["observedAt"] = "2026-11-27T11:00:00Z"
        with self.assertRaises(module.ContractError):
            module.validate_archive(document, self.config()["limits"])

    def test_incomplete_snapshot_cannot_run(self):
        module = self.module()
        document = public_archive()
        document["snapshot"]["complete"] = False
        with self.assertRaises(module.ContractError):
            module.validate_archive(document, self.config()["limits"])

    def test_missing_event_timestamp_is_not_synthesized(self):
        module = self.module()
        document = public_archive()
        del document["sources"][0]["observedAt"]
        with self.assertRaises(module.ContractError):
            module.validate_archive(document, self.config()["limits"])

    def test_duplicate_event_identity_is_rejected(self):
        module = self.module()
        document = public_archive()
        document["sources"].append(copy.deepcopy(document["sources"][0]))
        with self.assertRaises(module.ContractError):
            module.validate_archive(document, self.config()["limits"])

    def test_unknown_metadata_does_not_become_an_implicit_answer_channel(self):
        module = self.module()
        document = public_archive()
        document["sources"][0]["scoringAnnotation"] = "supports-the-answer"
        with self.assertRaises(module.ContractError):
            module.validate_archive(document, self.config()["limits"])

    def test_original_request_is_not_rewritten_or_trimmed(self):
        module = self.module()
        request = "  May we continue after the reported test failure?\n"
        self.assertEqual(module.validate_request(request, self.config()["limits"]), request)

    def test_archive_file_size_limit_precedes_json_parsing(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archive.json"
            path.write_text("not-json-but-oversized", encoding="utf-8")
            with self.assertRaises(module.BudgetExceeded):
                module.read_json_bounded(path, 3)

    def test_duplicate_json_keys_cannot_hide_supervision_or_cutoff(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "archive.json"
            path.write_text('{"snapshot":1,"snapshot":2}', encoding="utf-8")
            with self.assertRaises(module.ContractError):
                module.read_json_bounded(path, 1000)

    def test_call_cap_rejects_before_a_third_dispatch_is_reserved(self):
        module = self.module()
        limits = self.config()["limits"]
        limits["max_http_dispatches"] = 2
        budget = module.RunBudget(limits)
        budget.reserve_session("dev-01")
        budget.reserve_dispatch("embedding", 3)
        budget.reserve_dispatch("rerank", 4)
        with self.assertRaises(module.BudgetExceeded):
            budget.reserve_dispatch("embedding", 1)
        ledger = budget.snapshot()
        self.assertEqual(ledger["observed_http_dispatch_attempts"], 2)
        self.assertEqual(ledger["reference_input_tokens_observed"], 7)
        self.assertIsNone(ledger["http_requests_total"])

    def test_session_cap_rejects_a_second_task(self):
        module = self.module()
        budget = module.RunBudget(self.config()["limits"])
        budget.reserve_session("dev-01")
        with self.assertRaises(module.BudgetExceeded):
            budget.reserve_session("dev-02")
        self.assertEqual(budget.snapshot()["sessions_observed"], 1)

    def test_text_cap_blocks_before_any_dispatch(self):
        module = self.module()
        limits = self.config()["limits"]
        limits["max_processed_input_tokens"] = 10
        budget = module.RunBudget(limits)
        with self.assertRaises(module.BudgetExceeded):
            budget.reserve_dispatch("embedding", 11)
        self.assertEqual(budget.snapshot()["observed_http_dispatch_attempts"], 0)

    def test_upstream_log_rows_are_not_http_call_counts(self):
        module = self.module()
        budget = module.RunBudget(self.config()["limits"])
        budget.observe_upstream_log({"call_type": "rerank", "error_present": False})
        budget.observe_upstream_log({"call_type": "rerank", "error_present": True})
        ledger = budget.snapshot()
        self.assertEqual(ledger["upstream_log_entries_observed"], 2)
        self.assertEqual(ledger["observed_http_dispatch_attempts"], 0)
        self.assertIsNone(ledger["provider_cost_total"])

    def test_budget_matched_display_clips_only_after_full_expansion(self):
        module = self.module()
        expanded = "Memory 1 (chunk=0):\n" + "original full turn " * 30
        display = module.render_display(expanded, "budget-matched", 160, CharacterEncoding())
        self.assertEqual(display["policy"], "expanded-token-prefix-with-marker-v1")
        self.assertTrue(display["truncated"])
        self.assertTrue(display["context"].startswith("Memory 1 (chunk=0):\n"))
        self.assertIn("TRUNCATED", display["context"])
        self.assertLessEqual(len(display["context"]), 160)
        self.assertNotEqual(display["expanded_sha256"], display["delivered_sha256"])

    def test_faithful_display_never_silently_truncates(self):
        module = self.module()
        with self.assertRaises(module.BudgetExceeded):
            module.render_display("a" * 161, "faithful", 160, CharacterEncoding())
        text = "Memory 1: full original\n\nMemory 2: full original\n"
        display = module.render_display(text, "faithful", 160, CharacterEncoding())
        self.assertEqual(display["context"], text)
        self.assertEqual(display["expanded_sha256"], display["delivered_sha256"])
        self.assertFalse(display["truncated"])

    def test_missing_dependencies_fail_closed(self):
        module = self.module()
        with mock.patch.object(module.importlib.util, "find_spec", return_value=None):
            dependencies = module.dependency_report()
        self.assertFalse(dependencies["available"])
        self.assertIn("openai", dependencies["missing"])
        self.assertIn("tiktoken", dependencies["missing"])
        with self.assertRaises(module.ContractError):
            module.require_dependencies(dependencies)

    def test_changed_upstream_file_is_rejected(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "source.py"
            path.write_text("abc", encoding="utf-8")
            expected = {"source.py": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"}
            module.verify_source_files(root, expected)
            path.write_text("abd", encoding="utf-8")
            with self.assertRaises(module.ContractError):
                module.verify_source_files(root, expected)

    def test_wrong_checkout_commit_is_rejected(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(["git", "init", "-q", directory], check=True, capture_output=True)
            subprocess.run(["git", "-C", directory, "-c", "user.name=Test",
                            "-c", "user.email=test@example.invalid", "commit",
                            "--allow-empty", "-qm", "unrelated source"],
                           check=True, capture_output=True)
            with self.assertRaises(module.ContractError):
                module.verify_upstream(Path(directory), self.config())

    def test_default_check_never_dispatches_or_creates_output(self):
        module = self.module()
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with contextlib.redirect_stdout(output), mock.patch.object(
                module, "run_retrieval", side_effect=AssertionError("run was dispatched")
            ), mock.patch("socket.socket.connect", side_effect=AssertionError("network used")):
                code = module.main(["--upstream", directory])
            self.assertEqual(code, 2)
            result = json.loads(output.getvalue())
            self.assertEqual(result["mode"], "check")
            self.assertEqual(result["model_requests_sent"], 0)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_run_requires_explicit_inputs_and_output(self):
        module = self.module()
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                module.main(["--run", "--upstream", "/missing"])
        self.assertEqual(raised.exception.code, 2)

    def test_unexpected_run_failure_does_not_claim_zero_requests(self):
        module = self.module()
        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch.object(
            module, "run_retrieval", side_effect=OSError("provider may have run; do not print test-secret")
        ):
            code = module.main(["--run", "--upstream", "/unused", "--archive", "/unused-archive",
                                "--request", "/unused-request", "--output", "/unused-output"])
        self.assertEqual(code, 2)
        result = json.loads(output.getvalue())
        self.assertIsNone(result["model_requests_sent"])
        self.assertNotIn("test-secret", output.getvalue())

    def test_nested_expected_result_and_answer_annotations_are_rejected(self):
        module = self.module()
        for key in ("expected_result", "answer"):
            document = public_archive()
            document["sources"][0]["transport"] = {key: "passed"}
            with self.subTest(key=key), self.assertRaises(module.ContractError):
                module.validate_archive(document, self.config()["limits"])

    def test_check_reports_only_credential_availability(self):
        module = self.module()
        with mock.patch.dict(os.environ, {
            "VECTORIZE_API_KEY": "test-secret-embedding-should-never-print",
            "RERANK_API_KEY": "test-secret-reranker-should-never-print",
        }):
            status = module.credential_status(self.config())
        self.assertEqual(status, {"embedding": True, "reranker": True})
        encoded = json.dumps(status)
        self.assertNotIn("test-secret", encoded)

    def adapter_boundary(self):
        return SimpleNamespace(
            embedding_client=SimpleNamespace(
                max_retries=2,
                _client=SimpleNamespace(event_hooks={"request": [], "response": []},
                                        follow_redirects=True),
            ),
            rerank_api_key="test-service-key",
        )

    def test_rerank_cap_blocks_before_another_local_http_request(self):
        module = self.module()
        received = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                received.append(self.rfile.read(int(self.headers["Content-Length"])))
                body = b'{"results": [{"index": 0, "relevance_score": 0.8}]}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            config = self.config()
            config["limits"]["max_http_dispatches"] = 1
            url = f"http://127.0.0.1:{server.server_port}/rerank"
            config["models"]["reranker"]["base_url"] = url.rsplit("/", 1)[0]
            config["models"]["reranker"]["endpoint"] = "/rerank"
            budget = module.RunBudget(config["limits"], authorize_dispatch=fixture_admission,
                dispatch_binding={"attempt_id": "fixture", "config_sha256": module.digest_text(module.canonical(config)),
                                  "checkpoint_sha256": "a" * 64})
            adapter = self.adapter_boundary()
            module.instrument_adapter(adapter, budget, CharacterEncoding(), config)
            payload = {"model": "rerank-v3.5", "query": "q", "documents": ["d"], "top_n": 1}
            adapter._post_json(url, payload, 2)
            with self.assertRaises(module.BudgetExceeded):
                adapter._post_json(url, payload, 2)
            self.assertEqual(len(received), 1)
            self.assertEqual(budget.snapshot()["observed_http_dispatch_attempts"], 1)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_embedding_hook_rejects_non_embedding_requests_before_dispatch(self):
        module = self.module()
        config = self.config()
        budget = module.RunBudget(config["limits"])
        adapter = self.adapter_boundary()
        module.instrument_adapter(adapter, budget, CharacterEncoding(), config)
        request = SimpleNamespace(method="POST", url="https://unexpected.invalid/embeddings",
                                  content=b'{"input": ["some text"]}')
        with self.assertRaises(module.ContractError):
            asyncio.run(adapter.embedding_client._client.event_hooks["request"][-1](request))
        self.assertEqual(budget.snapshot()["observed_http_dispatch_attempts"], 0)

    def test_capture_log_discards_request_secrets_and_keeps_usage(self):
        module = self.module()
        config = self.config()
        budget = module.RunBudget(config["limits"])
        adapter = self.adapter_boundary()
        module.instrument_adapter(adapter, budget, CharacterEncoding(), config)
        asyncio.run(adapter._write_request_log(
            call_type="embedding", stage="add", request={"secret": "never-store-this"},
            response={"model": "text-embedding-3-small", "usage": {"prompt_tokens": 12, "total_tokens": 12}},
            started=0, error="possibly sensitive never-store-this",
        ))
        ledger = budget.snapshot()
        self.assertNotIn("never-store-this", json.dumps(ledger))
        self.assertEqual(ledger["provider_usage_observed"][0]["usage"]["prompt_tokens"], 12)
        self.assertIsNone(ledger["http_requests_total"])

    def test_returned_provider_model_is_recorded_instead_of_assumed(self):
        module = self.module()
        config = self.config()
        budget = module.RunBudget(config["limits"])
        adapter = self.adapter_boundary()
        module.instrument_adapter(adapter, budget, CharacterEncoding(), config)
        asyncio.run(adapter._write_request_log(
            call_type="embedding", stage="search", request={},
            response={"model": "text-embedding-3-small", "usage": {"total_tokens": 3}},
            started=0,
        ))
        event = budget.snapshot()["provider_usage_observed"][0]
        self.assertEqual(event.get("provider_model"), "text-embedding-3-small")

    def test_run_retains_dependency_preflight_when_local_runtime_fails(self):
        module = self.module()

        async def blocked_before_inference(*args, **kwargs):
            raise module.ContractError("test_local_runtime_unavailable")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "public.json"
            archive.write_text(json.dumps(public_archive()), encoding="utf-8")
            request = root / "request.txt"
            request.write_text("Can I continue?", encoding="utf-8")
            output = root / "result"
            preflight = {"status": "ready", "errors": [],
                         "credentials_available": {"embedding": True, "reranker": True},
                         "dependencies": {"modules": {"test-only": {"version": "1"}}}}
            with mock.patch.object(module, "preflight", return_value=preflight), mock.patch.object(
                module, "_retrieve", side_effect=blocked_before_inference
            ):
                result = module.run_retrieval(root, self.config(), archive, request, output, "faithful",
                    authorize_dispatch=fixture_admission,
                    dispatch_binding={"attempt_id": "fixture", "config_sha256": module.digest_text(module.canonical(self.config())),
                                      "checkpoint_sha256": "a" * 64})
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["observed_http_dispatch_attempts"], 0)
            self.assertTrue((output / "preflight.json").is_file())
            saved = json.loads((output / "preflight.json").read_text())
            self.assertEqual(saved["dependencies"]["modules"]["test-only"]["version"], "1")


if __name__ == "__main__":
    unittest.main()
