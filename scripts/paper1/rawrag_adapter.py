#!/usr/bin/env python3
"""Pinned official Raw-RAG retrieval for P1; no performance claim or reader call.

Default --check is offline: inspect source, dependency metadata, configuration and
credential *presence*. It never reads .env, imports the upstream adapter, loads a
tokenizer or makes a model request. --run requires explicit public archive,
original-request file and a new output directory. Live requests additionally
require the bound controller API; the standalone CLI has no cash admission.

Archive schema:
  {schema:1, taskId, snapshot:{cutoff,watermark,complete:true}, sources:[...]}
Sources use the public camelCase transport fields of paper1/archive.mjs. Their
semantic fields are ingestion assumptions, not an implemented natural-log parser.
Every comparison arm must receive the same fields. No gold/claims/answer-key input.

Runtime changes from the paper runner are declared: one conversation/query,
concurrency one, no SDK retries/redirects, bounded session/request time, and an
unused guarded reader client. Official add/search, models, query, chunks, ranking,
turn expansion and repeated turns are retained. Budget-matched display truncates
only the already-expanded text, with an explicit marker and both hashes.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.metadata
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

sys.dont_write_bytecode = True

UPSTREAM_COMMIT = "95639191e9547219b426710e50fe1a36235e26fc"
DEFAULT_CONFIG = Path(__file__).with_name("rawrag-config.json")
PINNED_FILES = {
    "methods/EverCore/evaluation/src/adapters/rag_adapter.py": "997c35db93feea77eed897b3d5640bd9cd6f114da40bff5128efae65a6466637",
    "methods/EverCore/evaluation/src/adapters/base.py": "c8a3683bfe2565541c0182dfda0b20f6780f49023c8333e9ec7aeb29adae8475",
    "methods/EverCore/evaluation/src/adapters/rag_pgvector_store.py": "143cc750dcd6c70206c7c3f30640dba4378593bf1667415dfc2184a7006b758f",
    "methods/EverCore/evaluation/src/adapters/registry.py": "537ca1724a9a5d2967b6d520860cd9c3cfadaa1926467bbfa071ddd1ebfbb912",
    "methods/EverCore/evaluation/src/core/data_models.py": "66a0005d55d9dc2e0c53ab0a5d788f8b263a685a6d4e06a90a9a248a54f59208",
    "methods/EverCore/evaluation/src/utils/config.py": "db2b6329a6c52847b0ed693e8c697fc3d470c39479c68f237b1241e97c6ba26e",
    "methods/EverCore/evaluation/src/utils/fingerprint.py": "969a35b869e61b23a6406b8cf744550efe9f7422c7dcf4f74421dc037674cf6e",
    "methods/EverCore/evaluation/config/prompts.yaml": "cfbfb39fc0a805ddf2da84f62b174f291ad47495d059523ad9ba64d320b94cdd",
    "scripts/paper/configs/systems/textemb3-gpt4omini.yaml": "9d7ec314dd66e1019c19514b7da50b7a87799f8d3e456ae869a4feb312f18737",
}
OFFICIAL_RETRIEVAL = {
    "strategy": "token", "chunk_size": 256, "chunk_overlap": 32,
    "tokenizer_model": "gpt-4", "tokenizer_encoding": "cl100k_base",
    "embedding_top_k": 128, "rerank_top_k": 15,
    "expand_turns_on_display": True, "dedup_turns_on_display": False,
    "sort_selected_chunks_by_time": False, "dynamic_top_k": False,
    "query_policy": "original_request",
}
REQUIRED_MODULES = {
    "openai": "openai", "yaml": "PyYAML", "rich": "rich",
    "tqdm": "tqdm", "tiktoken": "tiktoken",
}
SOURCE_FIELDS = {
    "eventId", "sourceId", "sourceSequence", "observedAt", "role", "type",
    "scope", "entity", "text", "kind", "status", "complete", "command",
    "completed", "executed", "exitCode", "version", "authoritative",
    # Shared public metadata from verification.mjs and normalize-node.mjs.
    "actor", "action", "effectiveAt", "expiresAt",
    "testCount", "skippedCount", "todoCount", "parserVersion",
    "validFrom", "validUntil", "revokedAt", "grantedAt", "value", "target",
    "targetVersion", "repository", "artifact", "sessionId", "threadId",
    "itemId", "sourceRef", "sourceDigest", "sha256", "recordId", "eventIndex",
    "transport",
}
FORBIDDEN_KEYS = {
    "gold", "golden", "goldsource", "goldanswer", "goldenanswer", "claims",
    "claim", "expected", "expectedsource", "expectedsources", "expectedanswer",
    "expectedsourceid", "correctsource", "correctanswer", "answerkey", "answer",
    "groundtruth", "oracle", "oraclesource", "labels", "label", "scoring",
    "scoringannotation", "evaluator", "private", "apikey", "password", "secret",
}
MARKER = "\n[RAW-RAG EVIDENCE TRUNCATED AT FROZEN TOKEN BUDGET]\n"


class ContractError(RuntimeError):
    """Safe public error code only; never include provider bodies or credentials."""


class BudgetExceeded(ContractError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate_json_key")
        result[key] = value
    return result


def _invalid_number(value):
    raise ContractError("nonfinite_json_number")


def read_bytes_bounded(path: Path, limit: int) -> bytes:
    try:
        with Path(path).open("rb") as handle:
            content = handle.read(limit + 1)
    except OSError:
        raise ContractError("input_file_unavailable") from None
    if len(content) > limit:
        raise BudgetExceeded("input_file_byte_limit")
    return content


def read_json_bounded(path: Path, limit: int):
    return decode_json_bytes(read_bytes_bounded(path, limit))


def decode_json_bytes(content):
    try:
        return json.loads(content.decode("utf-8"),
                          object_pairs_hook=_unique_object,
                          parse_constant=_invalid_number)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise ContractError("invalid_json_document") from None


def _keys(value, required, allowed, code):
    if not isinstance(value, dict) or not required.issubset(value) or set(value) - allowed:
        raise ContractError(code)


def _positive(value, code):
    if type(value) is not int or value < 1:
        raise ContractError(code)


def _endpoint(value):
    if not isinstance(value, str):
        raise ContractError("invalid_service_url")
    parsed = urllib.parse.urlsplit(value)
    loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
    if (parsed.scheme != "https" and not (parsed.scheme == "http" and loopback)) or not parsed.hostname:
        raise ContractError("invalid_service_url")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ContractError("service_url_must_not_contain_credentials_or_query")


def validate_config(config):
    _keys(config, {"schema", "implementation", "upstream", "retrieval", "models",
                   "display", "limits", "runtime"},
          {"schema", "implementation", "upstream", "retrieval", "models",
           "display", "limits", "runtime"}, "config_schema_mismatch")
    if config["schema"] != 1 or config["implementation"] != "official-rawrag-retrieval-p1-adapter-v1":
        raise ContractError("config_schema_mismatch")
    if config["upstream"] != {
        "repository": "https://github.com/Litmeb/RAW-RAG", "commit": UPSTREAM_COMMIT
    }:
        raise ContractError("upstream_identity_mismatch")
    if config["retrieval"] != OFFICIAL_RETRIEVAL:
        raise ContractError("official_retrieval_config_mismatch")
    models = config["models"]
    _keys(models, {"embedding", "reranker"}, {"embedding", "reranker"}, "model_config_mismatch")
    for kind, name, allowed in [
        ("embedding", "text-embedding-3-small", {"model", "base_url", "api_key_env", "batch_size"}),
        ("reranker", "rerank-v3.5", {"model", "base_url", "api_key_env", "endpoint"}),
    ]:
        item = models[kind]
        _keys(item, allowed, allowed, "model_config_mismatch")
        if item["model"] != name:
            raise ContractError("official_retrieval_model_mismatch")
        _endpoint(item["base_url"])
        if not isinstance(item["api_key_env"], str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", item["api_key_env"]):
            raise ContractError("invalid_credential_environment_name")
    if models["embedding"]["batch_size"] != 128:
        raise ContractError("embedding_batch_mismatch")
    endpoint = models["reranker"]["endpoint"]
    if not isinstance(endpoint, str) or not endpoint.startswith("/") or any(c in endpoint for c in "?#"):
        raise ContractError("invalid_rerank_endpoint")
    display = config["display"]
    _keys(display, {"default_mode", "budget_matched_tokens", "policy"},
          {"default_mode", "budget_matched_tokens", "policy"}, "display_config_mismatch")
    if display["default_mode"] not in {"faithful", "budget-matched"} or display["policy"] != "expanded-token-prefix-with-marker-v1":
        raise ContractError("display_config_mismatch")
    _positive(display["budget_matched_tokens"], "invalid_display_budget")
    limits = config["limits"]
    required_limits = {
        "max_sessions", "max_events", "max_archive_bytes", "max_source_text_bytes",
        "max_request_bytes", "max_raw_input_tokens", "max_processed_input_tokens",
        "max_http_dispatches", "max_session_seconds", "max_output_tokens", "max_response_bytes",
    }
    _keys(limits, required_limits, required_limits, "budget_config_mismatch")
    for value in limits.values():
        _positive(value, "invalid_budget_limit")
    if limits["max_sessions"] != 1 or display["budget_matched_tokens"] > limits["max_output_tokens"]:
        raise ContractError("unsupported_budget_configuration")
    runtime = config["runtime"]
    required_runtime = {"sdk_max_retries", "adapter_max_retries",
                        "request_timeout_seconds", "sample_workers"}
    _keys(runtime, required_runtime, required_runtime, "runtime_config_mismatch")
    if runtime["sdk_max_retries"] != 0 or runtime["adapter_max_retries"] != 3 or runtime["sample_workers"] != 1:
        raise ContractError("runtime_config_mismatch")
    _positive(runtime["request_timeout_seconds"], "invalid_request_timeout")
    if runtime["request_timeout_seconds"] > limits["max_session_seconds"]:
        raise ContractError("request_timeout_exceeds_session")
    return config


def load_config(path=DEFAULT_CONFIG):
    return validate_config(read_json_bounded(Path(path), 65536))


def _reject_supervision(value):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            if normalized in FORBIDDEN_KEYS or normalized.startswith(("gold", "oracle", "expected")):
                raise ContractError("supervision_or_private_metadata_forbidden")
            _reject_supervision(child)
    elif isinstance(value, list):
        for child in value:
            _reject_supervision(child)


def _timestamp(value):
    if not isinstance(value, str):
        raise ContractError("timestamp_required")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ContractError("invalid_timestamp") from None
    if result.tzinfo is None or result.utcoffset() is None:
        raise ContractError("timestamp_timezone_required")
    return result.astimezone(timezone.utc)


def validate_archive(document, limits):
    _reject_supervision(document)
    _keys(document, {"schema", "taskId", "snapshot", "sources"},
          {"schema", "taskId", "snapshot", "sources"}, "public_archive_schema_mismatch")
    if document["schema"] != 1 or not isinstance(document["taskId"], str) or not document["taskId"].strip():
        raise ContractError("public_archive_schema_mismatch")
    snapshot = document["snapshot"]
    _keys(snapshot, {"cutoff", "watermark", "complete"},
          {"cutoff", "watermark", "complete"}, "snapshot_schema_mismatch")
    if snapshot["complete"] is not True:
        raise ContractError("incomplete_snapshot")
    if not isinstance(snapshot["watermark"], str) or not snapshot["watermark"].strip():
        raise ContractError("snapshot_watermark_required")
    cutoff = _timestamp(snapshot["cutoff"])
    sources = document["sources"]
    if not isinstance(sources, list) or not sources:
        raise ContractError("nonempty_public_sources_required")
    if len(sources) > limits["max_events"]:
        raise BudgetExceeded("source_event_limit")
    seen = set()
    required = {"eventId", "sourceId", "sourceSequence", "observedAt", "role",
                "type", "scope", "entity", "text"}
    for source in sources:
        _keys(source, required, SOURCE_FIELDS, "public_source_schema_mismatch")
        for key in required - {"sourceSequence"}:
            if not isinstance(source[key], str) or not source[key].strip():
                raise ContractError("invalid_public_source_field")
        if source["role"] not in {"system", "developer", "user", "assistant", "tool"}:
            raise ContractError("invalid_source_role")
        sequence = source["sourceSequence"]
        if type(sequence) is not int or not 1 <= sequence <= 2**53 - 1:
            raise ContractError("invalid_source_sequence")
        if source["eventId"] in seen:
            raise ContractError("duplicate_event_identity")
        seen.add(source["eventId"])
        if _timestamp(source["observedAt"]) > cutoff:
            raise ContractError("source_after_snapshot_cutoff")
        if len(source["text"].encode("utf-8")) > limits["max_source_text_bytes"]:
            raise BudgetExceeded("source_text_byte_limit")
        if "transport" in source and not isinstance(source["transport"], dict):
            raise ContractError("transport_metadata_must_be_object")
    if len(canonical(document).encode("utf-8")) > limits["max_archive_bytes"]:
        raise BudgetExceeded("archive_byte_limit")
    return document


def validate_request(text, limits):
    if not isinstance(text, str) or not text.strip():
        raise ContractError("original_request_required")
    if len(text.encode("utf-8")) > limits["max_request_bytes"]:
        raise BudgetExceeded("request_byte_limit")
    return text


def dependency_report():
    modules = {}
    for module, distribution in REQUIRED_MODULES.items():
        try:
            present = importlib.util.find_spec(module) is not None
        except (ValueError, ImportError):
            present = False
        try:
            version = importlib.metadata.version(distribution) if present else None
        except importlib.metadata.PackageNotFoundError:
            version = None
        modules[module] = {"available": present, "version": version}
    missing = [name for name, state in modules.items() if not state["available"]]
    python_supported = sys.version_info[:2] == (3, 12)
    return {"available": not missing and python_supported, "missing": missing,
            "python": ".".join(map(str, sys.version_info[:3])),
            "python_supported": python_supported, "modules": modules}


def require_dependencies(report):
    if not report["available"]:
        raise ContractError("required_runtime_dependencies_unavailable")


def credential_status(config):
    return {
        kind: bool(os.environ.get(config["models"][kind]["api_key_env"], "").strip())
        for kind in ("embedding", "reranker")
    }


def verify_source_files(root, expected=PINNED_FILES):
    root = Path(root).resolve()
    for relative, wanted in expected.items():
        path = root / relative
        if not path.resolve().is_relative_to(root) or not path.is_file():
            raise ContractError("pinned_upstream_source_missing")
        if hashlib.sha256(path.read_bytes()).hexdigest() != wanted:
            raise ContractError("pinned_upstream_source_changed")


def verify_upstream(root, config):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ContractError("upstream_checkout_unavailable")

    def git(*arguments):
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "-c", "core.fsmonitor=false", *arguments],
                capture_output=True, text=True, timeout=15, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise ContractError("upstream_git_check_failed") from None
        if result.returncode:
            raise ContractError("upstream_git_check_failed")
        return result.stdout.strip()

    if Path(git("rev-parse", "--show-toplevel")).resolve() != root:
        raise ContractError("upstream_must_be_checkout_root")
    head = git("rev-parse", "HEAD")
    if head != UPSTREAM_COMMIT or config["upstream"]["commit"] != UPSTREAM_COMMIT:
        raise ContractError("upstream_commit_mismatch")
    if git("status", "--porcelain", "--untracked-files=no"):
        raise ContractError("upstream_tracked_files_dirty")
    verify_source_files(root)
    return {"commit": head, "source_files_verified": len(PINNED_FILES),
            "tracked_worktree_clean": True}


def preflight(root, config):
    dependencies = dependency_report()
    credentials = credential_status(config)
    errors = []
    try:
        source = verify_upstream(root, config)
    except ContractError as exc:
        source = None
        errors.append(str(exc))
    if not dependencies["available"]:
        errors.append("required_runtime_dependencies_unavailable")
    if not all(credentials.values()):
        errors.append("provider_credentials_unavailable")
    return {
        "mode": "check", "status": "ready" if not errors else "blocked",
        "upstream": source, "config_sha256": digest_text(canonical(config)),
        "dependencies": dependencies, "credentials_available": credentials,
        "model_requests_sent": 0, "errors": errors,
        "tokenizer_runtime_verified": False,
        "transport_hook_compatibility": "verified_only_during_run_preflight",
        "environment_files_read": False,
    }


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


class RunBudget:
    def __init__(self, limits, ledger_path=None, *, authorize_dispatch=None,
                 dispatch_binding=None):
        self.limits = dict(limits)
        self.started = time.monotonic()
        self.ledger_path = Path(ledger_path) if ledger_path is not None else None
        self.lock = threading.RLock()
        self.sessions = []
        self.dispatches = []
        self.upstream_logs = []
        self.admissions = []
        self.authorize_dispatch = authorize_dispatch
        self.dispatch_binding = dispatch_binding
        self.tokens = 0
        self.closed = False
        self._persist()

    def remaining(self):
        remaining = self.limits["max_session_seconds"] - (time.monotonic() - self.started)
        if self.closed or remaining <= 0:
            raise BudgetExceeded("session_time_limit_or_closed")
        return remaining

    def reserve_session(self, task_id):
        with self.lock:
            self.remaining()
            if len(self.sessions) >= self.limits["max_sessions"]:
                raise BudgetExceeded("session_count_limit")
            self.sessions.append(task_id)
            self._persist()

    def reserve_dispatch(self, kind, reference_tokens):
        with self.lock:
            self.remaining()
            if type(reference_tokens) is not int or reference_tokens < 0:
                raise ContractError("invalid_reference_token_count")
            if len(self.dispatches) >= self.limits["max_http_dispatches"]:
                raise BudgetExceeded("http_dispatch_limit")
            if self.tokens + reference_tokens > self.limits["max_processed_input_tokens"]:
                raise BudgetExceeded("processed_input_token_limit")
            self.tokens += reference_tokens
            number = len(self.dispatches) + 1
            self.dispatches.append({
                "dispatch_id": number, "kind": kind,
                "reference_input_tokens": reference_tokens,
                "http_status": None, "provider_request_id": None,
            })
            self._persist()
            return number

    def admit_dispatch(self, kind, reference_tokens, *, endpoint, model, request_bytes,
                       timeout_ms=30000):
        """Bind durable controller admission to one HTTP attempt, before sending.

        The trusted callback owns cash reservations. A matching receipt is an
        integration contract, not independent proof that a caller kept a ledger.
        Each upstream retry reaches this boundary with a fresh dispatch identity.
        """
        with self.lock:
            if not callable(self.authorize_dispatch):
                raise ContractError("dispatch_controller_required")
            binding = self.dispatch_binding
            if (not isinstance(binding, dict)
                    or set(binding) != {"attempt_id", "config_sha256", "checkpoint_sha256"}
                    or not isinstance(binding["attempt_id"], str)
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", binding["attempt_id"])
                    or binding["attempt_id"].startswith("sk-")
                    or any(not isinstance(binding[k], str) or not re.fullmatch(r"[a-f0-9]{64}", binding[k])
                           for k in ("config_sha256", "checkpoint_sha256"))):
                raise ContractError("dispatch_binding_required")
            self.remaining()
            if type(reference_tokens) is not int or reference_tokens < 0:
                raise ContractError("invalid_reference_token_count")
            if len(self.dispatches) >= self.limits["max_http_dispatches"]:
                raise BudgetExceeded("http_dispatch_limit")
            if self.tokens + reference_tokens > self.limits["max_processed_input_tokens"]:
                raise BudgetExceeded("processed_input_token_limit")
            if kind not in {"embedding", "rerank"} or not isinstance(request_bytes, bytes):
                raise ContractError("invalid_dispatch_intent")
            sequence = len(self.admissions) + 1
            identity = {**binding, "kind": kind, "sequence": sequence,
                        "request_sha256": hashlib.sha256(request_bytes).hexdigest()}
            intent = {"schema_version": 1, "kind": "p1-provider-dispatch-intent",
                      **binding, "provider": "openai" if kind == "embedding" else "cohere",
                      "component": kind, "model": model, "endpoint": endpoint,
                      "dispatch_id": "rawrag-" + digest_text(canonical(identity))[:40],
                      "request_sha256": identity["request_sha256"],
                      "request_bytes": len(request_bytes),
                      "reference_input_tokens": reference_tokens, "max_output_tokens": 0,
                      "max_response_bytes": self.limits["max_response_bytes"], "timeout_ms": timeout_ms}
            intent["intent_sha256"] = digest_text(canonical(intent))
            record = {"intent": intent, "status": "requested", "receipt": None}
            self.admissions.append(record)
            self._persist()
            try:
                receipt = self.authorize_dispatch(json.loads(canonical(intent)))
            except Exception:
                record["status"] = "unconfirmed"
                self._persist()
                raise ContractError("dispatch_admission_failed") from None
            required = {"schema_version", "kind", "decision", "dispatch_id",
                        "intent_sha256", "request_sha256", "admission_id"}
            if (not isinstance(receipt, dict) or set(receipt) != required
                    or type(receipt["schema_version"]) is not int or receipt["schema_version"] != 1
                    or receipt["kind"] != "p1-dispatch-admission-receipt" or receipt["decision"] != "allow"
                    or any(receipt[k] != intent[k] for k in ("dispatch_id", "intent_sha256", "request_sha256"))
                    or not isinstance(receipt["admission_id"], str)
                    or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", receipt["admission_id"])
                    or receipt["admission_id"].startswith("sk-")):
                record["status"] = "unconfirmed"
                self._persist()
                raise ContractError("dispatch_admission_unconfirmed")
            record.update(status="admitted", receipt=dict(receipt))
            self._persist()
            # A slow synchronous controller must not permit a send past expiry.
            self.remaining()
            number = self.reserve_dispatch(kind, reference_tokens)
            self.dispatches[-1].update(operation_id=intent["dispatch_id"],
                request_sha256=intent["request_sha256"], intent_sha256=intent["intent_sha256"],
                provider=intent["provider"], model=model, endpoint=endpoint,
                admission_id=receipt["admission_id"])
            self._persist()
            return number

    def observe_response(self, dispatch_id, status, provider_request_id=None):
        with self.lock:
            for record in self.dispatches:
                if record["dispatch_id"] == dispatch_id:
                    record["http_status"] = status if type(status) is int else None
                    record["provider_request_id"] = provider_request_id
                    break
            self._persist()

    def observe_upstream_log(self, event):
        with self.lock:
            self.upstream_logs.append(dict(event))
            self._persist()

    def close(self):
        with self.lock:
            self.closed = True
            self._persist()

    def snapshot(self):
        with self.lock:
            return {
                "schema": 1, "sessions_observed": len(self.sessions),
                "observed_http_dispatch_attempts": len(self.dispatches),
                "dispatch_observation_scope": "SDK request hooks plus rerank opener invocations",
                "http_requests_total": None,
                "reference_input_tokens_observed": self.tokens,
                "reference_tokenizer": "gpt-4/cl100k_base",
                "upstream_log_entries_observed": len(self.upstream_logs),
                "provider_usage_observed": list(self.upstream_logs),
                "dispatch_admissions": list(self.admissions),
                "controller_binding": self.dispatch_binding,
                "provider_cost_total": None, "reader_calls": 0,
                "closed": self.closed,
                "wall_seconds_observed": round(time.monotonic() - self.started, 6),
                "dispatches": [dict(item) for item in self.dispatches],
                "limits": dict(self.limits),
                "unknowns": [
                    "Provider billing beyond returned usage is not inferred.",
                    "Underlying transport/server requests are not inferred from log rows.",
                    "No native-host reader or evaluation cost is measured by this retrieval-only entrypoint.",
                ],
            }

    def _persist(self):
        if self.ledger_path is not None:
            write_json(self.ledger_path, self.snapshot())


def token_count(encoding, text):
    return len(encoding.encode(text, disallowed_special=()))


def render_display(expanded, mode, maximum, encoding):
    if mode not in {"faithful", "budget-matched"}:
        raise ContractError("unknown_display_mode")
    total = token_count(encoding, expanded)
    result = {
        "context": expanded, "expanded_sha256": digest_text(expanded),
        "delivered_sha256": digest_text(expanded),
        "expanded_tokens": total, "delivered_tokens": total,
        "truncated": False, "display_mode": mode,
        "policy": "official-full-turns-no-dedup" if mode == "faithful"
                  else "expanded-token-prefix-with-marker-v1",
    }
    if total <= maximum:
        return result
    if mode == "faithful":
        raise BudgetExceeded("faithful_context_exceeds_hard_output_limit")
    marker_tokens = token_count(encoding, MARKER)
    if maximum <= marker_tokens:
        raise BudgetExceeded("display_budget_cannot_fit_marker")
    tokens = encoding.encode(expanded, disallowed_special=())
    keep = maximum - marker_tokens
    while keep >= 0:
        candidate = encoding.decode(tokens[:keep], errors="ignore") + MARKER
        count = token_count(encoding, candidate)
        if count <= maximum:
            result.update(context=candidate, delivered_sha256=digest_text(candidate),
                          delivered_tokens=count, truncated=True)
            return result
        keep -= max(1, count - maximum)
    raise BudgetExceeded("display_budget_cannot_fit_marker")


def _numeric_usage(value):
    if isinstance(value, dict):
        return {key: _numeric_usage(item) for key, item in value.items()
                if isinstance(key, str) and (isinstance(item, dict)
                   or item is None or type(item) in {int, float})}
    if value is None or type(value) is int:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    return None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ContractError("provider_redirect_refused")


def instrument_adapter(adapter, budget, encoding, config):
    """Count at dispatch boundaries; fail before send on any budget overrun.

    SDK hook support is checked before add/search. These observed attempts are
    deliberately not labeled a complete provider/server HTTP request census.
    """
    if (budget.dispatch_binding is not None
            and budget.dispatch_binding.get("config_sha256") != digest_text(canonical(config))):
        raise ContractError("dispatch_config_binding_mismatch")
    client = adapter.embedding_client
    transport = getattr(client, "_client", None)
    hooks = getattr(transport, "event_hooks", None)
    if not isinstance(hooks, dict) or not hasattr(transport, "follow_redirects"):
        raise ContractError("sdk_transport_hooks_unavailable")
    client.max_retries = 0
    transport.follow_redirects = False
    embedding_url = config["models"]["embedding"]["base_url"].rstrip("/") + "/embeddings"
    rerank_url = config["models"]["reranker"]["base_url"].rstrip("/") + config["models"]["reranker"]["endpoint"]
    active = {"embedding": None, "rerank": None}
    active_lock = threading.RLock()

    async def before_embedding(request):
        with active_lock:
            active["embedding"] = None
        if request.method != "POST" or str(request.url) != embedding_url:
            raise ContractError("unexpected_embedding_http_target")
        try:
            payload = json.loads(request.content)
        except (ValueError, TypeError, AttributeError):
            raise ContractError("unobservable_embedding_request") from None
        texts = payload.get("input")
        if payload.get("model") != "text-embedding-3-small" or not isinstance(texts, list) or not all(isinstance(x, str) for x in texts):
            raise ContractError("unexpected_embedding_payload")
        number = budget.admit_dispatch("embedding", sum(token_count(encoding, x) for x in texts),
            endpoint=embedding_url, model="text-embedding-3-small", request_bytes=request.content,
            timeout_ms=config["runtime"]["request_timeout_seconds"] * 1000)
        with active_lock:
            active["embedding"] = number
        extensions = getattr(request, "extensions", None)
        if isinstance(extensions, dict):
            extensions["p1_dispatch_id"] = number
            timeout = min(config["runtime"]["request_timeout_seconds"], budget.remaining())
            extensions["timeout"] = {key: timeout for key in ("connect", "read", "write", "pool")}

    async def after_embedding(response):
        request = getattr(response, "request", None)
        extensions = getattr(request, "extensions", {})
        number = extensions.get("p1_dispatch_id") if isinstance(extensions, dict) else None
        if number is not None:
            budget.observe_response(number, getattr(response, "status_code", None),
                                    response.headers.get("x-request-id"))
        if not callable(getattr(response, "aiter_bytes", None)) or not callable(getattr(response, "aclose", None)):
            raise ContractError("sdk_response_body_not_bounded")
        limit = config["limits"]["max_response_bytes"]
        length = response.headers.get("content-length")
        try:
            if length is not None:
                if not isinstance(length, str) or len(length) > 32 or not length.isascii() or not length.isdigit():
                    raise ContractError("invalid_embedding_response_length")
                if int(length) > limit:
                    raise BudgetExceeded("embedding_response_byte_limit")
            body, size = [], 0
            async for chunk in response.aiter_bytes(chunk_size=min(65536, limit + 1)):
                budget.remaining()
                if not isinstance(chunk, bytes):
                    raise ContractError("invalid_embedding_response_bytes")
                size += len(chunk)
                if size > limit:
                    raise BudgetExceeded("embedding_response_byte_limit")
                body.append(chunk)
            # Preserve the bounded body for the SDK parser. This is the cache
            # slot used by httpx/httpx2 Response.aread(), verified by SDK tests.
            response._content = b"".join(body)
        except BaseException:
            await response.aclose()
            raise

    hooks.setdefault("request", []).append(before_embedding)
    hooks.setdefault("response", []).append(after_embedding)
    opener = urllib.request.build_opener(_NoRedirect())

    def post_json(url, payload, timeout_seconds):
        with active_lock:
            active["rerank"] = None
        if url != rerank_url or payload.get("model") != "rerank-v3.5":
            raise ContractError("unexpected_rerank_http_target_or_model")
        query, documents = payload.get("query"), payload.get("documents")
        if not isinstance(query, str) or not isinstance(documents, list) or not all(isinstance(x, str) for x in documents):
            raise ContractError("unexpected_rerank_payload")
        reference_tokens = sum(token_count(encoding, query + "\n" + text) for text in documents)
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        number = budget.admit_dispatch("rerank", reference_tokens, endpoint=url,
            model="rerank-v3.5", request_bytes=encoded,
            timeout_ms=config["runtime"]["request_timeout_seconds"] * 1000)
        with active_lock:
            active["rerank"] = number
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + adapter.rerank_api_key}
        request = urllib.request.Request(url, data=encoded, headers=headers, method="POST")
        timeout = min(timeout_seconds, config["runtime"]["request_timeout_seconds"], budget.remaining())
        try:
            with opener.open(request, timeout=timeout) as response:
                budget.observe_response(number, response.status, response.headers.get("x-request-id"))
                body = response.read(config["limits"]["max_response_bytes"] + 1)
        except urllib.error.HTTPError as exc:
            budget.observe_response(number, exc.code)
            raise ContractError("rerank_http_error") from None
        except urllib.error.URLError:
            raise ContractError("rerank_connection_error") from None
        if len(body) > config["limits"]["max_response_bytes"]:
            raise BudgetExceeded("rerank_response_byte_limit")
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ContractError("invalid_rerank_response_json") from None

    async def capture_log(*, call_type, stage, request, response, started, **kwargs):
        response_returned = isinstance(response, dict)
        response = response if isinstance(response, dict) else {}
        meta = response.get("meta") if isinstance(response.get("meta"), dict) else {}
        model = response.get("model")
        if not isinstance(model, str) or len(model) > 512:
            model = None
        wanted_model = "text-embedding-3-small" if call_type == "embedding" else "rerank-v3.5"
        model_mismatch = ((model is not None and model != wanted_model)
                          or call_type == "embedding" and response_returned and not kwargs.get("error") and model is None)
        if model_mismatch:
            model = None
        with active_lock:
            dispatch_id = active.get(call_type)
            if call_type in active:
                active[call_type] = None
        budget.observe_upstream_log({
            "call_type": call_type, "stage": stage,
            "dispatch_id": dispatch_id,
            "attempt": kwargs.get("attempt"),
            "error_present": bool(kwargs.get("error")),
            "provider_model": model,
            "provider_model_mismatch": model_mismatch,
            "usage": _numeric_usage(response.get("usage")),
            "billed_units": _numeric_usage(meta.get("billed_units")),
        })
        if model_mismatch:
            raise ContractError("provider_" + ("embedding" if call_type == "embedding" else "rerank") + "_model_mismatch")

    async def no_reader(*args, **kwargs):
        raise ContractError("reader_calls_forbidden_in_retrieval_adapter")

    adapter._post_json = post_json
    adapter._write_request_log = capture_log
    adapter.answer = no_reader


def _load_official(root):
    core = (Path(root) / "methods" / "EverCore").resolve()
    for name, module in list(sys.modules.items()):
        if name == "evaluation" or name.startswith("evaluation."):
            origin = getattr(module, "__file__", None)
            if origin and not Path(origin).resolve().is_relative_to(core):
                raise ContractError("conflicting_evaluation_module_already_loaded")
    sys.path.insert(0, str(core))
    adapter_module = importlib.import_module("evaluation.src.adapters.rag_adapter")
    models = importlib.import_module("evaluation.src.core.data_models")
    if not Path(adapter_module.__file__).resolve().is_relative_to(core):
        raise ContractError("upstream_import_origin_mismatch")
    return adapter_module.RAGAdapter, models.Conversation, models.Message


def _effective_config(config):
    retrieval = config["retrieval"]
    embedding, reranker = config["models"]["embedding"], config["models"]["reranker"]
    return {
        "name": "rag", "version": "paper-1", "adapter": "rag", "sample_workers": 1,
        "chunking": {key: retrieval[key] for key in (
            "strategy", "chunk_size", "chunk_overlap", "tokenizer_model",
            "expand_turns_on_display", "dedup_turns_on_display")},
        "embedding": {
            "provider": "openai", "model": embedding["model"],
            "api_key": os.environ[embedding["api_key_env"]],
            "base_url": embedding["base_url"], "batch_size": 128, "max_retries": 3,
        },
        "rerank": {
            "enabled": True, "model": reranker["model"],
            "api_key": os.environ[reranker["api_key_env"]],
            "base_url": reranker["base_url"], "endpoint": reranker["endpoint"],
            "timeout_seconds": config["runtime"]["request_timeout_seconds"], "max_retries": 3,
        },
        "storage": {"backend": "local", "save_every_conversations": 1},
        "search": {
            "embedding_top_k": 128, "rerank_top_k": 15,
            "sort_selected_chunks_by_time": False, "dynamic_top_k": {"enabled": False},
            "num_workers": 1,
        },
        # Upstream eagerly constructs this unused client. It is never called;
        # a loopback target plus the explicit answer guard prevent reader spend.
        "llm": {
            "provider": "openai", "model": "gpt-4o-mini",
            "api_key": "unused-retrieval-only-client",
            "base_url": "http://127.0.0.1:1/v1",
            "temperature": 0, "max_tokens": 16384,
        },
        "answer": {"prompt_key": "answer_prompt_cot", "num_workers": 1, "max_retries": 3},
    }


def _safe_public_config(effective):
    return {section: {key: value for key, value in values.items() if key != "api_key"}
            if isinstance(values, dict) else values for section, values in effective.items()}


async def _retrieve(root, config, archive, request, output, mode, budget):
    tokenizer = importlib.import_module("tiktoken")
    try:
        encoding = tokenizer.encoding_for_model("gpt-4")
    except Exception:
        raise ContractError("required_tokenizer_unavailable_no_fallback") from None
    if getattr(encoding, "name", None) != "cl100k_base":
        raise ContractError("tokenizer_encoding_mismatch")
    Adapter, Conversation, Message = _load_official(root)
    snapshot_sha = digest_text(canonical(archive))
    conversation = Conversation(
        conversation_id="p1_" + snapshot_sha,
        messages=[
            Message(sender_id=source["sourceId"], sender_name=source["role"],
                    content=canonical(source), timestamp=_timestamp(source["observedAt"]),
                    metadata={"event_id": source["eventId"]})
            for source in archive["sources"]
        ],
        metadata={"speaker_a": "user", "speaker_b": "agent",
                  "snapshot_sha256": snapshot_sha},
    )
    effective = _effective_config(config)
    adapter = Adapter(effective, output_dir=output / "upstream")
    try:
        if adapter._encoding is None or getattr(adapter._encoding, "name", None) != encoding.name:
            raise ContractError("upstream_tokenizer_fallback_forbidden")
        raw_tokens = token_count(encoding, adapter._format_conversation(conversation)) + token_count(encoding, request)
        if raw_tokens > config["limits"]["max_raw_input_tokens"]:
            raise BudgetExceeded("raw_input_token_limit")
        instrument_adapter(adapter, budget, encoding, config)
        index = await adapter.add([conversation])
        result = await adapter.search(request, conversation.conversation_id, index,
                                      question_id="p1-original-request")
        expanded = result.retrieval_metadata.get("formatted_context")
        if not isinstance(expanded, str):
            raise ContractError("missing_official_expanded_context")
        maximum = config["limits"]["max_output_tokens"] if mode == "faithful" else config["display"]["budget_matched_tokens"]
        display = render_display(expanded, mode, maximum, encoding)
        (output / "expanded-context.txt").write_text(expanded, encoding="utf-8")
        (output / "context.txt").write_text(display["context"], encoding="utf-8")
        records = []
        for selected in result.results:
            selected = json.loads(canonical(selected))
            metadata = selected.get("metadata", {})
            start, end = metadata.get("start_turn"), metadata.get("end_turn")
            if type(start) is int and type(end) is int:
                selected["source_event_ids"] = [source["eventId"] for source in archive["sources"][start:end]]
            else:
                selected["source_event_ids"] = []
            records.append(selected)
        report = {
            "schema": 1, "status": "retrieval_complete", "performance_pilot_completed": False,
            "implementation": config["implementation"], "upstream_commit": UPSTREAM_COMMIT,
            "snapshot_sha256": snapshot_sha, "snapshot": archive["snapshot"],
            "request_sha256": digest_text(request), "query_policy": "original_request",
            "config_sha256": digest_text(canonical(config)),
            "effective_retrieval_config": _safe_public_config(effective),
            "display": {key: value for key, value in display.items() if key != "context"},
            "raw_input_tokens": raw_tokens, "selected_chunks": records,
            "candidate_count": result.retrieval_metadata.get("candidate_count"),
            "all_rerank_results": result.retrieval_metadata.get("all_rerank_results"),
            "runtime_adaptations": {
                "sdk_max_retries": 0, "provider_redirects": False,
                "reader": "external_native_host_not_called_here",
                "sample_workers": 1, "source_order": "public_archive_input_order",
            },
            "transport_metadata_semantics": "public ingestion assumptions; no natural-log semantic parser",
        }
        write_json(output / "retrieval.json", report)
        return report
    finally:
        await adapter.close()


def run_retrieval(root, config, archive_path, request_path, output_path, mode, *,
                  authorize_dispatch=None, dispatch_binding=None, expected_inputs=None):
    if not callable(authorize_dispatch):
        return {"mode": "run", "status": "blocked", "errors": ["dispatch_controller_required"],
                "model_requests_sent": 0}
    check = preflight(root, config)
    if check["status"] != "ready":
        return {"mode": "run", "status": "blocked", "errors": check["errors"],
                "credentials_available": check["credentials_available"],
                "model_requests_sent": 0}
    archive_bytes = read_bytes_bounded(archive_path, config["limits"]["max_archive_bytes"])
    archive = validate_archive(decode_json_bytes(archive_bytes), config["limits"])
    request_bytes = read_bytes_bounded(request_path, config["limits"]["max_request_bytes"])
    try:
        request = request_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise ContractError("request_must_be_utf8") from None
    request = validate_request(request, config["limits"])
    if expected_inputs is not None:
        actual = {"task_id": archive["taskId"],
                  "source_archive_sha256": hashlib.sha256(archive_bytes).hexdigest(),
                  "original_request_sha256": hashlib.sha256(request_bytes).hexdigest()}
        if actual != expected_inputs:
            raise ContractError("bound_run_input_changed")
    output = Path(output_path).resolve()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise ContractError("output_directory_must_be_new") from None
    budget = RunBudget(config["limits"], output / "ledger.json",
                       authorize_dispatch=authorize_dispatch, dispatch_binding=dispatch_binding)
    budget.reserve_session(archive["taskId"])
    write_json(output / "config.public.json", config)
    write_json(output / "preflight.json", check)

    async def bounded():
        return await asyncio.wait_for(
            _retrieve(root, config, archive, request, output, mode, budget),
            timeout=budget.remaining(),
        )

    try:
        # Upstream progress and arbitrary provider exception text are not emitted.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            report = asyncio.run(bounded())
        result = {"mode": "run", "status": report["status"],
                  "performance_pilot_completed": False,
                  "display": report["display"], "output": str(output)}
    except (Exception, KeyboardInterrupt) as exc:
        code = str(exc) if isinstance(exc, ContractError) else type(exc).__name__
        result = {"mode": "run", "status": "failed", "error_code": code,
                  "performance_pilot_completed": False, "output": str(output)}
    finally:
        budget.close()
    result["observed_http_dispatch_attempts"] = budget.snapshot()["observed_http_dispatch_attempts"]
    result["http_requests_total"] = None
    write_json(output / "run.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--check", action="store_true", help="Offline preflight (the default).")
    operation.add_argument("--run", action="store_true", help="Explicitly run real embedding and reranking.")
    parser.add_argument("--upstream", type=Path, required=True, help="Root of the clean pinned official checkout.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--archive", type=Path, help="Explicit public archive JSON for --run.")
    parser.add_argument("--request", type=Path, help="Original request as an explicit UTF-8 text file.")
    parser.add_argument("--output", type=Path, help="New output directory for --run.")
    parser.add_argument("--display", choices=["faithful", "budget-matched"])
    args = parser.parse_args(argv)
    if args.run and not all([args.archive, args.request, args.output]):
        parser.error("--run requires --archive, --request and --output")
    if not args.run and any([args.archive, args.request, args.output, args.display]):
        parser.error("run inputs and --display require --run; --check performs offline preflight only")
    try:
        config = load_config(args.config)
        if args.run:
            result = run_retrieval(args.upstream, config, args.archive, args.request,
                                   args.output, args.display or config["display"]["default_mode"])
        else:
            result = preflight(args.upstream, config)
    except ContractError as exc:
        result = {"mode": "run" if args.run else "check", "status": "blocked",
                  "error_code": str(exc), "model_requests_sent": None if args.run else 0}
    except Exception:
        # Do not print traceback/provider messages that might contain credentials.
        result = {"mode": "run" if args.run else "check", "status": "blocked",
                  "error_code": "preflight_internal_error", "model_requests_sent": None if args.run else 0}
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0 if result["status"] in {"ready", "retrieval_complete"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
