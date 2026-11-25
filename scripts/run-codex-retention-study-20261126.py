#!/usr/bin/env python3
"""Run isolated, paired Codex retention tasks and preserve every attempted arm."""

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

REPO = Path(__file__).resolve().parent.parent
ORDERS = ("ABC", "BCA", "CAB", "ACB", "CBA", "BAC", "ABC", "BCA")
PILOT_LOCK = "6436f9bd5279bff514cbed75b3481507d28e79fff4020a2cdb732a7f412a8e77"
FORMAL_LOCK = "1da26d5a9e7708ebe2e21726368b080fad39b55394af03e3100befb9afda69be"


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("pilot", "formal"))
    parser.add_argument("tasks", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--jobs", type=int, choices=range(1, 9), default=2)
    args = parser.parse_args()
    root, output = args.tasks.resolve(), args.output.resolve()
    pilot = args.mode == "pilot"
    ids = ("P01", "P02") if pilot else tuple(f"R{i:02}" for i in range(1, 9))
    lock = root / ("lock-" + "-".join(ids) + ".json")
    assert hashlib.sha256(lock.read_bytes()).hexdigest() == (PILOT_LOCK if pilot else FORMAL_LOCK), "Task lock moved"
    output.mkdir(parents=True, exist_ok=False)
    stop = threading.Event()

    def task(task_id, order):
        for arm in order:
            if stop.is_set():
                print(task_id, arm, "NOT RUN: stopped admission", flush=True)
                continue
            task_path = root / task_id
            trial = output / task_id / arm
            workspace = trial / "workspace"
            shutil.copytree(task_path / "workspace", workspace)
            command = [sys.executable, str(REPO / "scripts/codex-retention-host.py"),
                       "--task", str(task_path), "--arm", arm, "--workdir", str(workspace),
                       "--logs", str(trial / "host")]
            if arm != "A":
                command.extend(("--memory-root", str(trial / "archive"),
                                "--memory-session", f"{output.name}-{task_id}-{arm}"))
            if not pilot:
                command.extend(("--stage-controller", str(REPO / "scripts/codex-retention-staged-tasks-20261126.py"),
                                "--task-id", task_id))
            print(task_id, arm, "START", flush=True)
            started = time.monotonic()
            with (trial / "runner.log").open("x") as output_log:
                status = subprocess.run(command, cwd=REPO, stdout=output_log, stderr=subprocess.STDOUT, check=False).returncode
            receipt_file = trial / "host" / "report.json"
            report = read(receipt_file) if receipt_file.exists() else {}
            result = {"task": task_id, "arm": arm, "exit": status, "seconds": time.monotonic() - started,
                      "status": report.get("status", "missing-host-receipt"),
                      "nativeBoundaries": len(report.get("boundaries", [])),
                      "taskTurns": len(report.get("turns", []))}
            result["error"] = report.get("error") or ""
            if status != 0:
                incident = (result["error"] + (trial / "runner.log").read_text() +
                            ((trial / "host" / "host.stderr").read_text() if (trial / "host" / "host.stderr").exists() else "")).lower()
                if any(word in incident for word in ("usage limit", "rate limit", "status 429", "http 429", "login was not verified")):
                    stop.set()
                    result["admissionStopped"] = True
            if status == 0 and report.get("status") == "completed":
                script = "codex-retention-task-fixtures-20261126.py" if pilot else "codex-retention-staged-tasks-20261126.py"
                grade = [sys.executable, str(REPO / "scripts" / script), "grade", str(root), task_id, str(workspace)]
                scored = subprocess.run(grade, cwd=REPO, capture_output=True, text=True, check=False)
                (trial / "grade.log").write_text(scored.stderr)
                if scored.returncode == 0:
                    (trial / "grade.json").write_text(scored.stdout)
                else:
                    (trial / "grade.stdout").write_text(scored.stdout)
                result["gradeExit"] = scored.returncode
            (trial / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
            print(task_id, arm, result["status"], result["nativeBoundaries"], f"{result['seconds']:.1f}s", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        jobs = [pool.submit(task, task_id, ORDERS[index]) for index, task_id in enumerate(ids)]
        for job in jobs:
            job.result()


if __name__ == "__main__":
    main()
