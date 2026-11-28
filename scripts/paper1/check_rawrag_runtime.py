#!/usr/bin/env python3
"""Constructor-only Raw-RAG diagnostic: local tokenizer, real SDK, zero requests.

This is separate from rawrag_adapter.py --check, which intentionally does not
import the upstream runtime. It never calls add/search/answer or sends a request.
The tokenizer must already be cached. Existing reports are never overwritten.
"""
from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import copy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from unittest.mock import patch


TOKENIZER_URL = "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
TOKENIZER_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
LOOPBACK = "http://127.0.0.1:1"
DUMMY_KEYS = {
    "P1_RUNTIME_EMBEDDING_DUMMY_KEY": "unused-offline-embedding-client",
    "P1_RUNTIME_RERANK_DUMMY_KEY": "unused-offline-rerank-client",
}


class RuntimeCheckError(RuntimeError):
    """A fixed, safe diagnostic code; no provider or environment value."""


class CredentialFreeEnvironment(Mapping):
    """Hide credential values without reading them; proxy settings pass through."""

    def __init__(self, source, overrides=None):
        self.source = source
        self.overrides = overrides or {}
        self.names = tuple(name for name in source if not self.hidden(name))

    @staticmethod
    def hidden(name):
        upper = name.upper()
        if upper in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}:
            return False
        return upper.startswith(("OPENAI_", "VECTORIZE_", "RERANK_", "LLM_")) or bool(
            set(upper.split("_")) & {"KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL",
                                   "CREDENTIALS", "AUTH", "AUTHORIZATION"})

    def __getitem__(self, name):
        if name in self.overrides:
            return self.overrides[name]
        if self.hidden(name):
            raise KeyError(name)
        return self.source[name]

    def __iter__(self):
        return iter(dict.fromkeys((*self.names, *self.overrides)))

    def __len__(self):
        return len(tuple(iter(self)))

    def copy(self):
        return dict(self)


class OfflineGuard:
    """Reject network, child processes and .env access during runtime imports."""

    def __init__(self):
        self.active = False
        self.network_attempts_blocked = 0
        self.environment_file_accesses_blocked = 0
        self.method_calls_blocked = []

    def audit(self, event, args):
        if not self.active:
            return
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto",
                     "http.client.connect", "urllib.Request"}:
            self.network_attempts_blocked += 1
            raise RuntimeCheckError("network_disabled_in_runtime_check")
        if event == "subprocess.Popen":
            raise RuntimeCheckError("child_process_disabled_in_runtime_check")
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            name = Path(os.fsdecode(args[0])).name
            if name == ".env" or name.startswith(".env."):
                self.environment_file_accesses_blocked += 1
                raise RuntimeCheckError("environment_file_access_disabled")

    def method_guard(self, name):
        def forbidden(*args, **kwargs):
            self.method_calls_blocked.append(name)
            raise RuntimeCheckError("model_method_disabled_in_runtime_check")
        return forbidden

    def __enter__(self):
        sys.addaudithook(self.audit)
        self.active = True
        return self

    def __exit__(self, *args):
        self.active = False


def check_tokenizer_cache(environment):
    directory = environment.get("TIKTOKEN_CACHE_DIR",
                                environment.get("DATA_GYM_CACHE_DIR",
                                                str(Path(tempfile.gettempdir()) / "data-gym-cache")))
    if not directory:
        raise RuntimeCheckError("local_tokenizer_cache_required")
    cache_key = hashlib.sha1(TOKENIZER_URL.encode()).hexdigest()
    path = Path(directory) / cache_key
    if not path.is_file():
        raise RuntimeCheckError("local_tokenizer_cache_required")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != TOKENIZER_SHA256:
        raise RuntimeCheckError("tokenizer_cache_hash_mismatch")
    return {"encoding": "cl100k_base", "data_url": TOKENIZER_URL,
            "cache_key": cache_key, "data_sha256": actual}


def load_baseline():
    path = Path(__file__).with_name("rawrag_adapter.py")
    spec = importlib.util.spec_from_file_location("p1_runtime_baseline", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frozen_requirements():
    packages = {dist.metadata["Name"]: dist.version
                for dist in importlib.metadata.distributions() if dist.metadata["Name"]}
    if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or "\n" in version
           for name, version in packages.items()):
        raise RuntimeCheckError("invalid_distribution_metadata")
    return "".join(f"{name}=={packages[name]}\n" for name in sorted(packages, key=str.lower))


