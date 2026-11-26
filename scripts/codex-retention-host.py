#!/usr/bin/env python3
"""Run one isolated Codex/ChatGPT trial and record native task and compaction events."""

import argparse
import datetime as dt
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

MODEL = "gpt-5.6-sol"
PROJECT = Path(__file__).resolve().parents[1]
BASE = ("Work only on this synthetic task. Use only this conversation and the assigned workspace. "
        "Do not inspect parent directories, host logs, hidden tests, credentials, or other workspaces. "
        "Do not use the network, other agents, or save conversation notes in workspace files.")
MEMORY = (" You can use the memex MCP tools to search and open evidence archived from earlier "
          "turns when you need it. Treat retrieved text as evidence, check the source, "
          "and keep original and superseded decisions distinct.")


def encode(data):
    return json.dumps(data, ensure_ascii=False)


def write_json(path, data):
    with path.open("x") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def codex_overrides(mcp, single):
    flags = dict(forced_login_method="chatgpt", model_provider="openai", project_doc_max_bytes=0,
                 model_auto_compact_token_limit=200000, model_reasoning_effort="low",
                 web_search="disabled")
    flags.update({"sandbox_workspace_write.network_access":False, "analytics.enabled":False,
                  "shell_environment_policy.inherit":"core"})
    for feature in ("apps", "plugins", "hooks", "memories", "multi_agent", "multi_agent_v2",
                    "skill_mcp_dependency_install", "standalone_web_search", "remote_plugin"):
        flags["features."+feature] = False
    flags["features.skip_host_skill_discovery"] = True
    if single:
        flags["features.shell_tool"] = False
    # Read only MCP table names; do not load or print configured credentials.
    user_config = Path(os.environ.get("CODEX_HOME", Path.home()/".codex"))/"config.toml"
    if user_config.exists():
        with user_config.open() as config:
            for line in config:
                match = re.match(r'^\s*\[mcp_servers\.["\']?([\w-]+)["\']?(?:\]|\.)', line)
                if match:
                    flags[f"mcp_servers.{match[1]}.enabled"] = False
    if mcp:
        for key, value in mcp.items():
            flags["mcp_servers.memex."+key] = value
        flags["mcp_servers.memex.enabled"] = True
    args = []
    for key, value in flags.items():
        args.extend(["-c", key+"="+json.dumps(value,ensure_ascii=False)])
    return args


