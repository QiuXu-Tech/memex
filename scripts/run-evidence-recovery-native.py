#!/usr/bin/env python3
"""Run locked, actual Codex A/B/C trials with auditable Memex tool calls."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import queue
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
import threading
import time

REPO = Path(__file__).resolve().parent.parent
HOST = runpy.run_path(str(REPO / "scripts/codex-retention-host.py"))
MODEL = HOST["MODEL"]
CLAIM_BUDGET = 1200
PROVIDER_STOP = ("usage limit", "rate limit", "status 429", "http 429", "quota_exceeded")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(data):
    return sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def send(proc, row):
    proc.stdin.write(json.dumps(row, ensure_ascii=False) + "\n")
    proc.stdin.flush()


class Mailbox:
    """Read sequential JSON lines with an operation deadline."""
    def __init__(self, proc):
        self.proc = proc
        self.lines = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for line in self.proc.stdout:
                self.lines.put(line)
        finally:
            self.lines.put(None)

    def receive(self):
        line = self.lines.get(timeout=80)
        if line is None:
            raise RuntimeError("local child closed its JSON stream")
        return json.loads(line)


class Memex:
    def __init__(self, node, root, workspace, session, directory):
        self.log = (directory / "mcp.jsonl").open("x")
        self.err = (directory / "mcp.stderr").open("x")
        self.proc = subprocess.Popen([node, str(REPO / "packages/memex-mcp/bin/server.mjs"),
            "--root", str(root), "--cwd", str(workspace), "--session", session, "--levels", "l2", "--evidence-search"],
            text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.err)
        self.mailbox = Mailbox(self.proc)
        self.sequence = 0
        self.claim_id = None

    def rpc(self, method, params):
        self.sequence += 1
        request = dict(jsonrpc="2.0", id=self.sequence, method=method, params=params)
        started = time.monotonic()
        send(self.proc, request)
        response = self.mailbox.receive()
        self.log.write(json.dumps(dict(claimId=self.claim_id, request=request, response=response,
            elapsedMs=(time.monotonic() - started)*1000), ensure_ascii=False) + "\n")
        self.log.flush()
        if response.get("id") != self.sequence or "error" in response:
            raise RuntimeError("invalid Memex RPC result")
        return response["result"]

    def __enter__(self):
        try:
            self.rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "retention-gate-study", "version": "1"}})
            send(self.proc, dict(jsonrpc="2.0", method="notifications/initialized", params={}))
            return self
        except Exception:
            self.__exit__()
            raise

    def __exit__(self, *_):
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.log.close()
        self.err.close()

    def call(self, name, arguments):
        result = self.rpc("tools/call", dict(name=name, arguments=arguments))
        if result.get("isError") is True:
            raise RuntimeError(f"Memex {name} reported an error")
        return result

    def search(self, query):
        identity = json.dumps([query["type"], query["scope"], query["entity"]], ensure_ascii=False, separators=(",", ":"))
        keywords = [query["entity"]]
        if query.get("attempt", 1) == 1:
            keywords.append(query["type"])
        if query.get("matchVersion", True):
            keywords.append(query["version"])
        arguments = {"query": " ".join(keywords), "source": identity, "limit": min(5, query.get("hitLimit", 5)),
                     "includeExpired": True}
        if query.get("matchVersion", True):
            arguments["version"] = query["version"]
        hits = self.call("memory_search", arguments)["structuredContent"]["hits"]
        return [{"sourceRef": card["id"]} for card in hits]

    def open(self, hit):
        chunks = []
        offset = 0
        for _ in range(2):
            result = self.call("memory_open", {"id":hit["sourceRef"],"eventIndex":1,
                "charOffset":offset,"maxChars":12000})
            page = json.loads("".join(block["text"] for block in result["content"] if block["type"]=="text"))
            if (page.get("recordId") != hit["sourceRef"] or page.get("eventIndex") != 1
                or page.get("charOffset") != offset):
                raise RuntimeError("original event locator mismatch")
            chunks.append(page["content"])
            next_offset = page.get("nextCharOffset")
            if next_offset is None:
                break
            if type(next_offset) is not int or next_offset <= offset:
                raise RuntimeError("invalid source continuation")
            offset = next_offset
        else:
            raise RuntimeError("clipped_source: original event exceeds bounded read")
        raw = json.loads("".join(chunks))
        line = raw["sourceLine"]
        if raw.get("sourceRef") != hit["sourceRef"] or raw["sha256"] != digest(line):
            raise RuntimeError("original event content mismatch")
        receipt = json.loads(line)
        if receipt.get("sourceRef") != hit["sourceRef"]:
            raise RuntimeError("original receipt identity mismatch")
        return receipt


def extract_stdout(rows, stage):
    wanted = stage.read_text(encoding="utf-8").splitlines()
    if not wanted:
        raise ValueError("empty expected stage input")
    for row in rows:
        item = row["item"]
        if item.get("type") != "commandExecution" or item.get("exitCode") != 0:
            continue
        observed = item.get("aggregatedOutput") or ""
        lines = observed.splitlines()
        for i in range(len(lines) - len(wanted) + 1):
            if lines[i:i+len(wanted)] == wanted:
                return {"valid": True, "itemId": item["id"], "stdoutSha256": digest(observed),
                        "sourceLines": lines[i:i+len(wanted)]}
    raise RuntimeError("verified complete original stdout not observed")


def run_turn(host, phase, prompt, workspace, context=None, read_only=False):
    host.phase = phase
    policy = dict(type="readOnly" if read_only else "workspaceWrite", networkAccess=False)
    if not read_only:
        policy.update(writableRoots=[str(workspace)], excludeTmpdirEnvVar=True, excludeSlashTmp=True)
    request = dict(threadId=host.tid, input=[{"type":"text","text":prompt}], sandboxPolicy=policy,
                   effort="low", approvalPolicy="never")
    if context:
        request["additionalContext"] = {"verified_originals":{"kind":"untrusted","value":context}}
    host.record("trial/prompt", messageSha256=digest(prompt), contextSha256=digest(context) if context else None)
    started = time.monotonic()
    turn = host.rpc("turn/start", request)["turn"]["id"]
    items = host.complete(turn)
    if any(row["item"]["type"] == "contextCompaction" for row in items):
        raise RuntimeError("unexpected automatic compaction inside task turn")
    final = [row["item"].get("text","") for row in items if row["item"]["type"] == "agentMessage"]
    if not final:
        raise RuntimeError("empty native final response")
    return turn, items, final[-1], time.monotonic() - started


def gate(node, service, claim, current, now, arm, tokenizer, directory):
    service.claim_id = claim["claimId"]
    payload = {"claim":claim,"currentEvidence":[{"source":source,"opened":True} for source in current],
               "now":now,"countReferenceTokens":True}
    if arm == "B":
        payload["mode"] = "forced"
    operations = []
    with (directory / "gate.stderr").open("a") as err:
        proc = subprocess.Popen([node, str(REPO/"scripts/evidence-check-gate.mjs")],
            text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err)
        mailbox = Mailbox(proc)
        try:
            send(proc, payload)
            while True:
                event = mailbox.receive()
                op = event["op"]
                if op == "result":
                    result = event["result"]
                    break
                try:
                    if op == "search":
                        value = service.search(event["query"])
                        summary = [item["sourceRef"] for item in value]
                    elif op == "open":
                        value = service.open(event["hit"])
                        summary = value["sourceRef"] if value else None
                    elif op == "count_tokens":
                        value = len(tokenizer.encode_ordinary(event["injection"]))
                        summary = value
                    else:
                        raise RuntimeError("invalid evidence-gate operation")
                    reply = {"value": value}
                except (RuntimeError, ValueError, KeyError, queue.Empty) as error:
                    summary = {"error": str(error)}
                    reply = summary
                operations.append({"op":op,"request":event,"responseSummary":summary})
                send(proc, reply)
        finally:
            proc.stdin.close()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if proc.returncode != 0:
            raise RuntimeError("evidence gate child failed")
    injection = result.get("injection") or ""
    reference_tokens = len(tokenizer.encode_ordinary(injection))
    if reference_tokens > CLAIM_BUDGET or (injection and result.get("referenceTokens") != reference_tokens):
        raise RuntimeError("evidence gate injection exceeds or misreports reference-token budget")
    source_refs = []
    source = result.get("source")
    if injection and source:
        source_refs = [source["sourceRef"]]
    if result.get("outcome") == "abstain":
        injection = json.dumps({"claimId":claim["claimId"],"status":"unverified",
            "gateReason":result["reason"],
            "note":"No qualifying original was recovered. Refrain from a definitive assertion unless the conversation supplies a valid original receipt."},ensure_ascii=False)
        reference_tokens = len(tokenizer.encode_ordinary(injection))
        if reference_tokens > CLAIM_BUDGET:
            raise RuntimeError("diagnostic exceeds recovery budget")
    return {"claimId":claim["claimId"],"result":result,"operations":operations,"injection":injection,
            "visibleSourceRefs":source_refs,"referenceTokens":reference_tokens}


def trial(args, fixture, arm, tokenizer, batch_env):
    case = read_json(fixture / "case.json")
    case_id = case["case_id"]
    directory = args.output / case_id / arm
    directory.mkdir(parents=True)
    host_dir = directory / "host"
    host_dir.mkdir()
    with tempfile.TemporaryDirectory(prefix=f"memex-trial-{case_id}-{arm}-") as scratch:
        workspace = Path(scratch) / "workspace"
        shutil.copytree(fixture/"workspace", workspace)
        stage = fixture/"stage/evidence.txt"
        target = workspace/".fixture-stage/evidence.txt"
        target.parent.mkdir()
        shutil.copyfile(stage, target)
        started = time.monotonic()
        report = {"status":"running","caseId":case_id,"arm":arm,
                  "model":MODEL,"nativeBoundaries":[],"hostTurnIds":[],"gates":[],
                  "implemented":False,"workspace":str(workspace)}
        host = HOST["Host"](args.codex, HOST["codex_overrides"](None,False), str(workspace), host_dir, batch_env, 170)
        try:
            thread = host.start(dict(cwd=str(workspace),model=MODEL,modelProvider="openai",
                allowProviderModelFallback=False,approvalPolicy="never",sandbox="workspace-write",
                baseInstructions=HOST["BASE"],ephemeral=False))
            report.update(threadId=host.tid,rollout=thread.get("path"),version=args.codex_version)
            inventory = host.rpc("mcpServerStatus/list", {"threadId":host.tid,"detail":"toolsAndAuthOnly","limit":100})
            if inventory.get("nextCursor") or any(server["tools"] for server in inventory["data"]):
                raise RuntimeError("unexpected model-visible extra MCP tools")
            turn, items, implementation, elapsed = run_turn(host,"implementation",case["implementation_prompt"],workspace)
            report.update(implemented=True,implementationText=implementation,implementationSeconds=elapsed)
            report["hostTurnIds"].append(turn)
            original = extract_stdout(items, stage)
            report["observedStage"] = {**original,"fileSha256":digest(stage.read_bytes())}
            if target.is_symlink() or target.read_bytes() != stage.read_bytes():
                raise RuntimeError("staged original source was changed")
            target.unlink()
            target.parent.rmdir()
            if target.exists():
                raise RuntimeError("source remained mounted")
            host.record("stage/removed", **report["observedStage"])
            claims = case["claims"]
            session = "trial-" + case_id + "-" + arm
            archive = directory/"archive"
            if arm != "A":
                ingest = json.dumps(dict(root=str(archive),cwd=str(workspace),session=session,
                    workspaceScopes=sorted({claim["scope"] for claim in claims}),threadId=host.tid,
                    itemId=original["itemId"],stdoutSha256=original["stdoutSha256"],
                    sourceLines=original["sourceLines"]),ensure_ascii=False)
                loaded = subprocess.run([args.node,str(REPO/"scripts/evidence-recovery-archive.mjs")],
                    input=ingest,text=True,capture_output=True,timeout=45)
                if loaded.returncode:
                    (directory/"archive.stderr").write_text(loaded.stderr)
                    raise RuntimeError("original source ingestion failed")
                report["archiveReceipt"] = json.loads(loaded.stdout)
            for n in range(case["depth"]):
                if args.stop.is_set():
                    raise RuntimeError("quota admission stopped before remaining boundaries")
                host.phase = f"boundary-{n+1}"
                receipt = host.compact()
                assert receipt["itemId"] not in {old["itemId"] for old in report["nativeBoundaries"]}
                report["nativeBoundaries"].append(receipt)
                host.record("compact/verified", **receipt)
            current = case.get("currentEvidence", [])
            report["modelVisibleCurrent"] = current
            prompt = case["decision_prompt"]
            if any(source["sourceRef"] not in prompt for source in current):
                raise RuntimeError("claimed model-visible original is absent from the frozen decision prompt")
            report["decisionPromptSha256"] = digest(prompt)
            report["implementationPromptSha256"] = digest(case["implementation_prompt"])
            recovered = []
            if arm != "A":
                with Memex(args.node, archive, workspace, session, directory) as service:
                    for claim in claims:
                        verdict = gate(args.node,service,claim,current,case["evaluatedAt"],arm,tokenizer,directory)
                        report["gates"].append(verdict)
                        host.record("gate/observed", claimId=claim["claimId"],
                                    outcome=verdict["result"].get("outcome"), delivered=bool(verdict["injection"]))
                        if verdict["injection"]:
                            recovered.append(verdict["injection"])
            context = "\n\n".join(recovered)
            if context:
                report["deliveredEvidenceSha256"] = digest(context)
                report["deliveredReferenceTokens"] = len(tokenizer.encode_ordinary(context))
            turn, _, final, elapsed = run_turn(host,"decision",prompt,workspace,context,read_only=True)
            report["hostTurnIds"].append(turn)
            report["finalText"] = final
            report["decisionSeconds"] = elapsed
            try:
                report["answer"] = json.loads(re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$","",final.strip(),flags=re.I))
            except json.JSONDecodeError:
                report["answer"] = None
            report["status"] = "completed"
        except Exception as error:
            report.update(status="failed",error=f"{type(error).__name__}: {error}")
            host.record("trial/failure",message=report["error"])
            if any(signal in str(error).lower() for signal in PROVIDER_STOP):
                args.stop.set()
        finally:
            report["usage"] = host.usage[-1]["tokenUsage"] if host.usage else None
            report["elapsedSeconds"] = time.monotonic() - started
            host.close()
            # Only preserve named task outputs from the synthetic workspace.
            receipt = directory/"workspace"
            receipt.mkdir()
            for name in ("app.py","test_public.py"):
                path = workspace/name
                if path.is_file() and not path.is_symlink() and path.stat().st_size <= 256_000:
                    shutil.copyfile(path,receipt/name)
            HOST["write_json"](directory/"report.json",report)
            print(case_id,arm,report["status"],len(report["nativeBoundaries"]),f"{report['elapsedSeconds']:.1f}s",report.get("error",""),flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cases", nargs="+", required=True)
    parser.add_argument("--jobs", type=int, choices=range(1,9), default=2)
    parser.add_argument("--node", default=shutil.which("node"))
    parser.add_argument("--codex", default=shutil.which("codex"))
    args = parser.parse_args()
    args.fixtures, args.output = args.fixtures.resolve(), args.output.resolve()
    args.stop = threading.Event()
    lock_path = args.fixtures / "lock.json"
    locked = read_json(lock_path)
    subprocess.run([sys.executable, "-B", str(REPO/"scripts/evidence-recovery-fixtures.py"),
                    "verify", str(args.fixtures)], check=True)
    if len(set(args.cases)) != len(args.cases) or not set(args.cases).issubset(locked["cohort"]):
        raise ValueError("only unique frozen cases can be run")
    scorer = REPO/"scripts/evidence-recovery-score.py"
    if locked.get("scoringScriptSha256") and digest(scorer.read_bytes()) != locked["scoringScriptSha256"]:
        raise ValueError("the frozen scorer has changed")
    import tiktoken
    if tiktoken.__version__ != "0.12.0":
        raise RuntimeError("reference tokenizer version mismatch")
    tokenizer = tiktoken.get_encoding("o200k_base")
    assert tokenizer.encode_ordinary("Hello, world!") == [13225, 11, 2375, 0]
    variables = {k:v for k,v in os.environ.items() if k not in
        ("OPENAI_API_KEY","CODEX_API_KEY","OPENAI_BASE_URL","OPENAI_API_BASE")}
    login = subprocess.run([args.codex,"login","status"],env=variables,capture_output=True,text=True,check=True,timeout=20)
    if (login.stdout+login.stderr).strip()!="Logged in using ChatGPT":
        raise RuntimeError("Existing ChatGPT login required for this experiment")
    args.codex_version = subprocess.check_output([args.codex,"--version"],env=variables,text=True).strip()
    args.output.mkdir(parents=True,exist_ok=False)
    observed_runtime = [
        "scripts/run-evidence-recovery-native.py", "scripts/evidence-check-gate.mjs",
        "scripts/evidence-recovery-archive.mjs", "scripts/codex-retention-host.py",
        "packages/memex-core/lib/engine.js", "packages/memex-core/lib/store.js",
        "packages/memex-mcp/bin/server.mjs",
    ]
    HOST["write_json"](args.output/"freeze.json", {
        "fixtureLockSha256":digest(lock_path.read_bytes()),
        "runtimeSha256":{name:digest((REPO/name).read_bytes()) for name in observed_runtime},
        "cases":args.cases,"model":MODEL,"version":args.codex_version,"jobs":args.jobs,
        "tokenizer":"tiktoken@0.12.0/o200k_base","claimBudget":CLAIM_BUDGET,
    })
    def run_case(name):
        fixture = args.fixtures/name
        order = read_json(fixture/"case.json")["order"]
        if sorted(order)!=list("ABC"):
            raise ValueError("arm order is incomplete")
        for arm in order:
            if args.stop.is_set():
                print(name,arm,"NOT RUN quota admission stopped",flush=True)
            else:
                trial(args,fixture,arm,tokenizer,variables)
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures=[executor.submit(run_case,name) for name in args.cases]
        for future in futures:
            future.result()


if __name__=="__main__":
    main()
