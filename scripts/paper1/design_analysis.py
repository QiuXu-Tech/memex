#!/usr/bin/env python3
"""Describe pilot feasibility and explicit resource scenarios without choosing N.

Existing analyze.py supplies the denominator and task means. No incomplete pair
is silently converted to an observed pilot difference. Resource scenarios are
deterministic arithmetic on separately declared assumptions, not standardized
cost measurements, power simulations or sample-size recommendations. This tool
does not fit or simulate a joint quality/cost model in the absence of defensible
pilot data and a frozen generative model.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import math
from pathlib import Path
import re

import numpy as np

import analyze as analysis
import experiment
import report


ContractError = experiment.ContractError


def paired_diagnostics(result, left, right):
    tasks = [row for row in result["tasks"] if left in row["arms"] or right in row["arms"]]
    grouped = defaultdict(list)
    for row in result["runs"]:
        if row["arm"] in {left, right}:
            grouped[(row["task_id"], row["project_id"])].append(row)
    complete, missing, unpaired = [], [], []
    for task in tasks:
        key = (task["task_id"], task["project_id"])
        if left not in task["arms"] or right not in task["arms"]:
            unpaired.append(task["task_id"])
        elif report.measurement_status(grouped[key]) != "measured":
            missing.append(task["task_id"])
        else:
            complete.append(task)
    ready = bool(tasks) and not unpaired and not missing and not result["input_issues"]
    output = {"planned_tasks": len(tasks), "planned_projects": len({row["project_id"] for row in tasks}),
              "complete_tasks": len(complete), "unpaired_tasks": unpaired, "incomplete_tasks": missing,
              "paired_task_mean": None, "paired_task_variance": None, "project_mean_variance": None,
              "task_discordance": None, "paired_replicate_discordance": None,
              "quality_cost_sample_covariance": None, "paired_cost_tasks": 0,
              "status": "unpaired_design" if unpaired else "complete" if ready else "incomplete_pairs" if complete else "unmeasured",
              "scope": "descriptive_planned_task_statistics_not_a_power_model"}
    if not ready:
        return output
    differences = [row["arms"][left]["decision_success_mean"] - row["arms"][right]["decision_success_mean"] for row in tasks]
    project_values = defaultdict(list)
    for row, value in zip(tasks, differences):
        project_values[row["project_id"]].append(value)
    project_means = [float(np.mean(values)) for values in project_values.values()]
    output.update(paired_task_mean=float(np.mean(differences)),
                  paired_task_variance=float(np.var(differences, ddof=1)) if len(differences) > 1 else None,
                  project_mean_variance=float(np.var(project_means, ddof=1)) if len(project_means) > 1 else None,
                  task_discordance={"left_better": sum(value > 0 for value in differences),
                                    "equal": sum(value == 0 for value in differences),
                                    "right_better": sum(value < 0 for value in differences)})
    paired_replicates = defaultdict(dict)
    for row in result["runs"]:
        if row["arm"] in {left, right}:
            paired_replicates[(row["task_id"], row["project_id"], row["replicate"])][row["arm"]] = row["decision_success"]
    pairs = [value for value in paired_replicates.values() if set(value) == {left, right}]
    output["paired_replicate_discordance"] = {"paired_replicates": len(pairs),
        "unpaired_replicate_slots": len(paired_replicates) - len(pairs),
        "left_only_success": sum(pair[left] == 1 and pair[right] == 0 for pair in pairs),
        "right_only_success": sum(pair[left] == 0 and pair[right] == 1 for pair in pairs),
        "both_success": sum(pair[left] == pair[right] == 1 for pair in pairs),
        "both_failure": sum(pair[left] == pair[right] == 0 for pair in pairs),
        "independent_sample_size": len(tasks)}
    costs = [(row["arms"][left]["standardized_cost_mean"], row["arms"][right]["standardized_cost_mean"]) for row in tasks]
    output["paired_cost_tasks"] = sum(a is not None and b is not None for a, b in costs)
    if output["paired_cost_tasks"] == len(tasks) and len(tasks) > 1:
        output["quality_cost_sample_covariance"] = float(np.cov(differences, [a - b for a, b in costs], ddof=1)[0, 1])
    return output


def resource_scenarios(spec):
    if spec is None:
        return []
    experiment.fields(spec, {"schema_version", "kind", "scenarios"})
    if type(spec["schema_version"]) is not int or spec["schema_version"] != 1 or spec["kind"] != "assumption_only":
        raise ContractError("assumption_only_scenarios_required")
    if not isinstance(spec["scenarios"], list):
        raise ContractError("invalid_resource_scenario")
    rows, names = [], set()
    for scenario in spec["scenarios"]:
        experiment.fields(scenario, {"name", "n_tasks", "n_projects", "replicates", "arms", "shared_prelude",
            "assumed_cost_per_continuation", "assumed_cost_per_prelude", "currency", "assumption_source"})
        if (not experiment.label(scenario["name"]) or scenario["name"] in names
                or any(type(scenario[key]) is not int or scenario[key] < 1 for key in ("n_tasks", "n_projects", "replicates"))
                or scenario["n_projects"] > scenario["n_tasks"] or type(scenario["shared_prelude"]) is not bool
                or not isinstance(scenario["arms"], list) or not scenario["arms"]
                or any(not experiment.label(arm) for arm in scenario["arms"])
                or len(set(scenario["arms"])) != len(scenario["arms"])
                or not experiment.label(scenario["assumption_source"])
                or not isinstance(scenario["currency"], str) or not re.fullmatch(r"[A-Z]{3}", scenario["currency"])
                or any(scenario[key] is not None and not analysis.finite_nonnegative(scenario[key])
                       for key in ("assumed_cost_per_continuation", "assumed_cost_per_prelude"))):
            raise ContractError("invalid_resource_scenario")
        names.add(scenario["name"])
        continuations = scenario["n_tasks"] * scenario["replicates"] * len(scenario["arms"])
        preludes = scenario["n_tasks"] * scenario["replicates"] if scenario["shared_prelude"] else continuations
        first, second = scenario["assumed_cost_per_continuation"], scenario["assumed_cost_per_prelude"]
        total = None if first is None or second is None else continuations * first + preludes * second
        if total is not None and not analysis.finite_nonnegative(total):
            raise ContractError("unrepresentable_resource_total")
        rows.append({**scenario, "kind": "assumption_only", "continuations": continuations, "preludes": preludes,
                     "total_executions": continuations + preludes, "assumed_total_cost": total, "power": None,
                     "counts_increase_independent_n": False, "observed_standardized_cost": None})
    return rows


def design_analysis(manifest_path, runs_path, output, *, data_kind="unverified", scenarios_path=None):
    manifest, records, analyzed = report.load_analysis(manifest_path, runs_path)
    summary = report.summarize(manifest, records, analyzed, data_kind=data_kind)
    scenarios = resource_scenarios(experiment.read_json(scenarios_path) if scenarios_path else None)
    paired = {name: paired_diagnostics(analyzed, "D", right) for name, right in (("D-B", "B"), ("D-C", "C"))}
    complete = summary["measurement_status"] == "measured" and not analyzed["input_issues"]
    result = {"schema_version": 1, "data_kind": data_kind, "study_phase": manifest["study_phase"],
              "measurement_status": summary["measurement_status"], "counts": summary["counts"],
              "real_pilot_estimates_available": bool(data_kind == "research" and manifest["study_phase"] == "pilot" and complete),
              "research_provenance_independently_verified": False,
              "paired_diagnostics": paired, "resource_distributions": summary["arms"], "resource_scenarios": scenarios,
              "formal_sample_size": None, "sample_size_recommendation_made": False,
              "power_simulation_performed": False, "simulation_seed": None, "monte_carlo_standard_error": None,
              "existing_interval_settings": analyzed["analysis"],
              "limitations": [
                  "Only a complete declared research pilot can supply descriptive pilot estimates; declarations do not authenticate its provenance.",
                  "Missing planned pairs suppress variance and discordance estimates; no favorable complete-case subset is substituted.",
                  "Project-mean variance is descriptive and unweighted; it is not an ICC estimate or a cluster-coverage guarantee.",
                  "Resource grids contain explicit assumptions. Their costs are not observed C_std or provider charges.",
                  "No power simulation, effect-size selection, noninferiority-margin justification, or automatic formal N is performed.",
                  "A defensible joint quality/cost generative model, clustering assumptions, MC precision target, and independent statistical review remain required before confirmatory design."]}
    inputs = {"manifest": manifest_path, "runs": runs_path}
    if scenarios_path:
        inputs["scenarios"] = scenarios_path
    result["provenance"] = report.provenance(inputs, [Path(__file__), Path(report.__file__), Path(analysis.__file__), Path(experiment.__file__)])
    title = "FIXTURE ONLY — NOT PILOT EVIDENCE" if data_kind == "fixture" else "P1 pilot design preparation"
    lines = ["# " + title, "", f"Phase: **{manifest['study_phase']}**. Measurement state: **{summary['measurement_status']}**.", "",
             "**Formal sample size: NOT SELECTED. No power simulation was run.**", "",
             "| Contrast | Planned / complete tasks | Paired mean | Paired task variance | Status |",
             "|---|---:|---:|---:|---|"]
    for name, row in paired.items():
        lines.append(f"| {name} | {row['planned_tasks']} / {row['complete_tasks']} | {report.format_number(row['paired_task_mean'])} | "
                     f"{report.format_number(row['paired_task_variance'])} | {row['status']} |")
    lines.extend(["", "## Resource assumptions", "", "These figures are scenario arithmetic, not measured costs or adequate-power designs.", "",
                  "| Scenario | Tasks / projects | Continuations | Preludes | Assumed cost |",
                  "|---|---:|---:|---:|---:|"])
    for row in scenarios:
        name = row["name"].replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {name} | {row['n_tasks']} / {row['n_projects']} | {row['continuations']} | {row['preludes']} | "
                     f"{report.format_number(row['assumed_total_cost'])} {row['currency']} |")
    lines.extend(["", "## Limits and remaining design work", ""] + ["- " + item for item in result["limitations"]])
    report.write_bundle(output, {"design-analysis.json": result, "design-analysis.md": "\n".join(lines) + "\n",
                                 "analysis.json": analyzed}, protect=[manifest_path, runs_path, *([scenarios_path] if scenarios_path else [])])
    return {"output": str(output), "measurement_status": summary["measurement_status"], "data_kind": data_kind,
            "formal_sample_size": None, "power_simulation_performed": False, "model_requests": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-kind", choices=sorted(report.DATA_KINDS), default="unverified")
    parser.add_argument("--scenarios", type=Path)
    args = parser.parse_args(argv)
    try:
        result = design_analysis(args.manifest, args.runs, args.output, data_kind=args.data_kind, scenarios_path=args.scenarios)
        print(experiment.canonical(result))
        return 0
    except (analysis.InputError, ContractError, OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        code = getattr(error, "code", str(error) if isinstance(error, ContractError) else type(error).__name__)
        print(experiment.canonical({"error": {"code": code}, "model_requests": 0}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
