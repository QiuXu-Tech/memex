#!/usr/bin/env python3
"""Grade a real Codex run using the frozen scale controls and MCP receipts."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
from statistics import median


def grade(archive, host):
    keys = json.loads((archive / "key.json").read_text())
    facts = json.loads((archive / "manifest.json").read_text())
    report = json.loads((host / "report.json").read_text())
    events = [json.loads(line) for line in (host / "events.jsonl").read_text().splitlines()]
    if report["status"] != "completed" or len(report["turns"]) != 1:
        raise ValueError("Requires a completed single-turn native response")
    final = report["turns"][0]["final"].strip()
    final = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", final, flags=re.I)
    answer = json.loads(final)
    if not isinstance(answer, dict):
        raise ValueError("The response must be a JSON object")
    tool_items = [row["item"] for row in events if row.get("event") == "item/completed"
                  and row.get("item", {}).get("type") == "mcpToolCall"]
    calls = [item for item in tool_items if item.get("server") == "memex"]
    if len(calls) != len(tool_items):
        raise ValueError("Unexpected tool server during archive evaluation")
    outputs = [block["text"] for item in calls for block in (item.get("result") or {}).get("content", [])
               if block.get("type") == "text"]
    open_results = {item["arguments"].get("id"): json.dumps(item.get("result"), ensure_ascii=False)
                    for item in calls if item.get("tool") == "memory_open"
                    and not item.get("error") and not (item.get("result") or {}).get("isError")}
    probes = {}
    for name, expected in keys.items():
        observed = answer.get(name)
        if expected["value"] == "NOT_FOUND":
            correct = observed == "NOT_FOUND"
            cited_and_read = None
        else:
            values = list(observed.values()) if isinstance(observed, dict) else []
            cited_and_read = any(record in values and expected["value"] in open_results.get(record, "")
                                 for record in expected["evidence"])
            required_value = expected["value"] in values
            required_hold = "holdMinutes" not in expected or any(
                type(v) is int and v == expected["holdMinutes"] for v in values)
            correct = required_value and required_hold and cited_and_read
        output_contains_control = any(value in text for value in expected.get("wrongValues", []) for text in outputs)
        scopes_paired = name in ("fern", "indigo")
        probes[name] = {"correct": bool(correct), "answer": observed, "sourceOpenedAndCited": cited_and_read,
                        "scopeControlExposed": output_contains_control if scopes_paired else None,
                        "control": expected["control"]}
    by_tool = Counter(item["tool"] for item in calls)
    timings = {tool: median(item["durationMs"] for item in calls
                            if item.get("tool") == tool and isinstance(item.get("durationMs"), (int, float)))
               for tool in by_tool if any(item.get("tool") == tool and item.get("durationMs") is not None for item in calls)}
    return {
        "status": "scored-live-codex",
        "nominalSize": facts["nominalSize"],
        "tokenizer": facts["tokenizer"],
        "visibleTokens": facts["visibleTokens"], "visibleRecords": facts["visibleRecords"],
        "visibleHot": facts["visibleHot"], "visibleCold": facts["visibleCold"],
        "archiveUsage": facts["archiveUsage"], "datasetSha256": facts["datasetSha256"],
        "timeSeconds": report["turns"][0]["elapsedSeconds"], "tools": dict(by_tool),
        "medianToolMs": timings, "returnedMcpTextChars": sum(len(text) for text in outputs),
        "providerUsage": report["usage"][-1]["tokenUsage"], "requestedModel": report["model"],
        "correct": sum(row["correct"] for row in probes.values()), "total": len(probes), "probes": probes,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("host", type=Path)
    args = parser.parse_args()
    print(json.dumps(grade(args.archive, args.host), ensure_ascii=False, indent=2))