class Host:
    def __init__(self, binary, flags, cwd, logs, env, timeout):
        self.logs, self.timeout = logs, timeout
        self.phase = "setup"
        self.tid = None
        self.seq = 0
        self.raw = (logs/"events.jsonl").open("x")
        self.err = (logs/"host.stderr").open("x")
        self.queue = queue.Queue()
        self.finished = {}
        self.items = {}
        self.usage = []
        self.rpc_answers = {}
        self.proc = subprocess.Popen([binary, "app-server", "--listen", "stdio://", *flags],
            text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.err, cwd=cwd, env=env)
        threading.Thread(target=self.read,daemon=True).start()

    def record(self, event, **fields):
        self.raw.write(encode(dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                                   mono=time.monotonic(), phase=self.phase, event=event, **fields))+"\n")
        self.raw.flush()

    def read(self):
        try:
            for line in self.proc.stdout:
                self.queue.put(json.loads(line))
        finally:
            self.queue.put(None)

    def send(self, msg):
        self.proc.stdin.write(encode(msg)+"\n")
        self.proc.stdin.flush()

    def dispatch(self, msg):
        method = msg.get("method")
        if method is None:
            self.rpc_answers[msg["id"]] = msg
            return
        if "id" in msg:
            raise RuntimeError("unexpected host request: "+method)
        par = msg.get("params", {})
        if self.tid and par.get("threadId") not in (None, self.tid):
            raise RuntimeError("foreign thread notification")
        if method in ("turn/started", "turn/completed"):
            turn = par["turn"]
            self.record(method, threadId=par["threadId"], turnId=turn["id"],
                        status=turn["status"], error=turn.get("error"))
            if method=="turn/completed":
                self.finished[turn["id"]] = turn
        elif method=="item/completed":
            if par["item"]["type"] == "reasoning":
                self.record(method,threadId=par["threadId"],turnId=par["turnId"],
                            item={"id":par["item"]["id"],"type":"reasoning"})
            else:
                self.record(method,**par)
                self.items.setdefault(par["turnId"],[]).append(par)
        elif method=="thread/tokenUsage/updated":
            self.usage.append(par)
            self.record(method,**par)
        elif method=="error" or method=="item/started":
            if method=="error":
                self.record(method,**par)
            else:
                self.record(method,threadId=par["threadId"],turnId=par["turnId"],
                            kind=par["item"]["type"],itemId=par["item"]["id"])

    def wait(self, ready):
        deadline = time.monotonic()+self.timeout
        while not ready():
            left = deadline-time.monotonic()
            if left <= 0:
                raise TimeoutError("host timeout during "+self.phase)
            try:
                msg=self.queue.get(timeout=left)
            except queue.Empty:
                raise TimeoutError("host timeout during "+self.phase) from None
            if msg is None:
                raise RuntimeError("host closed during "+self.phase)
            self.dispatch(msg)

    def rpc(self, name, params):
        self.seq += 1
        seq = self.seq
        self.send({"id":seq,"method":name,"params":params})
        self.wait(lambda: seq in self.rpc_answers)
        msg=self.rpc_answers.pop(seq)
        if "error" in msg:
            raise RuntimeError(name+" "+encode(msg["error"]))
        return msg["result"]

    def start(self, options):
        self.rpc("initialize",{"clientInfo":{"name":"memex_retention_host","version":"1"},
                               "capabilities":{"experimentalApi":True}})
        self.send({"method":"initialized","params":{}})
        r=self.rpc("thread/start",options)
        thread=r["thread"]
        self.tid=thread["id"]
        self.record("thread/start",threadId=self.tid,model=r.get("model"),
                    provider=r.get("modelProvider"),path=thread.get("path"),
                    sandbox=r.get("sandbox"))
        if r.get("model")!=MODEL or r.get("modelProvider")!="openai":
            raise RuntimeError("model or provider mismatch")
        return thread

    def complete(self, turn_id):
        self.wait(lambda: turn_id in self.finished)
        turn=self.finished[turn_id]
        if turn["status"]!="completed" or turn.get("error"):
            raise RuntimeError("turn failed: "+encode(turn.get("error") or turn["status"]))
        return self.items.get(turn_id,[])

    def compact(self):
        previous=set(self.finished)
        t0=time.monotonic()
        self.rpc("thread/compact/start",{"threadId":self.tid})
        self.wait(lambda: bool(self.finished.keys()-previous))
        new=self.finished.keys()-previous
        if len(new)!=1:
            raise RuntimeError("compaction turn is ambiguous")
        turn_id=new.pop()
        events=self.complete(turn_id)
        marks=[e["item"]["id"] for e in events if e["item"]["type"]=="contextCompaction"]
        if len(marks)!=1:
            raise RuntimeError("missing unique completed contextCompaction item")
        return {"turnId":turn_id,"itemId":marks[0],"elapsedSeconds":time.monotonic()-t0}

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.raw.close()
        self.err.close()


def helper(args, host, action, boundary, items, query):
    payload={"action":action,"root":str(args.memory_root),"cwd":str(args.workdir),
             "threadId":host.tid,"sessionId":args.memory_session,"boundary":boundary,
             "items":items,"query":query}
    result=subprocess.run([args.node,str(args.hook)],input=encode(payload),text=True,
                          capture_output=True,timeout=args.timeout)
    if result.returncode:
        host.record("helper/error",action=action,status=result.returncode,stderr=result.stderr[-4000:])
        raise RuntimeError(f"{action} helper failed: {result.returncode}")
    response=json.loads(result.stdout)
    if not isinstance(response,dict):
        raise ValueError("helper response must be an object")
    host.record("helper/"+action,boundary=boundary,itemIds=[e["item"]["id"] for e in items],
                requestSha256=sha(encode(payload)),response=response)
    return response


def stage_action(args, host, action, ordinal):
    cmd=[sys.executable, str(args.stage_controller), action, str(args.stage_root),
         args.task_id, str(args.workdir), str(ordinal)]
    proc=subprocess.run(cmd, text=True, capture_output=True, timeout=30)
    host.record("stage/"+action, ordinal=ordinal, returncode=proc.returncode,
                stderr=proc.stderr if proc.returncode else "")
    if proc.returncode:
        raise RuntimeError(f"{action} failed for turn {ordinal}")


def check_receipt(row, task_dir, items):
    ordinal=row["ordinal"]
    expected=(task_dir/"stages"/str(ordinal)/row["stage_file"]).read_bytes()
    wanted=expected.decode().splitlines()
    if not wanted:
        raise RuntimeError("empty stage evidence")
    locked=json.loads((task_dir/"lock.json").read_text())["stages"][str(ordinal)]["stdout_sha256"]
    if hashlib.sha256(expected).hexdigest()!=locked:
        raise RuntimeError("stage input changed")
    sources=[]
    for event in items:
        item=event["item"]
        if item["type"]!="commandExecution" or item.get("exitCode")!=0:
            continue
        output=item.get("aggregatedOutput") or ""
        lines=output.splitlines()
        if any(lines[i:i+len(wanted)]==wanted for i in range(len(lines)-len(wanted)+1)):
            sources.append({"turnId":event["turnId"],"itemId":item["id"],"stdoutSha256":sha(output)})
    return {"ordinal":ordinal,"stageFile":row["stage_file"],"expectedSha256":locked,
            "sources":sources,"verified":bool(sources)}


