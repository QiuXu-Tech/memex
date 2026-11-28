#!/usr/bin/env python3
"""Prepare blinded task-design review packets and validate returned records.

This is a structural checker. Names, timestamps and attestations cannot prove
that a person performed a review or remained blind. It never accepts a P1 task,
freezes labels, or converts a blank template into human evidence.
"""

import argparse
from datetime import datetime
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile

from taskpack import (ContractError, canonical, copy_public, digest, fields, inventory, label,
                      read_json, safe_relative_path, validate_package, write_json)


REVIEW_FIELDS = {"schema_version", "packet_id", "material_sha256", "reviewer_id", "reviewed_at",
                 "human_review_attestation", "independence_attestation", "method_outputs_seen", "decision",
                 "material_completeness", "critical_obligations", "gaps"}
ADJUDICATION_FIELDS = {"schema_version", "material_sha256", "review_sha256", "adjudicator_id", "adjudicated_at",
                       "human_review_attestation", "method_outputs_seen", "resolution", "rationale", "decision",
                       "resolved_obligations", "remaining_gaps"}
DECISIONS = {"accept_design", "revise_design", "insufficient_material"}


def identity(value):
    return " ".join(value.split()).casefold() if isinstance(value, str) else None


def valid_time(value):
    try:
        return isinstance(value, str) and datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None
    except ValueError:
        return False


