#!/usr/bin/env python3
"""Verify the exact study evidence packet in the original same-thread Codex history."""
import argparse
from hashlib import sha256
import json
from pathlib import Path


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from strings(child)


def audit(path, rollout_directory=None):
    report = json.loads(path.read_text(encoding="utf-8"))
    row = {"caseId": report["caseId"], "arm": report["arm"], "status": report["status"]}
    if report["status"] != "completed":
        return row
    rollout = (
        rollout_directory / (report["threadId"] + ".jsonl")
        if rollout_directory
        else Path(report.get("rollout") or "")
    )
    if not rollout.is_file():
        return {**row, "echo": "UNKNOWN", "reason": "named rollout missing"}
    packet = "\n\n".join(gate["injection"] for gate in report["gates"] if gate["injection"])
    match = sha256(packet.encode()).hexdigest() if packet else None
    session = None
    compacted = []
    echoes = []
    staged_lines = (report.get("observedStage") or {}).get("sourceLines", [])
    replacement_receipts = []
    for n, line in enumerate(rollout.read_text(encoding="utf-8").splitlines(), 1):
        decoded = json.loads(line)
        payload = decoded.get("payload", {})
        if decoded.get("type") == "session_meta":
            session = payload.get("id")
        elif decoded.get("type") == "compacted":
            compacted.append(n)
            replacement = list(strings(payload.get("replacement_history", [])))
            replacement_receipts.append(sum(any(line in fragment for fragment in replacement)
                                            for line in staged_lines))
        elif (
            packet
            and decoded.get("type") == "response_item"
            and payload.get("type") == "message"
            and payload.get("role") == "user"
            and any(packet in value for value in strings(payload.get("content", [])))
        ):
            echoes.append(n)
    identity = session == report["threadId"]
    written = bool(
        identity
        and match
        and match == report.get("deliveredEvidenceSha256")
        and compacted
        and len(compacted) == len(report["nativeBoundaries"])
        and len(echoes) == 1
        and echoes[0] > compacted[-1]
    )
    echo = "NO_PACKET"
    if packet:
        echo = "VERIFIED" if written else "MISSING_OR_MISMATCH"
    return {
        **row,
        "echo": echo,
        "threadIdentityMatched": identity,
        "nativeRolloutCompactions": len(compacted),
        "packetSha256": match,
        "matchingLineNumbers": echoes,
        "stagedLinesPerBoundary": len(staged_lines),
        "stagedLinesInPlaintextReplacements": replacement_receipts,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--rollouts", type=Path, help="verified copies, keyed by thread ID")
    args = parser.parse_args()
    rows = [audit(path, args.rollouts) for path in sorted(args.directory.glob("*/*/report.json"))]
    print(json.dumps(rows, ensure_ascii=False, indent=2))
