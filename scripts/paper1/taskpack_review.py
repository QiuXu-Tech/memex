#!/usr/bin/env python3
"""Read-only development assurance, separate from human annotation and scores.

Recompute public/source integrity and existing JUnit evidence, validate explicitly
AI-assisted obligation drafts, and report observable fixture facts. No model,
source program, credential, external service or execution ledger is used. This
does not accept a research task or produce a method-success observation.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import annotation
import taskpack
from report import write_bundle

ROOT = Path(__file__).resolve().parents[2]
ContractError = taskpack.ContractError
ORACLE_IDS = {
    "current_artifact_test_binding", "completed_nonempty_target_tests", "current_registry_readback",
    "complete_native_authorization_lifecycle", "exact_authority_object_action_scope",
    "authoritative_revision_conflict", "complete_paged_originals", "full_obligation_coverage",
    "review_final_artifact_binding", "local_only_no_publication", "flask_empty_name_behavior",
    "requests_proxy_auth_preservation", "regression_preservation", "actual_native_workflow",
}


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local_file(base, name, *, public=False):
    (taskpack.public_path if public else taskpack.safe_relative_path)(name)
    base = Path(base).absolute()
    target = base / name
    if any(p.is_symlink() for p in (target, *target.parents)) or not target.is_file() or target.stat().st_nlink != 1:
        raise ContractError("unsafe_review_evidence_file")
    if target.stat().st_size > 16 * 1024 * 1024:
        raise ContractError("review_evidence_size_limit")
    return target


def evidence_ref(public, name, start, end):
    source = local_file(public, name, public=True)
    data = source.read_bytes()
    if any(type(v) is not int for v in (start, end)) or not 0 <= start < end <= len(data):
        raise ContractError("invalid_evidence_span")
    return {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "start_byte": start,
            "end_byte": end, "span_sha256": hashlib.sha256(data[start:end]).hexdigest()}


def junit_counts(path):
    """Count actual testcase elements; never infer test success from exit zero."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ContractError("unsafe_junit_file")
    raw = path.read_bytes()
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ContractError("junit_entities_forbidden")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise ContractError("invalid_junit_xml") from None
    if root.tag not in {"testsuite", "testsuites"}:
        raise ContractError("invalid_junit_root")
    counts = {"tests": 0, "passed": 0, "failures": 0, "errors": 0, "skipped": 0}
    known = set()
    cases = list(root.iter("testcase"))
    if not cases:
        raise ContractError("junit_has_no_executed_cases")
    for case in cases:
        identity = (case.get("classname", ""), case.get("name"))
        if not identity[1] or identity in known:
            raise ContractError("junit_duplicate_or_missing_case_identity")
        known.add(identity)
        states = [name for name in ("failure", "error", "skipped") if case.find(name) is not None]
        if len(states) > 1:
            raise ContractError("junit_conflicting_case_states")
        counts["tests"] += 1
        counts[{"failure": "failures", "error": "errors", "skipped": "skipped"}.get(states[0] if states else "", "passed")] += 1
    for suite in root.iter("testsuite"):
        direct = list(suite.iter("testcase"))
        actual = {"tests": len(direct), "failures": sum(c.find("failure") is not None for c in direct),
                  "errors": sum(c.find("error") is not None for c in direct),
                  "skipped": sum(c.find("skipped") is not None for c in direct)}
        for name, value in actual.items():
            if name in suite.attrib and suite.attrib[name] != str(value):
                raise ContractError("junit_declared_counts_mismatch")
    return counts


