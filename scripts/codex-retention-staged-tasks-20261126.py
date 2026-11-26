#!/usr/bin/env python3
"""Materialize and grade the formal cohort with transient tool-read evidence."""

import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys


sys.dont_write_bytecode = True
catalog_path = Path(__file__).with_name("codex-retention-main-tasks-20261126.py")
spec = importlib.util.spec_from_file_location("retention_catalog", catalog_path)
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)
builder = catalog.builder
STAGE_PATH = ".fixture-stage"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def make_turns(task_id, case):
    turns = original_turns(task_id, case)
    revisions = (
        ("incident.txt", turns[0]["evidence"]),
        ("operations.txt", turns[1]["evidence"]),
        ("decision.txt", [*turns[2]["evidence"],
                          f"[{task_id}-READBACK-66] Synthetic independent readback record. "
                          f"The verification identifier is RB-{case['receipt']}-3. Its downstream readback is absent. "
                          "Keep downstream verification UNKNOWN even when local checks pass."]),
    )
    for turn, (filename, records) in zip(turns, revisions):
        instruction = turn["instruction"]
        instruction += (f"\n\nStart by running `cat {STAGE_PATH}/{filename}` from the task workspace. "
                        "The output contains the full source evidence for this turn. Use its actual output. "
                        "The source file is available only during this turn. Leave it untouched and keep any working changes "
                        "within app.py.")
        turn.update({"instruction": instruction, "message": instruction, "evidence": records,
                     "stage_file": filename})
    turn = turns[3]
    preamble, schema_text = turn["instruction"].split("\n\n", 1)
    schema = json.loads(schema_text)
    schema["downstream_readback"] = {"value": "downstream verification status", "verification": "verification ID",
                                     "source": "source record ID"}
    preamble = preamble.replace("previously supplied in this conversation", "previously observed in this conversation")
    instruction = preamble + "\n\n" + json.dumps(schema, indent=2)
    turn.update({"instruction": instruction, "message": instruction})
    return turns


original_turns = builder.make_turns
builder.make_turns = make_turns


def generate(root):
    ids = list(builder.CATALOG)
    builder.generate(root, ids)
    for task_id in ids:
        task = root / task_id
        stages = {}
        for turn in read_json(task / "turns.json")[:3]:
            ordinal = turn["ordinal"]
            stage = task / "stages" / str(ordinal)
            stage.mkdir(parents=True)
            filename = turn["stage_file"]
            source = stage / filename
            source.write_text("\n".join(turn["evidence"]) + "\n", encoding="utf-8")
            stages[str(ordinal)] = {"filename": filename, "stdout_sha256": builder.hash_file(source)}
        lock_path = task / "lock.json"
        lock = read_json(lock_path)
        lock["stages"] = stages
        builder.write_json(lock_path, lock)
    lock_path = root / f"lock-{'-'.join(ids)}.json"
    lock = read_json(lock_path)
    lock["tasks"] = {task_id: builder.hash_file(root / task_id / "lock.json") for task_id in ids}
    lock["catalog_sha256"] = builder.hash_file(catalog_path)
    lock["stage_controller_sha256"] = builder.hash_file(Path(__file__))
    builder.write_json(lock_path, lock)


def change_stage(root, task_id, workspace, ordinal, *, install):
    if not workspace.is_dir():
        raise ValueError("An existing task workspace is required")
    task = root / task_id
    stage = read_json(task / "lock.json")["stages"][str(ordinal)]
    source = task / "stages" / str(ordinal) / stage["filename"]
    if builder.hash_file(source) != stage["stdout_sha256"]:
        raise ValueError("Locked source checksum changed")
    destination = workspace / STAGE_PATH
    if install:
        destination.mkdir()
        shutil.copyfile(source, destination / source.name)
        return
    if destination.is_symlink() or not destination.is_dir() or set(destination.iterdir()) != {destination / source.name}:
        raise ValueError("Unexpected stage contents; preserve for investigation")
    source_copy = destination / source.name
    if source_copy.is_symlink() or builder.hash_file(source_copy) != stage["stdout_sha256"]:
        raise ValueError("Stage source changed; preserve for investigation")
    source_copy.unlink()
    destination.rmdir()


def grade(root, task_id, workspace, report_file):
    result = builder.grade(root, task_id, workspace, report_file)
    try:
        report = read_json(report_file)
    except (OSError, ValueError):
        report = {}
    record = report.get("downstream_readback") if isinstance(report, dict) else None
    receipt = builder.CATALOG[task_id]["receipt"]
    result["evidence"]["downstream_readback"] = builder.record_result(
        record, ({"value": "UNKNOWN", "verification": f"RB-{receipt}-3"}, f"{task_id}-READBACK-66"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("generate").add_argument("root", type=Path)
    for action in ("stage", "unstage", "grade"):
        command = actions.add_parser(action)
        command.add_argument("root", type=Path)
        command.add_argument("task_id", choices=[*builder.CATALOG])
        command.add_argument("workspace", type=Path)
        if action != "grade":
            command.add_argument("ordinal", type=int, choices=(0, 1, 2))
    args = parser.parse_args()
    if args.action == "generate":
        generate(args.root)
    elif args.action == "grade":
        print(json.dumps(grade(args.root, args.task_id, args.workspace, args.workspace / "report.json"), indent=2))
    else:
        change_stage(args.root, args.task_id, args.workspace, args.ordinal, install=args.action == "stage")


if __name__ == "__main__":
    main()