async def inspect_constructor(baseline, root, config, guard):
    baseline.require_dependencies(baseline.dependency_report())
    tokenizer_report = check_tokenizer_cache(os.environ)
    import tiktoken
    encoding = tiktoken.encoding_for_model("gpt-4")
    if encoding.name != "cl100k_base" or encoding.encode("hello world") != [15339, 1917]:
        raise RuntimeCheckError("exact_tokenizer_check_failed")
    Adapter, _, _ = baseline._load_official(root)
    temporary_config = copy.deepcopy(config)
    for kind, key in (("embedding", "P1_RUNTIME_EMBEDDING_DUMMY_KEY"),
                      ("reranker", "P1_RUNTIME_RERANK_DUMMY_KEY")):
        temporary_config["models"][kind]["api_key_env"] = key
        temporary_config["models"][kind]["base_url"] = LOOPBACK + ("/v1" if kind == "embedding" else "")
    effective = baseline._effective_config(temporary_config)
    budget = baseline.RunBudget(config["limits"])
    with ExitStack() as stack, tempfile.TemporaryDirectory(prefix="p1-rawrag-runtime-") as directory:
        for name in ("add", "search", "answer"):
            stack.enter_context(patch.object(Adapter, name, guard.method_guard(name)))
        adapter = Adapter(effective, output_dir=Path(directory))
        try:
            if adapter._encoding is None or adapter._encoding is not encoding:
                raise RuntimeCheckError("upstream_tokenizer_fallback_forbidden")
            for client in (adapter.embedding_client, adapter.answer_client):
                if not str(client.base_url).startswith(LOOPBACK + "/"):
                    raise RuntimeCheckError("non_loopback_client_rejected")
            if adapter.rerank_base_url != LOOPBACK:
                raise RuntimeCheckError("non_loopback_reranker_rejected")
            transport = adapter.embedding_client._client
            previous = {name: len(transport.event_hooks.get(name, []))
                        for name in ("request", "response")}
            original_post = adapter._post_json
            baseline.instrument_adapter(adapter, budget, encoding, temporary_config)
            for name in ("request", "response"):
                hooks = transport.event_hooks.get(name, [])
                if len(hooks) != previous[name] + 1 or not callable(hooks[-1]):
                    raise RuntimeCheckError("transport_hook_attachment_failed")
            if adapter.embedding_client.max_retries != 0 or transport.follow_redirects:
                raise RuntimeCheckError("transport_safety_options_failed")
            if adapter._post_json == original_post:
                raise RuntimeCheckError("rerank_transport_wrapper_missing")
            if budget.snapshot()["observed_http_dispatch_attempts"] != 0:
                raise RuntimeCheckError("unexpected_dispatch_in_constructor_check")
            tokenizer_report.update(model="gpt-4", n_vocab=encoding.n_vocab,
                                    known_fixture_ids=[15339, 1917], word_fallback=False)
            return {"tokenizer": tokenizer_report, "official_adapter_constructed": True,
                    "transport": {"class": type(transport).__module__ + "." + type(transport).__name__,
                                  "request_hook_attached": True, "response_hook_attached": True,
                                  "rerank_wrapper_attached": True, "sdk_max_retries": 0,
                                  "follow_redirects": False, "hooks_exercised_over_http": False},
                    "client_endpoints": "loopback_only_unused", "dispatch_observations": 0}
        finally:
            await adapter.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("rawrag-config.json"))
    parser.add_argument("--output", type=Path, required=True, help="New JSON report; never overwritten.")
    parser.add_argument("--requirements-output", type=Path, required=True, help="New pinned package inventory.")
    args = parser.parse_args(argv)
    if args.output.resolve() == args.requirements_output.resolve() or any(
            path.exists() for path in (args.output, args.requirements_output)):
        parser.error("output paths must be distinct and must not already exist")
    sys.dont_write_bytecode = True
    names = frozenset(os.environ)  # Names only; never retrieve credential values.
    guard = OfflineGuard()
    report = {"kind": "offline_dependency_runtime_check", "status": "blocked",
              "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "model_requests": 0, "provider_billing": None,
              "python": sys.version.split()[0], "environment_files_read": False,
              "real_credentials_read": False, "proxy_configuration_changed": False,
              "provider_credential_variables_present": {"embedding": "VECTORIZE_API_KEY" in names,
                                                        "reranker": "RERANK_API_KEY" in names},
              "formal_baseline_executed": False, "performance_pilot_completed": False}
    requirements = frozen_requirements()
    report["requirements_sha256"] = hashlib.sha256(requirements.encode()).hexdigest()
    report["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    try:
        baseline = load_baseline()
        config = baseline.load_config(args.config)
        report["upstream"] = baseline.verify_upstream(args.upstream, config)
        report["config_sha256"] = baseline.digest_text(baseline.canonical(config))
        report["dependencies"] = baseline.dependency_report()
        # Both the audit guard and the credential-free view apply to imports and
        # construction. Proxy values are forwarded unchanged; none are printed.
        with guard, patch.object(os, "environ", CredentialFreeEnvironment(os.environ, DUMMY_KEYS)), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            report.update(asyncio.run(inspect_constructor(baseline, args.upstream, config, guard)))
        if guard.network_attempts_blocked or guard.environment_file_accesses_blocked or guard.method_calls_blocked:
            raise RuntimeCheckError("prohibited_activity_attempted")
        report["status"] = "passed"
    except Exception as exc:
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc) if isinstance(exc, RuntimeCheckError) else "runtime_initialization_failed"
    report["network_attempts_blocked"] = guard.network_attempts_blocked
    report["environment_file_accesses_blocked"] = guard.environment_file_accesses_blocked
    report["forbidden_method_calls"] = guard.method_calls_blocked
    for path in (args.output, args.requirements_output):
        path.parent.mkdir(parents=True, exist_ok=True)
    with args.requirements_output.open("x", encoding="utf-8") as target:
        target.write(requirements)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with args.output.open("x", encoding="utf-8") as target:
        target.write(encoded)
    print(encoded, end="")
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
