#!/usr/bin/env python3
"""Recompute P1 tables from the scheduled denominator, without service calls.

Costs are supplied by experiment.py join; this tool never reconstructs missing
meters or substitutes zero. The preserved analysis.json contains the existing
ITT audit. Empirical table cells remain null until their scheduled quality
observations are complete, so an unrun plan is never presented as a measured
zero-success experiment. A data-kind declaration is not a provenance certificate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile

import numpy as np

import analyze as analysis
import experiment as experiment


ContractError = experiment.ContractError
UNMEASURED_STATUSES = {"missing", "running", "not_dispatched", "evaluator_error", "capture_incomplete", "malformed"}
DATA_KINDS = {"research", "fixture", "unverified"}
COMPONENTS = ("behavior_success", "incorrect_high_impact_affirmative", "unnecessary_abstention")


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_analysis(manifest_path, runs_path):
    manifest = experiment.read_json(manifest_path)
    path = Path(runs_path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise ContractError("unsafe_or_oversized_runs")
    records, issues = analysis.read_observations(path)
    result = analysis.analyze(manifest, records, input_issues=issues)
    return manifest, records, result


def measurement_status(rows):
    measured = sum(row["status"] not in UNMEASURED_STATUSES for row in rows)
    return "unmeasured" if not measured else "measured" if measured == len(rows) else "incomplete"


def component_records(score_dir, manifest, records, data_kind):
    if score_dir is None:
        return {}, None
    root = Path(score_dir)
    if root.is_symlink():
        raise ContractError("unsafe_score_directory")
    audit = experiment.read_json(root / "score-audit.json")
    source = root / "quality-components.jsonl"
    if (source.is_symlink() or audit.get("manifest_sha256") != experiment.digest(manifest)
            or audit.get("data_kind") != data_kind
            or audit.get("quality_components_sha256") != file_hash(source)):
        raise ContractError("score_artifact_binding_mismatch")
    observed = {analysis.run_key(row): row for row in records}
    mapped = {}
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = experiment.strict_json(line)
        key = analysis.run_key(row)
        actual = observed.get(key)
        if (key in mapped or actual is None or row.get("data_kind") != data_kind
                or not experiment.label(row.get("run_id")) or row["run_id"] != actual.get("run_id")
                or row.get("decision_success") != actual.get("decision_success")):
            raise ContractError("score_run_binding_mismatch")
        if any(row.get(name) is not None and type(row[name]) is not bool for name in COMPONENTS):
            raise ContractError("invalid_quality_component")
        mapped[key] = row
    return mapped, {"audit_sha256": file_hash(root / "score-audit.json"),
                    "quality_components_sha256": file_hash(source),
                    "semantic_correctness_independently_verified": False}


def summarize(manifest, records, result, *, data_kind="unverified", components=None):
    if data_kind not in DATA_KINDS:
        raise ContractError("invalid_data_kind")
    components = components or {}
    raw = {analysis.run_key(row): row for row in records}
    arms, status = [], measurement_status(result["runs"])
    for arm in sorted({row["arm"] for row in result["runs"]}):
        rows = [row for row in result["runs"] if row["arm"] == arm]
        tasks = [task["arms"][arm] for task in result["tasks"] if arm in task["arms"]]
        complete = measurement_status(rows) == "measured"
        durations, duration_issues = [], 0
        for row in rows:
            value = raw.get(analysis.run_key(row), {}).get("elapsed_seconds")
            if row["status"] not in {"missing", "running", "not_dispatched"} and analysis.finite_nonnegative(value):
                durations.append(value)
            elif value is not None:
                duration_issues += 1
        quality_components = {}
        for field in COMPONENTS:
            values = [components.get(analysis.run_key(row), {}).get(field) for row in rows]
            observed = [value for value in values if type(value) is bool]
            quality_components[field] = {"observed_runs": len(observed), "planned_runs": len(rows),
                "missing_runs": len(rows) - len(observed),
                "observed_rate": sum(observed) / len(observed) if observed else None,
                "scope": "observed_run_components_only_not_a_task_effect"}
        costs = [task["standardized_cost_mean"] for task in tasks]
        arms.append({"arm": arm, "planned_tasks": len(tasks),
            "planned_projects": len({row["project_id"] for row in rows}), "planned_runs": len(rows),
            "received_runs": sum(analysis.run_key(row) in raw for row in rows),
            "measured_quality_runs": sum(row["status"] not in UNMEASURED_STATUSES for row in rows),
            "measurement_status": measurement_status(rows),
            "statuses": dict(sorted(Counter(row["status"] for row in rows).items())),
            "decision_success_task_mean": (sum(task["decision_success_mean"] for task in tasks) / len(tasks)
                                            if complete and not result["input_issues"] else None),
            "itt_policy_task_mean": sum(task["decision_success_mean"] for task in tasks) / len(tasks),
            "standardized_cost_task_mean": (sum(costs) / len(costs)
                                            if costs and all(value is not None for value in costs) else None),
            "missing_cost_runs": sum(row["standardized_cost"] is None for row in rows),
            "latency": {"observed_runs": len(durations), "missing_runs": len(rows) - len(durations),
                "invalid_or_inapplicable_values": duration_issues,
                "p50_seconds": float(np.quantile(durations, 0.5, method="linear")) if durations else None,
                "p95_seconds": float(np.quantile(durations, 0.95, method="linear")) if durations else None,
                "timeout_or_budget_stop_runs": sum(row["status"] in {"host_timeout", "budget_exhausted"} for row in rows),
                "scope": "observed_attempt_duration_including_timeouts_not_successful_completion_latency"},
            "components": quality_components})
    comparisons = copy.deepcopy(result["comparisons"])
    for name, comparison in comparisons.items():
        relevant = [row for row in result["runs"] if row["arm"] in name.split("-")]
        if measurement_status(relevant) != "measured" or result["input_issues"]:
            for metric in ("quality", "cost"):
                comparison[metric].update(estimate=None, hierarchical_ci=None, task_ci=None,
                                          status="unmeasured_or_incomplete_collection")
    counts = {**result["counts"], "measured_quality_runs": sum(
        row["status"] not in UNMEASURED_STATUSES for row in result["runs"])}
    return {"schema_version": 1, "data_kind": data_kind, "study_phase": manifest["study_phase"],
        "measurement_status": status, "counts": counts, "arms": arms, "comparisons": comparisons,
        "scientific_effect_claims_allowed": False,
        "statistical_gate_results": result["hypotheses"] if data_kind == "research" else None,
        "human_provenance_or_task_acceptance_verified": False,
        "mechanism_metrics": {"status": "not_measured_by_this_contract", "values": None},
        "limitations": [
            "No execution, human identity, label semantics, task acceptance or preregistration is certified by this report.",
            "Incomplete scheduled quality observations suppress empirical table cells; analysis.json retains the complete ITT audit.",
            "Costs are the independently supplied experiment.py join totals; this tool does not invent missing meters or rates.",
            "Latency is the observed duration of attempts, including timeouts, with explicit missing counts.",
            "Behavior and assertion components require a bound score artifact; absent components remain unmeasured.",
            "Fixture and unverified inputs cannot create scientific-effect claims or pilot sample-size evidence."]}


def format_number(value):
    return "NOT MEASURED" if value is None else f"{value:.6g}"


def markdown(summary):
    heading = "FIXTURE ONLY — NOT STUDY RESULTS" if summary["data_kind"] == "fixture" else "P1 descriptive reporting artifact"
    lines = ["# " + heading, "", f"Data kind: **{summary['data_kind']}**. Phase: **{summary['study_phase']}**. "
             f"Measurement state: **{summary['measurement_status']}**.", "",
             "The complete planned denominator is retained. NOT MEASURED is not an observed zero. "
             "This artifact does not certify research readiness or authorize any scientific claim.", "",
             "| Arm | Planned tasks | Planned / received runs | Measured quality runs | Task success | Full standardized cost | Attempt p95 (s) |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for row in summary["arms"]:
        arm = row["arm"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {arm} | {row['planned_tasks']} | {row['planned_runs']} / {row['received_runs']} | "
                     f"{row['measured_quality_runs']} | {format_number(row['decision_success_task_mean'])} | "
                     f"{format_number(row['standardized_cost_task_mean'])} | {format_number(row['latency']['p95_seconds'])} |")
    lines.extend(["", "## Prespecified comparisons", "", "| Contrast | Endpoint | Estimate | Hierarchical 95% interval | Status |",
                  "|---|---|---:|---|---|"])
    for name, comparison in summary["comparisons"].items():
        for endpoint in ("quality", "cost"):
            metric = comparison[endpoint]
            ci = metric["hierarchical_ci"]
            interval = "NOT MEASURED / NOT INFERABLE" if ci is None else f"[{ci['lower']:.6g}, {ci['upper']:.6g}]"
            lines.append(f"| {name} | {endpoint} | {format_number(metric['estimate'])} | {interval} | {metric['status']} |")
    lines.extend(["", "## Interpretation and missing observations", ""])
    lines.extend("- " + item for item in summary["limitations"])
    return "\n".join(lines) + "\n"


def csv_arms(summary):
    output = io.StringIO(newline="")
    fields = ["arm", "planned_tasks", "planned_projects", "planned_runs", "received_runs", "measured_quality_runs",
              "measurement_status", "decision_success_task_mean", "standardized_cost_task_mean", "missing_cost_runs"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(summary["arms"])
    return output.getvalue()


def provenance(inputs, scripts):
    return {"schema_version": 1, "inputs": {name: {"filename": Path(path).name, "sha256": file_hash(path)}
            for name, path in inputs.items()}, "implementation": {Path(path).name: file_hash(path) for path in scripts},
            "python_version": sys.version.split()[0], "numpy_version": np.__version__,
            "model_requests": 0, "cost_recomputed_here": False}


def write_bundle(output, contents, *, protect=()):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ContractError("output_already_exists")
    destination = output.resolve()
    for source in protect:
        source = Path(source).resolve()
        if destination == source or (source.is_dir() and destination.is_relative_to(source)):
            raise ContractError("output_overlaps_protected_input")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".p1-report-", dir=output.parent))
    try:
        for name, value in contents.items():
            if Path(name).name != name:
                raise ContractError("invalid_artifact_filename")
            if isinstance(value, str):
                (staging / name).write_text(value, encoding="utf-8")
            else:
                experiment.write_new_json(staging / name, value)
        staging.rename(output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def create_report(manifest_path, runs_path, output, *, data_kind="unverified", score_dir=None):
    manifest, records, result = load_analysis(manifest_path, runs_path)
    components, score_binding = component_records(score_dir, manifest, records, data_kind)
    summary = summarize(manifest, records, result, data_kind=data_kind, components=components)
    summary["score_artifact"] = score_binding
    inputs = {"manifest": manifest_path, "runs": runs_path}
    if score_dir:
        inputs.update(score_audit=Path(score_dir) / "score-audit.json",
                      quality_components=Path(score_dir) / "quality-components.jsonl")
    sources = [Path(__file__), Path(analysis.__file__), Path(experiment.__file__)]
    write_bundle(output, {"summary.json": summary, "analysis.json": result, "report.md": markdown(summary),
                          "arms.csv": csv_arms(summary), "provenance.json": provenance(inputs, sources)},
                 protect=[manifest_path, runs_path, *([score_dir] if score_dir else [])])
    return {"output": str(output), "measurement_status": summary["measurement_status"], "data_kind": data_kind,
            "planned_runs": summary["counts"]["planned_runs"], "model_requests": 0, "scientific_effect_claims_allowed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-kind", choices=sorted(DATA_KINDS), default="unverified")
    parser.add_argument("--score-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        result = create_report(args.manifest, args.runs, args.output, data_kind=args.data_kind, score_dir=args.score_dir)
        print(experiment.canonical(result))
        return 0
    except (analysis.InputError, ContractError, OSError, ValueError, KeyError, TypeError) as error:
        code = getattr(error, "code", str(error) if isinstance(error, ContractError) else type(error).__name__)
        print(experiment.canonical({"error": {"code": code}, "model_requests": 0}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
