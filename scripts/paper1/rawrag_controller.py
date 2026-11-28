#!/usr/bin/env python3
"""Checkpoint-bound official retrieval, dispatched only by a cash controller.

This module never creates a checkpoint, authenticates a receipt, or replaces
the pinned retrieval models. The caller admits the real shared native parent
and owns the canonical cash ledger. Provider usage remains distinct from local
reference-token limits and from actual invoices.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import sys


_spec = importlib.util.spec_from_file_location("_p1_bound_rawrag_baseline",
                                               Path(__file__).with_name("rawrag_adapter.py"))
baseline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(baseline)
HEX = re.compile(r"[a-f0-9]{64}\Z")
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
CHECKPOINT_FIELDS = {
    "task_id", "replicate", "public_sha256", "workspace_snapshot_sha256",
    "native_parent_thread_id", "native_capture_sha256", "native_compaction_item_id",
    "source_archive_sha256", "shared_reader_config_sha256", "original_request_sha256",
}
TOKENIZER_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"


def _digest(value):
    return baseline.digest_text(baseline.canonical(value))


def _regular_input(path):
    path = Path(path).absolute()
    if any(part.is_symlink() for part in (path, *path.parents)) or not path.is_file():
        raise baseline.ContractError("bound_input_must_be_regular_file")
    return path


def validate_checkpoint(checkpoint):
    if not isinstance(checkpoint, dict) or set(checkpoint) != CHECKPOINT_FIELDS:
        raise baseline.ContractError("checkpoint_schema_mismatch")
    for key, value in checkpoint.items():
        if key.endswith("sha256"):
            valid = isinstance(value, str) and HEX.fullmatch(value)
        elif key == "replicate":
            valid = type(value) is int and value > 0
        else:
            valid = isinstance(value, str) and LABEL.fullmatch(value) and not value.startswith("sk-")
        if not valid:
            raise baseline.ContractError("invalid_checkpoint_identity")
    # Only identities, never evaluator claims or source locations, cross this seam.
    return json.loads(baseline.canonical(checkpoint))


def load_bound_inputs(*, config, checkpoint, archive_path, request_path):
    checkpoint = validate_checkpoint(checkpoint)
    archive_path, request_path = _regular_input(archive_path), _regular_input(request_path)
    archive_bytes = baseline.read_bytes_bounded(archive_path, config["limits"]["max_archive_bytes"])
    request_bytes = baseline.read_bytes_bounded(request_path, config["limits"]["max_request_bytes"])
    if hashlib.sha256(archive_bytes).hexdigest() != checkpoint["source_archive_sha256"]:
        raise baseline.ContractError("source_archive_binding_mismatch")
    if hashlib.sha256(request_bytes).hexdigest() != checkpoint["original_request_sha256"]:
        raise baseline.ContractError("original_request_binding_mismatch")
    try:
        archive = json.loads(archive_bytes.decode("utf-8"), object_pairs_hook=baseline._unique_object,
                             parse_constant=baseline._invalid_number)
        request = request_bytes.decode("utf-8")
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise baseline.ContractError("invalid_bound_input") from None
    baseline.validate_archive(archive, config["limits"])
    baseline.validate_request(request, config["limits"])
    if archive["taskId"] != checkpoint["task_id"]:
        raise baseline.ContractError("checkpoint_task_mismatch")
    return checkpoint, archive, request


def normalize_usage(ledger, *, binding, source_ref, source_sha256, terminal_status):
    """Produce additive experiment.py records from matched provider responses.

    Embedding uses the provider's prompt token count as a quantity in tokens.
    Cohere reranking uses its returned search units. Neither reference tokenizer
    counts nor the number of HTTP attempts is a substitute for these quantities.
    Failure/timeout requests lacking usage keep their component incomplete.
    """
    report = {"usage_rows": [], "complete": False, "issues": [], "actual_spend": None,
              "standardized_cost": None,
              "metering": {"embedding": {"kind": "quantity", "unit": "token"},
                           "rerank": {"kind": "quantity", "unit": "search_unit"}}}
    if (not isinstance(ledger, dict) or ledger.get("controller_binding") != binding
            or not isinstance(source_ref, str) or not source_ref.strip()
            or not isinstance(source_sha256, str) or not HEX.fullmatch(source_sha256)):
        report["issues"] = ["usage_binding_mismatch"]
        return report
    dispatches, logs = ledger.get("dispatches"), ledger.get("provider_usage_observed")
    if not isinstance(dispatches, list) or not isinstance(logs, list):
        report["issues"] = ["invalid_usage_ledger"]
        return report
    issues, incomplete = set(), set()
    if ledger.get("closed") is not True:
        issues.add("retrieval_usage_not_sealed")
        incomplete.update(("embedding", "rerank"))
    if ledger.get("observed_http_dispatch_attempts") != len(dispatches):
        issues.add("dispatch_inventory_mismatch")
        incomplete.update(("embedding", "rerank"))
    grouped = {}
    for row in logs:
        if not isinstance(row, dict):
            issues.add("malformed_provider_usage_log")
            incomplete.update(("embedding", "rerank"))
            continue
        number = row.get("dispatch_id")
        if type(number) is int:
            grouped.setdefault(number, []).append(row)
        elif row.get("usage") or row.get("billed_units"):
            issues.add("unbound_provider_usage_log")
            incomplete.update(("embedding", "rerank"))
    identities, operations = set(), set()
    inventories = {"embedding": [], "rerank": []}
    observed = {"embedding": 0, "rerank": 0}
    for dispatch in dispatches:
        component = dispatch.get("kind") if isinstance(dispatch, dict) else None
        if component not in inventories:
            issues.add("unknown_dispatch_component")
            incomplete.update(inventories)
            continue
        observed[component] += 1
        number, operation = dispatch.get("dispatch_id"), dispatch.get("operation_id")
        if (type(number) is not int or number < 1 or number in identities
                or not isinstance(operation, str) or not LABEL.fullmatch(operation)
                or operation in operations):
            issues.add("invalid_or_duplicate_dispatch_identity")
            incomplete.add(component)
            continue
        identities.add(number)
        operations.add(operation)
        records = grouped.get(number, [])
        if len(records) != 1:
            issues.add("provider_usage_inventory_mismatch:" + component)
            incomplete.add(component)
            continue
        record = records[0]
        wanted_provider = "openai" if component == "embedding" else "cohere"
        wanted_model = "text-embedding-3-small" if component == "embedding" else "rerank-v3.5"
        status = dispatch.get("http_status")
        if (record.get("call_type") != component or record.get("error_present") is not False
                or record.get("provider_model_mismatch") is True
                or dispatch.get("provider") != wanted_provider or dispatch.get("model") != wanted_model
                or record.get("provider_model") not in (None, wanted_model)
                or type(status) is not int or not 200 <= status < 300):
            issues.add("request_usage_unconfirmed:" + component)
            incomplete.add(component)
            continue
        if component == "embedding":
            usage = record.get("usage")
            quantity = usage.get("prompt_tokens") if isinstance(usage, dict) else None
            total = usage.get("total_tokens") if isinstance(usage, dict) else None
            valid = (type(quantity) is int and 0 < quantity <= 2**53 - 1
                     and type(total) is int and total == quantity
                     and record.get("provider_model") == wanted_model)
        else:
            units = record.get("billed_units")
            quantity = units.get("search_units") if isinstance(units, dict) else None
            valid = type(quantity) in (int, float) and math.isfinite(quantity) and 0 < quantity <= 2**53 - 1
        if not valid:
            issues.add("provider_quantity_missing_or_invalid:" + component)
            incomplete.add(component)
            continue
        identifier = "rawrag-usage-" + _digest({"binding": binding, "operation": operation,
                                                "component": component})[:40]
        row = {"event": "usage", "usage_id": identifier, "measurement_id": identifier,
               "operation_id": operation, "component": component, "counter_kind": "delta",
               "values": {"quantity": quantity}, "source_ref": source_ref,
               "source_sha256": source_sha256, "provider": wanted_provider, "model": wanted_model}
        request_id = dispatch.get("provider_request_id")
        if isinstance(request_id, str) and LABEL.fullmatch(request_id) and not request_id.startswith("sk-"):
            row["request_id"] = request_id
        report["usage_rows"].append(row)
        inventories[component].append(identifier)
    if set(grouped) - identities:
        issues.add("provider_usage_for_unknown_dispatch")
        incomplete.update(inventories)
    for component in inventories:
        if component in incomplete:
            coverage, reason = "incomplete", "provider_usage_missing_invalid_or_unbound"
        elif observed[component] == 0:
            if terminal_status == "retrieval_complete":
                coverage, reason = "incomplete", "completed_retrieval_missing_required_requests"
                issues.add("required_component_not_performed:" + component)
            else:
                coverage, reason = "not_performed", "stopped_before_component_dispatch"
        else:
            coverage, reason = "measured", None
        report["usage_rows"].append({"event": "component_end", "component": component,
            "coverage": coverage, "usage_ids": inventories[component], "reason": reason,
            "evidence_ref": source_ref})
    report["issues"] = sorted(issues)
    report["complete"] = not issues
    return report


def _write_new_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _file_sha(path):
    return hashlib.sha256(_regular_input(path).read_bytes()).hexdigest()


def _bound_packet(output, *, config, checkpoint, archive, binding, display):
    retrieval_path = _regular_input(output / "retrieval.json")
    retrieval = baseline.read_json_bounded(retrieval_path, 16 * 1024 * 1024)
    if (retrieval.get("status") != "retrieval_complete"
            or retrieval.get("implementation") != config["implementation"]
            or retrieval.get("upstream_commit") != baseline.UPSTREAM_COMMIT
            or retrieval.get("snapshot_sha256") != _digest(archive)
            or retrieval.get("snapshot") != archive["snapshot"]
            or retrieval.get("request_sha256") != checkpoint["original_request_sha256"]
            or retrieval.get("config_sha256") != binding["config_sha256"]
            or retrieval.get("query_policy") != "original_request"):
        raise baseline.ContractError("retrieval_output_binding_mismatch")
    metadata = retrieval.get("display")
    if not isinstance(metadata, dict) or metadata.get("display_mode") != display:
        raise baseline.ContractError("retrieval_display_binding_mismatch")
    expanded_bytes = baseline.read_bytes_bounded(_regular_input(output / "expanded-context.txt"), 16 * 1024 * 1024)
    delivered_bytes = baseline.read_bytes_bounded(_regular_input(output / "context.txt"), 16 * 1024 * 1024)
    if (hashlib.sha256(expanded_bytes).hexdigest() != metadata.get("expanded_sha256")
            or hashlib.sha256(delivered_bytes).hexdigest() != metadata.get("delivered_sha256")):
        raise baseline.ContractError("retrieval_context_digest_mismatch")
    maximum = config["limits"]["max_output_tokens"] if display == "faithful" else config["display"]["budget_matched_tokens"]
    if (type(metadata.get("delivered_tokens")) is not int or not 0 < metadata["delivered_tokens"] <= maximum
            or type(metadata.get("expanded_tokens")) is not int
            or metadata["expanded_tokens"] < metadata["delivered_tokens"]
            or type(metadata.get("truncated")) is not bool
            or display == "faithful" and (expanded_bytes != delivered_bytes or metadata["truncated"])
            or metadata.get("policy") != ("official-full-turns-no-dedup" if display == "faithful"
                                         else config["display"]["policy"])):
        raise baseline.ContractError("retrieval_display_contract_mismatch")
    try:
        text = delivered_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise baseline.ContractError("retrieval_context_must_be_utf8") from None
    receipt = {"schema_version": 1, "kind": "p1-bound-rawrag-retrieval",
        "attempt_id": binding["attempt_id"], "checkpoint": checkpoint,
        "checkpoint_sha256": binding["checkpoint_sha256"],
        "source_archive_sha256": checkpoint["source_archive_sha256"],
        "original_request_sha256": checkpoint["original_request_sha256"],
        "snapshot_sha256": _digest(archive), "rawrag_config_sha256": binding["config_sha256"],
        "upstream_commit": baseline.UPSTREAM_COMMIT, "retrieval_output_sha256": _file_sha(retrieval_path),
        "expanded_sha256": metadata["expanded_sha256"], "delivered_sha256": metadata["delivered_sha256"],
        "display": metadata, "reader_calls": 0,
        "checkpoint_admission": "caller_responsibility_not_attested_by_retrieval"}
    receipt_path = output / "binding-receipt.json"
    _write_new_json(receipt_path, receipt)
    return {"kind": "rawrag", "text": text, "bytes": len(delivered_bytes),
        "token_measurement": {"tokenizer": "gpt-4/cl100k_base", "tokenizer_sha256": TOKENIZER_SHA256,
                              "tokens": metadata["delivered_tokens"]},
        "archive_sha256": checkpoint["source_archive_sha256"],
        "original_request_sha256": checkpoint["original_request_sha256"],
        "rawrag_config_sha256": binding["config_sha256"],
        "retrieval_receipt_sha256": _file_sha(receipt_path)}


def run_bound_retrieval(*, upstream, config, archive_path, request_path, output_path,
                        checkpoint, attempt_id, authorize_dispatch, display):
    """Run the original upstream add/search under a caller's durable admission.

    ``authorize_dispatch(intent)`` is synchronous and may be called from a
    rerank worker thread. It must persist the unique canonical-ledger operation
    before returning the shared seven-field P1 admission receipt.
    """
    config = baseline.validate_config(json.loads(baseline.canonical(config)))
    checkpoint, archive, request = load_bound_inputs(config=config, checkpoint=checkpoint,
        archive_path=archive_path, request_path=request_path)
    if not isinstance(attempt_id, str) or not LABEL.fullmatch(attempt_id) or attempt_id.startswith("sk-"):
        raise baseline.ContractError("invalid_attempt_identity")
    if not callable(authorize_dispatch):
        raise baseline.ContractError("dispatch_controller_required")
    if display not in {"faithful", "budget-matched"}:
        raise baseline.ContractError("unknown_display_mode")
    binding = {"attempt_id": attempt_id, "config_sha256": _digest(config),
               "checkpoint_sha256": _digest(checkpoint)}
    output = Path(output_path).absolute()
    if any(part.is_symlink() for part in (output, *output.parents)) or output.exists():
        raise baseline.ContractError("bound_output_directory_must_be_new")
    expected_inputs = {key: checkpoint[key] for key in
                       ("task_id", "source_archive_sha256", "original_request_sha256")}
    result = baseline.run_retrieval(upstream, config, archive_path, request_path, output, display,
        authorize_dispatch=authorize_dispatch, dispatch_binding=binding, expected_inputs=expected_inputs)
    report = {"schema_version": 1, "kind": "p1-bound-rawrag-run", "status": result["status"],
        "packet": None, "usage_rows": [], "trace_refs": [],
        "completeness": {"usage": False, "evidence": False}, "retrieval_result": result,
        "performance_pilot_completed": False, "actual_spend": None, "standardized_cost": None}
    if not output.exists():
        # Preflight failures made no provider calls and leave no baseline ledger.
        output.mkdir(parents=True, exist_ok=False)
    _write_new_json(output / "controller-binding.json", {**binding, "checkpoint": checkpoint})
    ledger_path = output / "ledger.json"
    if ledger_path.is_file():
        ledger = baseline.read_json_bounded(_regular_input(ledger_path), 16 * 1024 * 1024)
        usage = normalize_usage(ledger, binding=binding, source_ref="ledger.json",
                                source_sha256=_file_sha(ledger_path), terminal_status=result["status"])
        report["usage_rows"] = usage["usage_rows"]
        report["completeness"]["usage"] = usage["complete"]
    else:
        usage = {"usage_rows": [], "complete": False, "issues": ["retrieval_not_started"],
                 "actual_spend": None, "standardized_cost": None}
    _write_new_json(output / "usage-audit.json", usage)
    with (output / "usage.jsonl").open("x", encoding="utf-8") as stream:
        for row in report["usage_rows"]:
            stream.write(baseline.canonical(row) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    if result["status"] == "retrieval_complete":
        try:
            report["packet"] = _bound_packet(output, config=config, checkpoint=checkpoint,
                archive=archive, binding=binding, display=display)
            report["completeness"]["evidence"] = True
        except baseline.ContractError as exc:
            report.update(status="failed", error_code=str(exc))
    for name in ("config.public.json", "preflight.json", "ledger.json", "run.json", "retrieval.json",
                 "context.txt", "expanded-context.txt", "controller-binding.json", "binding-receipt.json",
                 "usage.jsonl", "usage-audit.json"):
        path = output / name
        if path.is_file():
            report["trace_refs"].append({"path": name, "sha256": _file_sha(path)})
    _write_new_json(output / "controller-run.json", report)
    report["trace_refs"].append({"path": "controller-run.json", "sha256": _file_sha(output / "controller-run.json")})
    return report
