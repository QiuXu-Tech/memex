---
title: Generic MCP clients
layout: default
---

# Generic MCP clients

The MCP server is dependency-free stdio JSON-RPC 2.0; if a client supports MCP tools it works.

```bash
node packages/memex-mcp/bin/server.mjs \
  --root ~/.memex --model deepseek-flash --agent <agent-name> --levels l3
```

Options: `--root DIR`, `--levels l2,l3`, `--model ID`, `--agent NAME`, `--session ID`, `--cwd DIR`, `--capacity N`, `--session-capacity N`, `--all-tools`. stdout is protocol-only; diagnostics go to stderr.

## Tools

By default, discovery advertises four tools: `memory_search`, `memory_open`, `memory_write`, and `memory_set_status`. The status tool is included so an agent can mark a replaced record `superseded`. Add `--all-tools` to advertise the existing `memory_grep`, `memory_index`, `memory_list`, `memory_forget`, `memory_restore`, and `memory_compress` maintenance tools. Existing direct JSON-RPC calls to those names still work, but a client normally discovers only the advertised set.

Plus a `memory://catalog` resource and model-tailored `instructions` on `initialize`.

For a focused query, `memory_search` accepts `openTop: true` to include up to 2,000 characters from the first hit. Verify its relevance and use `memory_open` with `nextCharOffset` to continue a truncated preview.

## Source, version and validity

`memory_write` accepts an optional `evidence` object, for example:

```json
{"kind":"decision","title":"Deployment target","body":"Use staging","evidence":{"source":"deploy.yml","version":"git-commit-id","observedAt":"2026-11-02T00:00:00Z","validUntil":"2026-12-02T00:00:00Z"}}
```

`source` is required when `evidence` is supplied; the remaining fields are optional. Times use valid UTC ISO timestamps. The source and version are assertions supplied by the caller: Memex does not verify that the source exists or automatically compare it with a current Git checkout. Search and open display the stored metadata and trust label. Search accepts exact `source` plus `version` filters; a version filter requires a source.

Superseded and expired records are excluded from normal search and materialized windows. Search can explicitly select `status: "superseded"` or set `includeExpired: true`; an expired record can also be opened by id. Unknown validity does not mean current. Writing a new version does not automatically supersede another record: set its status after deciding it has been replaced. Existing records without the new metadata remain readable with unknown version/validity. Older arbitrary provenance is preserved on updates; an unparseable legacy expiry is treated as unknown rather than as expired.

## Client config examples

**Gemini CLI** (`~/.gemini/settings.json`):

```json
{ "mcpServers": { "memex": { "command": "node", "args": ["/path/to/server.mjs", "--root", "/Users/you/.memex", "--model", "gemini-2.5-pro", "--levels", "l3"] } } }
```

**Cursor** (`.cursor/mcp.json`):

```json
{ "mcpServers": { "memex": { "command": "node", "args": ["/path/to/server.mjs", "--root", "/Users/you/.memex", "--levels", "l3"] } } }
```

**Cline / Windsurf / Zed** — same `mcpServers` command/args shape; use the model id you run so the profile (budgets, injection format, manual) matches.

## Sharing one store

All agents can share `~/.memex` (or `$MEMEX_HOME`). Use a unique `--session ID` for an L2 namespace that must persist across processes; without an explicit id or session environment variable, each MCP server uses a fresh random id. Reusing an id shares that L2 namespace. Workspace keys are derived from `--cwd`, so a project opened by Claude Code and Codex sees the same L3 records when their workspace paths agree.
