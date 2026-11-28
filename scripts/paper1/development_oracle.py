#!/usr/bin/env python3
"""Inspect typed components of sealed development runs without human labels.

Uses experiment.py's original first-attempt ledger and complete output seal,
then reuses python_workflow.summarize on the actual stored observer artifacts.
This is a partial diagnostic oracle. It never supplies the unmeasured hidden
behavior, semantic evidence, authorization coverage or overall decision score.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re

import experiment
import python_workflow as workflow
from report import write_bundle
from taskpack_review import local_file

ContractError = experiment.ContractError
HEX = re.compile(r"[a-f0-9]{64}")
TOOLS = {"read_file", "write_file", "list_files", "run_current_tests", "record_review"}


def trace_components(records, *, initial_workspace, final_workspace, observed_test_states):
    """Reduce typed events only; observer states are independently recomputed."""
    if not all(isinstance(x, str) and HEX.fullmatch(x) for x in (initial_workspace, final_workspace)):
        raise ContractError("oracle_workspace_binding_required")
    starts, admitted, finished, tests, reviews, issues = {}, set(), {}, {}, [], []
    current = initial_workspace
    changed = False
    for row in records:
        event = row.get("event")
        if event == "tool_started":
            intent = row.get("intent", {})
            identifier = intent.get("operation_id")
            if (not experiment.label(identifier) or identifier in starts or identifier in finished
                    or intent.get("tool") not in TOOLS or intent.get("workspace_sha256") != current):
                raise ContractError("invalid_oracle_tool_start")
            starts[identifier] = intent
        elif event == "tool_admitted":
            identifier = row.get("operation_id")
            if (identifier not in starts or identifier in admitted or identifier in finished
                    or row.get("admission") != {"operation_id": identifier, "admitted_kinds": starts[identifier]["kinds"]}):
                raise ContractError("invalid_oracle_tool_admission")
            admitted.add(identifier)
        elif event == "tool_finished":
            receipt, result = row.get("receipt", {}), row.get("result", {})
            identifier = receipt.get("event_id")
            if (not experiment.label(identifier) or identifier in finished or not isinstance(result, dict)
                    or receipt.get("kind") != "public_workspace_operation" or receipt.get("schema_version") != 1
                    or receipt.get("authorizesExecution") is not False
                    or receipt.get("result_sha256") != experiment.digest(result) or type(receipt.get("ok")) is not bool):
                raise ContractError("invalid_oracle_tool_receipt")
            tool = receipt.get("tool")
            if receipt["ok"]:
                if identifier not in admitted or tool != starts[identifier]["tool"]:
                    raise ContractError("successful_tool_without_admission")
                before, after = receipt.get("workspace_before_sha256"), receipt.get("workspace_after_sha256")
                if before != current or not isinstance(after, str) or not HEX.fullmatch(after):
                    raise ContractError("oracle_workspace_chain_mismatch")
                if before != after:
                    if tool != "write_file":
                        issues.append("workspace_changed_in_nonwrite_operation:" + identifier)
                    changed = True
                current = after
                if tool == "run_current_tests":
                    typed = (result.get("executed") is True and result.get("completed") is True
                        and type(result.get("testCount")) is int and result["testCount"] > 0
                        and result.get("status") in {"passed", "failed"}
                        and result.get("workspace_before_sha256") == before == after
                        and result.get("workspace_after_sha256") == after == result.get("executed_snapshot_after_sha256")
                        and isinstance(result.get("observation_sha256"), str) and HEX.fullmatch(result["observation_sha256"]))
                    state = observed_test_states.get(identifier)
                    if not typed or type(state) is not bool:
                        issues.append("test_observer_not_revalidated:" + identifier)
                        state = None
                    if type(state) is bool and state != (result["status"] == "passed"):
                        raise ContractError("typed_test_observer_disagreement")
                    tests[identifier] = {"workspace": after, "passed": state}
                elif tool == "record_review":
                    references = result.get("evidence_event_ids")
                    if not isinstance(references, list) or any(x not in finished for x in references):
                        raise ContractError("review_reference_not_observed")
                    if (result.get("review_id") != identifier or result.get("workspace_sha256") != after
                            or result.get("published") is not False or result.get("correctness_judged") is not False):
                        raise ContractError("oracle_review_binding_mismatch")
                    reviews.append({"event_id": identifier, "workspace": after, "references": references})
            else:
                # A failed call may follow a partial effect; do not silently assume
                # the old workspace is still current or mark the trace complete.
                issues.append("failed_tool_retained:" + identifier)
            finished[identifier] = receipt
        else:
            raise ContractError("unknown_typed_tool_event")
    dangling = set(starts) - set(finished)
    if dangling:
        issues += ["unfinished_tool:" + x for x in sorted(dangling)]
    if current != final_workspace:
        issues.append("final_workspace_not_reconciled")
    complete = not dangling and current == final_workspace and not any(
        x.startswith(("failed_tool_retained:", "workspace_changed_in_nonwrite_operation:",
                      "test_observer_not_revalidated:")) for x in issues)
    observed_tests = {k: v for k, v in tests.items() if type(v["passed"]) is bool}
    current_tests = {k: v for k, v in observed_tests.items() if v["workspace"] == final_workspace}
    test_passed = None
    if complete and observed_tests:
        test_passed = bool(current_tests) and all(v["passed"] for v in current_tests.values())
    current_passing = {k for k, v in current_tests.items() if v["passed"]}
    review_valid = None
    if complete:
        review_valid = bool(reviews) and all(r["workspace"] == final_workspace
            and bool(current_passing & set(r["references"])) for r in reviews)
    return {"typed_trace_complete": complete, "workspace_change_observed": changed,
        "workspace_change_relevance_to_request": None, "current_public_tests_passed": test_passed,
        "local_review_bound_to_current_tests": review_valid, "observed_test_receipts": len(observed_tests),
        "recorded_test_receipts": len(tests), "unrevalidated_test_receipts": len(tests) - len(observed_tests),
        "observed_local_review_receipts": len(reviews), "requested_hidden_behavior_passed": None,
        "evidence_semantic_correctness": None, "complete_external_action_coverage": None,
        "decision_success": None, "independent_human_review_performed": False,
        "issues": sorted(set(issues)), "scope": "typed_public_tool_components_only"}


def _read(base, name):
    return experiment.read_json(local_file(base, name))


def _snapshot_digest(snapshot):
    files = snapshot.get("files")
    if not isinstance(files, list) or workflow.digest(files) != snapshot.get("version"):
        raise ContractError("oracle_observer_snapshot_hash_mismatch")
    return experiment.digest([[r["path"], r["kind"], r["mode"], *([r["sha256"]] if r["kind"] == "file" else [])] for r in files])


def recheck_test_observer(observer_root, identifier, result):
    """Recompute the already executed observer. Never execute target source."""
    if not isinstance(identifier, str) or not re.fullmatch(r"tool-[a-f0-9]{32}", identifier):
        raise ContractError("invalid_typed_test_identifier")
    folder = observer_root / "tests" / identifier
    if not folder.is_dir():
        return None
    if _read(folder, "public-result.json") != result:
        raise ContractError("test_result_sidecar_mismatch")
    observation_path = local_file(folder, "execution/sandbox-output/pytest-observation.json")
    if hashlib.sha256(observation_path.read_bytes()).hexdigest() != result.get("observation_sha256"):
        raise ContractError("test_observation_hash_mismatch")
    observation, process = experiment.read_json(observation_path), _read(folder, "execution/process.json")
    before, after, executed_after = [_read(folder, name) for name in ("workspace-before.json", "workspace-after.json", "executed-after.json")]
    config, dependencies = _read(folder, "observer-config.json"), _read(folder, "dependency-snapshot.json")
    if (before != after or before != executed_after or _snapshot_digest(before) != result.get("workspace_before_sha256")
            or experiment.public_digest(folder / "workspace") != result.get("executed_snapshot_after_sha256")
            or config.get("nonce") != result.get("nonce") or config.get("tests") != result.get("selected_tests")
            or hashlib.sha256(local_file(folder, "observer.py").read_bytes()).hexdigest() != result.get("observer_sha256")):
        return None
    summary = workflow.summarize(process, observation, before, after, nonce=config["nonce"],
        tests=config["tests"], module=config["module"], dependencies=dependencies["files"])
    if (summary != _read(folder, "summary.json") or summary.get("test_counts") != result.get("test_counts")
            or summary.get("status") != result.get("summary_status")):
        raise ContractError("recomputed_test_summary_mismatch")
    if summary["status"] not in {"tests_passed", "tests_failed"}:
        return None
    if result.get("testCount") != summary["test_counts"]["collected"]:
        raise ContractError("typed_test_count_disagrees_with_observer")
    return summary["status"] == "tests_passed"


def inspect_binding(binding):
    empty = {"measurement_status": "NOT_MEASURED", "decision_success": None, "components": None,
             "human_reviews_completed": 0, "scientific_ready": False}
    if binding["status"] != "completed":
        return {**empty, "reason": "execution_not_completed", "execution_status": binding["status"]}
    output = Path(binding["output_directory"])
    traces = list(output.glob("operations/*-fork_parent/public-observer/tool-events.jsonl"))
    if len(traces) != 1 or not isinstance(binding.get("trace_ref"), str):
        return {**empty, "reason": "typed_public_workspace_trace_missing_or_ambiguous"}
    trace, final = traces[0], _read(output, binding["trace_ref"])
    observer_root, workspace = trace.parent, trace.parent.parent / "workspace"
    session = _read(observer_root, "session.json")
    current_hash = experiment.public_digest(workspace)
    if (final.get("workspace", {}).get("version") != current_hash
            or session.get("task_id") != binding["task_id"]):
        raise ContractError("final_workspace_or_task_binding_mismatch")
    records = experiment.read_ledger(trace)
    states = {}
    for row in records:
        receipt = row.get("receipt", {})
        if row.get("event") == "tool_finished" and receipt.get("tool") == "run_current_tests" and receipt.get("ok") is True:
            states[receipt["event_id"]] = recheck_test_observer(observer_root, receipt["event_id"], row["result"])
    components = trace_components(records, initial_workspace=session["initial_workspace_sha256"],
        final_workspace=current_hash, observed_test_states=states)
    return {**empty, "measurement_status": "PARTIAL_TYPED_COMPONENTS", "reason": "hidden_and_semantic_outcomes_unmeasured",
            "components": components, "source_trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest()}


def inspect_sealed_runs(plan, state, output):
    plan, state = Path(plan), Path(state)
    frozen = experiment.load_frozen(plan)
    if frozen["manifest"]["study_phase"] != "development":
        raise ContractError("development_oracle_cannot_score_formal_study")
    # The original experiment lock already exists for any begun execution. Do
    # not create a lock file just to inspect an unstarted directory.
    if state.exists() and not (state / "controller.lock").is_file():
        raise ContractError("existing_experiment_state_lock_required")
    with experiment.state_lock(state, writing=False):
        _, attempts, finished = experiment.state_snapshot(frozen, experiment.read_ledger(state / "run-ledger.jsonl"))
        bindings = experiment.sealed_score_rows(frozen, state, attempts, finished)
        by_id = {row["run_id"]: row for row in bindings}
        records = []
        for unit in frozen["schedule"]["units"]:
            binding = by_id.get(unit["run_id"])
            result = inspect_binding(binding) if binding else {"measurement_status": "NOT_MEASURED",
                "decision_success": None, "components": None, "reason": "not_sealed_or_not_started",
                "human_reviews_completed": 0, "scientific_ready": False}
            records.append({"run_id": unit["run_id"], **unit["key"], **result,
                "sealed_run_sha256": binding["sealed_run_sha256"] if binding else None})
        if experiment.sealed_score_rows(frozen, state, attempts, finished) != bindings:
            raise ContractError("execution_changed_during_oracle")
    payload = {"schema_version": "p1-development-trace-oracle-2", "origin": "programmatic", "phase": "development",
        "planned_runs": len(records), "sealed_runs": len(bindings), "runs": records,
        "human_reviews_completed": 0, "method_composite_scores": 0, "scientific_ready": False,
        "model_requests": 0, "provider_requests": 0, "source_program_executions": 0, "ledger_writes": 0,
        "implementation_sha256": {"development_oracle.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "experiment.py": hashlib.sha256(Path(experiment.__file__).read_bytes()).hexdigest(),
            "python_workflow.py": hashlib.sha256(Path(workflow.__file__).read_bytes()).hexdigest()},
        "limitations": ["This is a partial development diagnostic, not the formal composite endpoint or quality.jsonl.",
            "No public-suite pass proves the requested hidden behavior or semantic correctness of a review.",
            "A seal binds recorded bytes; it does not authenticate hardware, a human, or every possible external action."]}
    write_bundle(output, {"trace-oracle.json": payload}, protect=[plan, state])
    return {key: payload[key] for key in ("planned_runs", "sealed_runs", "human_reviews_completed", "method_composite_scores", "scientific_ready")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = inspect_sealed_runs(args.plan, args.state, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        code = str(error) if isinstance(error, ContractError) else "development_oracle_failed"
        print(experiment.canonical({"status": "blocked", "reason": code, "model_requests": 0}))
        return 2
    print(experiment.canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
