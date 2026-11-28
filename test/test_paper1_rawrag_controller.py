"""Offline Raw-RAG controller contracts; fixtures are never research results."""
from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from test_paper1_rawrag import CharacterEncoding, public_archive


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    key = "p1_bound_" + name
    if key not in sys.modules:
        path = ROOT / "scripts/paper1" / (name + ".py")
        if not path.is_file():
            return None
        spec = importlib.util.spec_from_file_location(key, path)
        value = importlib.util.module_from_spec(spec)
        sys.modules[key] = value
        spec.loader.exec_module(value)
    return sys.modules[key]


def sha(value):
    return hashlib.sha256(value).hexdigest()


def admission(intent):
    return {"schema_version": 1, "kind": "p1-dispatch-admission-receipt",
            "decision": "allow", "dispatch_id": intent["dispatch_id"],
            "intent_sha256": intent["intent_sha256"],
            "request_sha256": intent["request_sha256"],
            "admission_id": "ledger-" + "a" * 64}


def adapter_boundary():
    return SimpleNamespace(embedding_client=SimpleNamespace(max_retries=2,
        _client=SimpleNamespace(event_hooks={"request": [], "response": []},
                               follow_redirects=True)), rerank_api_key="fixture-only-key")


def embedding_request():
    return SimpleNamespace(method="POST", url="https://api.openai.com/v1/embeddings",
        content=b'{"model":"text-embedding-3-small","input":["hello"]}', extensions={})


class DispatchAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.adapter = load("rawrag_adapter")
        self.config = self.adapter.load_config()

    def binding(self):
        return {"attempt_id": "fixture", "config_sha256": self.adapter.digest_text(self.adapter.canonical(self.config)),
                "checkpoint_sha256": "b" * 64}

    def test_embedding_without_admission_stops_before_any_observed_dispatch(self):
        budget = self.adapter.RunBudget(self.config["limits"])
        boundary = adapter_boundary()
        self.adapter.instrument_adapter(boundary, budget, CharacterEncoding(), self.config)
        with self.assertRaisesRegex(self.adapter.ContractError, "dispatch_controller_required"):
            asyncio.run(boundary.embedding_client._client.event_hooks["request"][-1](embedding_request()))
        self.assertEqual(budget.snapshot()["observed_http_dispatch_attempts"], 0)

    def test_standalone_run_without_admission_does_not_read_provider_credentials(self):
        with mock.patch.object(self.adapter, "preflight", side_effect=AssertionError("credential preflight ran")):
            result = self.adapter.run_retrieval("unused", self.config, "unused", "unused", "unused", "faithful")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["model_requests_sent"], 0)
        self.assertIn("dispatch_controller_required", result["errors"])

    def test_mismatched_admission_never_reserves_dispatch(self):
        self.assertTrue(hasattr(self.adapter.RunBudget, "admit_dispatch"), "dispatch admission is missing")
        def wrong(intent):
            return {**admission(intent), "request_sha256": "f" * 64}
        budget = self.adapter.RunBudget(self.config["limits"], authorize_dispatch=wrong,
            dispatch_binding=self.binding())
        boundary = adapter_boundary()
        self.adapter.instrument_adapter(boundary, budget, CharacterEncoding(), self.config)
        with self.assertRaisesRegex(self.adapter.ContractError, "dispatch_admission_unconfirmed"):
            asyncio.run(boundary.embedding_client._client.event_hooks["request"][-1](embedding_request()))
        self.assertEqual(budget.snapshot()["observed_http_dispatch_attempts"], 0)

    def test_retries_have_distinct_admissions_and_usage_is_linked_to_dispatch(self):
        self.assertTrue(hasattr(self.adapter.RunBudget, "admit_dispatch"), "dispatch admission is missing")
        intents = []
        def allow(intent):
            intents.append(copy.deepcopy(intent))
            return admission(intent)
        budget = self.adapter.RunBudget(self.config["limits"], authorize_dispatch=allow,
            dispatch_binding=self.binding())
        boundary = adapter_boundary()
        self.adapter.instrument_adapter(boundary, budget, CharacterEncoding(), self.config)
        hook = boundary.embedding_client._client.event_hooks["request"][-1]
        async def exercise():
            await hook(embedding_request())
            await boundary._write_request_log(call_type="embedding", stage="add", request={},
                response=None, started=0, attempt=1, error="fixture failure")
            await hook(embedding_request())
            await boundary._write_request_log(call_type="embedding", stage="add", request={},
                response={"model": "text-embedding-3-small", "usage": {"prompt_tokens": 1, "total_tokens": 1}},
                started=0, attempt=2)
        asyncio.run(exercise())
        ledger = budget.snapshot()
        self.assertEqual(ledger["observed_http_dispatch_attempts"], 2)
        self.assertNotEqual(intents[0]["dispatch_id"], intents[1]["dispatch_id"])
        self.assertEqual(intents[0].get("max_output_tokens"), 0)
        self.assertEqual(intents[0].get("max_response_bytes"), 8388608)
        self.assertEqual(intents[0].get("timeout_ms"), 30000)
        self.assertEqual([row["dispatch_id"] for row in ledger["provider_usage_observed"]], [1, 2])
        self.assertEqual(ledger["provider_usage_observed"][1]["usage"]["prompt_tokens"], 1)
        self.assertNotIn("fixture failure", json.dumps(ledger))

    def test_admission_bound_to_another_config_blocks_before_callback(self):
        budget = self.adapter.RunBudget(self.config["limits"], authorize_dispatch=admission,
            dispatch_binding={**self.binding(), "config_sha256": "f" * 64})
        boundary = adapter_boundary()
        with self.assertRaisesRegex(self.adapter.ContractError, "dispatch_config_binding_mismatch"):
            self.adapter.instrument_adapter(boundary, budget, CharacterEncoding(), self.config)
        self.assertEqual(budget.snapshot()["observed_http_dispatch_attempts"], 0)

    def test_slow_admission_cannot_send_after_session_deadline(self):
        def expire(intent):
            budget.started -= self.config["limits"]["max_session_seconds"] + 1
            return admission(intent)
        budget = self.adapter.RunBudget(self.config["limits"], authorize_dispatch=expire,
            dispatch_binding=self.binding())
        boundary = adapter_boundary()
        self.adapter.instrument_adapter(boundary, budget, CharacterEncoding(), self.config)
        with self.assertRaises(self.adapter.BudgetExceeded):
            asyncio.run(boundary.embedding_client._client.event_hooks["request"][-1](embedding_request()))
        self.assertEqual(budget.snapshot()["observed_http_dispatch_attempts"], 0)

    def test_failed_rerank_admission_never_opens_transport(self):
        def deny(intent):
            return {**admission(intent), "decision": "deny"}
        budget = self.adapter.RunBudget(self.config["limits"], authorize_dispatch=deny,
            dispatch_binding=self.binding())
        boundary = adapter_boundary()
        opener = SimpleNamespace(open=lambda *a, **kw: self.fail("HTTP opened before admission"))
        with mock.patch.object(self.adapter.urllib.request, "build_opener", return_value=opener):
            self.adapter.instrument_adapter(boundary, budget, CharacterEncoding(), self.config)
        with self.assertRaisesRegex(self.adapter.ContractError, "dispatch_admission_unconfirmed"):
            boundary._post_json("https://api.cohere.com/v2/rerank",
                {"model": "rerank-v3.5", "query": "q", "documents": ["d"], "top_n": 1}, 10)
        self.assertEqual(budget.snapshot()["observed_http_dispatch_attempts"], 0)

    def test_response_with_another_embedding_model_cannot_complete(self):
        budget = self.adapter.RunBudget(self.config["limits"], authorize_dispatch=admission,
            dispatch_binding=self.binding())
        boundary = adapter_boundary()
        self.adapter.instrument_adapter(boundary, budget, CharacterEncoding(), self.config)
        async def exercise():
            await boundary.embedding_client._client.event_hooks["request"][-1](embedding_request())
            await boundary._write_request_log(call_type="embedding", stage="add", request={},
                response={"model": "different-model", "usage": {"prompt_tokens": 7, "total_tokens": 7}},
                started=0, attempt=1)
        with self.assertRaisesRegex(self.adapter.ContractError, "provider_embedding_model_mismatch"):
            asyncio.run(exercise())
        self.assertEqual(budget.snapshot()["observed_http_dispatch_attempts"], 1)
        self.assertEqual(budget.snapshot()["provider_usage_observed"][0]["usage"]["prompt_tokens"], 7)
        self.assertNotIn("different-model", json.dumps(budget.snapshot()))

    def test_oversized_embedding_response_stops_at_declared_content_length(self):
        budget = self.adapter.RunBudget(self.config["limits"], authorize_dispatch=admission,
            dispatch_binding=self.binding())
        boundary = adapter_boundary()
        self.adapter.instrument_adapter(boundary, budget, CharacterEncoding(), self.config)
        request = embedding_request()
        closed = []
        async def close():
            closed.append(True)
        async def bytes_forbidden():
            self.fail("oversized body was read")
            yield b""
        response = SimpleNamespace(request=request, status_code=200,
            headers={"content-length": str(self.config["limits"]["max_response_bytes"] + 1)},
            aiter_bytes=bytes_forbidden, aclose=close)
        async def exercise():
            await boundary.embedding_client._client.event_hooks["request"][-1](request)
            await boundary.embedding_client._client.event_hooks["response"][-1](response)
        with self.assertRaisesRegex(self.adapter.BudgetExceeded, "embedding_response_byte_limit"):
            asyncio.run(exercise())
        self.assertEqual(closed, [True])


