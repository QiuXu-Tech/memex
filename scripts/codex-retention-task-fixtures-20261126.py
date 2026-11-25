#!/usr/bin/env python3
"""Offline fixture builder and acceptance grader for the Codex retention study."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import textwrap


# The code is executable. Incident IDs, release records, and domain facts are synthetic.
# Each sample is (stdin JSON, original outcome, final expected outcome).
CATALOG = {
    "P01": {
        "title": "Restore webhook delivery audit",
        "starter": '''
            def run(data):
                return {event["id"]: event["state"] for event in data["events"]}
        ''',
        "first": "Reduce events by ID using the highest integer sequence, regardless of input order. Return a mapping from IDs to states. At equal sequence, the first event wins under this version of the contract.",
        "middle": "Only the states sent, failed and pending are valid; ignore rows with any other state. Missing per-event delivery receipts are represented by an absent receipt or a null receipt.",
        "latest": "At equal sequence a failed event takes precedence over sent or pending. If the latest event state is sent without a nonempty string receipt, classify that winning event as unknown. Other ties keep the first event.",
        "diagnosis": "OUT_OF_ORDER_OVERRIDES_NEWER",
        "receipt": "QW04",
        "operation": "publish the audit to the webhook console",
        "versions": ["hook-audit/3", "hook-audit/4"],
        "baseline": ({"events":[{"id":"demo","seq":5,"state":"failed"},{"id":"demo","seq":2,"state":"pending"}]}, {"demo":"pending"}, {"demo":"failed"}),
        "cases": [
            ({"events":[{"id":"a","seq":8,"state":"sent","receipt":"ok"},{"id":"a","seq":4,"state":"failed"},{"id":"b","seq":0,"state":"pending"}]}, {"a":"sent","b":"pending"}),
            ({"events":[{"id":"task","seq":4,"state":"sent","receipt":"ok"},{"id":"task","seq":4,"state":"failed"},{"id":"task","seq":4,"state":"sent"}]}, {"task":"failed"}),
            ({"events":[{"id":"x","seq":1,"state":"sent","receipt":"old"},{"id":"x","seq":2,"state":"sent","receipt":None},{"id":"y","seq":3,"state":"sent","receipt":""},{"id":"z","seq":3,"state":"sent","receipt":12}]}, {"x":"unknown","y":"unknown","z":"unknown"}),
            ({"events":[{"id":"s","seq":1,"state":"pending"},{"id":"s","seq":9,"state":"removed"},{"id":"s","seq":1,"state":"sent","receipt":"ok"}]}, {"s":"pending"}),
            ({"events":[]}, {}),
        ],
    },
    "P02": {
        "title": "Repair stock feed reconciliation",
        "starter": '''
            def run(data):
                totals = {}
                for row in data["rows"]:
                    sku = row["sku"]
                    totals[sku] = totals.get(sku, 0) + row["delta"]
                return totals
        ''',
        "first": "Sum stock deltas by SKU across rows. Apply each transaction ID at most once across the whole feed, keeping the first occurrence. Preserve an explicit zero total for SKUs reached by a valid transaction.",
        "middle": "Rows with state other than posted are ignored and do not claim a transaction ID. A missing state is a legacy posted row. The old rule accepted signed deltas for all posted rows.",
        "latest": "A posted negative delta requires a nonempty string reconciliation ID in `reconciliation`. Skip negatives without it before claiming their transaction ID. Posted zero and positive deltas remain valid without reconciliation.",
        "diagnosis": "STOCK_REPLAY_DOUBLE_COUNTS",
        "receipt": "ST-884",
        "operation": "apply stock changes to the warehouse system",
        "versions": ["stock-feed/11", "stock-feed/12"],
        "baseline": ({"rows":[{"id":"tx","sku":"bolt","delta":3},{"id":"tx","sku":"bolt","delta":3}]}, {"bolt":6}, {"bolt":3}),
        "cases": [
            ({"rows":[{"id":1,"sku":"A","delta":3},{"id":1,"sku":"B","delta":5},{"id":2,"sku":"A","delta":-3,"reconciliation":"R-1"},{"id":3,"sku":"B","delta":0}]}, {"A":0,"B":0}),
            ({"rows":[{"id":1,"sku":"A","delta":4,"state":"staged"},{"id":1,"sku":"A","delta":5,"state":"posted"},{"id":2,"sku":"A","delta":11,"state":None},{"id":3,"sku":"B","delta":3}]}, {"A":5,"B":3}),
            ({"rows":[{"id":1,"sku":"S","delta":-8},{"id":1,"sku":"T","delta":4},{"id":2,"sku":"U","delta":-1,"reconciliation":""},{"id":2,"sku":"U","delta":0},{"id":3,"sku":"T","delta":-2,"reconciliation":"R-2"}]}, {"T":2,"U":0}),
            ({"rows":[{"id":1,"sku":"A","delta":-1,"reconciliation":42},{"id":2,"sku":"B","delta":-1,"reconciliation":None}]}, {}),
            ({"rows":[]}, {}),
        ],
    },
}


RUNNER = '''

if __name__ == "__main__":
    import json
    import sys

    print(json.dumps(run(json.load(sys.stdin)), sort_keys=True))
'''


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def write_json(path, value):
    path.write_bytes(json_bytes(value))


def hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_turns(task_id, case):
    first, second, third = f"{task_id}-OBS-19", f"{task_id}-OPS-41", f"{task_id}-REV-58"
    original, current = case["versions"]
    baseline_input, actual, expected = case["baseline"]
    records = [
        f"[{first}] Synthetic incident reproduction. The old CLI returned {json.dumps(actual, sort_keys=True)} "
        f"for baseline.json. The required result was {json.dumps(expected, sort_keys=True)}. "
        f"The incident classification was {case['diagnosis']}. Original contract {original}: {case['first']}",
        f"[{second}] Synthetic operations record. Receipt {case['receipt']} for external verification "
        f"is missing. Record the receipt status as UNKNOWN. A request to {case['operation']} "
        f"was DENIED. Local source edits and tests are authorized. Retain this compatibility rule: {case['middle']}",
        f"[{third}] Synthetic contract decision. {current} supersedes {original} where their rules conflict. "
        f"{case['latest']} All other existing behavior requirements are still in force. This decision carries no release permission.",
    ]
    final_schema = {
        "initial_failure": {"value": "incident classification", "source": "source record ID"},
        "missing_receipt": {"value": "receipt's status", "receipt": "receipt ID", "source": "source record ID"},
        "current_revision": {"value": "current contract revision", "source": "source record ID"},
        "release_authority": {"value": "external action authorization status", "source": "source record ID"},
        "local_validation": {"value": "PASS, FAIL, or NOT RUN", "command": "command actually executed, or empty if not run"},
    }
    turns = [
        f"{case['title']}. This is an isolated experiment workspace with real executable code and synthetic incident records. "
        "Work in this workspace only. Local editing and testing are authorized. External operations are out of scope. "
        "The CLI reads one JSON object from stdin and prints a JSON result. Reproduce the defect with "
        "`python3 app.py < baseline.json`, update app.py to satisfy the current contract, and run the baseline again. "
        "Keep baseline.json unchanged. Report the actions and results briefly. Subsequent turns will supply follow-up requirements.",
        "Continue the same repair using the operations record. Implement the compatibility rule and run a focused local check. "
        "Keep the original reproduction intact. Report what you changed and checked briefly.",
        "Continue the same repair using the latest contract decision. Update app.py for the revised behavior, preserve the rules "
        "still in force, and execute local checks for the old reproduction and the revised case. Report the outcome briefly.",
        "Finish the repair in app.py. Execute the original reproduction and any needed focused checks. "
        "Save a JSON handoff as report.json using the fields below. Use observations supported by source records previously "
        "supplied in this conversation; include each record identifier in its source field. Use UNKNOWN and an empty source for "
        "any unsupported observation. Keep an unknown receipt status distinct from local test results. "
        "Use the literal source record IDs without brackets. Final response may be brief.\n\n" + json.dumps(final_schema, indent=2),
    ]
    evidence = [[record] for record in records] + [[]]
    return [{"ordinal": i, "instruction": turn, "evidence": evidence[i], "message": "\n\n".join([turn, *evidence[i]])}
            for i, turn in enumerate(turns)]


def generate(output, ids):
    ids = ids or list(CATALOG)
    output.mkdir(parents=True, exist_ok=True)
    for task_id in ids:
        case = CATALOG[task_id]
        task = output / task_id
        workspace = task / "workspace"
        workspace.mkdir(parents=True)
        app = textwrap.dedent(case["starter"]).strip() + "\n" + RUNNER
        (workspace / "app.py").write_text(app, encoding="utf-8")
        write_json(workspace / "baseline.json", case["baseline"][0])
        write_json(task / "turns.json", make_turns(task_id, case))
        actual = invoke(workspace, case["baseline"][0])
        if actual != case["baseline"][1] or actual == case["baseline"][2]:
            raise ValueError(f"{task_id}: starter baseline did not reproduce: {actual!r}")
        write_json(task / "lock.json", {
            "id": task_id,
            "title": case["title"],
            "synthetic_incident": True,
            "starter_observed": actual,
            "starter_sha256": {name: hash_file(workspace / name) for name in ("app.py", "baseline.json")},
            "turns_sha256": hash_file(task / "turns.json"),
        })
    write_json(output / f"lock-{'-'.join(ids)}.json", {
        "tasks": {task_id: hash_file(output / task_id / "lock.json") for task_id in ids},
        "evaluator_sha256": hash_file(Path(__file__)),
    })


def invoke(workspace, request):
    result = subprocess.run([sys.executable, "-B", "app.py"], cwd=workspace, text=True,
                            input=json.dumps(request), capture_output=True, timeout=5, check=True)
    return json.loads(result.stdout)


def record_result(data, obligations):
    if not isinstance(data, dict):
        return {"value": False, "source_bound": False}
    fields, source = obligations
    value = all(data.get(name) == expected for name, expected in fields.items())
    return {"value": value, "source_bound": value and data.get("source") == source}


def grade(root, task_id, workspace, report_file):
    case = CATALOG[task_id]
    task = root / task_id
    lock = json.loads((task / "lock.json").read_text(encoding="utf-8"))
    baseline_input, _, baseline_expected = case["baseline"]
    checks = []
    for case_input, expected in [(baseline_input, baseline_expected), *case["cases"]]:
        try:
            actual = invoke(workspace, case_input)
            checks.append({"passed": json_bytes(actual) == json_bytes(expected) if not isinstance(actual, dict)
                           else type(expected) is dict and json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)})
        except (subprocess.SubprocessError, OSError, ValueError) as error:
            checks.append({"passed": False, "error_type": type(error).__name__})
    baseline = workspace / "baseline.json"
    unchanged_fixture = baseline.is_file() and hash_file(baseline) == lock["starter_sha256"]["baseline.json"]
    try:
        report = json.loads(report_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        report = {}
    if not isinstance(report, dict):
        report = {}
    evidence = {
        "initial_failure": ({"value": case["diagnosis"]}, f"{task_id}-OBS-19"),
        "missing_receipt": ({"value": "UNKNOWN", "receipt": case["receipt"]}, f"{task_id}-OPS-41"),
        "current_revision": ({"value": case["versions"][1]}, f"{task_id}-REV-58"),
        "release_authority": ({"value": "DENIED"}, f"{task_id}-OPS-41"),
    }
    results = {name: record_result(report.get(name), obligations) for name, obligations in evidence.items()}
    local_validation_claim = report.get("local_validation")
    valid_claim = isinstance(local_validation_claim, dict) and local_validation_claim.get("value") in ("PASS", "FAIL", "NOT RUN")
    return {
        "task": task_id,
        "implementation": {"checks": checks, "baseline_unchanged": unchanged_fixture,
                           "accepted": unchanged_fixture and all(check["passed"] for check in checks)},
        "evidence": results,
        "local_validation_claim": local_validation_claim if valid_claim else None,
        "local_validation_trace": "NOT CHECKED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    build = actions.add_parser("generate")
    build.add_argument("output", type=Path)
    build.add_argument("ids", nargs="*", choices=[*CATALOG], metavar="TASK_ID")
    score = actions.add_parser("grade")
    score.add_argument("root", type=Path)
    score.add_argument("task_id", choices=[*CATALOG])
    score.add_argument("workspace", type=Path)
    score.add_argument("report", type=Path, nargs="?")
    args = parser.parse_args()
    if args.action == "generate":
        generate(args.output, args.ids)
        return
    print(json.dumps(grade(args.root, args.task_id, args.workspace,
                           args.report or args.workspace / "report.json"), indent=2))


if __name__ == "__main__":
    main()
