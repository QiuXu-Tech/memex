---
title: Generic MCP clients
layout: default
---

# Generic MCP clients

The MCP server is dependency-free stdio JSON-RPC 2.0; if a client supports MCP tools it works.

```bash
node packages/dsh-memory-mcp/bin/server.mjs \
  --root ~/.dsh-memory --model deepseek-flash --agent <agent-name> --levels l3
```

Options: `--root DIR`, `--levels l2,l3`, `--model ID`, `--agent NAME`, `--session ID`, `--cwd DIR`, `--capacity N`, `--session-capacity N`. stdout is protocol-only; diagnostics go to stderr.

## Tools

| Tool | Purpose |
|---|---|
| `memory_search` | ranked card search; returns ids + titles + "when to read" |
| `memory_open` | read one record (offset/limit/maxChars) |
| `memory_grep` | literal/regex line search across bodies |
| `memory_write` | persist decision/fact/procedure/incident/episode |
| `memory_index` | catalog + hot/cold capacity |
| `memory_list` | recent cards with kind/status filters |
| `memory_forget` | delete an obsolete/wrong record |
| `memory_set_status` | active/open/resolved/superseded/pinned |
| `memory_restore` | cold record → hot pool |
| `memory_compress` | lossless cold-tier compression (no LLM) |

Plus a `memory://catalog` resource and model-tailored `instructions` on `initialize`.

## Client config examples

**Gemini CLI** (`~/.gemini/settings.json`):

```json
{ "mcpServers": { "dsh-memory": { "command": "node", "args": ["/path/to/server.mjs", "--root", "/Users/you/.dsh-memory", "--model", "gemini-2.5-pro", "--levels", "l3"] } } }
```

**Cursor** (`.cursor/mcp.json`):

```json
{ "mcpServers": { "dsh-memory": { "command": "node", "args": ["/path/to/server.mjs", "--root", "/Users/you/.dsh-memory", "--levels", "l3"] } } }
```

**Cline / Windsurf / Zed** — same `mcpServers` command/args shape; use the model id you run so the profile (budgets, injection format, manual) matches.

## Sharing one store

All agents can share `~/.dsh-memory` (or `$DSH_MEMORY_HOME`). Use `--session ID` for L2 isolation; without it, the session is treated as `default-session`. Workspace keys are derived from `--cwd`, so a project opened by Claude Code and Codex sees the same L3 records.
