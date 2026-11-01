---
title: Isolated pilot tools for MCP agents
layout: default
---

# Isolated pilot tools for MCP agents

`scripts/prospective-agent-mcp.mjs` exposes the existing bounded repository worker to an MCP-capable agent. The model can read and search an assigned repository, make exact replacements, search/open a supplied history archive, and run the assigned tests. The worker's `public_test` invokes `scripts/prospective-vm-sandbox.sh` inside a dedicated Linux VM: the tested source and checks are read-only, the test has no network, and the test command is fixed by the operator. The MCP bridge itself is an adapter; isolation depends on connecting it to the trusted worker and sandbox described here.

This interface was exercised by real Codex CLI `0.166.0-alpha.5.1` and by a Claude Code `2.1.283` connection smoke. The latter's event stream and tool trace show a successful read and test, but its wrapper failed while recording the process exit code. DSH has not been exercised through this interface. [Experiment and results](../production-real-agent-20261101.md).

## Prepare a worker

Use a disposable Linux VM with Node 24+ at `/opt/memex-pilot/node/bin/node`, Python 3, `bubblewrap`, `systemd-run`, `timeout`, `prlimit`, and the project's fixed sandbox supervisor installed at `/opt/memex-pilot/prospective-vm-sandbox.sh`. The worker invokes that supervisor using non-interactive `sudo` **inside the VM**. The supervisor requires a preassigned workspace under `/opt/memex-pilot/workspaces/` and a check directory under `/opt/memex-pilot/checks/`; the latter must contain a trusted `verify.js`. Install `scripts/prospective-agent-worker-v4.py` in that VM and assign each arm its own workspace. The [earlier VM boundary checks](../production-prospective-canary.md#isolated-agent-environment-and-synthetic-check) describe the tested setup.

The worker reads JavaScript, TypeScript, JSON and Python source; it edits the allowed source types, excludes test directories from edits, rejects absolute and escaping paths and symlinks, and runs only the assigned check. Put the verifier outside the editable workspace. The bridge allows five `repo_test` calls per server process. Its worker response timeout defaults to 120 seconds and can be changed with `--worker-timeout-ms`; after a timeout the worker is retired and the ambiguous request is not retried.

Optionally prepare a private UTF-8 archive as an array of records:

```json
[{"id":"H1","text":"Earlier project context available to this task."}]
```

`--trace` records tool arguments and results, which can include private project history. Use a private directory and retain failed calls as well as successful ones. Omitting `--archive` gives an empty history; omitting `--trace` disables this file log.

## Codex example

Replace the absolute paths, VM name, workspace and checks with your own preconfigured disposable environment. The following uses per-invocation overrides and does not install a global MCP entry. It disables unrelated app/plugin, shell and web-search tools for this evaluation; it is not a general-purpose Codex configuration. See the official [non-interactive](https://learn.chatgpt.com/docs/non-interactive-mode), [MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) and [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference) documentation for current flags.

```bash
codex exec --ignore-user-config \
  --disable shell_tool --disable unified_exec \
  --disable apps --disable plugins --disable remote_plugin --disable tool_suggest \
  --sandbox workspace-write --skip-git-repo-check --cd /ABS/WORK/agent \
  -c 'approval_policy="never"' -c 'web_search="disabled"' \
  -c 'mcp_servers.pilot.command="/opt/homebrew/bin/node"' \
  -c 'mcp_servers.pilot.args=["/ABS/MEMEX/scripts/prospective-agent-mcp.mjs","--archive","/ABS/WORK/history.json","--trace","/ABS/WORK/tools.jsonl","--","/opt/homebrew/bin/limactl","shell","pilot-vm","python3","/opt/memex-pilot/prospective-agent-worker-v4.py","--workspace","/opt/memex-pilot/workspaces/EXAMPLE","--checks","/opt/memex-pilot/checks/EXAMPLE"]' \
  -c 'mcp_servers.pilot.default_tools_approval_mode="approve"' \
  'Inspect the assigned repository, make the requested change, and run the assigned checks.'
```

For a memory-enabled run, add the Memex MCP server separately and generate its project manual in the disposable host workspace, as described in the [Codex integration](codex.md). Give the two processes in a cross-session test the same L3 store and workspace scope; a new L2 session is not automatically shared. The pilot disabled unrelated connectors after an earlier attempt found one automatically loaded despite `--ignore-user-config`. A later run also attempted built-in web search, so the example explicitly disables it.

## Claude Code example

Create a private `pilot-mcp.json` with the same trusted command and arguments:

```json
{
  "mcpServers": {
    "pilot": {
      "command": "/opt/homebrew/bin/node",
      "args": ["/ABS/MEMEX/scripts/prospective-agent-mcp.mjs", "--archive", "/ABS/WORK/history.json", "--trace", "/ABS/WORK/tools.jsonl", "--", "/opt/homebrew/bin/limactl", "shell", "pilot-vm", "python3", "/opt/memex-pilot/prospective-agent-worker-v4.py", "--workspace", "/opt/memex-pilot/workspaces/EXAMPLE", "--checks", "/opt/memex-pilot/checks/EXAMPLE"]
    }
  }
}
```

```bash
claude -p 'Inspect the assigned repository and run its assigned checks.' \
  --restricted --strict-mcp-config --mcp-config /ABS/WORK/pilot-mcp.json \
  --tools '' --allowedTools 'mcp__pilot__repo_read,mcp__pilot__repo_search,mcp__pilot__repo_test,mcp__pilot__archive_search,mcp__pilot__archive_open'
```

Add `mcp__pilot__repo_edit` to the allow list only for a task authorized to edit its disposable copy. Claude Code's [`--tools`](https://code.claude.com/docs/en/cli-reference) option controls built-in tools separately from MCP tools. Configure authentication through your existing provider mechanism; do not put credentials into the MCP configuration or trace file.