def run(args):
    args.workdir=args.workdir.resolve(strict=True)
    args.logs=args.logs.resolve()
    args.logs.mkdir(parents=True,exist_ok=True)
    if any(args.logs.iterdir()):
        raise ValueError("--logs must be new or empty to preserve prior receipts")
    if args.logs.is_relative_to(args.workdir):
        raise ValueError("receipts must be outside the model workspace")
    single=args.prompt_file is not None
    if single:
        messages=[args.prompt_file.read_text()]
    else:
        task_file=args.task/"turns.json" if args.task.is_dir() else args.task
        rows=json.loads(task_file.read_text())
        if [r["ordinal"] for r in rows]!=[0,1,2,3]:
            raise ValueError("expected four ordered task turns")
        messages=[r["message"] for r in rows]
    if args.arm=="A" and args.mcp_config:
        raise ValueError("A has no MCP")
    staged=not single and any("stage_file" in r for r in rows)
    if staged:
        if not (args.stage_controller and args.task_id):
            raise ValueError("staged rows require --stage-controller and --task-id")
        if task_file.parent.name!=args.task_id or not all("stage_file" in r for r in rows[:3]):
            raise ValueError("stage task ID or stage layout mismatch")
        args.stage_root=task_file.resolve().parent.parent
    elif args.stage_controller or args.task_id:
        raise ValueError("stage options require staged rows")
    mcp=None
    if args.arm!="A":
        if args.memory_root:
            args.memory_root=args.memory_root.resolve()
        if not single and not (args.memory_root and args.memory_session):
            raise ValueError("B/C four-turn trials require a private memory root and session")
        if args.mcp_config:
            mcp=json.loads(args.mcp_config.read_text())
            if set(mcp)-{"command","args","enabled_tools","tool_timeout_sec","startup_timeout_sec"}:
                raise ValueError("expected a local stdio command and supported options")
        elif args.memory_root and args.memory_session:
            mcp={"command":args.node,"args":[str(PROJECT/"packages/memex-mcp/bin/server.mjs"),
                 "--root",str(args.memory_root),"--session",args.memory_session,"--cwd",str(args.workdir),
                 "--model",MODEL,"--agent","codex","--levels","l2,l3"],
                 "enabled_tools":["memory_search","memory_open","memory_grep","memory_index","memory_list"]}
        else:
            raise ValueError("supply --mcp-config or private root/session")
        if not mcp.get("command") or not isinstance(mcp.get("args",[]),list):
            raise ValueError("invalid MCP command or args")
    budget_file = args.logs/"recovery-budget.json" if staged and mcp else None
    if budget_file:
        mcp["args"] = [str(PROJECT/"scripts/codex-retention-mcp-budget.mjs"), str(budget_file), *mcp["args"]]
    flags=codex_overrides(mcp,single)
    env={k:v for k,v in os.environ.items() if k not in
         ("OPENAI_API_KEY","CODEX_API_KEY","OPENAI_BASE_URL","OPENAI_API_BASE")}
    login=subprocess.run([args.codex,"login","status"],env=env,capture_output=True,text=True,timeout=20)
    if login.returncode or (login.stdout+login.stderr).strip()!="Logged in using ChatGPT":
        raise RuntimeError("Codex ChatGPT login was not verified")
    report={"arm":args.arm,"mode":"single" if single else "three-boundary","status":"running",
            "auth":"ChatGPT","model":MODEL,"version":subprocess.check_output(
                [args.codex,"--version"],env=env,text=True).strip(),"workdir":str(args.workdir),
            "messageSha256":[sha(s) for s in messages],"turns":[],"boundaries":[],"stageReceipts":[]}
    host=Host(args.codex,flags,args.workdir,args.logs,env,args.timeout)
    try:
        host.record("settings",flags=flags,auth=report["auth"],version=report["version"])
        instructions=BASE
        if single:
            instructions+=" Answer the supplied question. Use only explicitly provided retrieval tools."
        if mcp:
            instructions+=MEMORY
        thread=host.start({"cwd":str(args.workdir),"model":MODEL,"modelProvider":"openai",
            "allowProviderModelFallback":False,"approvalPolicy":"never",
            "sandbox":"read-only" if single else "workspace-write",
            "baseInstructions":instructions,"ephemeral":False})
        report.update(threadId=host.tid,rollout=thread.get("path"))
        inventory=host.rpc("mcpServerStatus/list",{"threadId":host.tid,"detail":"toolsAndAuthOnly","limit":100})
        servers={s["name"]:sorted(s["tools"]) for s in inventory["data"]}
        host.record("mcp/inventory",servers=servers)
        report["mcpTools"]=servers
        enabled={name for name,tools in servers.items() if tools}
        if inventory.get("nextCursor") or enabled!=({"memex"} if mcp else set()):
            raise RuntimeError("unexpected MCP inventory: "+encode(sorted(enabled)))
        context=""
        for n,message in enumerate(messages):
            host.phase=f"task-{n+1}"
            t0=time.monotonic()
            if staged and n<3:
                stage_action(args,host,"stage",n)
            policy={"type":"readOnly" if single else "workspaceWrite","networkAccess":False}
            if not single:
                policy.update(writableRoots=[str(args.workdir)],excludeTmpdirEnvVar=True,excludeSlashTmp=True)
            request={"threadId":host.tid,"input":[{"type":"text","text":message}],
                     "sandboxPolicy":policy,"effort":"low","approvalPolicy":"never"}
            if budget_file:
                proactive_chars=len(context.encode("utf-16-le"))//2
                if proactive_chars>4800:
                    raise RuntimeError("proactive evidence exceeds recovery budget")
                budget_file.write_text(encode({"ordinal":n,"remaining":4800-proactive_chars,
                    "proactive":proactive_chars,"delivered":0,"refused":0})+"\n")
            if context:
                request["additionalContext"]={"memex_archive":{"kind":"untrusted","value":context}}
            host.record("turn/request",messageSha256=sha(message),contextSha256=sha(context) if context else None)
            turn_id=host.rpc("turn/start",request)["turn"]["id"]
            items=host.complete(turn_id)
            if budget_file:
                budget=json.loads(budget_file.read_text())
                host.record("recovery/budget",**budget)
                report.setdefault("recoveryBudgets",[]).append(budget)
            if staged and n<3:
                stage_receipt=check_receipt(rows[n],task_file.parent,items)
                report["stageReceipts"].append(stage_receipt)
                host.record("stage/receipt",**stage_receipt)
                stage_action(args,host,"unstage",n)
                if not stage_receipt["verified"]:
                    raise RuntimeError("missing successful native command stdout for staged source")
            final=[e["item"].get("text","") for e in items if e["item"]["type"]=="agentMessage"]
            if not final:
                raise RuntimeError("completed turn had no agent response")
            if any(e["item"]["type"]=="contextCompaction" for e in items):
                raise RuntimeError("unexpected automatic boundary in task turn")
            report["turns"].append({"turnId":turn_id,"ordinal":n,"elapsedSeconds":time.monotonic()-t0,
                "final":final[-1],"itemKinds":[e["item"]["type"] for e in items]})
            if n==len(messages)-1:
                break
            host.phase=f"boundary-{n+1}"
            if mcp:
                eligible=[e for e in items if e["item"]["type"] in
                          ("userMessage","commandExecution","agentMessage")]
                helper(args,host,"capture",n+1,eligible,"")
            receipt=host.compact()
            report["boundaries"].append(receipt)
            host.record("compact/verified",**receipt)
            if args.arm=="C":
                context=helper(args,host,"restore",n+1,[],messages[n+1])["context"]
                if not isinstance(context,str):
                    raise ValueError("restore context must be text")
        report["status"]="completed"
    except BaseException as exc:
        report["status"]="failed"
        report["error"]=f"{type(exc).__name__}: {exc}"
        host.record("failure",error=report["error"])
        raise
    finally:
        report["usage"]=host.usage
        host.close()
        write_json(args.logs/"report.json",report)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    inp=parser.add_mutually_exclusive_group(required=True)
    inp.add_argument("--task",type=Path,help="directory containing turns.json or that file")
    inp.add_argument("--prompt-file",type=Path,help="single-turn input; skip archive and compaction")
    parser.add_argument("--arm",choices=["A","B","C"],required=True)
    parser.add_argument("--workdir",required=True,type=Path,help="private prepared workspace for this arm")
    parser.add_argument("--logs",required=True,type=Path,help="fresh directory outside the workspace")
    parser.add_argument("--memory-root",type=Path)
    parser.add_argument("--memory-session")
    parser.add_argument("--mcp-config",type=Path,help="JSON object with a local command and args")
    parser.add_argument("--stage-controller",type=Path,help="controller for staged source tasks")
    parser.add_argument("--task-id",help="staged fixture ID")
    parser.add_argument("--hook",type=Path,default=PROJECT/"scripts/codex-retention-evidence.mjs")
    parser.add_argument("--node",default=shutil.which("node"))
    parser.add_argument("--codex",default=shutil.which("codex"))
    parser.add_argument("--timeout",type=int,default=240,help="per-host-operation deadline in seconds")
    run(parser.parse_args())
