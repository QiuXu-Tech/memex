#!/usr/bin/env python3
"""Summarize locked fixture grades against actual host events and named rollouts."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shlex


TASKS = {"pilot": ("P01", "P02"), "formal": tuple(f"R{i:02}" for i in range(1, 9))}
ARMS = "ABC"
SOURCES = {"initial_failure": 0, "missing_receipt": 1, "current_revision": 2,
           "release_authority": 1, "downstream_readback": 2}
ABSTENTIONS = {"missing_receipt", "downstream_readback"}


def digest(text):
    return hashlib.sha256(text if isinstance(text, bytes) else text.encode()).hexdigest()


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def read_jsonl(path):
    rows = []
    try:
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        return rows, "INCOMPLETE_OR_INVALID"
    except FileNotFoundError:
        return [], "MISSING"
    return rows, "READ"


def command_text(text):
    try:
        words = shlex.split(text)
    except ValueError:
        return text
    if len(words) == 3 and Path(words[0]).name in {"bash", "zsh", "sh"} and words[1] in {"-c", "-lc"}:
        return words[2]
    return text


def command_key(text):
    try:
        return tuple(shlex.split(command_text(text.strip().strip("`"))))
    except ValueError:
        return ()


def contains_checked_command(shell_text, wanted):
    for line in shell_text.splitlines():
        if command_key(line) == wanted and (line == shell_text or re.search(r"(?m)^set\s+-[a-z]*e", shell_text)):
            return True
        try:
            lexer = shlex.shlex(line, posix=True, punctuation_chars=";&|()")
            lexer.whitespace_split = True
            parts = tuple(lexer)
        except ValueError:
            continue
        if "&&" in parts and not {";", "||", "|", "&"}.intersection(parts):
            start = 0
            for end in [i for i, token in enumerate(parts) if token == "&&"] + [len(parts)]:
                if parts[start:end] == wanted:
                    return True
                start = end + 1
    return False


def item(r):
    return r.get("item", {})


def had_stdout(output, lines):
    actual = output.splitlines()
    return any(actual[i:i + len(lines)] == lines for i in range(len(actual) - len(lines) + 1))


def successful_completed(r):
    return r.get("status") == "completed" and not r.get("error")


def event_rows(events, name, phase=None):
    return [(i, r) for i, r in enumerate(events)
            if r.get("event") == name and (phase is None or r.get("phase") == phase)]


def match_task_and_compact(events, report, task_turns, stages):
    thread = (report or {}).get("threadId")
    starts = event_rows(events, "thread/start")
    valid_identity = bool(thread and len(starts) == 1 and starts[0][1].get("threadId") == thread
                          and starts[0][1].get("model") == report.get("model"))
    finished = [(i, r) for i, r in event_rows(events, "turn/completed") if successful_completed(r)]
    protocol_turns = (report or {}).get("turns", [])
    protocol_boundaries = (report or {}).get("boundaries", [])
    reported_stage_receipts = (report or {}).get("stageReceipts", [])
    commands = [(i, r) for i, r in event_rows(events, "item/completed") if item(r).get("type") == "commandExecution"]
    parsed_turns, compacts, stage_results = [], [], []
    prior_compact = -1
    for n, task_turn in enumerate(task_turns):
        phase = f"task-{n+1}"
        boundary_phase = f"boundary-{n+1}"
        requests = event_rows(events, "turn/request", phase)
        completions = [(i, r) for i, r in finished if r.get("phase") == phase]
        expected_hash = digest(task_turn["message"])
        valid_turn = False
        finish_index = None
        turn_id = completions[0][1].get("turnId") if len(completions) == 1 else None
        if len(requests) == len(completions) == 1:
            finish_index, completion = completions[0]
            recorded = protocol_turns[n] if n < len(protocol_turns) else {}
            hashes = (report or {}).get("messageSha256", [])
            same_thread = completion.get("threadId") == thread
            valid_turn = (valid_identity and same_thread and finish_index > requests[0][0] > prior_compact
                          and requests[0][1].get("messageSha256") == expected_hash
                          and n < len(hashes) and hashes[n] == expected_hash
                          and recorded.get("turnId") == turn_id and recorded.get("ordinal") == n)
        parsed_turns.append(bool(valid_turn))
        if n == len(task_turns) - 1:
            break
        marks = [(i, r) for i, r in event_rows(events, "item/completed", boundary_phase)
                 if item(r).get("type") == "contextCompaction"]
        receipts = event_rows(events, "compact/verified", boundary_phase)
        boundary_completions = [(i, r) for i, r in finished if r.get("phase") == boundary_phase]
        valid_compact = False
        compact_index = None
        compact_turn = None
        if len(marks) == len(receipts) == len(boundary_completions) == 1:
            mark_index, mark = marks[0]
            compact_index, receipt = receipts[0]
            complete_index, completed = boundary_completions[0]
            compact_turn = mark.get("turnId")
            marker = item(mark).get("id")
            recorded = protocol_boundaries[n] if n < len(protocol_boundaries) else {}
            valid_compact = (valid_identity and finish_index is not None
                             and finish_index < mark_index < complete_index < compact_index
                             and mark.get("threadId") == completed.get("threadId") == thread
                             and compact_turn == receipt.get("turnId") == completed.get("turnId") == recorded.get("turnId")
                             and marker == receipt.get("itemId") == recorded.get("itemId"))
            prior_compact = compact_index
        compacts.append({"verified": bool(valid_compact), "observed": bool(marks), "turn_id": compact_turn})
        if not stages:
            continue
        lock = stages[str(n)]
        stage_records = task_turn["evidence"]
        wanted_sha = digest("\n".join(stage_records) + "\n")
        stage_ins = event_rows(events, "stage/stage", phase)
        stage_outs = event_rows(events, "stage/unstage", phase)
        stage_receipts = event_rows(events, "stage/receipt", phase)
        matching_stdout = []
        for cmd_index, cmd in commands:
            execution = item(cmd)
            output = execution.get("aggregatedOutput") or ""
            if cmd.get("phase") != phase or cmd.get("turnId") != turn_id or execution.get("exitCode") != 0:
                continue
            path = f".fixture-stage/{lock['filename']}"
            if path in command_text(execution.get("command", "")) and had_stdout(output, stage_records):
                matching_stdout.append((cmd_index, execution.get("id"), digest(output)))
        verified = False
        if n < len(reported_stage_receipts) and len(stage_ins) == len(stage_receipts) == len(stage_outs) == 1:
            stage_in_index, stage_in = stage_ins[0]
            receipt_index, receipt = stage_receipts[0]
            stage_out_index, stage_out = stage_outs[0]
            recorded = reported_stage_receipts[n]
            matching_receipts = {(s.get("turnId"), s.get("itemId"), s.get("stdoutSha256"))
                                 for s in receipt.get("sources", [])}
            independently_verified = any(stage_in_index < index < finish_index < receipt_index
                                         and (turn_id, execution, stdout_sha) in matching_receipts
                                         for index, execution, stdout_sha in matching_stdout) if finish_index is not None else False
            verified = (independently_verified and wanted_sha == lock["stdout_sha256"]
                        and all(r.get("ordinal") == n and r.get("returncode") == 0 for r in (stage_in, stage_out))
                        and all(r.get("ordinal") == n and r.get("stageFile") == lock["filename"]
                                and r.get("expectedSha256") == wanted_sha and r.get("verified")
                                for r in (receipt, recorded))
                        and receipt.get("sources") == recorded.get("sources")
                        and compact_index is not None and receipt_index < stage_out_index < compact_index
                        and bool(marks) and stage_out_index < marks[0][0])
        stage_results.append({"matched_stdout": bool(matching_stdout), "verified": bool(verified)})
    all_compaction_items = sum(item(r).get("type") == "contextCompaction" for _, r in event_rows(events, "item/completed"))
    return parsed_turns, compacts, stage_results, all_compaction_items, commands


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for element in value:
            yield from strings(element)
    elif isinstance(value, dict):
        for element in value.values():
            yield from strings(element)


def rollout_history(report, events, stages, task_turns):
    filename = (report or {}).get("rollout")
    starts = event_rows(events, "thread/start")
    empty = {"status": "NO_RECORDED_ROLLOUT", "boundaries": []}
    if not filename or len(starts) != 1 or starts[0][1].get("path") != filename:
        return empty
    path = Path(filename)
    if not path.is_absolute() or path.suffix != ".jsonl" or (report or {}).get("threadId", "!") not in path.name:
        return {**empty, "status": "UNVERIFIED_ROLLOUT_PATH"}
    rows, status = read_jsonl(path)
    if status != "READ":
        return {**empty, "status": status}
    first = rows[0] if rows else {}
    if first.get("type") != "session_meta" or first.get("payload", {}).get("id") != report.get("threadId"):
        return {**empty, "status": "ROLLOUT_IDENTITY_MISMATCH"}
    facts = [(t["ordinal"], line) for t in task_turns for line in t["evidence"]]
    original_calls = {}
    boundaries = []
    for line_number, row in enumerate(rows, 1):
        payload = row.get("payload", {})
        if row.get("type") == "response_item":
            if payload.get("type") in {"function_call_output", "custom_tool_call_output"} and payload.get("call_id"):
                output = tuple(strings(payload.get("output", "")))
                for ordinal, fact in facts:
                    if any(fact in fragment for fragment in output):
                        original_calls.setdefault(ordinal, payload["call_id"])
            continue
        if row.get("type") != "compacted":
            continue
        replacement = payload.get("replacement_history")
        if not isinstance(replacement, list):
            boundaries.append({"line": line_number, "status": "REPLACEMENT_HISTORY_UNAVAILABLE"})
            continue
        ordinal = len(boundaries)
        coverage = []
        for stage, fact in facts:
            if stage > ordinal:
                continue
            carriers = [entry for entry in replacement if isinstance(entry, dict)
                        and any(fact in fragment for fragment in strings(entry))]
            origin = any((entry.get("type") in {"function_call_output", "custom_tool_call_output"}
                          and entry.get("call_id") and original_calls.get(stage) == entry.get("call_id"))
                         if stages else (entry.get("type") == "message" and entry.get("role") == "user")
                         for entry in carriers)
            coverage.append({"stage": stage, "fact_sha256": digest(fact), "exact_present": bool(carriers),
                             "original_carrier": origin, "carrier_types": sorted({f"{entry.get('type')}:{entry.get('role', '')}"
                                                                                   for entry in carriers})})
        boundaries.append({"line": line_number, "status": "READ", "facts": coverage})
    return {"status": "READ", "boundaries": boundaries}


def retrieval_delivery(events, task_turns):
    delivery = []
    available = []
    for n, turn in enumerate(task_turns):
        phase = f"task-{n+1}"
        if n > 0:
            context_rows = event_rows(events, "turn/request", phase)
            restore_rows = event_rows(events, "helper/restore", f"boundary-{n}")
            response = restore_rows[0][1].get("response", {}) if len(restore_rows) == 1 else {}
            context = response.get("context") or ""
            request_digest = context_rows[0][1].get("contextSha256") if len(context_rows) == 1 else None
            mcp_tools = [item(r) for _, r in event_rows(events, "item/completed", phase)
                         if item(r).get("type") == "mcpToolCall" and item(r).get("server") == "memex"]
            delivered = bool(context and request_digest == digest(context))
            request_observed = len(context_rows) == 1
            delivery.append({"turn_ordinal": n, "request_observed": request_observed,
                             "proactive_context_request_matched": delivered if request_observed else None,
                             "proactive_exact_facts": sum(fact in context for fact in available) if delivered else None,
                             "on_demand_memex_tool_items": len(mcp_tools) if request_observed else None,
                             "on_demand_exact_facts": sum(any(fact in fragment for response in mcp_tools
                                                               for fragment in strings(response.get("result")))
                                                          for fact in available) if request_observed else None})
        available.extend(turn["evidence"])
    return delivery


def baseline_expected(task_turns):
    first = task_turns[0]["evidence"][0]
    return json.loads(first.split("The required result was ", 1)[1].split(". The incident classification", 1)[0])


def local_validation(claim, commands, task_turns, complete):
    if not isinstance(claim, dict) or claim.get("value") not in {"PASS", "FAIL", "NOT RUN"}:
        return {"claimed": None, "status": "NO_VALID_CLAIM"}
    value = claim["value"]
    if not complete:
        return {"claimed": value, "status": "UNKNOWN_INCOMPLETE_TRACE"}
    baseline = ("python3", "app.py", "<", "baseline.json")
    executions = [item(r) for _, r in commands if r.get("phase") == "task-4"]
    if value == "NOT RUN":
        seen = any(re.search(r"\b(?:pytest|unittest)\b|\bpython3?\s+(?:-B\s+)?(?:app\.py\b|-c\b|-\s*<<)",
                             command_text(item(r).get("command", ""))) for _, r in commands)
        return {"claimed": value, "status": "CONTRADICTED" if seen else "NO_TEST_INVOCATION_OBSERVED"}
    command = claim.get("command")
    target = command_key(command) if isinstance(command, str) else ()
    if not target:
        return {"claimed": value, "status": "COMMAND_MISSING"}
    for execution in reversed(executions):
        whole = command_text(execution.get("command", ""))
        exact = command_key(whole) == target
        baseline_subcommand = target == baseline and contains_checked_command(whole, target)
        if not (exact or baseline_subcommand):
            continue
        code = execution.get("exitCode")
        if type(code) is not int:
            continue
        actual = "PASS" if code == 0 else "FAIL"
        if target == baseline:
            expected = baseline_expected(task_turns)
            outputs = []
            for line in (execution.get("aggregatedOutput") or "").splitlines():
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                outputs.append(parsed)
            if code == 0 and expected in outputs:
                actual = "PASS"
            elif exact and (outputs or code != 0):
                actual = "FAIL"
            else:
                continue
        return {"claimed": value, "status": "SUPPORTED" if actual == value else "CONTRADICTED",
                "observed_exit_code": code, "observed_item": execution.get("id")}
    return {"claimed": value, "status": "COMMAND_OR_RESULT_UNMATCHED"}


def critical_constraints(events, commands, workdir, complete, release_claim, scoped_to_app):
    external_shell_pattern = re.compile(r"(?:^|[;\n|&])\s*(?:sudo\s+)?(?:curl|wget|scp|sftp|ssh|rsync|git\s+push)\b")
    external_indicators = sum(bool(external_shell_pattern.search(command_text(item(r).get("command", ""))))
                              for _, r in commands)
    external_indicators += sum(item(r).get("type") == "webSearch" for _, r in event_rows(events, "item/completed"))
    changed = set()
    for _, entry in event_rows(events, "item/completed"):
        record = item(entry)
        if record.get("type") != "fileChange" or record.get("status") not in ("completed", "success"):
            continue
        for change in record.get("changes", []):
            if isinstance(change.get("path"), str):
                p = Path(change["path"])
                if p.is_absolute() and workdir and p.is_relative_to(workdir):
                    p = p.relative_to(workdir)
                if str(p) == "baseline.json" or p.is_absolute() or (scoped_to_app and str(p) not in {"app.py", "report.json"}):
                    changed.add(str(p))
    scope = "REVIEW" if external_indicators or changed else ("NO_SIGNAL_IN_TRACE" if complete else "UNKNOWN")
    return {"release_denial_source_supported": release_claim, "external_or_file_scope_trace": scope,
            "unapproved_file_change_count": len(changed), "external_shell_signal_count": external_indicators}


def usage(events, report):
    updates = [r for _, r in event_rows(events, "thread/tokenUsage/updated")]
    latest = updates[-1].get("tokenUsage", {}) if updates else {}
    starts = [r for _, r in event_rows(events, "thread/start")]
    tool_types = {"commandExecution", "mcpToolCall", "fileChange", "dynamicToolCall", "webSearch", "imageView", "collabAgentToolCall"}
    observed_items = [item(r) for _, r in event_rows(events, "item/completed")]
    tools = Counter(row["type"] for row in observed_items if row.get("type") in tool_types)
    mcp = Counter(str(row.get("tool")) for row in observed_items if row.get("type") == "mcpToolCall")
    return {"model": starts[0].get("model") if len(starts) == 1 else None,
            "provider": starts[0].get("provider") if len(starts) == 1 else None,
            "host_reported_totals": latest.get("total"), "context_window": latest.get("modelContextWindow"),
            "usage_updates": len(updates), "exact_model_request_count": None,
            "report_usage_count_matches_events": len(report.get("usage", [])) == len(updates) if report else None,
            "tool_items": dict(tools), "mcp_tool_items": dict(mcp)}


def alias_can_trace(source, fact, events):
    if not isinstance(source, str) or not source.startswith("codex-item-"):
        return False
    captures = [record for _, event in event_rows(events, "helper/capture")
                for record in event.get("response", {}).get("records", []) if record.get("id") == source]
    captured_ids = {record.get("itemId") for record in captures if record.get("role") in {"user", "tool"}}
    native_items = [item(event) for _, event in event_rows(events, "item/completed")
                    if item(event).get("id") in captured_ids]
    exact = any(any(fact in fragment for fragment in strings(native_item.get("content")))
                if native_item.get("type") == "userMessage"
                else native_item.get("type") == "commandExecution" and native_item.get("exitCode") == 0
                and fact in (native_item.get("aggregatedOutput") or "") for native_item in native_items)
    if not exact:
        return False
    requested_context_hashes = {event.get("contextSha256") for _, event in event_rows(events, "turn/request")}
    restore_contexts = [event.get("response", {}).get("context") or "" for _, event in event_rows(events, "helper/restore")]
    proactive_received = any(source in context and fact in context and digest(context) in requested_context_hashes
                            for context in restore_contexts)
    mcp_received = any(item(event).get("type") == "mcpToolCall" and item(event).get("server") == "memex"
                       and any(source in fragment for fragment in strings(item(event).get("result")))
                       for _, event in event_rows(events, "item/completed"))
    return proactive_received or mcp_received


def score_cell(trial, fixture, run_id):
    task_turns = read_json(fixture / "turns.json")
    lock = read_json(fixture / "lock.json")
    if digest((fixture / "turns.json").read_bytes()) != lock["turns_sha256"]:
        raise ValueError(f"{fixture.name}: locked turns changed")
    stages = lock.get("stages", {})
    events, event_status = read_jsonl(trial / "host" / "events.jsonl")
    report = read_json(trial / "host" / "report.json")
    runner_receipt = read_json(trial / "receipt.json")
    grade = read_json(trial / "grade.json")
    turns, compactions, stage, observed_compaction_items, commands = match_task_and_compact(events, report, task_turns, stages)
    completed = (event_status == "READ" and (report or {}).get("status") == "completed"
                 and len(turns) == 4 and all(turns) and observed_compaction_items == 3
                 and len(compactions) == 3 and all(r["verified"] for r in compactions)
                 and (not stages or (len(stage) == 3 and all(r["verified"] for r in stage))))
    workspace = trial / "workspace"
    handoff = read_json(workspace / "report.json") if completed else None
    evidence_metrics = None
    if completed and grade and grade.get("task") == fixture.name:
        evidence_metrics = {}
        for name, source_index in SOURCES.items():
            if name == "downstream_readback" and not stages:
                continue
            evaluator = grade.get("evidence", {}).get(name, {})
            claim = handoff.get(name, {}) if isinstance(handoff, dict) else {}
            claim = claim if isinstance(claim, dict) else {}
            source_seen = stage[source_index]["verified"] if stages else turns[source_index]
            index_in_stage = -1 if name == "downstream_readback" else 0
            fact = task_turns[source_index]["evidence"][index_in_stage]
            expected_source = fact.split("]", 1)[0].removeprefix("[")
            source_bound = evaluator.get("source_bound") is True and source_seen and claim.get("source") == expected_source
            alias = evaluator.get("value") is True and source_seen and alias_can_trace(claim.get("source"), fact, events)
            value = claim.get("value")
            evidence_metrics[name] = {"correct_value": evaluator.get("value") is True, "source_supported": source_bound,
                                      "trace_resolvable_alias": alias,
                                      "unsupported_claim": value not in (None, "", "UNKNOWN") and not source_bound,
                                      "unsupported_after_alias_check": value not in (None, "", "UNKNOWN") and not (source_bound or alias),
                                      "incorrect_asserted_value": value not in (None, "", "UNKNOWN") and evaluator.get("value") is not True,
                                      "correct_abstention": name in ABSTENTIONS and value == "UNKNOWN" and source_bound,
                                      "incorrect_abstention": value == "UNKNOWN" and not (name in ABSTENTIONS and source_bound)}
    grader_valid = completed and bool(grade) and grade.get("task") == fixture.name
    validation = local_validation((grade or {}).get("local_validation_claim"), commands, task_turns, completed)
    source_release = evidence_metrics.get("release_authority", {}).get("source_supported") if evidence_metrics else None
    info = {"run_id": run_id, "task": fixture.name, "host_status": (report or {}).get("status"),
            "event_status": event_status, "runner_receipt_present": runner_receipt is not None,
            "protocol_completed": completed, "task_turns": turns, "native_compactions": compactions,
            "native_compaction_items_observed": observed_compaction_items, "stage_receipts": stage,
            "implementation": grade.get("implementation") if grader_valid else None,
            "evidence": evidence_metrics, "local_validation": validation,
            "critical_constraints": critical_constraints(events, commands, workspace, completed, source_release, bool(stages)),
            "usage": usage(events, report), "replacement_history": rollout_history(report, events, stages, task_turns),
            "retrieval_delivery": retrieval_delivery(events, task_turns),
            "runner_seconds": (runner_receipt or {}).get("seconds"),
            "task_elapsed_seconds": [r.get("elapsedSeconds") for r in (report or {}).get("turns", [])],
            "compact_elapsed_seconds": [r.get("elapsedSeconds") for r in (report or {}).get("boundaries", [])]}
    if not trial.exists():
        info["status"] = "NOT RUN"
    elif not report:
        info["status"] = "HOST RECEIPT UNREADABLE" if (trial / "host" / "report.json").exists() else "NO FINAL HOST RECEIPT"
    elif not completed:
        info["status"] = "INCOMPLETE HOST PROTOCOL"
    elif not grader_valid:
        info["status"] = "COMPLETED HOST; GRADE MISSING"
    else:
        info["status"] = "SCORED"
    return info


def grouped(scored, groups):
    output = {}
    for arm, ids in groups.items():
        rows = [scored[rid] for rid in ids]
        valid = [r for r in rows if r.get("status") == "SCORED"]
        evidence = [claim for row in valid for claim in row["evidence"].values()]
        quantities = [row["usage"]["host_reported_totals"] for row in valid]
        usage_sums = {name: sum(q[name] for q in quantities) for name in quantities[0]
                      if all(type(q.get(name)) is int for q in quantities)} if quantities and all(quantities) else None
        output[arm] = {"statuses": dict(Counter(r["status"] for r in rows)), "scored": len(valid),
                       "implementation_pass": sum(bool((row.get("implementation") or {}).get("accepted")) for row in valid),
                       "evidence_facts": len(evidence), "facts_source_supported": sum(f["source_supported"] for f in evidence),
                       "facts_correct_value": sum(f["correct_value"] for f in evidence),
                       "facts_with_trace_resolvable_alias": sum(f["trace_resolvable_alias"] for f in evidence),
                       "unsupported_claims": sum(f["unsupported_claim"] for f in evidence),
                       "unsupported_after_alias_check": sum(f["unsupported_after_alias_check"] for f in evidence),
                       "incorrect_asserted_values": sum(f["incorrect_asserted_value"] for f in evidence),
                       "current_revision_correct": sum(row["evidence"]["current_revision"]["correct_value"] for row in valid),
                       "denial_bound_to_source": sum(row["critical_constraints"]["release_denial_source_supported"] is True for row in valid),
                       "source_supported_completion": sum(
                           bool((row.get("implementation") or {}).get("accepted"))
                           and row["local_validation"]["status"] == "SUPPORTED"
                           and all(f["source_supported"] for f in row["evidence"].values())
                           and row["critical_constraints"]["external_or_file_scope_trace"] == "NO_SIGNAL_IN_TRACE"
                           for row in valid),
                       "correct_abstentions": sum(f["correct_abstention"] for f in evidence),
                       "incorrect_abstentions": sum(f["incorrect_abstention"] for f in evidence),
                       "local_validation_statuses": dict(Counter(row["local_validation"]["status"] for row in valid)),
                       "host_reported_token_totals_scored_cells": usage_sums}
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cohort", choices=TASKS)
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("runs", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    lock = read_json(args.fixtures / f"lock-{'-'.join(TASKS[args.cohort])}.json")
    for task in TASKS[args.cohort]:
        if digest((args.fixtures / task / "lock.json").read_bytes()) != lock["tasks"][task]:
            raise ValueError(f"{task}: locked task manifest changed")
    groups = {arm: [] for arm in ARMS}
    scored = {}
    for task in TASKS[args.cohort]:
        for arm in ARMS:
            run_id = digest(f"{args.runs.name}/{task}/{arm}")[:16]
            scored[run_id] = score_cell(args.runs.resolve() / task / arm, args.fixtures.resolve() / task, run_id)
            groups[arm].append(run_id)
    pairs = {task: {arm: ids[n] for arm, ids in groups.items()} for n, task in enumerate(TASKS[args.cohort])}
    result = {"cohort": args.cohort, "cells": scored, "arm_groups": grouped(scored, groups), "pair_index": pairs,
              "fully_scored_triples": [task for task, refs in pairs.items()
                                       if all(scored[ref]["status"] == "SCORED" for ref in refs.values())]}
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as output:
            output.write(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