def usage_fixture():
    return {"schema": 1, "closed": True, "observed_http_dispatch_attempts": 2,
        "controller_binding": {"attempt_id": "fixture", "config_sha256": "a" * 64,
                               "checkpoint_sha256": "b" * 64},
        "dispatches": [
            {"dispatch_id": 1, "kind": "embedding", "operation_id": "embed-op",
             "provider": "openai", "model": "text-embedding-3-small", "http_status": 200,
             "reference_input_tokens": 9999, "provider_request_id": "req_fixture1"},
            {"dispatch_id": 2, "kind": "rerank", "operation_id": "rerank-op",
             "provider": "cohere", "model": "rerank-v3.5", "http_status": 200,
             "reference_input_tokens": 9999, "provider_request_id": None}],
        "provider_usage_observed": [
            {"dispatch_id": 1, "call_type": "embedding", "error_present": False,
             "provider_model": "text-embedding-3-small", "provider_model_mismatch": False,
             "usage": {"prompt_tokens": 7, "total_tokens": 7}, "billed_units": None},
            {"dispatch_id": 2, "call_type": "rerank", "error_present": False,
             "provider_model": None, "provider_model_mismatch": False,
             "usage": None, "billed_units": {"search_units": 2.0}}]}


class UsageNormalizationTests(unittest.TestCase):
    def normalize(self, ledger):
        controller = load("rawrag_controller")
        self.assertTrue(hasattr(controller, "normalize_usage"), "provider usage normalization is missing")
        return controller.normalize_usage(ledger, binding=usage_fixture()["controller_binding"],
            source_ref="rawrag/ledger.json", source_sha256="c" * 64, terminal_status="retrieval_complete")

    def test_provider_units_are_normalized_without_reference_token_substitution(self):
        report = self.normalize(usage_fixture())
        rows = [row for row in report["usage_rows"] if row["event"] == "usage"]
        self.assertTrue(report["complete"], report["issues"])
        self.assertEqual([(r["component"], r["values"]) for r in rows],
                         [("embedding", {"quantity": 7}), ("rerank", {"quantity": 2.0})])
        self.assertEqual([r["operation_id"] for r in rows], ["embed-op", "rerank-op"])
        self.assertEqual(report["metering"]["rerank"]["unit"], "search_unit")
        self.assertIsNone(report["actual_spend"])

    def test_failed_retry_without_usage_keeps_total_incomplete(self):
        ledger = usage_fixture()
        ledger["dispatches"].append({"dispatch_id": 3, "kind": "embedding", "operation_id": "retry-op",
            "provider": "openai", "model": "text-embedding-3-small", "http_status": None,
            "reference_input_tokens": 400, "provider_request_id": None})
        ledger["observed_http_dispatch_attempts"] = 3
        ledger["provider_usage_observed"].append({"dispatch_id": 3, "call_type": "embedding",
            "error_present": True, "provider_model": None, "usage": None, "billed_units": None})
        report = self.normalize(ledger)
        self.assertFalse(report["complete"])
        self.assertEqual(len([r for r in report["usage_rows"] if r["event"] == "usage"]), 2)
        seals = {r["component"]: r for r in report["usage_rows"] if r["event"] == "component_end"}
        self.assertEqual(seals["embedding"]["coverage"], "incomplete")

    def test_duplicate_success_logs_are_not_charged_twice(self):
        ledger = usage_fixture()
        ledger["provider_usage_observed"].append(copy.deepcopy(ledger["provider_usage_observed"][0]))
        report = self.normalize(ledger)
        self.assertFalse(report["complete"])
        self.assertEqual([r["component"] for r in report["usage_rows"] if r["event"] == "usage"], ["rerank"])

    def test_missing_rerank_units_do_not_become_dispatch_count(self):
        ledger = usage_fixture()
        ledger["provider_usage_observed"][1]["billed_units"] = None
        report = self.normalize(ledger)
        self.assertFalse(report["complete"])
        self.assertEqual([r["component"] for r in report["usage_rows"] if r["event"] == "usage"], ["embedding"])

    def test_wrong_checkpoint_ledger_is_rejected(self):
        ledger = usage_fixture()
        ledger["controller_binding"]["checkpoint_sha256"] = "f" * 64
        report = self.normalize(ledger)
        self.assertFalse(report["complete"])
        self.assertEqual(report["usage_rows"], [])

    def test_real_experiment_cost_accepts_provider_quantities_and_rejects_missing_usage(self):
        experiment = load("experiment")
        rates = {"generic": {"price": 1, "per": 1, "unit": "operation", "source": "fixture", "as_of": "2026-11-28"},
                 "model": {"price": 1, "per": 1, "unit": "token", "source": "fixture", "as_of": "2026-11-28"},
                 "embedding": {"price": 2, "per": 1, "unit": "token", "source": "fixture", "as_of": "2026-11-28"},
                 "rerank": {"price": 3, "per": 1, "unit": "search_unit", "source": "fixture", "as_of": "2026-11-28"}}
        components = {name: {"kind": "quantity", "unit": "operation", "rate": "generic"}
                      for name in experiment.PIPELINE_COMPONENTS}
        components.update(model={"kind": "tokens", "rates": {"input_uncached": "model", "input_cached": "model", "output": "model"}},
                          embedding={"kind": "quantity", "unit": "token", "rate": "embedding"},
                          rerank={"kind": "quantity", "unit": "search_unit", "rate": "rerank"})
        omitted = [name for name in experiment.PIPELINE_COMPONENTS if name not in {"model", "embedding", "rerank"}]
        measurement = {"schema_version": 1, "frozen": True, "currency": "USD", "rate_card_id": "fixture",
            "rates": rates, "components": components, "cost_scope": "full_pipeline_per_scheduled_task",
            "allocation_rule": "component_factors_per_scheduled_task_v1",
            "required_components": {"B": list(experiment.PIPELINE_COMPONENTS)},
            "mandatory_measured_components": {"B": ["model", "embedding", "rerank"]},
            "not_applicable": {"B": omitted}, "allocation_factors": {name: 1 for name in components}}
        remaining = [{"event": "usage", "usage_id": "model-fixture", "measurement_id": "model-fixture",
            "operation_id": "model-fixture", "component": "model", "counter_kind": "delta",
            "values": {"input_tokens": 5, "cached_input_tokens": 0, "output_tokens": 1}, "source_ref": "fixture"},
            {"event": "component_end", "component": "model", "coverage": "measured",
             "usage_ids": ["model-fixture"], "reason": None, "evidence_ref": "fixture"}]
        remaining.extend({"event": "component_end", "component": name, "coverage": "not_applicable",
                          "usage_ids": [], "reason": "fixture_scope", "evidence_ref": "fixture"} for name in omitted)
        result = experiment.standardized_cost(measurement, "B", self.normalize(usage_fixture())["usage_rows"] + remaining)
        self.assertTrue(result["complete"], result["issues"])
        self.assertEqual(result["standardized_cost"], 26.0)  # 7*2 + 2*3 + (5+1)*1.
        ledger = usage_fixture()
        ledger["provider_usage_observed"][1]["billed_units"] = None
        partial = experiment.standardized_cost(measurement, "B", self.normalize(ledger)["usage_rows"] + remaining)
        self.assertFalse(partial["complete"])
        self.assertIsNone(partial["standardized_cost"])