def _fixture_authorization(events, public):
    if not any("permission" in e["body"].lower() or "approv" in e["body"].lower() for e in events):
        return None
    clock = public / "workspace/clock.json"
    logical_time = taskpack.read_json(clock).get("logical_time") if clock.is_file() else None
    state, applicable, ignored = "no_matching_native_grant", [], []
    latest_revision = None
    revision_conflict = False
    for event in sorted(events, key=lambda e: e["sequence"]):
        if event["native_role"] != "user" or event["principal"] != "owner":
            ignored.append(event["event_id"])
            continue
        grant = re.fullmatch(r"Grant release permission to principal reviewer for widget/staging until logical time ([0-9]+)\.", event["body"])
        revoke = event["body"] == "Revoke that release permission for widget/staging immediately."
        if grant or revoke:
            if event.get("object_id") != "widget/staging" or type(event.get("object_revision")) is not int:
                state = "unknown_untyped_scope"; applicable.append(event["event_id"]); continue
            applicable.append(event["event_id"])
            revision = event["object_revision"]
            if latest_revision is not None and revision <= latest_revision:
                revision_conflict = True
            latest_revision = revision if latest_revision is None else max(revision, latest_revision)
            if revoke:
                state = "withdrawn"
            elif type(logical_time) is not int:
                state = "unknown_current_time"
            else:
                state = "grant_within_declared_ttl" if logical_time < int(grant.group(1)) else "expired"
        elif event["body"] in {"Grant reviewer permission to read widget/staging.",
                               "Grant reviewer permission to release gadget/staging.",
                               "Grant reviewer permission for local review notes only; no production release."}:
            ignored.append(event["event_id"])
        else:
            state = "unknown_unrecognized_owner_statement"; applicable.append(event["event_id"])
    if revision_conflict:
        state = "unknown_nonmonotone_or_duplicate_native_revision"
    return {"status": state, "target": {"principal": "reviewer", "object": "widget/staging", "action": "release"},
            "logical_time_from_fixture_file": logical_time, "applicable_event_ids": applicable,
            "ignored_nonmatching_event_ids": ignored, "real_world_authorization": None,
            "rule_scope": "only_the_explicit_synthetic_fixture_grammar"}


def material_facts(public, kind):
    public = Path(public)
    result = {"evidence_domain": "synthetic_fixture_content_only" if kind == "synthetic_fixture" else "public_source_bytes",
              "actual_test_execution": None, "actual_restricted_action": None, "artifact_bindings": [],
              "test_records": [], "registry": None, "authorization": None, "revision_conflict": None,
              "archive_records": 0, "archive_is_real_native_capture": False}
    if kind != "synthetic_fixture":
        return result
    archive = local_file(public, "archive.jsonl", public=True)
    events = [taskpack.strict_json(line) for line in archive.read_text().splitlines() if line.strip()]
    taskpack.validate_archive(archive.read_text())
    result["archive_records"] = len(events)
    artifact = public / "workspace/artifact.json"
    current_hash = file_sha(artifact) if artifact.is_file() else None
    for event in events:
        if "artifact_sha256" in event:
            result["artifact_bindings"].append({"event_id": event["event_id"], "archived_sha256": event["artifact_sha256"],
                "current_sha256": current_hash, "matches_current_bytes": event["artifact_sha256"] == current_hash})
        if "completion" in event or "check" in event["source_name"] or "transport" in event["source_name"]:
            counts = re.findall(r"\bassertions=([0-9]+)\b", event["body"])
            legacy = re.fullmatch(r"Completed unit check: ([0-9]+) assertions passed; exit=0\. Artifact SHA-256=[a-f0-9]{64}", event["body"])
            count = int(counts[0]) if len(counts) == 1 else int(legacy.group(1)) if legacy else None
            result["test_records"].append({"event_id": event["event_id"], "source_name": event["source_name"],
                "completion": event.get("completion", "unknown"), "body_bytes": len(event["body"].encode()),
                "assertions_reported_in_text": count, "actual_test_passed": None})
    registry = public / "workspace/registry.json"
    if registry.is_file():
        result["registry"] = {"file_sha256": file_sha(registry), "observed_json": taskpack.read_json(registry),
                              "native_tool_readback_observed": False}
    result["authorization"] = _fixture_authorization(events, public)
    authorities_path = public / "workspace/authorities.json"
    authorities = taskpack.read_json(authorities_path).get("authorities", []) if authorities_path.is_file() else []
    candidates = []
    for event in events:
        match = re.search(r"widget channel=([a-z]+); revision=([0-9]+);", event["body"])
        if (match and event.get("native_role") == "tool" and event.get("principal") == "local-tool"
                and event.get("source_name") in {name + "-readback" for name in authorities}
                and event.get("object_id") == "widget-channel" and event.get("object_revision") == int(match.group(2))):
            candidates.append({"event_id": event["event_id"], "revision": event["object_revision"],
                               "value": match.group(1), "source_name": event["source_name"]})
    if candidates:
        latest = max(x["revision"] for x in candidates)
        values = sorted({x["value"] for x in candidates if x["revision"] == latest})
        conflict = len(values) != 1
        result["revision_conflict"] = {"latest_native_revision_in_fixture": latest, "candidate_values": values,
            "status": "conflict_at_latest_revision" if conflict else "one_value_in_material",
            "resolved_value": None if conflict else values[0], "records": candidates,
            "wall_clock_used_as_order": False, "new_readback_observed": False}
    return result


