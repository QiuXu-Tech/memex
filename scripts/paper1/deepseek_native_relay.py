#!/usr/bin/env python3
"""Bounded loopback Responses relay for a real, separately controlled host.

The host receives only an epoch-specific local token. Real credentials stay in
the credential callback and HTTPS request. Every upstream request is admitted
before send, uses the complete supplied input, and is buffered until terminal
SSE/usage validation. No request text, output text, reasoning or key is logged.
This transport does not create or attest native threads or compaction receipts.
"""
from __future__ import annotations

import base64
import copy
from datetime import datetime, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import re
import secrets
import threading
import time
import urllib.error
import urllib.request


ENDPOINT = "https://api.deepseek.com/responses"
MODEL = "deepseek-flash"
HEX = re.compile(r"[a-f0-9]{64}\Z")
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
COMPONENTS = {"reader", "prelude", "extraction", "compaction"}
PUBLIC_TOOLS = {"read_file", "write_file", "list_files", "run_current_tests", "record_review"}
# Fixed local rejection codes only: never persist an exception's arbitrary text,
# request field name, header value, or any client metadata value.
LOCAL_REJECTION_CODES = {
    "unknown_relay_path", "bounded_content_length_required", "request_byte_limit", "json_request_required",
    "request_body_incomplete", "relay_deadline_exhausted", "relay_epoch_expired", "relay_request_failed",
    "duplicate_json_key", "nonfinite_json_number", "invalid_json", "unsupported_request_fields",
    "fixed_model_and_stream_required", "stateless_complete_input_required", "unsupported_include",
    "invalid_client_metadata", "invalid_prompt_cache_key", "complete_input_required", "unsupported_input_item",
    "unsupported_input_message", "text_only_input_required", "unsupported_input_tool_call",
    "unsupported_input_tool_output", "complete_tool_history_required", "invalid_instructions",
    "unsupported_tools", "server_or_unknown_tools_forbidden", "unsupported_function_tool",
    "unsupported_tool_choice", "invalid_parallel_tool_calls", "nonthinking_mode_required",
    "fixed_temperature_required", "store_false_required", "invalid_request_output_limit",
    "unsupported_text_format", "scope_output_budget_exhausted", "scope_dispatch_budget_exhausted",
    "reference_token_measurement_failed", "invalid_reference_token_measurement",
    "scope_reference_input_budget_exhausted", "scope_input_budget_exhausted",
}
TERMINAL = {"response.completed": "completed", "response.incomplete": "incomplete", "response.failed": "failed"}
EVENTS = set(TERMINAL) | {"response.created", "response.in_progress", "response.output_item.added",
    "response.output_item.done", "response.content_part.added", "response.content_part.done",
    "response.output_text.delta", "response.output_text.done", "response.function_call_arguments.delta",
    "response.function_call_arguments.done"}


