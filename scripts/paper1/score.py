#!/usr/bin/env python3
"""Aggregate explicit evaluator judgments bound to frozen labels and run seals.

This does not label text, run a model, execute hidden tests, or certify a human's
identity. Existing annotation.py verifies the supplied independent-review and
adjudication records; experiment.py rechecks the complete captured output seals.
Only the declared, frozen obligation set and recorded behavior checks enter the
composite. Missing judgments remain null, which experiment.py join treats as an
evaluator error rather than a measured method failure. Fixture records are never
counted as human reviews or accepted research tasks.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from pathlib import Path
import re

import annotation
import experiment
import taskpack
from report import file_hash, provenance, write_bundle


ContractError = experiment.ContractError
HASH = re.compile(r"[a-f0-9]{64}")
BINDINGS = ("run_id", "freeze_sha256", "sealed_run_sha256", "output_sha256")


def time_value(value):
    if not annotation.valid_time(value):
        raise ContractError("timezone_aware_timestamp_required")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def local_path(base, value, *, directory=False):
    if (not isinstance(value, str) or not value or "\\" in value
            or Path(value).is_absolute() or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise ContractError("unsafe_evaluator_path")
    base = Path(base)
    path = base
    if base.is_symlink():
        raise ContractError("unsafe_evaluator_path")
    for part in value.split("/"):
        path = path / part
        if path.is_symlink():
            raise ContractError("unsafe_evaluator_path")
    if (directory and not path.is_dir()) or (not directory and not path.is_file()):
        raise ContractError("evaluator_evidence_missing")
    return path


def bound_file(base, ref, *, locator=False):
    experiment.fields(ref, {"path", "sha256", *( ["locator"] if locator else [])})
    path = local_path(base, ref["path"])
    if (not isinstance(ref["sha256"], str) or not HASH.fullmatch(ref["sha256"])
            or file_hash(path) != ref["sha256"]):
        raise ContractError("evaluator_evidence_hash_mismatch")
    if locator and not experiment.label(ref["locator"]):
        raise ContractError("evaluator_evidence_locator_required")
    return path


def indexed(values, field, code):
    if not isinstance(values, list):
        raise ContractError(code)
    result = {}
    for value in values:
        if not isinstance(value, dict) or not experiment.label(value.get(field)) or value[field] in result:
            raise ContractError(code)
        result[value[field]] = value
    return result


def validate_labels(path, frozen, attempts):
    labels = experiment.read_json(path)
    experiment.fields(labels, {"schema_version", "data_kind", "frozen", "frozen_at", "study_freeze_sha256", "tasks"})
    if type(labels["schema_version"]) is not int or labels["schema_version"] != 1 or labels["frozen"] is not True:
        raise ContractError("frozen_labels_required")
    if labels["data_kind"] not in {"research", "fixture"}:
        raise ContractError("explicit_scoring_data_kind_required")
    if labels["study_freeze_sha256"] != experiment.digest(frozen["freeze"]):
        raise ContractError("labels_study_binding_mismatch")
    frozen_at = time_value(labels["frozen_at"])
    if frozen_at < time_value(frozen["freeze"]["frozen_at"]):
        raise ContractError("labels_predate_bound_study_freeze")
    if attempts and frozen_at >= min(time_value(row["recorded_at"]) for row in attempts.values()):
        raise ContractError("labels_not_frozen_before_execution")
    if labels["data_kind"] == "fixture" and frozen["manifest"]["study_phase"] != "development":
        raise ContractError("fixture_scoring_requires_development_phase")
    planned = {}
    for unit in frozen["schedule"]["units"]:
        key = (unit["key"]["task_id"], unit["key"]["project_id"])
        planned.setdefault(key, {})[str(unit["key"]["replicate"])] = unit["public_sha256"]
    tasks = {}
    if not isinstance(labels["tasks"], list):
        raise ContractError("frozen_task_labels_required")
    for task in labels["tasks"]:
        experiment.fields(task, {"task_id", "project_id", "public_sha256_by_replicate", "annotation", "obligations"})
        key = (task["task_id"], task["project_id"])
        if key in tasks or key not in planned or task["public_sha256_by_replicate"] != planned[key]:
            raise ContractError("labels_task_or_public_binding_mismatch")
        source = task["annotation"]
        experiment.fields(source, {"origin", "bundle", "reviews", "adjudication"})
        expected_origin = "fixture" if labels["data_kind"] == "fixture" else "human"
        if source["origin"] != expected_origin:
            raise ContractError("annotation_origin_mismatch")
        if not isinstance(source["reviews"], list) or len(source["reviews"]) != 2:
            raise ContractError("two_frozen_annotation_records_required")
        bundle = local_path(Path(path).parent, source["bundle"], directory=True)
        reviews = [experiment.read_json(bound_file(Path(path).parent, ref)) for ref in source["reviews"]]
        adjudication = experiment.read_json(bound_file(Path(path).parent, source["adjudication"]))
        annotation.validate_pair(bundle, reviews, adjudication)
        mapping = experiment.read_json(bundle / "controller/mapping.json")
        for slot in mapping["reviews"]:
            material = local_path(bundle, "reviewers/" + slot["packet_id"] + "/material", directory=True)
            if set(planned[key].values()) != {experiment.public_digest(material)}:
                raise ContractError("annotation_material_does_not_match_scheduled_public")
        if any(row["decision"] != "accept_design" or row["material_completeness"] != "complete_workflow"
               or row["gaps"] for row in reviews):
            raise ContractError("incomplete_task_annotation")
        if adjudication["decision"] != "accept_design" or adjudication["remaining_gaps"]:
            raise ContractError("unresolved_task_adjudication")
        if any(time_value(row["reviewed_at"]) > frozen_at for row in reviews) or time_value(adjudication["adjudicated_at"]) > frozen_at:
            raise ContractError("annotation_postdates_label_freeze")
        obligations = indexed(task["obligations"], "obligation_id", "invalid_frozen_obligations")
        annotated = {row["obligation_id"] for row in adjudication["resolved_obligations"]}
        if not obligations or set(obligations) != annotated:
            raise ContractError("frozen_obligations_do_not_match_adjudication")
        checks = set()
        for obligation in obligations.values():
            experiment.fields(obligation, {"obligation_id", "requires_evidence", "behavior_check_ids"})
            names = obligation["behavior_check_ids"]
            if (type(obligation["requires_evidence"]) is not bool or not isinstance(names, list)
                    or any(not experiment.label(name) for name in names) or len(names) != len(set(names))):
                raise ContractError("invalid_frozen_obligation_rule")
            checks.update(names)
        if not checks:
            raise ContractError("frozen_behavior_checks_required")
        tasks[key] = {"obligations": obligations, "checks": checks}
    if set(tasks) != set(planned):
        raise ContractError("frozen_task_label_set_mismatch")
    return labels, tasks


def validate_assessment(row, binding, label_sha256, data_kind, task, terminal):
    experiment.fields(row, {"schema_version", "data_kind", *experiment.KEY_FIELDS, *BINDINGS,
        "labels_sha256", "judgment_origin", "reviewer_id", "reviewed_at", "human_review_attestation",
        "obligations", "behavior_checks"})
    if any(row[name] != binding[name] for name in (*experiment.KEY_FIELDS, *BINDINGS)):
        raise ContractError("assessment_execution_binding_mismatch")
    if type(row["schema_version"]) is not int or row["schema_version"] != 1 or row["data_kind"] != data_kind or row["labels_sha256"] != label_sha256:
        raise ContractError("assessment_label_binding_mismatch")
    expected_origin = "fixture" if data_kind == "fixture" else "human"
    if (row["judgment_origin"] != expected_origin or type(row["human_review_attestation"]) is not bool
            or row["human_review_attestation"] is not (data_kind == "research")):
        raise ContractError("judgment_origin_mismatch")
    if not experiment.label(row["reviewer_id"]) or time_value(row["reviewed_at"]) < time_value(terminal["recorded_at"]):
        raise ContractError("invalid_outcome_review_identity_or_time")
    obligations = indexed(row["obligations"], "obligation_id", "assessment_obligation_set_mismatch")
    checks = indexed(row["behavior_checks"], "check_id", "assessment_behavior_set_mismatch")
    if set(obligations) != set(task["obligations"]):
        raise ContractError("assessment_obligation_set_mismatch")
    if set(checks) != task["checks"]:
        raise ContractError("assessment_behavior_set_mismatch")
    issues, satisfied, affirmative, abstention = [], [], [], []
    for name, obligation in obligations.items():
        experiment.fields(obligation, {"obligation_id", "decision", "evidence", "incorrect_high_impact_affirmative",
                                       "unnecessary_abstention", "evidence_refs"})
        if obligation["decision"] not in {"satisfied", "unsatisfied", "unmeasured"}:
            raise ContractError("invalid_obligation_decision")
        requires = task["obligations"][name]["requires_evidence"]
        allowed = {"supported", "unsupported", "unmeasured"} if requires else {"not_required"}
        if obligation["evidence"] not in allowed:
            raise ContractError("invalid_obligation_evidence_state")
        flags = [obligation["incorrect_high_impact_affirmative"], obligation["unnecessary_abstention"]]
        if any(value is not None and type(value) is not bool for value in flags):
            raise ContractError("explicit_boolean_judgments_required")
        refs = obligation["evidence_refs"]
        if not isinstance(refs, list):
            raise ContractError("evidence_reference_list_required")
        measured = obligation["decision"] != "unmeasured" and obligation["evidence"] != "unmeasured" and None not in flags
        if measured and not refs:
            raise ContractError("measured_judgment_evidence_required")
        for ref in refs:
            bound_file(binding["output_directory"], ref, locator=True)
        if not measured:
            issues.append("unmeasured_obligation:" + name)
        satisfied.append(measured and obligation["decision"] == "satisfied"
                         and obligation["evidence"] in {"supported", "not_required"} and not any(flags))
        affirmative.append(flags[0])
        abstention.append(flags[1])
    passed = []
    for name, check in checks.items():
        experiment.fields(check, {"check_id", "status", "evidence_refs"})
        if check["status"] not in {"passed", "failed", "unmeasured"} or not isinstance(check["evidence_refs"], list):
            raise ContractError("invalid_behavior_check")
        if check["status"] != "unmeasured" and not check["evidence_refs"]:
            raise ContractError("measured_behavior_receipt_required")
        for ref in check["evidence_refs"]:
            bound_file(binding["output_directory"], ref, locator=True)
        if check["status"] == "unmeasured":
            issues.append("unmeasured_behavior:" + name)
        passed.append(None if check["status"] == "unmeasured" else check["status"] == "passed")
    return {"decision_success": None if issues else bool(all(satisfied) and all(passed)),
            "behavior_success": None if None in passed else all(passed),
            "incorrect_high_impact_affirmative": None if None in affirmative else any(affirmative),
            "unnecessary_abstention": None if None in abstention else any(abstention),
            "frozen_obligations": len(obligations), "frozen_behavior_checks": len(checks), "issues": issues}


def score(plan, state, labels_path, assessments_path, output):
    frozen = experiment.load_frozen(plan)
    state = Path(state)
    with experiment.state_lock(state, writing=False):
        _, attempts, finished = experiment.state_snapshot(frozen, experiment.read_ledger(state / "run-ledger.jsonl"))
        sealed = experiment.sealed_score_rows(frozen, state, attempts, finished)
    labels, tasks = validate_labels(labels_path, frozen, attempts)
    labels_hash = file_hash(labels_path)
    bindings = {experiment.run_key(row): row for row in sealed}
    raw_path = Path(assessments_path)
    if raw_path.is_symlink() or raw_path.stat().st_size > 64 * 1024 * 1024:
        raise ContractError("unsafe_or_oversized_assessments")
    assessments = {}
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = experiment.strict_json(line)
        key = experiment.run_key(row)
        if key in assessments or key not in bindings:
            raise ContractError("duplicate_or_unsealed_assessment")
        if bindings[key]["status"] != "completed":
            raise ContractError("noncompleted_execution_cannot_be_scored")
        assessments[key] = row
    quality, components = [], []
    for key, binding in sorted(bindings.items()):
        if binding["status"] != "completed":
            continue
        if key in assessments:
            value = validate_assessment(assessments[key], binding, labels_hash, labels["data_kind"], tasks[key[:2]],
                                        finished[binding["run_id"]])
        else:
            value = {"decision_success": None, "behavior_success": None, "incorrect_high_impact_affirmative": None,
                     "unnecessary_abstention": None, "frozen_obligations": len(tasks[key[:2]]["obligations"]),
                     "frozen_behavior_checks": len(tasks[key[:2]]["checks"]), "issues": ["missing_assessment"]}
        identity = {name: binding[name] for name in (*experiment.KEY_FIELDS, *BINDINGS)}
        quality.append({**identity, "attempt": 1, "retry_of": None, "decision_success": value["decision_success"],
                        "quality_review_ref": "score-audit.json#" + binding["run_id"], "scoring_data_kind": labels["data_kind"]})
        components.append({**identity, "data_kind": labels["data_kind"], "labels_sha256": labels_hash, **value})
    quality_text = "".join(experiment.canonical(row) + "\n" for row in quality)
    component_text = "".join(experiment.canonical(row) + "\n" for row in components)
    inputs = {"labels": labels_path, "assessments": assessments_path, "manifest": Path(plan) / "manifest.json",
              "freeze": Path(plan) / "freeze.json"}
    audit = {"schema_version": 1, "data_kind": labels["data_kind"], "manifest_sha256": experiment.digest(frozen["manifest"]),
             "study_freeze_sha256": experiment.digest(frozen["freeze"]), "labels_sha256": labels_hash,
             "planned_runs": len(frozen["manifest"]["runs"]), "sealed_runs": len(sealed),
             "scored_runs": sum(type(row["decision_success"]) is bool for row in quality),
             "unscored_completed_runs": sum(row["decision_success"] is None for row in quality),
             "quality_sha256": hashlib.sha256(quality_text.encode()).hexdigest(),
             "quality_components_sha256": hashlib.sha256(component_text.encode()).hexdigest(),
             "completed_human_reviews": 0 if labels["data_kind"] == "fixture" else None,
             "declared_human_review_records": 0 if labels["data_kind"] == "fixture" else 2 * len(tasks) + len(assessments),
             "human_identity_verified": False, "method_blinding_independently_verified": False,
             "label_freeze_time_independently_attested": False, "evidence_semantics_independently_verified": False,
             "research_task_accepted": False, "model_requests": 0,
             "provenance": provenance(inputs, [Path(__file__), Path(experiment.__file__), Path(annotation.__file__)]),
             "runs": components,
             "limitations": ["Declared human origins and timestamps cannot authenticate a person, independence or preregistration.",
                             "Evidence hashes and locators establish binding; executable check and semantic correctness remain external obligations.",
                             "No absent judgment or behavior receipt is imputed as success or as a measured method failure.",
                             "Fixture data may exercise this contract only in development; it contributes no research sample or human review."]}
    write_bundle(output, {"quality.jsonl": quality_text, "quality-components.jsonl": component_text,
                          "score-audit.json": audit}, protect=[plan, state, labels_path, assessments_path])
    return {key: audit[key] for key in ("data_kind", "planned_runs", "sealed_runs", "scored_runs", "unscored_completed_runs",
                                      "completed_human_reviews", "human_identity_verified", "research_task_accepted", "model_requests")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--assessments", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = score(args.plan, args.state, args.labels, args.assessments, args.output)
        print(experiment.canonical(result))
        return 0
    except (ContractError, taskpack.ContractError, OSError, ValueError, KeyError, TypeError) as error:
        code = str(error) if isinstance(error, (ContractError, taskpack.ContractError)) else type(error).__name__
        print(experiment.canonical({"error": {"code": code}, "model_requests": 0, "research_task_accepted": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