def source_qualification(package, spec, repository_root):
    exported = taskpack.read_json(package / "controller/source-export.json")
    if exported["base_commit"] != spec["source"]["base_commit"] or exported["repository_url"] != spec["source"]["repository_url"]:
        raise ContractError("source_export_identity_mismatch")
    expected = set()
    for row in exported["files"]:
        target = local_file(package / "public/workspace", row["path"], public=True)
        raw = target.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        if row["path"] in expected or file_sha(target) != row["sha256"] or len(raw) != row["bytes"] or blob != row["git_blob"]:
            raise ContractError("source_export_blob_mismatch")
        expected.add(row["path"])
    actual = {x["path"] for x in taskpack.inventory(package / "public/workspace") if x["kind"] == "file"}
    if actual != expected:
        raise ContractError("source_export_file_set_mismatch")
    qualification = spec["evaluator"]["program_qualification"]
    target = local_file(repository_root, qualification["receipt"])
    if file_sha(target) != qualification["receipt_sha256"]:
        raise ContractError("source_qualification_hash_mismatch")
    receipt = taskpack.read_json(target)
    if (receipt["candidate_id"] != spec["evaluator"]["source_candidate_id"]
            or receipt["upstream"]["base_commit"] != spec["source"]["base_commit"]
            or receipt["kind"] != "program_regression_reproduction_not_agent_evaluation"):
        raise ContractError("source_qualification_identity_mismatch")
    counts, refs = {}, [{"path": qualification["receipt"], "sha256": file_sha(target)}]
    for phase in ("base", "fixed"):
        details = receipt[phase + "_result"]
        junit = local_file(target.parent, details["junit"])
        counts[phase] = junit_counts(junit)
        if counts[phase] != details["counts"]:
            raise ContractError("source_junit_receipt_mismatch")
        refs.append({"path": junit.relative_to(Path(repository_root).absolute()).as_posix(), "sha256": file_sha(junit)})
    return {"kind": "rechecked_existing_source_qualification_not_method_evaluation", "new_source_execution": False,
            "git_blob_files_recomputed": len(expected), "base_commit": spec["source"]["base_commit"],
            "required_notices_present": all(x in expected for x in spec["source"]["required_notices"]),
            "excluded_files": exported.get("excluded_files", []), "junit_recomputed": counts,
            "evidence": refs, "original_limitations": receipt["limitations"],
            "historical_environment_equals_current_device": None, "method_success": None}


def inspect_package(package, *, repository_root=ROOT):
    package = Path(package).absolute()
    original = file_sha(package / "manifest.json")
    checked = taskpack.validate_package(package)
    spec = taskpack.read_json(package / "controller/spec.json")
    source = source_qualification(package, spec, Path(repository_root).absolute()) if checked["kind"] == "real_source_seed" else None
    facts = material_facts(package / "public", checked["kind"])
    if file_sha(package / "manifest.json") != original or taskpack.validate_package(package) != checked:
        raise ContractError("package_changed_during_review")
    return {"schema_version": "p1-programmatic-task-inspection-2", "task_id": checked["task_id"],
            "project_id": checked["project_id"], "workflow_family_id": checked["workflow_family_id"],
            "material_kind": checked["kind"], "origin": "programmatic", "material_integrity_verified": True,
            "public_sha256": checked["public_sha256"], "manifest_sha256": original,
            "public_file_count": checked["public_file_count"], "public_bytes": checked["public_bytes"],
            "source_qualification": source, "material_facts": facts,
            "development_material_inspection_complete": True, "live_dispatch_authorization_evaluated": False,
            "research_task_accepted": False, "frozen": False, "workflow_outcome": "NOT_MEASURED",
            "independent_human_review_count": 0, "human_review_attestation": False,
            "method_outputs_read": False, "model_requests": 0, "provider_requests": 0,
            "source_program_executions": 0, "ledger_writes": 0,
            "legacy_v1_acceptance_gates": checked["acceptance"]["blocking_gates"]}


