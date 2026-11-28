#!/usr/bin/env python3
"""Prepare inspectable P1 development material, without running an agent.

The package is a controller artifact. Only its verified public/ subtree may be
mounted into a method process. Hash checks are integrity checks, not an OS
sandbox, a human review, or evidence of a native-compaction experiment.
"""

import argparse
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile


class ContractError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ContractError("duplicate_json_property")
            result[key] = value
        return result

    def nonfinite(_):
        raise ContractError("nonfinite_json_number")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ContractError("invalid_json") from exc


def read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ContractError("unsafe_json_file")
    return strict_json(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n")
    path.chmod(0o644)


def fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise ContractError("unexpected_fields")


def label(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 2000


def safe_relative_path(value):
    if (not isinstance(value, str) or not value or "\\" in value or "\0" in value
            or value != str(PurePosixPath(value)) or PurePosixPath(value).is_absolute()
            or any(p in {"", ".", ".."} for p in value.split("/"))):
        raise ContractError("unsafe_relative_path")
    return value


def public_path(value):
    safe_relative_path(value)
    for part in value.split("/"):
        low = part.lower()
        if low in {".git", ".hg", ".svn", "evaluator", "private", "controller", "gold"} or low == ".env" or low.startswith(".env."):
            raise ContractError("private_public_path")
    return value


def inventory(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ContractError("unsafe_public_file")
    entries, total = [], 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        public_path(relative)
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
            raise ContractError("unsafe_public_file")
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise ContractError("unsafe_public_file")
        row = {"path": relative, "mode": stat.S_IMODE(info.st_mode), "kind": "directory" if path.is_dir() else "file"}
        if path.is_file():
            data = path.read_bytes()
            row.update({"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            total += len(data)
        entries.append(row)
        if total > 256 * 1024 * 1024 or len(entries) > 20000:
            raise ContractError("public_package_size_limit")
    return entries


def private_inventory(root):
    entries = []
    for domain in ("controller", "evaluator"):
        path = Path(root) / domain
        if path.is_symlink() or not path.is_dir():
            raise ContractError("unsafe_private_file")
        for item in sorted(path.rglob("*")):
            info = item.lstat()
            if item.is_symlink() or not (item.is_file() or item.is_dir()) or (item.is_file() and info.st_nlink != 1):
                raise ContractError("unsafe_private_file")
            if item.is_file():
                data = item.read_bytes()
                entries.append({"path": item.relative_to(root).as_posix(), "bytes": len(data),
                                "sha256": hashlib.sha256(data).hexdigest()})
    return entries


BUDGET_NUMBERS = {
    "max_initial_context_bytes", "max_source_open_bytes_total", "max_source_open_bytes_per_call",
    "max_source_open_calls", "max_tool_calls", "max_model_input_tokens", "max_model_output_tokens", "max_wall_seconds",
}
PRIVATE_JSON_KEYS = {
    "claims", "case.claims", "gold", "gold_claims", "answer_key", "critical_obligations", "expected_behavior",
    "correct_source_id", "correct_source_ids", "is_latest", "supports_claim", "fail_to_pass", "pass_to_pass",
    "source_fix_commit", "fix_commit", "test_patch", "solution_patch",
}
PRIVATE_VALUE_KEYS = {
    "source_fix_commit", "fix_commit", "pr_url", "candidate_id", "source_candidate_id", "test_patch", "solution_patch",
}


def reject_private_json_keys(value):
    if isinstance(value, dict):
        if any(key.lower() in PRIVATE_JSON_KEYS for key in value):
            raise ContractError("evaluator_field_in_public_json")
        for child in value.values():
            reject_private_json_keys(child)
    elif isinstance(value, list):
        for child in value:
            reject_private_json_keys(child)


def private_literals(spec):
    needles = set(spec["forbidden_public_literals"])

    def collect(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in PRIVATE_VALUE_KEYS and isinstance(child, str) and len(child) >= 8:
                    needles.add(child)
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(spec["controller"])
    collect(spec["evaluator"])
    return needles


def validate_budget(value):
    fields(value, BUDGET_NUMBERS | {"schema_version", "frozen", "scope", "reader_model", "tokenizer"})
    if value["schema_version"] != 1 or value["frozen"] is not False or value["scope"] != "continuation_per_arm":
        raise ContractError("development_budget_must_be_unfrozen")
    if any(type(value[k]) is not int or value[k] < 1 for k in BUDGET_NUMBERS):
        raise ContractError("invalid_budget_limit")
    if any(value[k] is not None and not label(value[k]) for k in ("reader_model", "tokenizer")):
        raise ContractError("invalid_reader_declaration")
    if value["max_source_open_bytes_per_call"] > value["max_source_open_bytes_total"]:
        raise ContractError("source_page_exceeds_total_budget")
    if value["max_source_open_calls"] > value["max_tool_calls"]:
        raise ContractError("source_calls_exceed_tool_budget")
    return value


def validate_archive(text):
    required = {"event_id", "sequence", "native_role", "principal", "source_name", "body", "capture_kind"}
    optional = {"object_id", "object_revision", "artifact_sha256", "occurred_at", "completion"}
    ids, sequences = set(), set()
    for line in text.splitlines():
        if not line.strip():
            raise ContractError("blank_archive_record")
        event = strict_json(line)
        if not isinstance(event, dict) or not required <= set(event) or set(event) - required - optional:
            raise ContractError("invalid_archive_fields")
        reject_private_json_keys(event)
        if any(isinstance(event[key], (dict, list)) for key in optional if key in event):
            raise ContractError("invalid_archive_metadata")
        if event["capture_kind"] != "synthetic_fixture":
            raise ContractError("synthetic_capture_kind_required")
        if (not all(label(event[k]) for k in ("event_id", "native_role", "principal", "source_name"))
                or not isinstance(event["body"], str) or not event["body"]
                or event["native_role"] not in {"user", "assistant", "tool", "system"}
                or type(event["sequence"]) is not int or event["sequence"] < 1):
            raise ContractError("invalid_archive_record")
        if event["event_id"] in ids or event["sequence"] in sequences:
            raise ContractError("duplicate_archive_event")
        ids.add(event["event_id"])
        sequences.add(event["sequence"])
    if not ids:
        raise ContractError("empty_archive")


def validate_spec(spec):
    fields(spec, {"schema_version", "task_id", "project_id", "workflow_family_id", "kind", "request", "budget",
                  "public_files", "source", "controller", "evaluator", "forbidden_public_literals"})
    if spec["schema_version"] != 1 or not all(label(spec[k]) for k in ("task_id", "project_id", "workflow_family_id")):
        raise ContractError("invalid_package_identity")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", spec["task_id"]):
        raise ContractError("invalid_public_task_handle")
    if spec["kind"] not in {"synthetic_fixture", "real_source_seed"}:
        raise ContractError("unsupported_material_kind")
    if not isinstance(spec["request"], str) or not spec["request"].strip():
        raise ContractError("natural_request_required")
    validate_budget(spec["budget"])
    if not isinstance(spec["public_files"], dict) or not isinstance(spec["controller"], dict) or not isinstance(spec["evaluator"], dict):
        raise ContractError("invalid_package_material")
    needles = spec["forbidden_public_literals"]
    if not isinstance(needles, list) or any(not isinstance(x, str) or len(x) < 8 for x in needles):
        raise ContractError("invalid_leak_guard")
    if spec["evaluator"].get("status") != "draft_unreviewed" or spec["evaluator"].get("human_reviews") != [] or spec["evaluator"].get("adjudication") is not None:
        raise ContractError("preparation_cannot_claim_annotation")
    if spec["kind"] == "real_source_seed":
        if spec["public_files"]:
            raise ContractError("source_seed_overlay_forbidden")
        source = spec["source"]
        fields(source, {"repository_url", "base_commit", "include", "required_notices"}, {"exclude"})
        if not label(source["repository_url"]) or not re.fullmatch(r"[0-9a-f]{40}", source["base_commit"]):
            raise ContractError("fixed_source_commit_required")
        if any(not isinstance(source.get(key, []), list) for key in ("include", "required_notices", "exclude")) or not source["include"] or not source["required_notices"]:
            raise ContractError("source_whitelist_and_notice_required")
        for pattern in source["include"] + source["required_notices"]:
            public_path(pattern)
        for pattern in source.get("exclude", []):
            safe_relative_path(pattern)
    else:
        if spec["source"] is not None:
            raise ContractError("synthetic_source_must_be_null")
        for path, text in spec["public_files"].items():
            public_path(path)
            if (path != "archive.jsonl" and not path.startswith("workspace/")) or not isinstance(text, str):
                raise ContractError("public_file_not_allowlisted")
        if "archive.jsonl" not in spec["public_files"] or not any(p.startswith("workspace/") for p in spec["public_files"]):
            raise ContractError("synthetic_workspace_and_archive_required")
        validate_archive(spec["public_files"]["archive.jsonl"])
    return spec


def git_output(repo, *args):
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8", "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_OPTIONAL_LOCKS": "0"}
    command = ["git", "--literal-pathspecs", "-C", str(repo), "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", *args]
    result = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False)
    if result.returncode:
        raise ContractError("fixed_source_git_read_failed")
    return result.stdout


def export_source(source, repo, workspace):
    if repo is None:
        raise ContractError("local_source_repository_required")
    commit = source["base_commit"]
    if git_output(repo, "rev-parse", "--verify", commit + "^{commit}").decode().strip() != commit:
        raise ContractError("source_commit_mismatch")
    entries, excluded = [], []
    for raw in git_output(repo, "ls-tree", "-r", "-z", "--full-tree", commit).split(b"\0"):
        if not raw:
            continue
        meta, encoded_path = raw.split(b"\t", 1)
        mode, kind, oid = meta.decode("ascii").split()
        path = encoded_path.decode("utf-8")
        if not any(fnmatch.fnmatchcase(path, pattern) for pattern in source["include"]):
            continue
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in source.get("exclude", [])):
            excluded.append({"path": path, "git_blob": oid, "reason": "explicit_source_exclusion"})
            continue
        public_path(path)
        if mode not in {"100644", "100755"} or kind != "blob":
            raise ContractError("source_tree_not_regular")
        data = git_output(repo, "cat-file", "blob", oid)
        target = workspace / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(data)
        target.chmod(0o755 if mode == "100755" else 0o644)
        entries.append({"path": path, "git_blob": oid, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    paths = {x["path"] for x in entries}
    if not entries or not set(source["required_notices"]) <= paths:
        raise ContractError("required_notice_not_exported")
    return {"schema_version": 1, **source, "export_method": "git_ls_tree_then_cat_file_exact_base_blobs",
            "working_tree_used": False, "git_history_exported": False, "files": sorted(entries, key=lambda x: x["path"]),
            "excluded_files": sorted(excluded, key=lambda x: x["path"])}


def public_descriptor(spec):
    return {"schema_version": "p1-public-task-1", "task_handle": spec["task_id"], "material_kind": spec["kind"],
            "request_path": "request.txt", "workspace_path": "workspace", "budget_path": "budget.json",
            "archive_path": "archive.jsonl" if spec["kind"] == "synthetic_fixture" else None}


def check_public(root, spec):
    public = Path(root) / "public"
    entries = inventory(public)
    if read_json(public / "task.json") != public_descriptor(spec) or read_json(public / "budget.json") != spec["budget"]:
        raise ContractError("public_descriptor_mismatch")
    if (public / "request.txt").read_text(encoding="utf-8") != spec["request"].rstrip() + "\n":
        raise ContractError("public_request_mismatch")
    initial = sum((public / name).stat().st_size for name in ("task.json", "request.txt", "budget.json"))
    if initial > spec["budget"]["max_initial_context_bytes"]:
        raise ContractError("initial_context_budget_exceeded")
    needles = [x.encode() for x in private_literals(spec)]
    for row in entries:
        if row["kind"] == "file":
            data = (public / row["path"]).read_bytes()
            if any(needle in data for needle in needles):
                raise ContractError("forbidden_public_literal")
            # Exact base blobs are verified separately. Authored public JSON must
            # not hide evaluator fields inside a nominal workspace data file.
            if row["path"].endswith(".json") and (spec["kind"] == "synthetic_fixture" or not row["path"].startswith("workspace/")):
                reject_private_json_keys(strict_json(data.decode("utf-8")))
    if spec["kind"] == "synthetic_fixture":
        validate_archive((public / "archive.jsonl").read_text())
    else:
        source = read_json(Path(root) / "controller/source-export.json")
        expected = {"workspace/" + x["path"]: x["sha256"] for x in source["files"]}
        actual = {x["path"]: x["sha256"] for x in entries if x["kind"] == "file" and x["path"].startswith("workspace/")}
        if actual != expected:
            raise ContractError("source_blob_inventory_mismatch")
    return entries


def build_package(spec, output, *, source_repo=None):
    validate_spec(spec)
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ContractError("output_already_exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".p1-taskpack-", dir=output.parent))
    try:
        for name in ("public", "public/workspace", "controller", "evaluator"):
            (stage / name).mkdir(parents=True, exist_ok=True)
        write_json(stage / "public/task.json", public_descriptor(spec))
        write_json(stage / "public/budget.json", spec["budget"])
        (stage / "public/request.txt").write_text(spec["request"].rstrip() + "\n", encoding="utf-8")
        if spec["source"] is not None:
            exported = export_source(spec["source"], source_repo, stage / "public/workspace")
            write_json(stage / "controller/source-export.json", exported)
        for path, text in sorted(spec["public_files"].items()):
            target = stage / "public" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        write_json(stage / "controller/spec.json", spec)
        write_json(stage / "evaluator/blueprint.json", spec["evaluator"])
        for path in stage.rglob("*"):
            path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
        public_files = check_public(stage, spec)
        private_files = private_inventory(stage)
        manifest = {"schema_version": "p1-taskpack-1", "domain": "controller_evaluator_only",
                    **{key: spec[key] for key in ("task_id", "project_id", "workflow_family_id", "kind")},
                    "status": "prepared_unaccepted", "accepted": False, "frozen": False,
                    "public_sha256": digest(public_files), "public_files": public_files,
                    "private_sha256": digest(private_files), "private_files": private_files}
        write_json(stage / "manifest.json", manifest)
        validate_package(stage)
        stage.chmod(0o755)
        stage.rename(output)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return validate_package(output)


def validate_package(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir() or {x.name for x in root.iterdir()} != {"manifest.json", "public", "controller", "evaluator"}:
        raise ContractError("invalid_package_root")
    manifest = read_json(root / "manifest.json")
    if manifest.get("schema_version") != "p1-taskpack-1" or manifest.get("status") != "prepared_unaccepted" or manifest.get("accepted") is not False or manifest.get("frozen") is not False:
        raise ContractError("preparation_cannot_claim_acceptance")
    public_files = inventory(root / "public")
    if public_files != manifest.get("public_files") or digest(public_files) != manifest.get("public_sha256"):
        raise ContractError("public_inventory_mismatch")
    private_files = private_inventory(root)
    if private_files != manifest.get("private_files") or digest(private_files) != manifest.get("private_sha256"):
        raise ContractError("private_inventory_mismatch")
    spec = validate_spec(read_json(root / "controller/spec.json"))
    if any(manifest.get(key) != spec[key] for key in ("task_id", "project_id", "workflow_family_id", "kind")):
        raise ContractError("package_identity_mismatch")
    check_public(root, spec)
    gates = ["actual_native_prelude_missing", "native_compaction_receipt_missing", "post_retrieval_behavior_trace_missing",
             "independent_double_review_missing", "adjudication_missing", "hidden_p1_behavior_check_not_executed",
             "shared_reader_and_tokenizer_unfrozen", "arm_runner_not_integrated", "study_budget_and_assignment_unfrozen"]
    if spec["kind"] == "synthetic_fixture":
        gates.append("synthetic_fixture_is_not_real_pilot_source")
    else:
        gates.append("relevant_workflow_state_change_not_captured")
    return {"schema_version": 1, "validation": "pass", "task_id": spec["task_id"], "project_id": spec["project_id"],
            "workflow_family_id": spec["workflow_family_id"], "kind": spec["kind"], "public_sha256": digest(public_files),
            "public_file_count": sum(x["kind"] == "file" for x in public_files),
            "public_bytes": sum(x.get("bytes", 0) for x in public_files), "budget_sha256": digest(spec["budget"]),
            "model_requests": 0, "isolation_enforced_by_packager": False,
            "acceptance": {"stage": "ready_for_acceptance_review", "accepted": False, "frozen": False,
                           "eligible_for_pilot": False, "independent_human_reviews": 0, "blocking_gates": gates}}


def copy_public(source, output):
    """Copy only verified ordinary files; caller rechecks the resulting hash."""
    source, output = Path(source), Path(output)
    rows = inventory(source)
    if output.exists() or output.is_symlink():
        raise ContractError("output_already_exists")
    output.mkdir(parents=True)
    try:
        for row in rows:
            target = output / row["path"]
            if row["kind"] == "directory":
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as handle:
                    handle.write((source / row["path"]).read_bytes())
            target.chmod(row["mode"])
        if inventory(output) != rows or inventory(source) != rows:
            raise ContractError("public_changed_during_copy")
    except BaseException:
        shutil.rmtree(output, ignore_errors=True)
        raise
    return rows


def export_public(package, output):
    result = validate_package(package)
    rows = copy_public(Path(package) / "public", output)
    if digest(rows) != result["public_sha256"]:
        shutil.rmtree(output, ignore_errors=True)
        raise ContractError("public_changed_during_copy")
    return {"public_sha256": digest(rows), "public_path": str(Path(output).resolve()), "model_requests": 0,
            "isolation_enforced_by_packager": False}


def draft_plan(packages, arms, replicates):
    # Reuse the existing freezer's algorithm instead of calling a different
    # digest by the same name at the integration boundary. This import is pure.
    from experiment import public_digest as experiment_public_digest
    if not arms or len(arms) != len(set(arms)) or any(a not in {"A", "B", "C", "D", "T"} for a in arms):
        raise ContractError("invalid_arms")
    if type(replicates) is not int or replicates < 1 or not packages:
        raise ContractError("invalid_replicates_or_packages")
    tasks, units, families, identities, budget_hashes, reports = [], [], set(), set(), set(), []
    for package in packages:
        report = validate_package(package)
        if report["task_id"] in identities:
            raise ContractError("duplicate_task_id")
        if report["workflow_family_id"] in families:
            raise ContractError("duplicate_workflow_family")
        identities.add(report["task_id"])
        families.add(report["workflow_family_id"])
        budget_hashes.add(report["budget_sha256"])
        reports.append(report)
        public = str((Path(package) / "public").resolve())
        freezer_hash = experiment_public_digest(Path(public))
        task = {"task_id": report["task_id"], "project_id": report["project_id"],
                "public_by_replicate": {str(r): public for r in range(1, replicates + 1)}}
        tasks.append(task)
        for replicate in range(1, replicates + 1):
            for arm in arms:
                units.append({"task_id": task["task_id"], "project_id": task["project_id"], "arm": arm, "replicate": replicate,
                              "public_sha256": freezer_hash, "taskpack_public_sha256": report["public_sha256"]})
    if len(budget_hashes) != 1:
        raise ContractError("budget_contract_mismatch")
    return {"schema_version": "p1-draft-task-fragment-1", "domain": "controller_only", "study_phase": "development",
            "frozen": False, "mode": "structural_dryrun_no_runner", "model_requests": 0, "planned_units": len(units),
            "material_family_count": len(families), "accepted_p1_task_count": 0,
            "real_source_family_count": sum(r["kind"] == "real_source_seed" for r in reports),
            "synthetic_family_count": sum(r["kind"] == "synthetic_fixture" for r in reports),
            "shared_budget_sha256": next(iter(budget_hashes)),
            "experiment_spec_fragment": {"tasks": tasks, "arms": list(arms), "replicates": replicates}, "units": units,
            "missing_before_experiment_freeze": ["real_arm_runner", "shared_reader_and_tokenizer",
                                                 "complete_frozen_measurement_declaration", "native_prelude_and_branching_design",
                                                 "reviewed_hidden_behavior_checks", "workflow_acceptance"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--spec", type=Path, required=True)
    build.add_argument("--repo", type=Path)
    build.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("validate")
    check.add_argument("--package", type=Path, required=True)
    export = sub.add_parser("export-public")
    export.add_argument("--package", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    plan = sub.add_parser("draft-plan")
    plan.add_argument("--package", type=Path, action="append", required=True)
    plan.add_argument("--arms", nargs="+", default=["A", "B", "C", "D"])
    plan.add_argument("--replicates", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build_package(read_json(args.spec), args.output, source_repo=args.repo)
        elif args.command == "validate":
            result = validate_package(args.package)
        elif args.command == "export-public":
            result = export_public(args.package, args.output)
        else:
            result = draft_plan(args.package, args.arms, args.replicates)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ContractError, OSError, UnicodeError, subprocess.SubprocessError) as exc:
        code = str(exc) if isinstance(exc, ContractError) else type(exc).__name__
        print(json.dumps({"error": code, "model_requests": 0, "accepted": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
