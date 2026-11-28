#!/usr/bin/env python3
"""Freeze a bounded NOT READY document-source ZIP and supplementary inventory."""
from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
PACKAGE = HERE / "tmlr-review"
RESEARCH = HERE.parent
REPO = HERE.parents[3]
ALLOWLIST = [
    "README.md", "main.pdf", "main.tex", "main.bbl", "abstract.tex", "status.tex",
    "body.tex", "appendices.tex", "abstract.md", "status.md", "body.md", "appendices.md",
    "references.bib", "build.py", "tmlr.sty", "tmlr.bst", "fancyhdr.sty",
    "style-provenance.json", "upstream/LICENSE", "upstream/README.md", "upstream/main.tex",
]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    qa = json.loads((HERE / "qa-report.json").read_text())
    derivation = json.loads((HERE / "derivation.json").read_text())
    if digest((RESEARCH / "manuscript.md").read_bytes()) != derivation["canonical_source_sha256"]:
        raise SystemExit("Canonical manuscript changed; deliberately rederive, rebuild, and repeat QA before freezing.")
    if digest((RESEARCH / "references.bib").read_bytes()) != derivation["canonical_bibliography_sha256"]:
        raise SystemExit("Canonical bibliography changed after derivation.")
    if not all(qa["checks"].values()) or qa["visual_review"]["status"] != "INSPECTED":
        raise SystemExit("Complete and record PDF visual QA before freezing the source ZIP.")
    if digest((PACKAGE / "main.pdf").read_bytes()) != qa["pdf_sha256"]:
        raise SystemExit("PDF changed after QA.")
    contents, records = {}, []
    for name in ALLOWLIST:
        path = PACKAGE / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(PACKAGE.resolve()):
            raise SystemExit(f"Invalid package member: {name}")
        data = path.read_bytes()
        if digest(data) != qa["source_member_sha256"].get(name):
            raise SystemExit(f"Source member changed after QA: {name}")
        contents[name] = data
        records.append({"path": name, "bytes": len(data), "sha256": digest(data)})
    manifest = {
        "schema": 1, "status": "NOT_READY_NOT_SUBMITTED",
        "kind": "document_source_only", "template_commit": "7bf90efe3a0debbba703c05c43f3ff7e4d4a2992",
        "human_origin_condition": "UNRESOLVED", "scientific_artifact_complete": False,
        "files": records,
        "excluded_controller_material": ["author/contribution worksheet", "cover-letter draft",
                                         "canonical identifying provenance", "evaluator/gold data",
                                         "raw datasets", "credentials", "model execution services"],
    }
    inventory = (json.dumps(manifest, indent=2) + "\n").encode()
    contents["PACKAGE_MANIFEST.json"] = inventory
    target = HERE / "review-source.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(contents.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, data)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(contents):
            raise SystemExit("ZIP integrity/member mismatch.")
        for name, data in contents.items():
            if archive.read(name) != data:
                raise SystemExit(f"ZIP byte mismatch: {name}")
    if target.stat().st_size >= 100_000_000 or sum(map(len, contents.values())) >= 100_000_000:
        raise SystemExit("Draft package exceeds conservative 100 MB bound.")
    (HERE / "review-source-manifest.json").write_bytes(inventory)

    available = []
    paths = [
        ("protocol", "docs/research/p1-evidence-verification/PROTOCOL.md"),
        ("analysis_manifest_schema", "docs/research/p1-evidence-verification/schemas/study-manifest.schema.json"),
        ("analysis_run_schema", "docs/research/p1-evidence-verification/schemas/run.schema.json"),
        ("source_candidates", "docs/research/p1-evidence-verification/tasks/acquisition/candidate-manifest.json"),
        ("environment_reproduction", "docs/research/p1-evidence-verification/tasks/reproduction/summary.json"),
        ("expanded_source_environment_qualification", "docs/research/p1-evidence-verification/tasks/reproduction-expansion/summary.json"),
        ("unaccepted_workflow_drafts", "docs/research/p1-evidence-verification/tasks/workflows/catalog.json"),
        ("blocked_live_components", "docs/research/p1-evidence-verification/artifacts/live-native/manifest.json"),
        ("readonly_native_development", "docs/research/p1-evidence-verification/artifacts/readonly-native/attempt-01/summary.json"),
        ("readonly_native_usage_audit", "docs/research/p1-evidence-verification/artifacts/readonly-native/usage-audit.json"),
    ]
    for category, relative in paths:
        path = REPO / relative
        exists = path.is_file()
        available.append({"category": category, "controller_path": relative,
                          "state": "available_not_in_review_source_zip" if exists else "not_present",
                          "sha256": digest(path.read_bytes()) if exists else None,
                          "reason": "Requires a separately frozen, permitted, review-safe scientific artifact; availability is not readiness."})
    supplementary = {
        "schema": 1, "status": "NOT_READY_NOT_SUBMITTED",
        "candidate_archive": {"path": "review-source.zip", "kind": "document_source_only",
                              "sha256": digest(target.read_bytes()), "bytes": target.stat().st_size,
                              "uncompressed_bytes": sum(map(len, contents.values())),
                              "members": len(contents), "zip_integrity": "verified",
                              "under_100_MB": True, "uploaded": False},
        "document_qa_pdf_sha256": qa["pdf_sha256"],
        "available_controller_material": available,
        "outstanding_scientific_categories": [
            "Verified human-origin and contribution record; factual author declarations.",
            "Accepted/frozen P1 workflow definitions and public/evaluator separation.",
            "Independent human labels and adjudication with permitted review access.",
            "Immutable implementation/configuration snapshot covering the actual final study.",
            "All scheduled attempts, failures, native receipts, delivered evidence, and scored outcomes.",
            "Reconciled resource meters/rates and complete uncertainty/outcome analysis, or narrowed claims.",
            "Human source-rights/anonymity review and exact final author-approved artifact hashes.",
        ],
        "human_origin_condition": "UNRESOLVED", "complete_study_artifact": False,
        "scientific_effect_claim": None, "submission_action_performed": False,
    }
    (HERE / "supplementary-manifest.json").write_text(json.dumps(supplementary, indent=2) + "\n")
    print(json.dumps(supplementary["candidate_archive"]))


if __name__ == "__main__":
    main()