def validate_drafts(draft, packages):
    taskpack.fields(draft, {"schema_version", "origin", "phase", "status", "human_review_attestation",
        "independent_human_review_count", "method_outputs_used", "ai_reviewer", "prepared_at", "exposure_disclosure", "tasks"})
    if (draft["schema_version"] != "p1-assisted-task-review-2" or draft["origin"] != "ai_assisted"
            or draft["phase"] != "development" or draft["status"] != "unfrozen_draft"
            or draft["human_review_attestation"] is not False or draft["method_outputs_used"] is not False
            or type(draft["independent_human_review_count"]) is not int or draft["independent_human_review_count"] != 0
            or not taskpack.label(draft["ai_reviewer"]) or not taskpack.label(draft["exposure_disclosure"])):
        raise ContractError("explicit_nonhuman_development_draft_required")
    try:
        prepared = datetime.fromisoformat(draft["prepared_at"].replace("Z", "+00:00"))
        if prepared.tzinfo is None:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ContractError("draft_timestamp_requires_timezone") from None
    if not isinstance(draft["tasks"], list):
        raise ContractError("complete_draft_task_set_required")
    results = {}
    for row in draft["tasks"]:
        taskpack.fields(row, {"task_id", "public_sha256", "obligations", "remaining_gaps"})
        task_id = row["task_id"]
        if task_id not in packages or task_id in results:
            raise ContractError("draft_task_set_mismatch")
        package = packages[task_id]
        public = package / "public"
        if row["public_sha256"] != taskpack.validate_package(package)["public_sha256"]:
            raise ContractError("draft_public_binding_mismatch")
        if not isinstance(row["obligations"], list) or not row["obligations"]:
            raise ContractError("nonempty_draft_obligations_required")
        seen = set()
        for obligation in row["obligations"]:
            taskpack.fields(obligation, {"obligation_id", "kind", "description", "expected_behavior", "answerability", "evidence", "oracle_ids"})
            if any(not taskpack.label(obligation[k]) for k in ("obligation_id", "description", "expected_behavior")) or obligation["obligation_id"] in seen:
                raise ContractError("invalid_or_duplicate_draft_obligation")
            seen.add(obligation["obligation_id"])
            if obligation["kind"] not in {"test", "version", "authorization", "artifact", "other"} or obligation["answerability"] not in {
                "answerable_from_material", "requires_new_observation", "conflicted", "unknown"}:
                raise ContractError("invalid_draft_obligation_type")
            if (not isinstance(obligation["oracle_ids"], list) or not obligation["oracle_ids"]
                    or any(x not in ORACLE_IDS for x in obligation["oracle_ids"])):
                raise ContractError("unsupported_draft_oracle")
            if not isinstance(obligation["evidence"], list) or not obligation["evidence"]:
                raise ContractError("draft_evidence_required")
            for ref in obligation["evidence"]:
                taskpack.fields(ref, {"path", "sha256", "start_byte", "end_byte", "span_sha256"})
                actual = evidence_ref(public, ref["path"], ref["start_byte"], ref["end_byte"])
                if actual != ref:
                    raise ContractError("draft_evidence_binding_mismatch")
        if not isinstance(row["remaining_gaps"], list) or any(not taskpack.label(x) for x in row["remaining_gaps"]):
            raise ContractError("invalid_draft_gap_list")
        results[task_id] = row
    if set(results) != set(packages):
        raise ContractError("draft_task_set_mismatch")
    return results


def inspect_blank_assignment(bundle, public_sha256):
    """Audit the old unfilled route without completing or interpreting it."""
    bundle = Path(bundle)
    mapping = taskpack.read_json(local_file(bundle, "controller/mapping.json"))
    if (mapping.get("material_sha256") != public_sha256 or mapping.get("actual_reviewers_assigned") is not None
            or mapping.get("independent_human_review_count") != 0 or len(mapping.get("reviews", [])) != 2):
        raise ContractError("nonblank_legacy_assignment_requires_separate_accounting")
    for slot in mapping["reviews"]:
        taskpack.safe_relative_path(slot["packet_id"])
        packet = bundle / "reviewers" / slot["packet_id"]
        meta = annotation.load_packet(packet)
        if taskpack.digest(meta) != slot["packet_sha256"] or meta["material_sha256"] != public_sha256:
            raise ContractError("legacy_assignment_material_binding_mismatch")
        template = taskpack.read_json(local_file(packet, "review-template.json"))
        blank = annotation.REVIEW_FIELDS - {"schema_version", "packet_id", "material_sha256"}
        if any(template.get(key) is not None for key in blank):
            raise ContractError("nonblank_legacy_review_requires_separate_accounting")
    adjudication = taskpack.read_json(local_file(bundle, "controller/adjudication-template.json"))
    if any(adjudication.get(key) is not None for key in annotation.ADJUDICATION_FIELDS - {"schema_version", "material_sha256"}):
        raise ContractError("nonblank_legacy_adjudication_requires_separate_accounting")
    return {"blank_review_templates_verified": 2, "blank_adjudication_templates_verified": 1,
            "completed_human_reviews": 0, "human_identity_verified": False}


