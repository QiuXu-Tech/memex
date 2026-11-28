#!/usr/bin/env python3
"""Freeze a paired P1 plan, journal first attempts, then join evaluator quality.

The default dispatch is a dry run. Only dispatch --run starts the explicitly
frozen executable. No evaluator input or controller plan path reaches that
process. This controller is not an OS sandbox or a host/model implementation.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import signal
import stat
import subprocess
import sys
import time
import uuid


KEY_FIELDS = ("task_id", "project_id", "arm", "replicate")
PHASES = {"development", "pilot", "confirmatory", "external"}
TERMINAL_STATUSES = {
    "completed", "failed", "host_error", "host_failed", "host_failure", "host_timeout",
    "provider_error", "model_invalid_output", "budget_exhausted", "capture_incomplete", "prelude_failed",
}
PIPELINE_COMPONENTS = (
    "setup", "prelude", "compaction", "extraction", "query_generation", "embedding", "rerank",
    "source_open", "parsing", "freshness", "certificate_validation", "cache_read", "cache_write",
    "evidence_delivery", "model", "cpu", "gpu", "storage",
)
MANDATORY_MEASURED_FLOORS = {
    "A": {"model"}, "B": {"model", "embedding", "rerank"},
    "C": {"model", "extraction"}, "D": {"model", "extraction"}, "T": {"model"},
}
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_PUBLIC_BYTES = 256 * 1024 * 1024
MAX_PUBLIC_FILES = 20000


class ContractError(ValueError):
    """Stable codes only; subprocess output and environment values are not printed."""


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def strict_json(text):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ContractError("duplicate_json_property")
            result[key] = value
        return result

    def constant(_):
        raise ContractError("nonfinite_json_number")
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ContractError("invalid_json") from None


def read_json(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > MAX_JSON_BYTES:
        raise ContractError("unsafe_or_oversized_json")
    return strict_json(path.read_text(encoding="utf-8"))


def write_new_json(path, value):
    with Path(path).open("x", encoding="utf-8") as target:
        target.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        target.flush()
        os.fsync(target.fileno())


def fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys() - set(required) - set(optional):
        raise ContractError("schema_fields_mismatch")


def label(value):
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def number(value, positive=False):
    try:
        return type(value) in (int, float) and math.isfinite(value) and (value > 0 if positive else value >= 0)
    except OverflowError:
        return False


def run_key(row):
    if not isinstance(row, dict) or not all(label(row.get(k)) for k in KEY_FIELDS[:-1]):
        raise ContractError("invalid_run_key")
    if type(row.get("replicate")) is not int or row["replicate"] < 1:
        raise ContractError("invalid_run_key")
    return tuple(row[k] for k in KEY_FIELDS)


def public_digest(path):
    path = Path(path)
    if path.is_symlink() or not path.exists():
        raise ContractError("public_input_missing_or_symlink")
    entries = [path, *sorted(path.rglob("*"))] if path.is_dir() else [path]
    records, size = [], 0
    for entry in entries:
        if entry.is_symlink():
            raise ContractError("public_input_symlink_forbidden")
        relative = entry.relative_to(path).as_posix() if path.is_dir() else "."
        mode = stat.S_IMODE(entry.stat().st_mode)
        if len(records) >= MAX_PUBLIC_FILES:
            raise ContractError("public_input_size_limit")
        if entry.is_dir():
            records.append([relative, "directory", mode])
            continue
        if not entry.is_file():
            raise ContractError("public_input_must_be_regular_file")
        if entry.name == ".env" or entry.name.startswith(".env."):
            raise ContractError("environment_file_not_public_input")
        size += entry.stat().st_size
        if size > MAX_PUBLIC_BYTES or len(records) >= MAX_PUBLIC_FILES:
            raise ContractError("public_input_size_limit")
        records.append([relative, "file", mode, hashlib.sha256(entry.read_bytes()).hexdigest()])
    if not records:
        raise ContractError("empty_public_input")
    return digest(records)


def validate_measurement(value, arms):
    fields(value, {"schema_version", "frozen", "currency", "rate_card_id", "rates", "cost_scope",
                   "allocation_rule", "components", "required_components", "mandatory_measured_components",
                   "not_applicable", "allocation_factors"})
    if type(value["schema_version"]) is not int or value["schema_version"] != 1 or value["frozen"] is not True:
        raise ContractError("measurement_must_be_frozen")
    if not re.fullmatch(r"[A-Z]{3}", str(value["currency"])) or not label(value["rate_card_id"]):
        raise ContractError("invalid_cost_identity")
    if value["cost_scope"] != "full_pipeline_per_scheduled_task" or value["allocation_rule"] != "component_factors_per_scheduled_task_v1":
        raise ContractError("unsupported_cost_scope_or_allocation")
    rates, components = value["rates"], value["components"]
    if not isinstance(rates, dict) or not rates or not isinstance(components, dict):
        raise ContractError("rate_and_component_declarations_required")
    for name, rate in rates.items():
        fields(rate, {"price", "per", "unit", "source", "as_of"}, {"zero_price_evidence"})
        if not all(label(v) for v in (name, rate["unit"], rate["source"])) or not number(rate["per"], True):
            raise ContractError("invalid_rate_unit_or_source")
        if rate["price"] is not None and not number(rate["price"]):
            raise ContractError("invalid_rate_price")
        if rate["price"] == 0:
            evidence = rate.get("zero_price_evidence")
            fields(evidence, {"ref", "sha256"})
            if not label(evidence["ref"]) or not isinstance(evidence["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", evidence["sha256"]):
                raise ContractError("documented_zero_reference_price_required")
        try:
            date.fromisoformat(rate["as_of"])
        except (ValueError, TypeError):
            raise ContractError("dated_rate_source_required") from None
    for name, spec in components.items():
        if not label(name) or not isinstance(spec, dict):
            raise ContractError("invalid_component")
        if spec.get("kind") == "tokens":
            fields(spec, {"kind", "rates"})
            fields(spec["rates"], {"input_uncached", "input_cached", "output"})
            references = list(spec["rates"].values())
            unit = "token"
        elif spec.get("kind") == "quantity":
            fields(spec, {"kind", "rate", "unit"})
            references, unit = [spec["rate"]], spec["unit"]
        else:
            raise ContractError("unsupported_meter_kind")
        if not label(unit) or any(not isinstance(r, str) or r not in rates or rates[r]["unit"] != unit for r in references):
            raise ContractError("rate_unit_mismatch")
    if components.get("model", {}).get("kind") != "tokens":
        raise ContractError("model_must_account_for_cached_token_partition")
    for key in ("required_components", "mandatory_measured_components", "not_applicable"):
        if not isinstance(value[key], dict) or set(value[key]) != set(arms):
            raise ContractError("component_declaration_arm_mismatch")
    for arm in arms:
        required = value["required_components"][arm]
        mandatory = value["mandatory_measured_components"][arm]
        omitted = value["not_applicable"][arm]
        if (not isinstance(required, list) or not all(label(c) for c in required)
                or len(set(required)) != len(required) or not set(PIPELINE_COMPONENTS) <= set(required)
                or not set(required) <= components.keys()):
            raise ContractError("full_pipeline_component_declaration_required")
        if (not isinstance(omitted, list) or not all(label(c) for c in omitted)
                or len(set(omitted)) != len(omitted) or not set(omitted) <= set(required)):
            raise ContractError("invalid_not_applicable_declaration")
        floor = MANDATORY_MEASURED_FLOORS.get(arm, {"model"})
        if (not isinstance(mandatory, list) or not all(label(c) for c in mandatory)
                or len(set(mandatory)) != len(mandatory) or not floor <= set(mandatory)
                or not set(mandatory) <= set(required) or set(mandatory) & set(omitted)):
            raise ContractError("mandatory_measured_component_policy_mismatch")
    factors = value["allocation_factors"]
    if not isinstance(factors, dict) or set(factors) != set(components) or any(
            not number(f, True) or f > 1 for f in factors.values()):
        raise ContractError("explicit_component_allocation_factors_required")
    return value


def freeze_study(spec_path, output):
    spec = read_json(spec_path)
    fields(spec, {"schema_version", "study_phase", "tasks", "arms", "replicates", "seed",
                  "runner", "env_allowlist", "budgets", "measurement"}, {"analysis_plan"})
    if type(spec["schema_version"]) is not int or spec["schema_version"] != 1 or spec["study_phase"] not in PHASES:
        raise ContractError("invalid_study_schema")
    arms = spec["arms"]
    if not isinstance(arms, list) or not arms or not all(label(a) for a in arms) or len(set(arms)) != len(arms):
        raise ContractError("invalid_arms")
    if type(spec["replicates"]) is not int or spec["replicates"] < 1 or type(spec["seed"]) is not int or spec["seed"] < 0:
        raise ContractError("invalid_replication_or_seed")
    budget = spec["budgets"]
    fields(budget, {"max_runs", "max_wall_seconds", "per_run_seconds"})
    if type(budget["max_runs"]) is not int or budget["max_runs"] < 1 or any(
            not number(budget[k], True) for k in ("max_wall_seconds", "per_run_seconds")):
        raise ContractError("invalid_execution_budget")
    runner = Path(spec["runner"])
    if not runner.is_absolute() or runner.is_symlink() or not runner.is_file() or not os.access(runner, os.X_OK):
        raise ContractError("explicit_executable_runner_required")
    env = spec["env_allowlist"]
    if not isinstance(env, list) or any(not isinstance(k, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k)
                                      or re.search(r"GOLD|EVALUATOR|PRIVATE", k, re.I) for k in env) or len(set(env)) != len(env):
        raise ContractError("invalid_runner_environment_allowlist")
    measurement = validate_measurement(spec["measurement"], arms)
    blocks, seen = [], set()
    if not isinstance(spec["tasks"], list) or not spec["tasks"]:
        raise ContractError("nonempty_tasks_required")
    for task in spec["tasks"]:
        fields(task, {"task_id", "project_id", "public_by_replicate"})
        if not all(label(task[k]) for k in ("task_id", "project_id")) or task["task_id"] in seen:
            raise ContractError("task_identity_must_be_unique")
        seen.add(task["task_id"])
        public = task["public_by_replicate"]
        if not isinstance(public, dict) or set(public) != {str(r) for r in range(1, spec["replicates"] + 1)}:
            raise ContractError("public_snapshot_required_for_every_replicate")
        for replicate in range(1, spec["replicates"] + 1):
            source = Path(public[str(replicate)])
            if not source.is_absolute():
                raise ContractError("public_path_must_be_absolute")
            blocks.append({"task_id": task["task_id"], "project_id": task["project_id"], "replicate": replicate,
                           "public": str(source), "public_sha256": public_digest(source)})
    rng = random.Random(spec["seed"])
    rng.shuffle(blocks)
    units, runs = [], []
    for block in blocks:
        order = list(arms)
        rng.shuffle(order)
        for arm in order:
            key = {"task_id": block["task_id"], "project_id": block["project_id"], "arm": arm,
                   "replicate": block["replicate"]}
            runs.append(key)
            identity = {"key": key, "spec_sha256": digest(spec), "public_sha256": block["public_sha256"],
                        "runner_sha256": hashlib.sha256(runner.read_bytes()).hexdigest()}
            units.append({"key": key, "run_id": "p1_" + digest(identity)[:24],
                          "public": block["public"], "public_sha256": block["public_sha256"]})
    manifest = {"schema_version": 1, "study_phase": spec["study_phase"], "frozen": True, "runs": runs}
    if "analysis_plan" in spec:
        analysis = spec["analysis_plan"]
        fields(analysis, {"frozen", "primary_contrast", "secondary_contrast", "confidence_level",
                          "noninferiority_margin", "bootstrap_method", "task_weighting", "replicate_aggregation",
                          "seed", "bootstrap_samples", "min_tasks", "min_projects"})
        constants = {"primary_contrast": "D-B", "secondary_contrast": "D-C", "confidence_level": 0.95,
                     "noninferiority_margin": 0.03, "bootstrap_method": "project_then_task_percentile",
                     "task_weighting": "equal", "replicate_aggregation": "mean"}
        if type(analysis["frozen"]) is not bool or any(analysis[k] != v for k, v in constants.items()):
            raise ContractError("unsupported_analysis_plan")
        minima = {"seed": 0, "bootstrap_samples": 1000 if spec["study_phase"] == "confirmatory" else 1,
                  "min_tasks": 2, "min_projects": 2}
        if any(type(analysis[k]) is not int or analysis[k] < minimum for k, minimum in minima.items()):
            raise ContractError("invalid_frozen_analysis_settings")
        manifest["analysis_plan"] = analysis
    if spec["study_phase"] == "confirmatory" and not (manifest.get("analysis_plan", {}).get("frozen") is True):
        raise ContractError("confirmatory_analysis_plan_must_be_frozen")
    known_rates = {k: r["price"] for k, r in measurement["rates"].items() if r["price"] is not None}
    if known_rates:
        manifest["cost_model"] = {k: measurement[k] for k in
                                  ("frozen", "currency", "rate_card_id", "cost_scope", "allocation_rule")}
        manifest["cost_model"]["rates"] = known_rates
    schedule = {"schema_version": 1, "manifest_sha256": digest(manifest), "measurement_sha256": digest(measurement),
                "seed": spec["seed"], "ordering": "seeded_task_replicate_blocks_then_seeded_arms",
                "first_attempt_policy": True, "budgets": budget, "env_allowlist": env,
                "runner": str(runner), "runner_sha256": hashlib.sha256(runner.read_bytes()).hexdigest(), "units": units}
    freeze = {"schema_version": 1, "manifest_sha256": digest(manifest), "schedule_sha256": digest(schedule),
              "measurement_sha256": digest(measurement), "spec_sha256": digest(spec),
              "python_version": sys.version.split()[0], "frozen_at": datetime.now(timezone.utc).isoformat()}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (("manifest", manifest), ("schedule", schedule), ("measurement", measurement), ("freeze", freeze)):
        write_new_json(output / (name + ".json"), value)
    return {"plan": str(output), "planned_runs": len(runs), "manifest_sha256": digest(manifest),
            "study_phase": spec["study_phase"], "model_requests": 0}


def load_frozen(path):
    path = Path(path)
    loaded = {name: read_json(path / (name + ".json")) for name in ("manifest", "schedule", "measurement", "freeze")}
    for name in ("manifest", "schedule", "measurement"):
        if digest(loaded[name]) != loaded["freeze"].get(name + "_sha256"):
            raise ContractError("frozen_plan_hash_mismatch")
    schedule, manifest = loaded["schedule"], loaded["manifest"]
    if schedule["manifest_sha256"] != digest(manifest) or schedule["measurement_sha256"] != digest(loaded["measurement"]):
        raise ContractError("sidecar_binding_mismatch")
    keys = [run_key(r) for r in manifest["runs"]]
    if len(keys) != len(set(keys)) or keys != [run_key(u["key"]) for u in schedule["units"]]:
        raise ContractError("scheduled_denominator_mismatch")
    validate_measurement(loaded["measurement"], {r["arm"] for r in manifest["runs"]})
    return loaded


def standardized_cost(measurement, arm, rows, *, capture_complete=True, terminal_status="completed"):
    """Recompute C_std from delta quantities; never repair missing data with zero."""
    issues, charges = [], []
    partial = Decimal(0)
    try:
        validate_measurement(measurement, measurement["required_components"].keys())
    except (ContractError, KeyError, TypeError, ValueError):
        return {"complete": False, "standardized_cost": None, "partial_observed_cost": None,
                "issues": ["invalid_measurement_or_rate_card"], "charges": []}
    if not capture_complete:
        issues.append("usage_capture_incomplete")
    if terminal_status not in TERMINAL_STATUSES:
        issues.append("execution_not_terminal")
    required = measurement["required_components"].get(arm)
    if required is None:
        return {"complete": False, "standardized_cost": None, "partial_observed_cost": None,
                "issues": ["arm_component_declaration_missing"], "charges": []}
    usages, endings, identifiers, measurements, operations = defaultdict(list), {}, set(), set(), set()
    activity = defaultdict(Decimal)

    def price(quantity, rate_name, unit):
        rate = measurement["rates"][rate_name]
        if rate["unit"] != unit or rate["price"] is None:
            raise ContractError("unknown_price_or_unit_mismatch")
        return Decimal(str(quantity)) * Decimal(str(rate["price"])) / Decimal(str(rate["per"]))

    for row in rows:
        try:
            if not isinstance(row, dict) or row.get("component") not in required:
                raise ContractError("unknown_or_unassignable_usage_component")
            component = row["component"]
            if row.get("event") == "component_end":
                fields(row, {"event", "component", "coverage", "usage_ids", "reason", "evidence_ref"})
                if component in endings or not label(row["evidence_ref"]):
                    raise ContractError("duplicate_or_unsubstantiated_component_end")
                if not isinstance(row["usage_ids"], list) or not all(label(i) for i in row["usage_ids"]):
                    raise ContractError("invalid_component_usage_inventory")
                endings[component] = row
                continue
            fields(row, {"event", "usage_id", "measurement_id", "operation_id", "component",
                         "counter_kind", "values", "source_ref"}, {"provider", "model", "request_id", "source_sha256"})
            if row["event"] != "usage" or not all(label(row[k]) for k in ("usage_id", "measurement_id", "operation_id", "source_ref")):
                raise ContractError("invalid_usage_identity")
            if component in endings:
                raise ContractError("usage_after_component_seal")
            spec = measurement["components"][component]
            unit = "token" if spec["kind"] == "tokens" else spec["unit"]
            operation = (row["operation_id"], unit)
            if row["usage_id"] in identifiers or row["measurement_id"] in measurements or operation in operations:
                raise ContractError("duplicate_pricing_measurement")
            identifiers.add(row["usage_id"])
            measurements.add(row["measurement_id"])
            operations.add(operation)
            usages[component].append(row["usage_id"])
            if row["counter_kind"] != "delta":
                raise ContractError("non_delta_usage_is_not_additive")
            values = row["values"]
            if spec["kind"] == "tokens":
                fields(values, {"input_tokens", "cached_input_tokens", "output_tokens"})
                if any(type(v) is not int or v < 0 for v in values.values()):
                    raise ContractError("unknown_or_invalid_token_usage")
                if values["cached_input_tokens"] > values["input_tokens"]:
                    raise ContractError("cached_tokens_exceed_total_input")
                quantities = {"input_uncached": values["input_tokens"] - values["cached_input_tokens"],
                              "input_cached": values["cached_input_tokens"], "output": values["output_tokens"]}
                charge = sum((price(q, spec["rates"][name], "token") for name, q in quantities.items()), Decimal(0))
                observed_activity = Decimal(values["input_tokens"] + values["output_tokens"])
            else:
                fields(values, {"quantity"})
                if not number(values["quantity"]):
                    raise ContractError("unknown_or_invalid_quantity")
                quantities = {"quantity": values["quantity"]}
                charge = price(values["quantity"], spec["rate"], unit)
                observed_activity = Decimal(str(values["quantity"]))
            factor = Decimal(str(measurement["allocation_factors"][component]))
            charge *= factor
            if not math.isfinite(float(charge)) or (charge > 0 and float(charge) == 0):
                raise ContractError("unrepresentable_cost")
            activity[component] += observed_activity
            partial += charge
            charges.append({"usage_id": row["usage_id"], "component": component, "quantities": quantities,
                            "allocation_factor": float(factor), "cost": float(charge)})
        except (ContractError, KeyError, TypeError, InvalidOperation, OverflowError) as error:
            issues.append(str(error) if isinstance(error, ContractError) else "malformed_usage_record")
    for component in required:
        ending = endings.get(component)
        if ending is None:
            issues.append("component_not_sealed:" + component)
            continue
        declared = ending["usage_ids"]
        if len(declared) != len(set(declared)) or set(declared) != set(usages[component]):
            issues.append("component_inventory_mismatch:" + component)
        if ending["coverage"] == "not_applicable":
            if component not in measurement["not_applicable"][arm] or usages[component] or not label(ending["reason"]):
                issues.append("undeclared_or_priced_not_applicable:" + component)
        elif ending["coverage"] == "not_performed":
            if terminal_status == "completed" or usages[component] or not label(ending["reason"]):
                issues.append("invalid_not_performed_component:" + component)
        elif ending["coverage"] != "measured" or not usages[component]:
            issues.append("component_unmeasured_or_incomplete:" + component)
        if terminal_status == "completed" and component in measurement["mandatory_measured_components"][arm]:
            if ending["coverage"] != "measured" or activity[component] <= 0:
                issues.append("completed_stage_lacks_measured_activity:" + component)
    partial_value = float(partial)
    if not math.isfinite(partial_value):
        partial_value = None
        issues.append("total_cost_not_representable")
    complete = not issues
    return {"complete": complete, "standardized_cost": partial_value if complete else None,
            "partial_observed_cost": partial_value, "currency": measurement["currency"],
            "issues": sorted(set(issues)), "charges": charges}


def _ledger_envelopes(path):
    path = Path(path)
    if not path.exists():
        return []
    if path.is_symlink():
        raise ContractError("ledger_symlink_forbidden")
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        raise ContractError("ledger_incomplete_tail_requires_audit")
    result, previous = [], None
    for sequence, line in enumerate(raw.splitlines(), 1):
        try:
            envelope = strict_json(line)
            fields(envelope, {"seq", "prev_sha256", "record", "sha256"})
            expected = {k: envelope[k] for k in ("seq", "prev_sha256", "record")}
            if envelope["seq"] != sequence or envelope["prev_sha256"] != previous or digest(expected) != envelope["sha256"]:
                raise ContractError("ledger_hash_chain_mismatch")
            if not isinstance(envelope["record"], dict):
                raise ContractError("invalid_ledger_record")
            previous = envelope["sha256"]
            result.append(envelope)
        except (ValueError, TypeError, KeyError):
            raise ContractError("ledger_integrity_error") from None
    return result


def read_ledger(path):
    return [row["record"] for row in _ledger_envelopes(path)]


class Journal:
    """Single-writer O_APPEND + fsync journal; corruption is never truncated away."""

    def __init__(self, path):
        self.path = Path(path)
        envelopes = _ledger_envelopes(path)
        self.records = [row["record"] for row in envelopes]
        self.previous = envelopes[-1]["sha256"] if envelopes else None
        self.size = self.path.stat().st_size if self.path.exists() else 0

    def append(self, record):
        current = self.path.stat().st_size if self.path.exists() else 0
        if self.path.is_symlink() or current != self.size:
            raise ContractError("concurrent_or_altered_ledger")
        envelope = {"seq": len(self.records) + 1, "prev_sha256": self.previous, "record": record}
        envelope["sha256"] = digest(envelope)
        encoded = (canonical(envelope) + "\n").encode()
        descriptor = os.open(self.path, os.O_CREAT | os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        try:
            pending = memoryview(encoded)
            while pending:
                written = os.write(descriptor, pending)
                if written < 1:
                    raise ContractError("ledger_append_failed")
                pending = pending[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self.records.append(record)
        self.previous = envelope["sha256"]
        self.size += len(encoded)


def append_ledger(path, record):
    Journal(path).append(record)


@contextmanager
def state_lock(state, *, writing):
    state = Path(state)
    if writing:
        state.mkdir(parents=True, exist_ok=True)
    if not state.exists():
        yield
        return
    path = state / "controller.lock"
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(descriptor, (fcntl.LOCK_EX if writing else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ContractError("controller_state_locked") from None
        yield
    finally:
        os.close(descriptor)


def state_snapshot(frozen, records):
    units = {u["run_id"]: u for u in frozen["schedule"]["units"]}
    start, attempts, finished = None, {}, {}
    for row in records:
        event = row.get("event")
        if event == "study_started":
            if start is not None or row.get("plan_sha256") != digest(frozen["freeze"]):
                raise ContractError("state_plan_binding_mismatch")
            start = row
            continue
        if start is None:
            raise ContractError("state_missing_study_start")
        if event == "budget_stop":
            continue
        identifier = row.get("run_id")
        if identifier not in units or row.get("key") != units[identifier]["key"] or row.get("attempt") != 1:
            raise ContractError("unplanned_or_nonfirst_ledger_record")
        if event == "run_started":
            if identifier in attempts:
                raise ContractError("duplicate_attempt_reservation")
            if not label(row.get("execution_id")):
                raise ContractError("execution_identity_required")
            attempts[identifier] = row
        elif event == "run_finished":
            if identifier not in attempts or identifier in finished or row.get("status") not in TERMINAL_STATUSES:
                raise ContractError("invalid_terminal_ledger_record")
            finished[identifier] = row
        else:
            raise ContractError("unknown_run_ledger_event")
    return start, attempts, finished


def seal_terminal(frozen, reservation, terminal, output):
    """Bind a specific first attempt and its complete captured output tree."""
    result = {**terminal, "freeze_sha256": digest(frozen["freeze"]),
              "execution_id": reservation["execution_id"], "output_sha256": public_digest(output)}
    result["sealed_run_sha256"] = digest({"reservation": reservation, "terminal": result})
    return result


def sealed_score_rows(frozen, state, attempts, finished):
    rows = []
    for unit in frozen["schedule"]["units"]:
        identifier = unit["run_id"]
        if identifier not in finished:
            continue
        terminal = finished[identifier]
        expected = seal_terminal(frozen, attempts[identifier],
                                 {k: v for k, v in terminal.items() if k not in {
                                     "freeze_sha256", "execution_id", "output_sha256", "sealed_run_sha256"}},
                                 Path(state) / "runs" / identifier)
        if terminal != expected:
            raise ContractError("sealed_execution_or_output_changed")
        rows.append({**unit["key"], "run_id": identifier,
                     "freeze_sha256": terminal["freeze_sha256"],
                     "sealed_run_sha256": terminal["sealed_run_sha256"],
                     "output_sha256": terminal["output_sha256"],
                     "execution_id": terminal["execution_id"], "status": terminal["status"],
                     "output_directory": str((Path(state) / "runs" / identifier).absolute()),
                     "trace_ref": terminal.get("result", {}).get("trace_ref")})
    return rows


def export_score_inputs(plan, state, output):
    frozen, state, output = load_frozen(plan), Path(state), Path(output)
    if output.absolute().is_relative_to((state / "runs").absolute()):
        raise ContractError("score_export_must_not_modify_sealed_outputs")
    with state_lock(state, writing=False):
        _, attempts, finished = state_snapshot(frozen, read_ledger(state / "run-ledger.jsonl"))
        rows = sealed_score_rows(frozen, state, attempts, finished)
    payload = {"schema_version": 1, "freeze_sha256": digest(frozen["freeze"]),
               "planned_runs": len(frozen["schedule"]["units"]), "sealed_runs": len(rows),
               "runs": rows, "model_requests": 0}
    output.parent.mkdir(parents=True, exist_ok=True)
    write_new_json(output, payload)
    return {"score_inputs": str(output), "sealed_runs": len(rows), "model_requests": 0}


def launch_runner(argv, *, cwd, env, timeout, stdout, stderr):
    """Only explicit --run reaches here. The caller provides a host-isolated runner."""
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                               stdout=stdout, stderr=stderr, shell=False, start_new_session=True)
    try:
        return process.wait(timeout=timeout)
    finally:
        # Bound descendants as well as the wrapper; do not leave model workers
        # running after a normal exit, timeout or controller interruption.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()


def collect_usage(output, unit, journal):
    path = Path(output) / "usage.jsonl"
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_JSON_BYTES:
        return {"usage_capture_complete": False, "usage_sha256": None, "usage_records": 0}
    raw = path.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    complete = not raw or raw.endswith(b"\n")
    existing = {(r["run_id"], r["line_number"]): r for r in journal.records if r.get("event") == "usage_record"}
    count = 0
    for line_number, line in enumerate(raw.splitlines(), 1):
        if not line.strip():
            continue
        record, error, text = None, None, None
        try:
            text = line.decode("utf-8")
            record = strict_json(text)
        except (ContractError, UnicodeDecodeError):
            error, complete = "unreadable_usage_record", False
        entry = {"event": "usage_record", "run_id": unit["run_id"], "key": unit["key"], "attempt": 1,
                 "line_number": line_number, "source_sha256": source_hash, "raw_line": text,
                 "record": record, "parse_error": error}
        old = existing.get((unit["run_id"], line_number))
        if old is not None:
            if old != entry:
                raise ContractError("usage_changed_after_capture")
        else:
            journal.append(entry)
        count += 1
    return {"usage_capture_complete": complete, "usage_sha256": source_hash, "usage_records": count}


def result_metadata(output):
    try:
        result = read_json(Path(output) / "result.json")
        fields(result, {"status"}, {"schema_version", "host_version", "model_version", "trace_ref", "failure_reason"})
        if result["status"] not in TERMINAL_STATUSES:
            raise ContractError("invalid_runner_status")
        if any(not label(result[k]) for k in ("host_version", "model_version", "trace_ref") if k in result):
            raise ContractError("invalid_runner_metadata")
        return result, None
    except (OSError, ContractError, TypeError):
        return {}, "runner_result_missing_or_invalid"


def dispatch(plan, state, *, run=False, launcher=None):
    frozen = load_frozen(plan)
    schedule, state = frozen["schedule"], Path(state).absolute()
    launcher_binding = None
    if launcher is not None:
        if not callable(launcher) or not callable(getattr(launcher, "validate_frozen", None)):
            raise ContractError("bound_launcher_contract_required")
        launcher_binding = launcher.validate_frozen(frozen, state)
    records = read_ledger(state / "run-ledger.jsonl")
    _, attempts, _ = state_snapshot(frozen, records)
    pending = [u for u in schedule["units"] if u["run_id"] not in attempts]
    if not run:
        return {"mode": "dry-run", "planned_runs": len(schedule["units"]), "already_attempted": len(attempts),
                "pending_runs": len(pending), "ordered_pending_run_ids": [u["run_id"] for u in pending],
                "budgets": schedule["budgets"], "model_requests": 0, "external_processes_started": 0}
    runner = Path(schedule["runner"])
    if runner.is_symlink() or hashlib.sha256(runner.read_bytes()).hexdigest() != schedule["runner_sha256"]:
        raise ContractError("runner_changed_after_freeze")
    # Detect input drift before reserving any attempt. Runner workspaces must be
    # separate from these immutable public bundles.
    for unit in pending:
        public = Path(unit["public"])
        if (public.is_dir() and state.is_relative_to(public.resolve())) or public_digest(public) != unit["public_sha256"]:
            raise ContractError("public_input_changed_or_output_overlaps_input")
    launched = 0
    with state_lock(state, writing=True):
        runs = Journal(state / "run-ledger.jsonl")
        usage = Journal(state / "usage-ledger.jsonl")
        start, attempts, finished = state_snapshot(frozen, runs.records)
        if start is not None and start.get('launcher_binding') != launcher_binding:
            raise ContractError('launcher_binding_changed_within_study')
        if start is None:
            now = time.time()
            start = {"event": "study_started", "plan_sha256": digest(frozen["freeze"]), "started_epoch": now,
                     "deadline_epoch": now + schedule["budgets"]["max_wall_seconds"],
                     "recorded_at": datetime.fromtimestamp(now, timezone.utc).isoformat()}
            if launcher_binding is not None:
                start["launcher_binding"] = launcher_binding
            runs.append(start)
        remaining_at_entry = max(0, start["deadline_epoch"] - time.time())
        monotonic_deadline = time.monotonic() + remaining_at_entry
        for identifier in attempts.keys() - finished.keys():
            unit = next(u for u in schedule["units"] if u["run_id"] == identifier)
            output = state / "runs" / identifier
            captured = collect_usage(output, unit, usage)
            captured["usage_capture_complete"] = False
            terminal = {"event": "run_finished", "run_id": identifier, "key": unit["key"], "attempt": 1,
                         "status": "capture_incomplete", "failure_reason": "controller_interrupted_after_reservation",
                         "returncode": None, "elapsed_seconds": None, "result": {}, **captured,
                         "recorded_at": datetime.now(timezone.utc).isoformat()}
            runs.append(seal_terminal(frozen, attempts[identifier], terminal, output))
        for unit in schedule["units"]:
            if unit["run_id"] in attempts:
                continue
            remaining = min(start["deadline_epoch"] - time.time(), monotonic_deadline - time.monotonic())
            if len(attempts) >= schedule["budgets"]["max_runs"] or remaining <= 0:
                runs.append({"event": "budget_stop", "reason": "run_cap" if remaining > 0 else "wall_clock_cap",
                             "attempted_runs": len(attempts), "recorded_at": datetime.now(timezone.utc).isoformat()})
                break
            if public_digest(unit["public"]) != unit["public_sha256"]:
                raise ContractError("public_input_changed_after_freeze")
            if runner.is_symlink() or hashlib.sha256(runner.read_bytes()).hexdigest() != schedule["runner_sha256"]:
                raise ContractError("runner_changed_after_freeze")
            remaining = min(start["deadline_epoch"] - time.time(), monotonic_deadline - time.monotonic())
            if remaining <= 0:
                runs.append({"event": "budget_stop", "reason": "wall_clock_cap_after_input_check",
                             "attempted_runs": len(attempts), "recorded_at": datetime.now(timezone.utc).isoformat()})
                break
            output = state / "runs" / unit["run_id"]
            output.mkdir(parents=True, exist_ok=False)
            reservation = {"event": "run_started", "run_id": unit["run_id"], "key": unit["key"], "attempt": 1,
                           "execution_id": uuid.uuid4().hex,
                           "public_sha256": unit["public_sha256"], "runner_sha256": schedule["runner_sha256"],
                           "recorded_at": datetime.now(timezone.utc).isoformat()}
            runs.append(reservation)  # Durable before Popen; crash cannot make this unit pending again.
            attempts[unit["run_id"]] = reservation
            timeout = min(remaining, schedule["budgets"]["per_run_seconds"])
            argv = [schedule["runner"], "--public", unit["public"], "--arm", unit["key"]["arm"],
                    "--replicate", str(unit["key"]["replicate"]), "--run-id", unit["run_id"],
                    "--output", str(output), "--timeout-seconds", str(timeout)]
            environment = {k: os.environ[k] for k in schedule["env_allowlist"] if k in os.environ}
            before, returncode, reason, status = time.monotonic(), None, None, None
            with (output / "stdout.log").open("xb") as stdout, (output / "stderr.log").open("xb") as stderr:
                try:
                    launched += 1
                    returncode = (launcher or launch_runner)(argv, cwd=output, env=environment, timeout=timeout,
                                               stdout=stdout, stderr=stderr)
                except subprocess.TimeoutExpired:
                    status = "budget_exhausted" if timeout < schedule["budgets"]["per_run_seconds"] else "host_timeout"
                    reason = "controller_timeout"
                except OSError:
                    status, reason = "host_error", "runner_launch_failed"
                except Exception:
                    if launcher is None:
                        raise
                    status, reason = "capture_incomplete", "bound_launcher_failed"
            elapsed = max(0, time.monotonic() - before)
            if launcher is not None and elapsed > timeout:
                status, reason = "host_timeout", "bound_launcher_deadline_exceeded"
            result, result_error = result_metadata(output)
            if status is None:
                if returncode != 0:
                    status, reason = "host_failed", "runner_nonzero_exit"
                elif result_error:
                    status, reason = "capture_incomplete", result_error
                else:
                    status = result["status"]
            captured = collect_usage(output, unit, usage)
            if status in {"host_timeout", "budget_exhausted", "capture_incomplete"}:
                # A killed worker cannot certify that its earlier seal includes
                # all in-flight/provider work, even when that file parses.
                captured["usage_capture_complete"] = False
            terminal = {"event": "run_finished", "run_id": unit["run_id"], "key": unit["key"], "attempt": 1,
                         "status": status, "failure_reason": reason, "returncode": returncode,
                         "elapsed_seconds": elapsed, "result": result, **captured,
                         "recorded_at": datetime.now(timezone.utc).isoformat()}
            runs.append(seal_terminal(frozen, reservation, terminal, output))
    return {"mode": "run", "planned_runs": len(schedule["units"]), "attempted_runs": len(attempts),
            "external_processes_started": launched if launcher is None else 0,
            "launcher_invocations": launched,
            "launcher_mode": "subprocess" if launcher is None else "bound_in_process",
            "external_process_counter_scope": "runner_wrapper_only",
            "model_requests": None,
            "run_ledger": str(state / "run-ledger.jsonl"), "usage_ledger": str(state / "usage-ledger.jsonl")}


def read_quality(path, units, sealed):
    by_key, planned = {}, {run_key(u["key"]): u for u in units}
    bindings = {run_key(row): row for row in sealed}
    raw = Path(path).read_bytes()
    for line in raw.splitlines():
        if not line.strip():
            continue
        row = strict_json(line)
        key = run_key(row)
        if key in by_key or key not in planned:
            raise ContractError("duplicate_or_unplanned_evaluator_record")
        if ("attempt" in row and (type(row["attempt"]) is not int or row["attempt"] != 1)) or row.get("retry_of") is not None:
            raise ContractError("nonfirst_evaluator_attempt")
        binding = bindings.get(key)
        if binding is None or any(not label(row.get(k)) or row[k] != binding[k]
                                  for k in ("run_id", "freeze_sha256", "sealed_run_sha256")):
            raise ContractError("evaluator_sealed_execution_binding_mismatch")
        by_key[key] = row
    return by_key, hashlib.sha256(raw).hexdigest()


def join_results(plan, state, quality_path, output):
    frozen = load_frozen(plan)
    units, state = frozen["schedule"]["units"], Path(state)
    if Path(output).absolute().is_relative_to((state / "runs").absolute()):
        raise ContractError("join_must_not_modify_sealed_outputs")
    with state_lock(state, writing=False):
        records = read_ledger(state / "run-ledger.jsonl")
        _, attempts, finished = state_snapshot(frozen, records)
        usage_events = read_ledger(state / "usage-ledger.jsonl")
        sealed = sealed_score_rows(frozen, state, attempts, finished)
    quality, quality_hash = read_quality(quality_path, units, sealed)
    usage_by_run, usage_issues = defaultdict(list), defaultdict(list)
    seen_usage = set()
    for event in usage_events:
        identifier = event.get("run_id")
        if (event.get("event") != "usage_record" or identifier not in attempts
                or event.get("key") != attempts[identifier]["key"] or event.get("attempt") != 1):
            raise ContractError("unbound_usage_ledger_record")
        identity = (identifier, event.get("line_number"))
        if identity in seen_usage:
            raise ContractError("duplicate_usage_capture")
        seen_usage.add(identity)
        if event.get("parse_error"):
            usage_issues[identifier].append(event["parse_error"])
        terminal = finished.get(identifier)
        if terminal is None or event.get("source_sha256") != terminal.get("usage_sha256"):
            usage_issues[identifier].append("usage_terminal_digest_mismatch")
        usage_by_run[identifier].append(event.get("record"))
    rows, audit = [], []
    for unit in units:
        identifier, key = unit["run_id"], run_key(unit["key"])
        terminal, evaluation = finished.get(identifier), quality.get(key)
        if terminal and terminal.get("usage_records") != len(usage_by_run[identifier]):
            usage_issues[identifier].append("usage_terminal_count_mismatch")
        execution_status = terminal["status"] if terminal else ("running" if identifier in attempts else "not_dispatched")
        cost = standardized_cost(frozen["measurement"], unit["key"]["arm"], usage_by_run[identifier],
                                 capture_complete=bool(terminal and terminal.get("usage_capture_complete")
                                                       and not usage_issues[identifier]),
                                 terminal_status=execution_status)
        cost["issues"] = sorted(set(cost["issues"] + usage_issues[identifier]))
        quality_issues = []
        if execution_status == "completed":
            if evaluation is not None and type(evaluation.get("decision_success")) is bool:
                status, success = "completed", evaluation["decision_success"]
            else:
                status, success = "evaluator_error", None
                quality_issues.append("missing_or_unreadable_evaluator_outcome")
        else:
            status, success = execution_status, (None if execution_status in {"running", "not_dispatched", "capture_incomplete"} else False)
            if evaluation is not None:
                quality_issues.append("evaluation_not_used_for_noncompleted_execution")
        row = {**unit["key"], "run_id": identifier, "attempt": 1, "retry_of": None, "status": status,
               "decision_success": success, "standardized_cost": cost["standardized_cost"],
               "actual_spend": None, "actual_spend_currency": None,
               "elapsed_seconds": terminal.get("elapsed_seconds") if terminal else None,
               "cost_ledger_ref": "usage-ledger.jsonl#" + identifier,
               "failure_ledger_ref": "run-ledger.jsonl#" + identifier}
        metadata = terminal.get("result", {}) if terminal else {}
        for name in ("host_version", "model_version", "trace_ref"):
            if name in metadata:
                row[name] = metadata[name]
        if evaluation and label(evaluation.get("quality_review_ref")):
            row["quality_review_ref"] = evaluation["quality_review_ref"]
        rows.append(row)
        audit.append({**unit["key"], "run_id": identifier, "execution_status": execution_status,
                      "quality_issues": quality_issues, "cost": cost})
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    with (output / "runs.jsonl").open("x", encoding="utf-8") as target:
        for row in rows:
            target.write(canonical(row) + "\n")
        target.flush()
        os.fsync(target.fileno())
    write_new_json(output / "join-audit.json", {
        "schema_version": 1, "manifest_sha256": digest(frozen["manifest"]),
        "freeze_sha256": digest(frozen["freeze"]), "score_inputs": sealed,
        "measurement_sha256": digest(frozen["measurement"]), "quality_sha256": quality_hash,
        "run_ledger_sha256": digest(records), "usage_ledger_sha256": digest(usage_events),
        "quality_and_cost_parsed_independently": True, "actual_spend_reconciliation_performed": False,
        "runs": audit,
    })
    return {"runs_path": str(output / "runs.jsonl"), "audit_path": str(output / "join-audit.json"),
            "planned_runs": len(units), "complete_cost_runs": sum(a["cost"]["complete"] for a in audit),
            "model_requests": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze", help="Freeze paired public inputs and controller-only sidecars.")
    freeze.add_argument("--spec", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    execute = commands.add_parser("dispatch", help="Dry run by default; --run executes the frozen runner.")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--state", type=Path, required=True)
    execute.add_argument("--run", action="store_true")
    scores = commands.add_parser("score-inputs", help="Export checked sealed-run bindings for the independent evaluator.")
    scores.add_argument("--plan", type=Path, required=True)
    scores.add_argument("--state", type=Path, required=True)
    scores.add_argument("--output", type=Path, required=True)
    join = commands.add_parser("join", help="Join sealed execution, evaluator quality and independently computed costs.")
    join.add_argument("--plan", type=Path, required=True)
    join.add_argument("--state", type=Path, required=True)
    join.add_argument("--quality", type=Path, required=True)
    join.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "freeze":
            result = freeze_study(args.spec, args.output)
        elif args.command == "dispatch":
            result = dispatch(args.plan, args.state, run=args.run)
        elif args.command == "score-inputs":
            result = export_score_inputs(args.plan, args.state, args.output)
        else:
            result = join_results(args.plan, args.state, args.quality, args.output)
    except (ContractError, OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"error": str(error) if isinstance(error, ContractError) else "invalid_input_or_io_failure"}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