class RelayError(ValueError):
    """Fixed public code; provider errors and credentials are never interpolated."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _label(value):
    return isinstance(value, str) and bool(LABEL.fullmatch(value)) and not value.startswith("sk-")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RelayError("duplicate_json_key")
        result[key] = value
    return result


def _constant(_):
    raise RelayError("nonfinite_json_number")


def strict_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_unique, parse_constant=_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise RelayError("invalid_json") from None


def validate_profile(profile):
    required = {"schema_version", "kind", "provider", "model", "endpoint", "max_request_bytes",
        "max_response_bytes", "timeout_seconds", "max_output_tokens", "max_model_input_tokens",
        "max_model_output_tokens", "max_http_dispatches", "reference_input_token_limit",
        "reasoning_effort", "temperature", "retries"}
    metadata = {"tokenizer", "provenance", "host", "shared_budget_sha256", "formal_study_frozen", "checked_date", "scope"}
    if not isinstance(profile, dict) or not required <= profile.keys() or profile.keys() - required - metadata:
        raise RelayError("invalid_relay_profile")
    if (type(profile["schema_version"]) is not int or profile["schema_version"] != 1
            or profile["kind"] != "p1-deepseek-native-reader-profile" or profile["provider"] != "deepseek"
            or profile["model"] != MODEL or profile["endpoint"] != ENDPOINT
            or profile["reasoning_effort"] != "none" or type(profile["temperature"]) not in (int, float)
            or profile["temperature"] != 0 or type(profile["retries"]) is not int or profile["retries"] != 0):
        raise RelayError("invalid_relay_profile")
    ceilings = {"max_request_bytes": 262144, "max_response_bytes": 4194304, "timeout_seconds": 30,
        "max_output_tokens": 8192, "max_model_input_tokens": 65536, "max_model_output_tokens": 8192,
        "max_http_dispatches": 8, "reference_input_token_limit": 65536}
    if any(type(profile[k]) is not int or not 0 < profile[k] <= maximum for k, maximum in ceilings.items()):
        raise RelayError("invalid_relay_limits")
    if profile["max_output_tokens"] > profile["max_model_output_tokens"]:
        raise RelayError("invalid_relay_output_limit")
    return strict_json(canonical(profile))


def _parts(value):
    if isinstance(value, str):
        return
    if not isinstance(value, list) or not value:
        raise RelayError("text_only_input_required")
    for part in value:
        if (not isinstance(part, dict) or part.get("type") not in {"input_text", "output_text"}
                or not isinstance(part.get("text"), str)
                or set(part) - {"type", "text", "annotations", "logprobs"}
                or any(part.get(k, []) not in (None, []) for k in ("annotations", "logprobs"))):
            raise RelayError("text_only_input_required")


def _input(value):
    if isinstance(value, str) and value.strip():
        return
    if not isinstance(value, list) or not value or len(value) > 10000:
        raise RelayError("complete_input_required")
    calls, outputs = set(), set()
    for item in value:
        if not isinstance(item, dict):
            raise RelayError("unsupported_input_item")
        kind = item.get("type", "message")
        common = {"type", "id", "status"}
        if kind == "message":
            if (set(item) - common - {"role", "content", "phase"}
                    or item.get("role") not in {"user", "assistant", "system", "developer"}
                    or item.get("phase") not in (None, "commentary", "final", "final_answer")):
                raise RelayError("unsupported_input_message")
            _parts(item.get("content"))
        elif kind == "function_call":
            extra = {"call_id", "name", "arguments"}
            if (set(item) - common - extra or not _label(item.get("call_id"))
                    or item.get("name") not in PUBLIC_TOOLS or item["call_id"] in calls
                    or not isinstance(item.get("arguments"), str)):
                raise RelayError("unsupported_input_tool_call")
            calls.add(item["call_id"])
        elif kind == "function_call_output":
            if set(item) - common - {"call_id", "output"} or not _label(item.get("call_id")) or item["call_id"] in outputs:
                raise RelayError("unsupported_input_tool_output")
            _parts(item.get("output"))
            outputs.add(item["call_id"])
        else:
            raise RelayError("unsupported_input_item")
    if calls != outputs:
        raise RelayError("complete_tool_history_required")


def _tools(value):
    if not isinstance(value, list) or len(value) > 128:
        raise RelayError("unsupported_tools")
    names = set()
    for tool in value:
        if not isinstance(tool, dict):
            raise RelayError("unsupported_tools")
        kind, name = tool.get("type"), tool.get("name")
        if kind != "function" or name not in PUBLIC_TOOLS or name in names:
            raise RelayError("server_or_unknown_tools_forbidden")
        if (set(tool) - {"type", "name", "description", "parameters", "strict"}
                or not isinstance(tool.get("parameters", {}), dict)
                or type(tool.get("strict", False)) is not bool):
            raise RelayError("unsupported_function_tool")
        if "description" in tool and not isinstance(tool["description"], str):
            raise RelayError("unsupported_tools")
        names.add(name)
    return names


def _metadata_string(value, maximum=256, *, ascii_only=False):
    if not isinstance(value, str) or len(value) > maximum:
        return False
    try:
        return (len(value.encode("utf-8")) <= maximum
            and all(ord(c) >= 32 and ord(c) != 127 and (not ascii_only or ord(c) <= 126) for c in value))
    except UnicodeEncodeError:
        return False


def _turn_metadata(raw):
    """Bounded, typed Codex 0.153 metadata; validated then discarded in full.

    Schema: openai/codex 41e22fee981a63b3698df7ed36bad393cda24715,
    core/src/responses_metadata.rs and analytics/src/facts.rs. Rust's flattened
    arbitrary user extras deliberately are not part of this compatibility map.
    This metadata never grants tools, changes history, or reaches the provider.
    """
    if not _metadata_string(raw, 16384):
        raise RelayError("invalid_client_metadata")
    value = strict_json(raw)
    strings = {"installation_id", "session_id", "thread_id", "agent_name", "turn_id", "window_id",
        "context_window_id", "forked_from_thread_id", "parent_thread_id", "parent_turn_id", "root_turn_id",
        "subagent_kind", "thread_source", "turn_trigger", "sandbox", "sandbox_mode"}
    unsigned = {"window_number", "forked_from_ordinal_exclusive"}
    booleans = {"auto_review_enabled", "node_repl_auto_review_required", "node_repl_disabled", "history_ingest_requested"}
    known = strings | unsigned | booleans | {"request_kind", "turn_started_at_unix_ms", "workspaces", "tool_namespaces_info", "compaction"}
    if not isinstance(value, dict) or set(value) - known:
        raise RelayError("invalid_client_metadata")
    for key, item in value.items():
        if ((key in strings and not _metadata_string(item))
                or (key in unsigned and (type(item) is not int or not 0 <= item < 2**64))
                or (key in booleans and type(item) is not bool)
                or (key == "turn_started_at_unix_ms" and (type(item) is not int or not -(2**63) <= item < 2**63))
                or (key == "request_kind" and item not in ("turn", "prewarm", "compaction", "memory"))):
            raise RelayError("invalid_client_metadata")
    if "workspaces" in value:
        workspaces = value["workspaces"]
        if not isinstance(workspaces, dict) or len(workspaces) > 16:
            raise RelayError("invalid_client_metadata")
        for path, workspace in workspaces.items():
            if (not _metadata_string(path, 4096) or not isinstance(workspace, dict)
                    or set(workspace) - {"associated_remote_urls", "latest_git_commit_hash", "has_changes"}
                    or "latest_git_commit_hash" in workspace and not _metadata_string(workspace["latest_git_commit_hash"])
                    or "has_changes" in workspace and type(workspace["has_changes"]) is not bool):
                raise RelayError("invalid_client_metadata")
            if "associated_remote_urls" in workspace:
                remotes = workspace["associated_remote_urls"]
                if (not isinstance(remotes, dict) or len(remotes) > 16 or any(
                        not _metadata_string(name) or not _metadata_string(url, 4096)
                        for name, url in remotes.items())):
                    raise RelayError("invalid_client_metadata")
    if "tool_namespaces_info" in value:
        namespaces = value["tool_namespaces_info"]
        if not isinstance(namespaces, dict) or len(namespaces) > 16:
            raise RelayError("invalid_client_metadata")
        for key, namespace in namespaces.items():
            if (not _metadata_string(key) or not isinstance(namespace, dict)
                    or set(namespace) != {"name", "functions"} or not _metadata_string(namespace["name"])
                    or not isinstance(namespace["functions"], dict) or len(namespace["functions"]) > 128):
                raise RelayError("invalid_client_metadata")
            for name, function in namespace["functions"].items():
                if (not _metadata_string(name) or not isinstance(function, dict)
                        or set(function) != {"name", "direct", "code_mode_name", "deferred", "source"}
                        or not _metadata_string(function["name"]) or type(function["direct"]) is not bool
                        or type(function["deferred"]) is not bool
                        or function["code_mode_name"] is not None and not _metadata_string(function["code_mode_name"])):
                    raise RelayError("invalid_client_metadata")
                source = function["source"]
                if not isinstance(source, dict) or not (
                        source == {"kind": "harness"} or set(source) == {"kind", "server_name"}
                        and source["kind"] == "mcp" and _metadata_string(source["server_name"])):
                    raise RelayError("invalid_client_metadata")
    if "compaction" in value:
        enums = {"trigger": ("manual", "auto"),
            "reason": ("user_requested", "context_limit", "model_downshift", "comp_hash_changed"),
            "implementation": ("responses", "responses_compaction_v2", "responses_compact"),
            "phase": ("standalone_turn", "pre_turn", "mid_turn"), "strategy": ("memento", "prefix_compaction")}
        compaction = value["compaction"]
        if (not isinstance(compaction, dict) or set(compaction) != set(enums)
                or any(compaction[key] not in choices for key, choices in enums.items())):
            raise RelayError("invalid_client_metadata")


def _client_metadata(value):
    keys = {"x-codex-installation-id", "session_id", "thread_id", "x-codex-window-id", "turn_id",
        "x-openai-subagent", "x-codex-parent-thread-id", "parent_turn_id", "root_turn_id", "x-codex-turn-metadata"}
    if not isinstance(value, dict) or set(value) - keys:
        raise RelayError("invalid_client_metadata")
    for key, item in value.items():
        if key == "x-codex-turn-metadata":
            _turn_metadata(item)
        elif not _metadata_string(item, ascii_only=True):
            raise RelayError("invalid_client_metadata")


def prepare_request(raw, profile, remaining_output):
    value = strict_json(raw)
    allowed = {"model", "input", "instructions", "stream", "tools", "tool_choice", "parallel_tool_calls",
        "reasoning", "text", "max_output_tokens", "temperature", "store", "previous_response_id",
        "conversation", "include", "prompt_cache_key", "client_metadata"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise RelayError("unsupported_request_fields")
    if value.get("model") != MODEL or value.get("stream") is not True:
        raise RelayError("fixed_model_and_stream_required")
    if value.get("previous_response_id") is not None or value.get("conversation") is not None:
        raise RelayError("stateless_complete_input_required")
    if value.get("include") not in (None, [], ["reasoning.encrypted_content"]):
        raise RelayError("unsupported_include")
    if "prompt_cache_key" in value and (not isinstance(value["prompt_cache_key"], str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,256}", value["prompt_cache_key"])):
        raise RelayError("invalid_prompt_cache_key")
    if "client_metadata" in value:
        _client_metadata(value["client_metadata"])
    _input(value.get("input"))
    if "instructions" in value and not isinstance(value["instructions"], str):
        raise RelayError("invalid_instructions")
    names = _tools(value.get("tools", []))
    choice = value.get("tool_choice", "auto")
    if isinstance(choice, dict):
        if set(choice) != {"type", "name"} or choice["type"] != "function" or choice["name"] not in names:
            raise RelayError("unsupported_tool_choice")
    elif choice not in {"none", "auto", "required"} or choice == "required" and not names:
        raise RelayError("unsupported_tool_choice")
    if "parallel_tool_calls" in value and type(value["parallel_tool_calls"]) is not bool:
        raise RelayError("invalid_parallel_tool_calls")
    reasoning = value.get("reasoning")
    if reasoning is not None and (not isinstance(reasoning, dict) or set(reasoning) - {"effort"}
                                  or reasoning.get("effort") != "none"):
        raise RelayError("nonthinking_mode_required")
    if value.get("temperature", 0) != 0 or type(value.get("temperature", 0)) not in (int, float):
        raise RelayError("fixed_temperature_required")
    if value.get("store", False) is not False:
        raise RelayError("store_false_required")
    maximum = value.get("max_output_tokens", profile["max_output_tokens"])
    if type(maximum) is not int or not 0 < maximum <= profile["max_output_tokens"]:
        raise RelayError("invalid_request_output_limit")
    if "text" in value:
        if not isinstance(value["text"], dict) or set(value["text"]) - {"format", "verbosity"}:
            raise RelayError("unsupported_text_format")
        form = value["text"].get("format", {"type": "text"})
        if not isinstance(form, dict) or form.get("type") not in {"text", "json_object", "json_schema"}:
            raise RelayError("unsupported_text_format")
    forwarded = {k: v for k, v in value.items() if k not in {
        "previous_response_id", "conversation", "include", "prompt_cache_key", "client_metadata"}}
    forwarded.update(reasoning={"effort": "none"}, store=False, temperature=0,
                     max_output_tokens=min(maximum, remaining_output))
    if forwarded["max_output_tokens"] < 1:
        raise RelayError("scope_output_budget_exhausted")
    encoded = canonical(forwarded).encode("utf-8")
    if len(encoded) > profile["max_request_bytes"]:
        raise RelayError("request_byte_limit")
    return forwarded, encoded, names


def _contains_secret(value, keys):
    if isinstance(value, dict):
        return any(_contains_secret(k, keys) or _contains_secret(v, keys) for k, v in value.items())
    if isinstance(value, list):
        return any(_contains_secret(item, keys) for item in value)
    if not isinstance(value, str):
        return False
    patterns = [pattern for key in keys if key for pattern in (key, base64.b64encode(key.encode()).decode())]
    for _ in range(6):
        if any(pattern in value for pattern in patterns):
            return True
        decoded = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m[1], 16)), value)
        decoded = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m[1], 16)), decoded)
        decoded = decoded.replace("\\\\", "\\").replace("\\/", "/")
        if decoded == value:
            break
        value = decoded
    return False


def normalize_usage(value):
    if not isinstance(value, dict):
        return None
    input_tokens, output_tokens = value.get("input_tokens"), value.get("output_tokens")
    detail = value.get("input_tokens_details")
    cached = detail.get("cached_tokens") if isinstance(detail, dict) else None
    if any(type(v) is not int or not 0 <= v <= 2**53 - 1 for v in (input_tokens, output_tokens, cached)):
        return None
    if input_tokens < 1 or cached > input_tokens or value.get("total_tokens", input_tokens + output_tokens) != input_tokens + output_tokens:
        return None
    output_detail = value.get("output_tokens_details")
    if isinstance(output_detail, dict) and output_detail.get("reasoning_tokens", 0) != 0:
        return None
    return {"input_tokens": input_tokens, "cached_input_tokens": cached, "output_tokens": output_tokens}


def _output_item(item, tool_names):
    if not isinstance(item, dict):
        raise RelayError("invalid_response_output")
    kind = item.get("type")
    if kind == "message":
        if item.get("role") != "assistant":
            raise RelayError("invalid_response_role")
        _parts(item.get("content", []))
    elif kind == "function_call":
        if item.get("name") not in tool_names:
            raise RelayError("undeclared_response_tool")
    else:
        raise RelayError("server_tool_or_reasoning_output_forbidden")


def parse_sse(body, *, tool_names, credential, local_token):
    try:
        content = body.decode("utf-8")
    except UnicodeDecodeError:
        raise RelayError("invalid_sse_utf8") from None
    if _contains_secret(content, (credential, local_token)):
        raise RelayError("credential_reflection_rejected")
    events, event_name, data = [], None, []
    for line in content.replace("\r\n", "\n").split("\n") + [""]:
        if not line:
            if data:
                value = strict_json("\n".join(data))
                if not isinstance(value, dict) or value.get("type") != event_name or event_name not in EVENTS:
                    raise RelayError("unsupported_sse_event")
                if _contains_secret(value, (credential, local_token)):
                    raise RelayError("credential_reflection_rejected")
                events.append(value)
                if len(events) > 65536:
                    raise RelayError("sse_event_limit")
            event_name, data = None, []
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            if event_name is not None:
                raise RelayError("duplicate_sse_event_field")
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" "))
        else:
            raise RelayError("unsupported_sse_field")
    if not events or events[0]["type"] != "response.created":
        raise RelayError("sse_creation_missing")
    last_sequence, terminals = -1, []
    response_id = None
    for index, event in enumerate(events):
        sequence = event.get("sequence_number")
        if type(sequence) is not int or sequence <= last_sequence:
            raise RelayError("invalid_sse_sequence")
        last_sequence = sequence
        if "item" in event:
            item = event["item"]
            # Added message items can have an empty content list until deltas.
            if not (event["type"] == "response.output_item.added" and isinstance(item, dict)
                    and item.get("type") == "message" and item.get("role") == "assistant" and item.get("content") == []):
                _output_item(item, tool_names)
        if "part" in event:
            _parts([event["part"]])
        response = event.get("response")
        if response is not None:
            if (not isinstance(response, dict) or response.get("model") != MODEL
                    or not _label(response.get("id"))):
                raise RelayError("response_identity_mismatch")
            if response_id is None:
                response_id = response["id"]
            elif response["id"] != response_id:
                raise RelayError("response_identity_mismatch")
            for item in response.get("output", []):
                _output_item(item, tool_names)
            if response.get("tools") is not None:
                if not _tools(response["tools"]) <= tool_names:
                    raise RelayError("undeclared_response_tool")
        if event["type"] in TERMINAL:
            if index != len(events) - 1 or not isinstance(response, dict) or response.get("status") != TERMINAL[event["type"]]:
                raise RelayError("invalid_sse_terminal")
            terminals.append(event)
    if len(terminals) != 1:
        raise RelayError("sse_terminal_missing")
    final = terminals[0]
    usage = normalize_usage(final["response"].get("usage"))
    return {"terminal_event": final["type"], "provider_response_id": response_id,
            "usage": usage, "usage_complete": usage is not None, "event_count": len(events)}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RelayError("provider_redirect_refused")


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    def handle_error(self, request, client_address):
        # Never emit request text or provider exception tracebacks.
        pass


class DeepSeekRelay:
    def __init__(self, *, profile, output, credential_provider, authorize_dispatch, complete_dispatch, token_counter):
        self.profile = validate_profile(profile)
        if not all(callable(fn) for fn in (credential_provider, authorize_dispatch, complete_dispatch, token_counter)):
            raise RelayError("relay_callbacks_required")
        self.credential_provider, self.authorize_dispatch, self.token_counter = credential_provider, authorize_dispatch, token_counter
        self.complete_dispatch = complete_dispatch
        self.config_sha256 = digest(self.profile)
        self.relay_source_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.output = Path(output).absolute()
        if any(p.is_symlink() for p in (self.output, *self.output.parents)) or self.output.exists():
            raise RelayError("relay_output_must_be_new")
        self.output.mkdir(parents=True, mode=0o700, exist_ok=False)
        self._lock = threading.RLock()
        self._records, self._scopes, self._rejections = [], {}, []
        self._active, self._inflight = None, None
        self._closed, self._epoch = False, 0
        self._registration_receipt = None
        self._transport_id = "native-relay-transport-" + secrets.token_hex(16)
        self._token = secrets.token_urlsafe(32)
        self._opener = urllib.request.build_opener(_NoRedirect())
        registration = {"schema_version": 1, "kind": "p1-deepseek-relay-registration",
            "transport_id": self._transport_id, "audit_root": str(self.output),
            "config_sha256": self.config_sha256, "relay_source_sha256": self.relay_source_sha256}
        registration_hash = self._write_immutable("transport.json", registration)
        self._registration = {**registration, "evidence": {
            "path": str(self.output / "transport.json"), "sha256": registration_hash}}
        relay = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def setup(self):
                super().setup()
                self.connection.settimeout(relay.profile["timeout_seconds"])
            def log_message(self, *args):
                pass
            def do_POST(self):
                lease = None
                received, received_hash, body_complete = 0, hashlib.sha256(), False
                try:
                    if self.path != "/responses":
                        raise RelayError("unknown_relay_path")
                    lease = relay._begin(self.headers.get("Authorization"))
                    lengths = self.headers.get_all("Content-Length", [])
                    if self.headers.get("Transfer-Encoding") is not None or len(lengths) != 1 or not lengths[0].isdigit():
                        raise RelayError("bounded_content_length_required")
                    if len(lengths[0]) > 12:
                        raise RelayError("request_byte_limit")
                    length = int(lengths[0])
                    if not 0 < length <= relay.profile["max_request_bytes"]:
                        raise RelayError("request_byte_limit")
                    if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                        raise RelayError("json_request_required")
                    chunks, remaining = [], length
                    while remaining:
                        self.connection.settimeout(relay._remaining(lease))
                        chunk = self.rfile.read1(min(65536, remaining))
                        if not chunk:
                            raise RelayError("request_body_incomplete")
                        received += len(chunk)
                        received_hash.update(chunk)
                        chunks.append(chunk)
                        remaining -= len(chunk)
                    raw = b"".join(chunks)
                    body_complete = True
                    body = relay._process(raw, lease)
                    # Epoch invalidation cannot race the reviewed local replay.
                    with relay._lock:
                        relay._ensure_active(lease)
                        self.connection.settimeout(relay._remaining(lease))
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream")
                        self.send_header("Content-Length", str(len(body)))
                        self.send_header("Connection", "close")
                        self.end_headers()
                        self.wfile.write(body)
                except BaseException as exc:
                    code = str(exc) if isinstance(exc, RelayError) else "relay_request_failed"
                    if lease is not None and lease["record_id"] is None:
                        code = code if code in LOCAL_REJECTION_CODES else "relay_request_failed"
                        try:
                            relay._reject_local(lease, code=code, received=received,
                                received_hash=received_hash.hexdigest() if received else None,
                                body_complete=body_complete)
                        except Exception:
                            # An unrecordable rejection cannot be used to probe then dispatch.
                            code = "local_rejection_audit_failed"
                            with relay._lock:
                                relay._scopes[lease["scope_id"]].update(blocked=True, block_reason=code)
                    status = 401 if code == "relay_token_rejected" else 409 if code in {"relay_busy", "scope_blocked", "relay_inactive"} else 502 if lease and relay._has_dispatch(lease) else 400
                    body = canonical({"error": {"code": code, "message": "Controlled relay request rejected."}}).encode()
                    try:
                        self.send_response(status)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(body)))
                        self.send_header("Connection", "close")
                        self.end_headers()
                        self.wfile.write(body)
                    except (OSError, ValueError):
                        pass
                finally:
                    self.close_connection = True
                    if lease is not None:
                        relay._release(lease)
            def do_GET(self):
                self.send_error(405, "POST required")
        self._server = _Server(("127.0.0.1", 0), Handler)
        self.base_url = "http://127.0.0.1:" + str(self._server.server_port)
        self._thread = threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self._persist()
        self._thread.start()

    @property
    def local_token(self):
        with self._lock:
            return self._token

    @property
    def registration(self):
        return copy.deepcopy(self._registration)

    def bind_transport(self, receipt):
        required = {"schema_version", "kind", "transport_id", "config_sha256", "relay_source_sha256",
                    "registration_sha256", "admission_id"}
        if (not isinstance(receipt, dict) or set(receipt) != required or type(receipt["schema_version"]) is not int
                or receipt["schema_version"] != 1 or receipt["kind"] != "p1-relay-registration-receipt"
                or receipt["transport_id"] != self._transport_id or receipt["config_sha256"] != self.config_sha256
                or receipt["relay_source_sha256"] != self.relay_source_sha256
                or receipt["registration_sha256"] != digest(self._registration) or not _label(receipt["admission_id"])):
            raise RelayError("relay_registration_unconfirmed")
        with self._lock:
            if self._closed or self._active is not None or self._inflight is not None or self._registration_receipt is not None:
                raise RelayError("relay_registration_already_consumed")
            self._registration_receipt = copy.deepcopy(receipt)
            self._persist()

    @property
    def records(self):
        with self._lock:
            return copy.deepcopy(self._records)

    @property
    def local_rejections(self):
        with self._lock:
            return copy.deepcopy(self._rejections)

    @property
    def scope_states(self):
        with self._lock:
            return copy.deepcopy(self._scopes)

    def _persist(self):
        state = {"schema_version": 1, "kind": "p1-native-relay-audit", "config_sha256": self.config_sha256,
            "epoch": self._epoch, "closed": self._closed, "records": self._records, "scopes": self._scopes,
            "actual_spend": None, "native_host_attested": False,
            "transport_id": self._transport_id, "relay_source_sha256": self.relay_source_sha256,
            "registration_receipt": self._registration_receipt, "local_rejections": self._rejections}
        temporary = self.output / ("relay-state-" + secrets.token_hex(8) + ".tmp")
        with temporary.open("x", encoding="utf-8") as stream:
            os.chmod(temporary, 0o600)
            stream.write(canonical(state) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(self.output / "relay-state.json")
        directory = os.open(self.output, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def _write_immutable(self, name, value):
        target = self.output / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        raw = (canonical(value) + "\n").encode("utf-8")
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return hashlib.sha256(raw).hexdigest()

    def _reject_local(self, lease, *, code, received, received_hash, body_complete):
        """Evidence of a local refusal; never a dispatch, usage observation or bill."""
        with self._lock:
            if lease["record_id"] is not None:
                return
            name = "rejections/" + str(len(self._rejections) + 1).zfill(6) + ".json"
            value = {"schema_version": 1, "kind": "p1-native-relay-local-rejection",
                "transport_id": self._transport_id, "relay_source_sha256": self.relay_source_sha256,
                "config_sha256": self.config_sha256, "scope_id": lease["scope_id"],
                "component": lease["component"], "checkpoint_sha256": lease["checkpoint_sha256"],
                "epoch": lease["epoch"], "error_code": code, "request_bytes_received": received,
                "request_bytes_sha256": received_hash, "request_body_complete": body_complete,
                "provider_dispatch_started": False}
            record_hash = self._write_immutable(name, value)
            self._rejections.append({"path": name, "sha256": record_hash})
            self._persist()

    def _complete(self, record):
        """One immutable actual observation and one required controller handshake."""
        if record.get("completion_attempted"):
            if not record.get("completion_receipt"):
                raise RelayError("dispatch_completion_unconfirmed")
            return record["completion_receipt"]["decision"]
        value = {"schema_version": 1, "kind": "p1-deepseek-dispatch-result",
            "transport_id": self._transport_id, "relay_source_sha256": self.relay_source_sha256,
            "config_sha256": self.config_sha256, "scope_id": record["scope_id"],
            "dispatch_id": record["dispatch_id"], "intent_sha256": record["intent"]["intent_sha256"],
            "request_sha256": record["request_sha256"], "provider_dispatch_started": record["provider_dispatch_started"],
            "status": record["status"], "usage": record["usage"], "usage_complete": record["usage_complete"],
            "terminal_event": record["terminal_event"], "response_sha256": record.get("response_sha256"),
            "response_bytes": record.get("response_bytes"), "error_code": record.get("error_code")}
        record_hash = self._write_immutable("dispatches/" + record["dispatch_id"] + ".json", value)
        completion = {"schema_version": 1, "kind": "p1-provider-dispatch-completion",
            "transport_id": self._transport_id, "dispatch_id": record["dispatch_id"],
            "request_sha256": record["request_sha256"], "intent_sha256": record["intent"]["intent_sha256"],
            "record_sha256": record_hash}
        with self._lock:
            record.update(completion_attempted=True, completion_record_sha256=record_hash, completion_receipt=None)
            self._persist()
        try:
            receipt = self.complete_dispatch(copy.deepcopy(completion), scope_id=record["scope_id"])
        except Exception:
            raise RelayError("dispatch_completion_callback_failed") from None
        required = {"schema_version", "kind", "dispatch_id", "intent_sha256", "record_sha256", "decision", "admission_id"}
        if (not isinstance(receipt, dict) or set(receipt) != required or type(receipt["schema_version"]) is not int
                or receipt["schema_version"] != 1 or receipt["kind"] != "p1-dispatch-completion-receipt"
                or receipt["decision"] not in {"continue", "blocked"} or not _label(receipt["admission_id"])
                or any(receipt[key] != completion[key] for key in ("dispatch_id", "intent_sha256", "record_sha256"))):
            raise RelayError("dispatch_completion_unconfirmed")
        with self._lock:
            record["completion_receipt"] = copy.deepcopy(receipt)
            self._persist()
        return receipt["decision"]

    def activate(self, *, scope_id, component, checkpoint_sha256, deadline):
        if (not _label(scope_id) or component not in COMPONENTS
                or checkpoint_sha256 is not None and (not isinstance(checkpoint_sha256, str) or not HEX.fullmatch(checkpoint_sha256))
                or component == "reader" and checkpoint_sha256 is None
                or type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline <= time.monotonic()):
            raise RelayError("invalid_relay_activation")
        with self._lock:
            if self._closed:
                raise RelayError("relay_closed")
            if self._registration_receipt is None:
                raise RelayError("relay_registration_required")
            if self._inflight is not None:
                raise RelayError("relay_busy")
            state = self._scopes.setdefault(scope_id, {"dispatches": 0, "reference_input_tokens": 0,
                "input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0, "blocked": False,
                "block_reason": None, "usage_complete": True, "checkpoint_sha256": checkpoint_sha256})
            if state["blocked"]:
                raise RelayError("scope_blocked")
            if state["checkpoint_sha256"] != checkpoint_sha256:
                raise RelayError("scope_checkpoint_changed")
            self._epoch += 1
            self._token = secrets.token_urlsafe(32)
            self._active = {"scope_id": scope_id, "component": component, "checkpoint_sha256": checkpoint_sha256,
                            "deadline": deadline, "epoch": self._epoch}
            self._persist()
            return {"base_url": self.base_url, "local_token": self._token, "epoch": self._epoch}

    def deactivate(self):
        with self._lock:
            if self._inflight is not None:
                state = self._scopes[self._inflight["scope_id"]]
                state.update(blocked=True, block_reason="deactivated_with_inflight_request", usage_complete=False)
            self._active = None
            self._epoch += 1
            self._token = secrets.token_urlsafe(32)
            self._persist()

    def close(self):
        with self._lock:
            if self._closed:
                return
            self.deactivate()
            self._closed = True
            self._persist()
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=1)

    def _begin(self, authorization):
        with self._lock:
            if not isinstance(authorization, str) or len(authorization) > 256 or not hmac.compare_digest(authorization, "Bearer " + self._token):
                raise RelayError("relay_token_rejected")
            if self._closed or self._active is None:
                raise RelayError("relay_inactive")
            if self._inflight is not None:
                raise RelayError("relay_busy")
            if self._scopes[self._active["scope_id"]]["blocked"]:
                raise RelayError("scope_blocked")
            lease = copy.deepcopy(self._active)
            lease["request_deadline"] = min(lease["deadline"], time.monotonic() + self.profile["timeout_seconds"])
            lease["local_token"] = self._token
            lease["record_id"] = None
            self._remaining(lease)
            self._inflight = lease
            return lease

    def _remaining(self, lease):
        remaining = min(lease["deadline"], lease["request_deadline"]) - time.monotonic()
        if remaining <= 0:
            raise RelayError("relay_deadline_exhausted")
        return remaining

    def _ensure_active(self, lease):
        with self._lock:
            if self._closed or self._active is None or self._active["epoch"] != lease["epoch"]:
                raise RelayError("relay_epoch_expired")
            self._remaining(lease)

    def _has_dispatch(self, lease):
        with self._lock:
            index = lease.get("record_id")
            return type(index) is int and self._records[index]["provider_dispatch_started"]

    def _release(self, lease):
        with self._lock:
            if self._inflight is lease:
                self._inflight = None

    def _read_upstream(self, response, lease, deadline):
        if response.status != 200 or response.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "text/event-stream":
            raise RelayError("upstream_sse_response_required")
        limit = self.profile["max_response_bytes"]
        length = response.headers.get("content-length")
        if length is not None and (not length.isdigit() or len(length) > 12 or int(length) > limit):
            raise RelayError("response_byte_limit")
        parts, size = [], 0
        while True:
            self._ensure_active(lease)
            remaining = min(deadline, lease["deadline"], lease["request_deadline"]) - time.monotonic()
            if remaining <= 0:
                raise RelayError("relay_request_timeout")
            sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
            if sock is not None:
                sock.settimeout(remaining)
            # read1 returns after one socket read, so a slow trickle cannot
            # restart the total request deadline inside a large buffered read.
            chunk = getattr(response, "read1", response.read)(min(65536, limit - size + 1))
            if not isinstance(chunk, bytes):
                raise RelayError("invalid_upstream_body")
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise RelayError("response_byte_limit")
            parts.append(chunk)
        if time.monotonic() > deadline:
            raise RelayError("relay_request_timeout")
        return b"".join(parts)

    def _process(self, raw, lease):
        self._ensure_active(lease)
        with self._lock:
            state = self._scopes[lease["scope_id"]]
            if state["dispatches"] >= self.profile["max_http_dispatches"]:
                raise RelayError("scope_dispatch_budget_exhausted")
            forwarded, encoded, names = prepare_request(raw, self.profile,
                self.profile["max_model_output_tokens"] - state["output_tokens"])
            try:
                reference = self.token_counter(encoded.decode("utf-8"))
            except Exception:
                raise RelayError("reference_token_measurement_failed") from None
            if type(reference) is not int or reference < 0:
                raise RelayError("invalid_reference_token_measurement")
            if state["reference_input_tokens"] + reference > self.profile["reference_input_token_limit"]:
                raise RelayError("scope_reference_input_budget_exhausted")
            if state["input_tokens"] >= self.profile["max_model_input_tokens"]:
                raise RelayError("scope_input_budget_exhausted")
            operation = "native-relay-" + secrets.token_hex(20)
            timeout_ms = max(1, int(min(self.profile["timeout_seconds"], self._remaining(lease)) * 1000))
            intent = {"schema_version": 1, "kind": "p1-deepseek-native-intent", "provider": "deepseek",
                "model": MODEL, "endpoint": ENDPOINT, "scope_id": lease["scope_id"],
                "component": lease["component"], "checkpoint_sha256": lease["checkpoint_sha256"],
                "dispatch_id": operation, "request_sha256": hashlib.sha256(encoded).hexdigest(),
                "request_bytes": len(encoded), "config_sha256": self.config_sha256,
                "transport_id": self._transport_id, "relay_source_sha256": self.relay_source_sha256,
                "reference_input_tokens": reference, "max_output_tokens": forwarded["max_output_tokens"],
                "max_response_bytes": self.profile["max_response_bytes"], "timeout_ms": timeout_ms}
            intent["intent_sha256"] = digest(intent)
            record = {"schema_version": 1, "scope_id": lease["scope_id"], "component": lease["component"],
                "checkpoint_sha256": lease["checkpoint_sha256"], "epoch": lease["epoch"],
                "dispatch_id": operation, "wire_request_sha256": hashlib.sha256(raw).hexdigest(),
                "request_sha256": intent["request_sha256"], "config_sha256": self.config_sha256,
                "intent": intent, "admission": None, "provider_dispatch_started": False,
                "admission_attempted": False, "completion_attempted": False, "completion_receipt": None,
                "status": "admission_pending", "usage": None, "usage_complete": False,
                "terminal_event": None, "actual_spend": None,
                "started_at_utc": datetime.now(timezone.utc).isoformat()}
            lease["record_id"] = len(self._records)
            self._records.append(record)
            self._persist()
        try:
            try:
                credential = self.credential_provider()
            except Exception:
                raise RelayError("provider_credential_unavailable") from None
            if not isinstance(credential, str) or not 8 <= len(credential) <= 4096 or any(c.isspace() or ord(c) > 126 or ord(c) < 33 for c in credential):
                raise RelayError("provider_credential_unavailable")
            if _contains_secret(forwarded, (credential, lease["local_token"])):
                raise RelayError("credential_in_request_rejected")
            self._ensure_active(lease)
            try:
                with self._lock:
                    record["admission_attempted"] = True
                    self._persist()
                admission = self.authorize_dispatch(copy.deepcopy(intent), scope_id=lease["scope_id"])
            except Exception:
                raise RelayError("dispatch_admission_failed") from None
            required = {"schema_version", "kind", "decision", "dispatch_id", "intent_sha256", "request_sha256", "admission_id"}
            if (not isinstance(admission, dict) or set(admission) != required or type(admission.get("schema_version")) is not int
                    or admission["schema_version"] != 1 or admission["kind"] != "p1-dispatch-admission-receipt"
                    or admission["decision"] != "allow" or not _label(admission["admission_id"])
                    or any(admission[k] != intent[k] for k in ("dispatch_id", "intent_sha256", "request_sha256"))):
                raise RelayError("dispatch_admission_unconfirmed")
            if _contains_secret(admission, (credential, lease["local_token"])):
                raise RelayError("credential_in_admission_rejected")
            self._ensure_active(lease)
            with self._lock:
                record.update(admission=copy.deepcopy(admission), provider_dispatch_started=True, status="provider_request_started")
                state["dispatches"] += 1
                state["reference_input_tokens"] += reference
                self._persist()
            deadline = min(lease["deadline"], lease["request_deadline"])
            request = urllib.request.Request(ENDPOINT, data=encoded, method="POST",
                headers={"Authorization": "Bearer " + credential, "Content-Type": "application/json", "Accept": "text/event-stream"})
            try:
                with self._opener.open(request, timeout=max(0.001, deadline - time.monotonic())) as response:
                    body = self._read_upstream(response, lease, deadline)
            except urllib.error.HTTPError:
                raise RelayError("provider_http_error") from None
            except urllib.error.URLError:
                raise RelayError("provider_connection_error") from None
            parsed = parse_sse(body, tool_names=names, credential=credential, local_token=lease["local_token"])
            self._ensure_active(lease)
            with self._lock:
                record.update(parsed, response_sha256=hashlib.sha256(body).hexdigest(), response_bytes=len(body))
                usage = parsed["usage"]
                if usage is None:
                    raise RelayError("provider_usage_missing_or_invalid")
                for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
                    state[key] += usage[key]
                if (state["input_tokens"] > self.profile["max_model_input_tokens"]
                        or state["output_tokens"] > self.profile["max_model_output_tokens"]
                        or usage["output_tokens"] > forwarded["max_output_tokens"]):
                    raise RelayError("provider_usage_exceeds_scope_budget")
                if parsed["terminal_event"] != "response.completed":
                    raise RelayError("provider_response_not_completed")
                record["status"] = "completed"
                self._persist()
            if self._complete(record) != "continue":
                raise RelayError("dispatch_completion_scope_blocked")
            self._ensure_active(lease)
            return body
        except BaseException as exc:
            code = str(exc) if isinstance(exc, RelayError) else "relay_dispatch_failed"
            with self._lock:
                state.update(blocked=True, block_reason=code,
                             usage_complete=state["usage_complete"] and record["usage_complete"])
                record.update(status="failed", error_code=code)
                self._persist()
            if record["admission_attempted"] and not record["completion_attempted"]:
                try:
                    self._complete(record)
                except Exception:
                    with self._lock:
                        record["completion_error"] = "dispatch_completion_unconfirmed"
                        self._persist()
            raise RelayError(code) from None