def review_catalog(catalog_path, draft_path, output, *, repository_root=ROOT):
    catalog_path, draft_path = Path(catalog_path).absolute(), Path(draft_path).absolute()
    catalog, draft = taskpack.read_json(catalog_path), taskpack.read_json(draft_path)
    packages, old_assignments = {}, {}
    for row in catalog["packages"]:
        taskpack.safe_relative_path(row["package"])
        package = catalog_path.parent / row["package"]
        if row["task_id"] in packages or any(x.is_symlink() for x in (package, *package.parents)):
            raise ContractError("unsafe_or_duplicate_catalog_package")
        checked = taskpack.validate_package(package)
        if any(checked[key] != row[key] for key in ("task_id", "project_id", "kind", "public_sha256", "workflow_family_id")):
            raise ContractError("catalog_package_binding_mismatch")
        packages[row["task_id"]] = package
        taskpack.safe_relative_path(row["annotation"])
        old_assignments[row["task_id"]] = inspect_blank_assignment(catalog_path.parent / row["annotation"], checked["public_sha256"])
    if len(packages) != catalog["package_count"]:
        raise ContractError("catalog_package_count_mismatch")
    drafts = validate_drafts(draft, packages)
    reports = [inspect_package(package, repository_root=repository_root) for _, package in sorted(packages.items())]
    for report in reports:
        report["legacy_assignment_inspection"] = old_assignments[report["task_id"]]
    obligations = sum(len(row["obligations"]) for row in drafts.values())
    summary = {"schema_version": "p1-development-assurance-2", "phase": "development", "frozen": False,
        "package_count": len(reports), "programmatic_material_reviews": len(reports), "ai_assisted_task_drafts": len(drafts),
        "ai_assisted_obligation_drafts": obligations, "independent_human_review_count": 0, "adjudication_count": 0,
        "blank_legacy_review_templates_verified": sum(x["blank_review_templates_verified"] for x in old_assignments.values()),
        "blank_legacy_adjudication_templates_verified": len(old_assignments),
        "accepted_p1_workflow_count": 0, "method_quality_observations": 0, "scientific_ready": False,
        "model_requests": 0, "provider_requests": 0, "source_program_executions": 0, "ledger_writes": 0,
        "live_dispatch_authorization_evaluated": False, "method_outputs_used": False,
        "catalog_sha256": file_sha(catalog_path), "drafts_sha256": file_sha(draft_path),
        "implementation_sha256": {"taskpack_review.py": file_sha(__file__), "taskpack.py": file_sha(taskpack.__file__),
                                  "annotation.py": file_sha(annotation.__file__)},
        "scope": "material_pre_review_and_deterministic_existing_evidence_only",
        "limitations": ["Programmatic evidence checks do not authenticate the author of prior source records.",
            "AI-assisted obligations are explicit nonblind drafts, not independent human or validated study labels.",
            "Synthetic archive content is never counted as actual native activity or a completed target test.",
            "Source qualification does not establish hidden behavior or success of any method continuation.",
            "The human-only v1 route remains intact; it is not a requirement to collect development observations."]}
    lines = ["# Development assurance v2 — actual material review", "",
        f"Reviewed {len(reports)} existing packages programmatically and validated {obligations} AI-assisted obligation drafts. "
        "Human reviews **0**, accepted P1 workflows **0**, method outcomes **NOT MEASURED**.", "",
        "These checks require no human signature to perform. They are not research scores, run permits, or publication clearance.", "",
        "| Task | Kind | Files | Existing source evidence | Archive records | P1 outcome |",
        "|---|---|---:|---|---:|---|"]
    for row in reports:
        source = row["source_qualification"]
        state = "Not applicable" if source is None else "Git blobs + existing base/fixed JUnit recounted"
        lines.append(f"| {row['task_id']} | {row['material_kind']} | {row['public_file_count']} | {state} | {row['material_facts']['archive_records']} | NOT MEASURED |")
    lines += ["", "## Limits", ""] + ["- " + x for x in summary["limitations"]]
    contents = {"summary.json": summary, "reviews.json": {"tasks": reports}, "report.md": "\n".join(lines) + "\n"}
    write_bundle(output, contents, protect=[catalog_path.parent, draft_path, *packages.values()])
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--drafts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = review_catalog(args.catalog, args.drafts, args.output)
    except (OSError, ValueError, KeyError, TypeError) as error:
        code = str(error) if isinstance(error, ContractError) else "development_review_failed"
        print(taskpack.canonical({"status": "blocked", "reason": code, "model_requests": 0}))
        return 2
    print(taskpack.canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