def prepare(package, output, *, assignment_seed):
    report = validate_package(package)
    if not isinstance(assignment_seed, str) or len(assignment_seed) < 8:
        raise ContractError("explicit_assignment_seed_required")
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ContractError("output_already_exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".p1-annotation-", dir=output.parent))
    records = []
    try:
        for slot in (1, 2):
            packet_id = "review-" + digest([assignment_seed, report["public_sha256"], slot])[:20]
            packet = stage / "reviewers" / packet_id
            packet.mkdir(parents=True)
            entries = copy_public(Path(package) / "public", packet / "material")
            if digest(entries) != report["public_sha256"]:
                raise ContractError("public_changed_during_assignment")
            meta = {"schema_version": "p1-review-packet-1", "packet_id": packet_id,
                    "material_sha256": report["public_sha256"], "material_kind": report["kind"],
                    "public_files": entries, "method_arm": None, "method_outputs": None,
                    "evaluator_answers_provided": False}
            write_json(packet / "packet.json", meta)
            template = {"schema_version": "p1-independent-review-1", "packet_id": packet_id,
                        "material_sha256": report["public_sha256"],
                        **{key: None for key in REVIEW_FIELDS - {"schema_version", "packet_id", "material_sha256"}}}
            write_json(packet / "review-template.json", template)
            (packet / "INSTRUCTIONS.md").write_text(
                "# Independent task-design review — unfilled template\n\n"
                "Review only this packet. Do not inspect another review, method output, the controller mapping, "
                "a proposed answer key, or an upstream future fix. Identify the decision obligations independently "
                "from the request and the supplied observations. Read the material before completing a review.\n\n"
                "Describe what is answerable, which new observations/actions are required, and what is missing. "
                "Every obligation needs a local material path, its SHA-256 and a usable span/locator. "
                "The presence of source code or synthetic events does not establish a real native-compaction workflow. "
                "Use insufficient_material or revise_design when appropriate. Do not invent evidence.\n\n"
                "Only an actual human reviewer may enter their identity and true attestations. A passing JSON "
                "validator establishes structure and bindings only. No fields in this packet are completed human labels.\n",
                encoding="utf-8")
            records.append({"slot": slot, "packet_id": packet_id, "packet_sha256": digest(meta)})
        mapping = {"schema_version": 1, "domain": "controller_evaluator_only", "task_id": report["task_id"],
                   "workflow_family_id": report["workflow_family_id"], "material_sha256": report["public_sha256"],
                   "assignment_seed_sha256": hashlib.sha256(assignment_seed.encode()).hexdigest(), "reviews": records,
                   "actual_reviewers_assigned": None, "independent_human_review_count": 0, "accepted": False, "frozen": False}
        write_json(stage / "controller/mapping.json", mapping)
        adjudication = {"schema_version": "p1-adjudication-1", "material_sha256": report["public_sha256"],
                        **{key: None for key in ADJUDICATION_FIELDS - {"schema_version", "material_sha256"}}}
        write_json(stage / "controller/adjudication-template.json", adjudication)
        for path in stage.rglob("*"):
            path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
        stage.chmod(0o755)
        stage.rename(output)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return {"schema_version": 1, "prepared_review_packets": 2, "completed_human_reviews": 0,
            "adjudication_completed": False, "task_id": report["task_id"], "material_sha256": report["public_sha256"],
            "research_task_accepted": False, "frozen": False, "model_requests": 0}


def load_packet(packet):
    packet = Path(packet)
    if packet.is_symlink() or not packet.is_dir():
        raise ContractError("unsafe_annotation_packet")
    meta = read_json(packet / "packet.json")
    fields(meta, {"schema_version", "packet_id", "material_sha256", "material_kind", "public_files", "method_arm",
                  "method_outputs", "evaluator_answers_provided"})
    if (meta["schema_version"] != "p1-review-packet-1" or meta["method_arm"] is not None
            or meta["method_outputs"] is not None or meta["evaluator_answers_provided"] is not False):
        raise ContractError("annotation_packet_not_blinded")
    actual = inventory(packet / "material")
    if actual != meta["public_files"] or digest(actual) != meta["material_sha256"]:
        raise ContractError("annotation_material_mismatch")
    return meta


def check_obligations(obligations, packet):
    if not isinstance(obligations, list) or not obligations:
        raise ContractError("critical_obligations_required")
    meta = load_packet(packet)
    known = {x["path"]: x["sha256"] for x in meta["public_files"] if x["kind"] == "file"}
    identifiers = set()
    for obligation in obligations:
        fields(obligation, {"obligation_id", "kind", "description", "expected_behavior", "answerability", "evidence"})
        if not all(label(obligation[k]) for k in ("obligation_id", "description", "expected_behavior")):
            raise ContractError("invalid_obligation")
        if obligation["obligation_id"] in identifiers:
            raise ContractError("duplicate_obligation_id")
        identifiers.add(obligation["obligation_id"])
        if obligation["kind"] not in {"test", "version", "authorization", "artifact", "other"} or obligation["answerability"] not in {
            "answerable_from_material", "requires_new_observation", "conflicted", "unknown"
        }:
            raise ContractError("invalid_obligation_kind_or_answerability")
        if not isinstance(obligation["evidence"], list) or not obligation["evidence"]:
            raise ContractError("annotation_evidence_required")
        for ref in obligation["evidence"]:
            fields(ref, {"path", "sha256", "locator"})
            safe_relative_path(ref["path"])
            if ref["path"] not in known:
                raise ContractError("annotation_evidence_not_in_material")
            if ref["sha256"] != known[ref["path"]]:
                raise ContractError("annotation_evidence_hash_mismatch")
            if not label(ref["locator"]):
                raise ContractError("annotation_evidence_locator_required")


def validate_review(review, packet):
    fields(review, REVIEW_FIELDS)
    meta = load_packet(packet)
    if review["schema_version"] != "p1-independent-review-1" or review["packet_id"] != meta["packet_id"] or review["material_sha256"] != meta["material_sha256"]:
        raise ContractError("review_packet_mismatch")
    if not label(review["reviewer_id"]) or not valid_time(review["reviewed_at"]) or review["decision"] is None:
        raise ContractError("review_incomplete")
    if review["human_review_attestation"] is not True or review["independence_attestation"] is not True or review["method_outputs_seen"] is not False:
        raise ContractError("review_attestation_required")
    if review["decision"] not in DECISIONS or review["material_completeness"] not in {"complete_workflow", "incomplete_workflow"}:
        raise ContractError("invalid_review_decision")
    if not isinstance(review["gaps"], list) or any(not label(x) for x in review["gaps"]) or (review["material_completeness"] == "incomplete_workflow" and not review["gaps"]):
        raise ContractError("review_gaps_required")
    check_obligations(review["critical_obligations"], packet)
    return {"structurally_complete": True, "review_sha256": digest(review), "human_identity_verified": False,
            "research_task_accepted": False, "method_blinding_independently_verified": False}


def assessment(review):
    return {key: review[key] for key in ("decision", "material_completeness", "critical_obligations", "gaps")}


def validate_pair(bundle, reviews, adjudication):
    bundle = Path(bundle)
    mapping = read_json(bundle / "controller/mapping.json")
    if not isinstance(reviews, list) or len(reviews) != 2 or len(mapping.get("reviews", [])) != 2:
        raise ContractError("exactly_two_review_records_required")
    packets, receipts = [], []
    for slot, review in zip(mapping["reviews"], reviews):
        safe_relative_path(slot["packet_id"])
        packet = bundle / "reviewers" / slot["packet_id"]
        meta = load_packet(packet)
        if digest(meta) != slot["packet_sha256"] or meta["material_sha256"] != mapping.get("material_sha256"):
            raise ContractError("assignment_binding_mismatch")
        packets.append(packet)
        receipts.append(validate_review(review, packet))
    reviewers = {identity(x["reviewer_id"]) for x in reviews}
    if len(reviewers) != 2:
        raise ContractError("distinct_reviewers_required")
    if adjudication is None:
        raise ContractError("adjudication_required")
    fields(adjudication, ADJUDICATION_FIELDS)
    if adjudication["schema_version"] != "p1-adjudication-1" or adjudication["material_sha256"] != mapping["material_sha256"]:
        raise ContractError("adjudication_material_mismatch")
    if adjudication["review_sha256"] != [x["review_sha256"] for x in receipts]:
        raise ContractError("adjudication_review_hash_mismatch")
    if not label(adjudication["adjudicator_id"]) or identity(adjudication["adjudicator_id"]) in reviewers:
        raise ContractError("independent_adjudicator_required")
    if (not valid_time(adjudication["adjudicated_at"]) or adjudication["human_review_attestation"] is not True
            or adjudication["method_outputs_seen"] is not False):
        raise ContractError("adjudication_attestation_required")
    if adjudication["resolution"] not in {"confirmed_agreement", "resolved_disagreement"}:
        raise ContractError("explicit_resolution_required")
    disagreement = assessment(reviews[0]) != assessment(reviews[1])
    if disagreement and adjudication["resolution"] != "resolved_disagreement":
        raise ContractError("disagreement_requires_resolution")
    if not label(adjudication["rationale"]) or adjudication["decision"] not in DECISIONS:
        raise ContractError("adjudication_rationale_required")
    if not isinstance(adjudication["remaining_gaps"], list) or any(not label(x) for x in adjudication["remaining_gaps"]):
        raise ContractError("invalid_adjudication_gaps")
    check_obligations(adjudication["resolved_obligations"], packets[0])
    return {"schema_version": 1, "structurally_complete": True, "independent_review_records": 2,
            "adjudication_sha256": digest(adjudication), "review_sha256": [x["review_sha256"] for x in receipts],
            "material_sha256": mapping["material_sha256"], "disagreement_recorded": disagreement,
            "human_identity_verified": False, "method_blinding_independently_verified": False,
            "research_task_accepted": False, "frozen": False, "model_requests": 0,
            "remaining_external_checks": ["verify_actual_human_identities_and_independence", "verify_blinding_procedure",
                                          "evaluate_obligation_semantics_and_coverage", "complete_workflow_acceptance",
                                          "freeze_final_labels_before_arm_outputs"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("prepare")
    make.add_argument("--package", type=Path, required=True)
    make.add_argument("--output", type=Path, required=True)
    make.add_argument("--assignment-seed", required=True)
    review = sub.add_parser("validate-review")
    review.add_argument("--packet", type=Path, required=True)
    review.add_argument("--review", type=Path, required=True)
    pair = sub.add_parser("validate-pair")
    pair.add_argument("--bundle", type=Path, required=True)
    pair.add_argument("--review", type=Path, action="append", required=True)
    pair.add_argument("--adjudication", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare(args.package, args.output, assignment_seed=args.assignment_seed)
        elif args.command == "validate-review":
            result = validate_review(read_json(args.review), args.packet)
        else:
            result = validate_pair(args.bundle, [read_json(x) for x in args.review],
                                   read_json(args.adjudication) if args.adjudication else None)
        print(canonical(result))
        return 0
    except (ContractError, OSError, UnicodeError, KeyError, TypeError) as exc:
        code = str(exc) if isinstance(exc, ContractError) else type(exc).__name__
        print(canonical({"error": code, "research_task_accepted": False, "frozen": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
