#!/usr/bin/env python3
"""Audit a frozen P1 run plan and score its observed JSONL without model calls.

The manifest contains schema_version=1, study_phase, frozen, and a runs array.
Every planned run has task_id, project_id, arm and an integer replicate >= 1.
Observed rows use the same key plus status, decision_success (boolean for a
completed run), and standardized_cost (nonnegative number or null). Additional
claims, seeds, token telemetry and attempt labels never create observations.

Exactly one record per planned key is accepted. Duplicate records are rejected,
including retries; this entry point does not choose the best attempt. Missing or
invalid outcomes and noncompleted runs score zero in the planned denominator.
Unknown costs remain null. Actual spend is reported separately by currency.
Quality and cost are parsed independently: an invalid cost never changes a
valid completed outcome. Per-run data_issues identify invalid cost fields and
unreadable quality records separately. Unknown statuses or unreadable completed
outcomes block confirmation while retaining a zero in the planned denominator;
predefined method failures such as model_invalid_output are ordinary ITT zeros.

Confirmatory decisions additionally require an explicitly frozen analysis_plan:
primary_contrast="D-B", secondary_contrast="D-C", confidence_level=0.95,
noninferiority_margin=0.03, bootstrap_method="project_then_task_percentile",
task_weighting="equal", replicate_aggregation="mean", seed, bootstrap_samples,
min_tasks and min_projects. Unfrozen/default settings only permit description.
The sample-count guards are configurable operational safeguards, not power or
coverage guarantees. A degenerate empirical bootstrap does not yield certainty.

H2 also requires cost_model.frozen=true, currency, rate_card_id, a nonempty
numeric rates map, cost_scope="full_pipeline_per_scheduled_task", and a nonempty
allocation_rule. This audits supplied totals and rate declarations; it does not
reconstruct a missing usage ledger or independently certify pre-registration.
"""

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import sys

import numpy as np


KEY_FIELDS = ("task_id", "project_id", "arm", "replicate")
PHASES = {"development", "pilot", "confirmatory", "external"}
FAILURE_STATUSES = {
    "failed", "host_error", "host_failed", "host_failure", "host_timeout",
    "provider_error", "model_invalid_output", "budget_exhausted",
    "capture_incomplete", "evaluator_error", "prelude_failed",
    "not_dispatched", "running",
}
MIN_TASKS = 20
MIN_PROJECTS = 8
MIN_BOOTSTRAP_SAMPLES = 1000
NUMERICAL_TOLERANCE = 1e-12