class BoundInputTests(unittest.TestCase):
    def make_inputs(self, root):
        archive = root / "archive.json"
        request = root / "request.txt"
        archive.write_text(json.dumps(public_archive()), encoding="utf-8")
        request.write_text("original request\n", encoding="utf-8")
        checkpoint = {"task_id": "dev-01", "replicate": 1,
            "public_sha256": "1" * 64, "workspace_snapshot_sha256": "2" * 64,
            "native_parent_thread_id": "parent", "native_capture_sha256": "3" * 64,
            "native_compaction_item_id": "compaction", "source_archive_sha256": sha(archive.read_bytes()),
            "shared_reader_config_sha256": "4" * 64, "original_request_sha256": sha(request.read_bytes())}
        return archive, request, checkpoint

    def test_changed_original_request_is_rejected_before_runtime_preflight(self):
        controller = load("rawrag_controller")
        self.assertIsNotNone(controller, "bound retrieval controller is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, request, checkpoint = self.make_inputs(root)
            checkpoint["original_request_sha256"] = "0" * 64
            with mock.patch.object(controller.baseline, "preflight", side_effect=AssertionError("runtime ran")):
                with self.assertRaisesRegex(controller.baseline.ContractError, "original_request_binding_mismatch"):
                    controller.run_bound_retrieval(upstream=root, config=load("rawrag_adapter").load_config(),
                        archive_path=archive, request_path=request, output_path=root / "output",
                        checkpoint=checkpoint, attempt_id="fixture", authorize_dispatch=admission, display="faithful")
            self.assertFalse((root / "output").exists())

    def test_input_change_during_preflight_cannot_reach_retrieval(self):
        controller = load("rawrag_controller")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, request, checkpoint = self.make_inputs(root)
            def changed(*args):
                request.write_text("another request\n", encoding="utf-8")
                return {"status": "ready", "errors": [], "credentials_available": {"embedding": True, "reranker": True}}
            with mock.patch.object(controller.baseline, "preflight", side_effect=changed), mock.patch.object(
                    controller.baseline, "_retrieve", side_effect=AssertionError("changed input dispatched")):
                with self.assertRaisesRegex(controller.baseline.ContractError, "bound_run_input_changed"):
                    controller.run_bound_retrieval(upstream=root, config=controller.baseline.load_config(),
                        archive_path=archive, request_path=request, output_path=root / "output",
                        checkpoint=checkpoint, attempt_id="fixture", authorize_dispatch=admission, display="faithful")
            self.assertFalse((root / "output").exists())

    def test_completed_adapter_output_becomes_a_bound_packet_and_separate_usage(self):
        controller = load("rawrag_controller")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, request, checkpoint = self.make_inputs(root)
            config = controller.baseline.load_config()
            expanded, delivered = "Full expanded fixture context", "Fixture delivered context"
            async def local_retrieval(upstream, cfg, document, original, output, mode, budget):
                # Replace external inference only. Exercise the real outer budget,
                # output persistence and controller receipt/usage conversion.
                for kind, model, endpoint, response in [
                    ("embedding", "text-embedding-3-small", "https://api.openai.com/v1/embeddings",
                     {"usage": {"prompt_tokens": 7, "total_tokens": 7}, "provider_model": "text-embedding-3-small"}),
                    ("rerank", "rerank-v3.5", "https://api.cohere.com/v2/rerank",
                     {"billed_units": {"search_units": 2}, "provider_model": None})]:
                    number = budget.admit_dispatch(kind, 100, endpoint=endpoint, model=model, request_bytes=b"fixture")
                    budget.observe_response(number, 200)
                    budget.observe_upstream_log({"dispatch_id": number, "call_type": kind,
                        "error_present": False, "provider_model_mismatch": False, **response})
                report = {"schema": 1, "status": "retrieval_complete",
                    "implementation": cfg["implementation"], "upstream_commit": controller.baseline.UPSTREAM_COMMIT,
                    "snapshot_sha256": controller._digest(document), "snapshot": document["snapshot"],
                    "request_sha256": sha(original.encode()), "query_policy": "original_request",
                    "config_sha256": controller._digest(cfg),
                    "display": {"display_mode": mode, "policy": "expanded-token-prefix-with-marker-v1",
                        "expanded_sha256": sha(expanded.encode()), "delivered_sha256": sha(delivered.encode()),
                        "expanded_tokens": 10, "delivered_tokens": 5, "truncated": True}}
                (output / "expanded-context.txt").write_text(expanded)
                (output / "context.txt").write_text(delivered)
                controller.baseline.write_json(output / "retrieval.json", report)
                return report
            preflight = {"status": "ready", "errors": [], "credentials_available": {"embedding": True, "reranker": True}}
            with mock.patch.object(controller.baseline, "preflight", return_value=preflight), mock.patch.object(
                    controller.baseline, "_retrieve", side_effect=local_retrieval):
                result = controller.run_bound_retrieval(upstream=root, config=config, archive_path=archive,
                    request_path=request, output_path=root / "output", checkpoint=checkpoint,
                    attempt_id="fixture", authorize_dispatch=admission, display="budget-matched")
            self.assertIn("packet", result, "bound packet publication is missing")
            self.assertEqual(result["packet"]["text"], delivered)
            self.assertEqual(result["packet"]["original_request_sha256"], checkpoint["original_request_sha256"])
            self.assertEqual(result["packet"]["archive_sha256"], checkpoint["source_archive_sha256"])
            self.assertEqual(result["completeness"], {"usage": True, "evidence": True})
            self.assertEqual([r["values"]["quantity"] for r in result["usage_rows"] if r["event"] == "usage"], [7, 2])
            self.assertTrue((root / "output/usage.jsonl").read_bytes().endswith(b"\n"))
            receipt = json.loads((root / "output/binding-receipt.json").read_text())
            self.assertEqual(receipt["checkpoint"], checkpoint)
            self.assertNotEqual(receipt["expanded_sha256"], receipt["delivered_sha256"])
            self.assertNotIn("checkpoint", result["packet"])
            self.assertTrue(all(set(ref) == {"path", "sha256"} for ref in result["trace_refs"]))


class InstalledSdkBoundaryTests(unittest.TestCase):
    def test_installed_sdk_consumes_bounded_body_with_exactly_one_admission(self):
        if importlib.util.find_spec("openai") is None:
            self.skipTest("run with the isolated Raw-RAG environment for its real SDK")
        runtime = load("check_rawrag_runtime")
        safe_environment = runtime.CredentialFreeEnvironment(os.environ)
        with mock.patch.object(os, "environ", safe_environment), runtime.OfflineGuard():
            import openai
            http = importlib.import_module("httpx2" if importlib.util.find_spec("httpx2") else "httpx")
            baseline = load("rawrag_adapter")
            config = baseline.load_config()
            observed = []
            def allow(intent):
                observed.append("admitted")
                return admission(intent)
            def receive(request):
                observed.append("transport")
                return http.Response(200, json={"object": "list", "model": "text-embedding-3-small",
                    "data": [{"object": "embedding", "index": 0, "embedding": [0.25, 0.75]}],
                    "usage": {"prompt_tokens": 1, "total_tokens": 1}}, headers={"x-request-id": "req_fixture"})
            async def exercise():
                client = openai.AsyncOpenAI(api_key="offline-fixture-only", base_url="https://api.openai.com/v1",
                    http_client=http.AsyncClient(transport=http.MockTransport(receive), trust_env=False))
                boundary = SimpleNamespace(embedding_client=client, rerank_api_key="offline-fixture-only")
                budget = baseline.RunBudget(config["limits"], authorize_dispatch=allow,
                    dispatch_binding={"attempt_id": "sdk-fixture", "config_sha256": baseline.digest_text(baseline.canonical(config)),
                                      "checkpoint_sha256": "a" * 64})
                try:
                    baseline.instrument_adapter(boundary, budget, CharacterEncoding(), config)
                    value = await client.embeddings.create(model="text-embedding-3-small", input=["hello"])
                    await boundary._write_request_log(call_type="embedding", stage="add", request={},
                        response=value.model_dump(), started=0, attempt=1)
                    self.assertEqual(value.data[0].embedding, [0.25, 0.75])
                    self.assertEqual(budget.snapshot()["dispatches"][0]["http_status"], 200)
                    self.assertEqual(budget.snapshot()["provider_usage_observed"][0]["dispatch_id"], 1)
                finally:
                    await client.close()
            asyncio.run(exercise())
        self.assertEqual(observed, ["admitted", "transport"])


if __name__ == "__main__":
    unittest.main()