class InputError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def finite_nonnegative(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def strict_json(text):
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ValueError(f"duplicate JSON property: {key}")
            result[key] = value
        return result

    def constant(value):
        raise ValueError(f"nonfinite JSON number: {value}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def run_key(row):
    if not isinstance(row, dict):
        raise ValueError("run must be an object")
    for field in KEY_FIELDS[:-1]:
        value = row.get(field)
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ValueError(f"{field} must be a nonempty, unpadded string")
    if type(row.get("replicate")) is not int or row["replicate"] < 1:
        raise ValueError("replicate must be an integer >= 1")
    return tuple(row[field] for field in KEY_FIELDS)


def validate_manifest(manifest):
    if (not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int
            or manifest["schema_version"] != 1):
        raise InputError("invalid_manifest", "manifest requires schema_version 1")
    if (not isinstance(manifest.get("study_phase"), str) or manifest["study_phase"] not in PHASES
            or type(manifest.get("frozen")) is not bool):
        raise InputError("invalid_manifest", "study_phase and boolean frozen are required")
    if not isinstance(manifest.get("runs"), list):
        raise InputError("invalid_manifest", "manifest.runs must be an array")
    planned = {}
    projects = {}
    for row in manifest["runs"]:
        try:
            key = run_key(row)
        except ValueError as error:
            raise InputError("invalid_manifest", str(error)) from error
        if key in planned:
            raise InputError("duplicate_plan", f"duplicate planned key: {key}")
        task, project, _, _ = key
        if task in projects and projects[task] != project:
            raise InputError("inconsistent_project", f"task {task} belongs to multiple projects")
        projects[task] = project
        planned[key] = {field: row[field] for field in KEY_FIELDS}
    return planned


def read_observations(path):
    records, issues = [], []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = strict_json(line)
            run_key(row)
        except ValueError as error:
            issues.append({"line": line_number, "code": "unassignable_record", "message": str(error)})
            continue
        records.append(row)
    return records, issues


def normalize_run(planned, observed):
    if observed is None:
        return {**planned, "status": "missing", "observed_status": None,
                "decision_success": 0, "standardized_cost": None,
                "actual_spend": None, "actual_spend_currency": None, "data_issues": []}
    status = observed.get("status")
    cost = observed.get("standardized_cost")
    issues = []
    known_status = isinstance(status, str) and status in FAILURE_STATUSES | {"completed"}
    if not known_status:
        issues.append({"field": "status", "code": "unknown_status",
                       "blocks_quality_confirmation": True})
    elif status == "completed" and type(observed.get("decision_success")) is not bool:
        issues.append({"field": "decision_success", "code": "unreadable_quality_outcome",
                       "blocks_quality_confirmation": True})
    quality_unreadable = bool(issues)
    if cost is not None and not finite_nonnegative(cost):
        issues.append({"field": "standardized_cost", "code": "invalid_standardized_cost",
                       "blocks_quality_confirmation": False})
    actual = observed.get("actual_spend")
    currency = observed.get("actual_spend_currency")
    valid_actual = finite_nonnegative(actual) and isinstance(currency, str) and bool(currency.strip())
    return {
        **planned, "status": "malformed" if quality_unreadable else status,
        "observed_status": status,
        "decision_success": int(not quality_unreadable and status == "completed"
                                and observed["decision_success"] is True),
        "standardized_cost": cost if finite_nonnegative(cost) else None,
        "actual_spend": actual if valid_actual else None,
        "actual_spend_currency": currency if valid_actual else None,
        "data_issues": issues,
    }


def task_means(joined):
    groups = defaultdict(lambda: defaultdict(list))
    for row in joined:
        groups[(row["task_id"], row["project_id"])][row["arm"]].append(row)
    tasks = []
    for (task, project), arms in sorted(groups.items()):
        summarized = {}
        for arm, rows in sorted(arms.items()):
            costs = [row["standardized_cost"] for row in rows]
            summarized[arm] = {
                "planned_replicates": len(rows),
                "decision_success_mean": sum(row["decision_success"] for row in rows) / len(rows),
                "standardized_cost_mean": (sum(costs) / len(costs)
                                           if all(cost is not None for cost in costs) else None),
                "missing_cost_runs": sum(cost is None for cost in costs),
            }
        tasks.append({"task_id": task, "project_id": project, "arms": summarized})
    return tasks


def analysis_settings(manifest, seed, bootstrap_samples):
    declared = manifest.get("analysis_plan")
    declared = declared if isinstance(declared, dict) else {}
    settings = {
        "seed": seed if seed is not None else declared.get("seed", 20261127),
        "bootstrap_samples": (bootstrap_samples if bootstrap_samples is not None
                              else declared.get("bootstrap_samples", 5000)),
        "min_tasks": declared.get("min_tasks", MIN_TASKS),
        "min_projects": declared.get("min_projects", MIN_PROJECTS),
        "bootstrap_method": "project_then_task_percentile", "confidence_level": 0.95,
        "task_weighting": "equal", "replicate_aggregation": "mean",
        "min_bootstrap_samples": MIN_BOOTSTRAP_SAMPLES, "numpy_version": np.__version__,
        "guard_not_power_analysis": True,
        "small_sample_note": "Count guards are not a power or coverage guarantee; task_ci is sensitivity-only.",
    }
    minima = {"seed": 0, "bootstrap_samples": 1, "min_tasks": 2, "min_projects": 2}
    if any(type(settings[key]) is not int or settings[key] < minimum for key, minimum in minima.items()):
        raise InputError("invalid_analysis_config", "invalid seed, resample count, or sample-count guard")
    return settings


def paired_interval(values, projects, *, settings):
    """Equal-task mean; project resampling, then tasks within each sampled project.

    Each selected project contributes its original number of tasks, sampled with
    replacement. The pooled resample is averaged by task, not by project. The
    task-only interval deliberately ignores clustering and is sensitivity-only.
    Count thresholds are conservative computation guards, not a power analysis.
    Empirically degenerate bootstrap samples cannot establish certainty.
    """
    array = np.asarray(values, dtype=float)
    summary = {"estimate": float(np.mean(array)) if len(array) else None,
               "hierarchical_ci": None, "task_ci": None, "status": "insufficient_tasks"}
    seed, bootstrap_samples = settings["seed"], settings["bootstrap_samples"]
    if len(array) < settings["min_tasks"]:
        return summary
    if bootstrap_samples < MIN_BOOTSTRAP_SAMPLES:
        summary["status"] = "insufficient_resamples"
        return summary
    if np.ptp(array) == 0:
        summary["status"] = "degenerate_bootstrap"
        return summary

    def interval(draws):
        lower, upper = np.quantile(draws, [0.025, 0.975], method="linear")
        return {"lower": float(lower), "upper": float(upper), "confidence_level": 0.95}

    task_rng = np.random.default_rng(np.random.SeedSequence([seed, 1]))
    task_draws = np.empty(bootstrap_samples)
    # Avoid allocating a bootstrap_samples x tasks matrix for a large manifest.
    for index in range(bootstrap_samples):
        task_draws[index] = np.mean(array[task_rng.integers(len(array), size=len(array))])
    summary["task_ci"] = interval(task_draws)
    names = sorted(set(projects))
    if len(names) < settings["min_projects"]:
        summary["status"] = "insufficient_projects"
        return summary
    groups = [array[np.asarray([name == project for project in projects])] for name in names]
    rng = np.random.default_rng(np.random.SeedSequence([seed, 0]))
    draws = np.empty(bootstrap_samples)
    for index in range(bootstrap_samples):
        selected = rng.integers(len(groups), size=len(groups))
        sampled = [group[rng.integers(len(group), size=len(group))] for group in
                   (groups[group_index] for group_index in selected)]
        draws[index] = np.mean(np.concatenate(sampled))
    if np.ptp(draws) == 0:
        summary["status"] = "degenerate_bootstrap"
        return summary
    summary.update(status="ok", hierarchical_ci=interval(draws))
    return summary


def contrast(tasks, left, right, *, settings):
    candidates = [row for row in tasks if left in row["arms"] or right in row["arms"]]
    unpaired = [row["task_id"] for row in candidates
                if left not in row["arms"] or right not in row["arms"]]
    paired = [row for row in candidates if row["task_id"] not in unpaired]
    result = {"n_tasks": len(paired), "n_projects": len({row["project_id"] for row in paired}),
              "unpaired_tasks": unpaired}
    for output, field in (("quality", "decision_success_mean"), ("cost", "standardized_cost_mean")):
        values = [(row["arms"][left][field], row["arms"][right][field]) for row in paired]
        missing = any(a is None or b is None for a, b in values)
        if missing or unpaired:
            result[output] = {"estimate": None, "hierarchical_ci": None, "task_ci": None,
                              "status": "unpaired_design" if unpaired else "missing_cost"}
        else:
            result[output] = paired_interval(
                [a - b for a, b in values], [row["project_id"] for row in paired],
                settings=settings)
    return result


def hypothesis_decisions(manifest, comparisons, *, cost_complete, integrity_ok, settings):
    """Frozen hierarchical H1/H2 rule; descriptive phases can never satisfy it."""
    declared = manifest.get("analysis_plan")
    declared = declared if isinstance(declared, dict) else {}
    reasons = []
    if manifest.get("study_phase") != "confirmatory":
        reasons.append("nonconfirmatory_phase")
    if manifest.get("frozen") is not True or declared.get("frozen") is not True:
        reasons.append("analysis_plan_not_explicitly_frozen")
    expected = {"primary_contrast": "D-B", "secondary_contrast": "D-C",
                "confidence_level": 0.95, "noninferiority_margin": 0.03,
                "bootstrap_method": "project_then_task_percentile",
                "task_weighting": "equal", "replicate_aggregation": "mean"}
    for key, value in expected.items():
        if declared.get(key) != value:
            reasons.append(f"analysis_plan_mismatch:{key}")
    for key in ("seed", "bootstrap_samples", "min_tasks", "min_projects"):
        if type(declared.get(key)) is not int or declared[key] != settings[key]:
            reasons.append(f"analysis_setting_not_frozen_or_overridden:{key}")
    if not integrity_ok:
        reasons.append("unresolved_input_or_collection_issue")
    eligible = not reasons

    def valid_ci(metric):
        ci = metric.get("hierarchical_ci")
        return (metric.get("status") == "ok" and isinstance(ci, dict)
                and ci.get("confidence_level") == 0.95
                and all(type(ci.get(key)) in (int, float) and math.isfinite(ci[key])
                        for key in ("lower", "upper")) and ci["lower"] <= ci["upper"])

    primary = comparisons["D-B"]["quality"]
    quality = comparisons["D-C"]["quality"]
    cost = comparisons["D-C"]["cost"]
    h1_bound = valid_ci(primary) and primary["hierarchical_ci"]["lower"] > NUMERICAL_TOLERANCE
    h1 = bool(eligible and h1_bound)
    quality_bound = (valid_ci(quality)
                     and quality["hierarchical_ci"]["lower"] > -0.03 + NUMERICAL_TOLERANCE)
    cost_bound = valid_ci(cost) and cost["hierarchical_ci"]["upper"] < -NUMERICAL_TOLERANCE
    model = manifest.get("cost_model")
    model = model if isinstance(model, dict) else {}
    rates = model.get("rates")
    metadata_ready = (
        model.get("frozen") is True
        and all(isinstance(model.get(key), str) and bool(model[key].strip())
                for key in ("currency", "rate_card_id", "allocation_rule"))
        and model.get("cost_scope") == "full_pipeline_per_scheduled_task"
        and isinstance(rates, dict) and bool(rates)
        and all(isinstance(key, str) and bool(key.strip()) and finite_nonnegative(value)
                for key, value in rates.items())
    )
    h2 = bool(h1 and quality_bound and metadata_ready and cost_complete and cost_bound)
    return {
        "mode": "confirmatory" if eligible else "descriptive",
        "protocol_eligible": eligible,
        "inferential_ready": bool(eligible and valid_ci(primary)),
        "blocking_reasons": reasons,
        "numerical_tolerance": NUMERICAL_TOLERANCE,
        "cost_validation_scope": "supplied_totals_and_declared_rate_card; usage_not_recomputed",
        "H1": {"supported": h1, "positive_quality_bound": bool(h1_bound)},
        "H2": {"supported": h2, "h1_supported": h1,
               "quality_lower_bound_satisfied": bool(quality_bound),
               "cost_upper_bound_satisfied": bool(cost_bound),
               "frozen_full_cost_model_available": bool(metadata_ready),
               "all_costs_observed": bool(cost_complete), "noninferiority_margin": 0.03},
    }


def analyze(manifest, records, *, input_issues=(), seed=None, bootstrap_samples=None):
    planned = validate_manifest(manifest)
    settings = analysis_settings(manifest, seed, bootstrap_samples)
    observed = {}
    for row in records:
        try:
            key = run_key(row)
        except ValueError as error:
            raise InputError("invalid_run", str(error)) from error
        if key in observed:
            raise InputError("duplicate_run", f"duplicate run key; attempts are not selected: {key}")
        if key not in planned:
            raise InputError("unplanned_run", f"run absent from the frozen plan: {key}")
        if ("attempt" in row and (type(row["attempt"]) is not int or row["attempt"] != 1)) or row.get("retry_of") is not None:
            raise InputError("unsupported_attempt", "only first-attempt records are accepted; retries require a separately frozen analysis")
        observed[key] = row
    joined = [normalize_run(row, observed.get(key)) for key, row in sorted(planned.items())]
    tasks = task_means(joined)
    actual = defaultdict(lambda: {"observed_total": 0.0, "observed_runs": 0})
    for row in joined:
        if row["actual_spend"] is not None:
            group = actual[row["actual_spend_currency"]]
            group["observed_total"] += row["actual_spend"]
            group["observed_runs"] += 1
    statuses = Counter(row["status"] for row in joined)
    data_issues = [{**{key: row[key] for key in KEY_FIELDS}, **issue}
                   for row in joined for issue in row["data_issues"]]
    comparisons = {label: contrast(tasks, "D", right, settings=settings)
                   for label, right in (("D-B", "B"), ("D-C", "C"))}
    cost_rows = [row for row in joined if row["arm"] in {"C", "D"}]
    cost_complete = bool(cost_rows) and all(row["standardized_cost"] is not None for row in cost_rows)
    # Outcomes remain zero in the ITT table even when the study is not ready for
    # confirmation. Administrative noncollection cannot establish efficacy.
    integrity_ok = (
        not input_issues
        and not any(issue["blocks_quality_confirmation"] for issue in data_issues)
        and not any(row["status"] in {
            "missing", "running", "not_dispatched", "evaluator_error", "capture_incomplete"
        } for row in joined)
    )
    return {
        "schema_version": 1, "study_phase": manifest["study_phase"],
        "counts": {"planned_runs": len(planned), "received_runs": len(records),
                   "tasks": len(tasks), "projects": len({row["project_id"] for row in tasks}),
                   "missing_runs": statuses["missing"], "malformed_runs": statuses["malformed"],
                   "invalid_cost_runs": sum(issue["field"] == "standardized_cost" for issue in data_issues),
                   "successful_runs": sum(row["decision_success"] for row in joined),
                   "statuses": dict(sorted(statuses.items()))},
        "runs": joined, "tasks": tasks, "input_issues": list(input_issues), "data_issues": data_issues,
        "analysis": settings,
        "comparisons": comparisons,
        "actual_spend": {"by_currency": dict(sorted(actual.items())),
                         "missing_runs": sum(row["actual_spend"] is None for row in joined)},
        "hypotheses": hypothesis_decisions(manifest, comparisons, cost_complete=cost_complete,
                                           integrity_ok=integrity_ok, settings=settings),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--seed", type=int, help="override frozen seed (makes a differing analysis descriptive)")
    parser.add_argument("--bootstrap-samples", type=int, help="override frozen resampling count")
    args = parser.parse_args(argv)
    try:
        manifest = strict_json(args.manifest.read_text(encoding="utf-8"))
        records, issues = read_observations(args.runs)
        result = analyze(manifest, records, input_issues=issues,
                         seed=args.seed, bootstrap_samples=args.bootstrap_samples)
    except (InputError, OSError, ValueError) as error:
        print(json.dumps({"error": {"code": getattr(error, "code", "input_error"),
                                    "message": str(error)}}, ensure_ascii=False, allow_nan=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
