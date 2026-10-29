---
title: Integrations
layout: default
---

# Integrations: use memex from any agent

memex is now an **agent-agnostic memory layer**. One core, four ways in:

```
                        ┌─────────────────────────────┐
                        │ @qiuxu/memex-core      │
                        │ store · retrieval · cold tier│
                        │ model profiles · manual      │
                        └─────────────┬───────────────┘
        ┌───────────────────┬─────────┴─────────┬───────────────────┐
        │                   │                   │                   │
  DSH bundle          MCP stdio server    Claude Code adapter   Codex adapter
  (native L1 eviction  (any MCP client:    (MCP + hooks +        (MCP + AGENTS.md)
   panel, routes)       Claude, Codex,     CLAUDE.md)
                        Gemini, Cursor…)
```

| Agent | Setup | Capture | Recall |
|---|---|---|---|
| DeepSeek Harness | install bundle, enable L2/L3 in the ring/panel | L1 eviction seam (verbatim spans) | `memory_search` + auto-recall |
| [Claude Code](integrations/claude-code.html) | `memex-claude init` | `PreCompact` hook archives the raw transcript; `memory_write` tools | `SessionStart` catalog, `UserPromptSubmit` auto-recall, MCP tools |
| [OpenAI Codex](integrations/codex.html) | `memex-codex init --write-config` | agent calls `memory_write` | MCP tools + `AGENTS.md` guidance |
| [Gemini CLI / Cursor / Cline / Windsurf / Zed …](integrations/mcp.html) | register the stdio MCP server | agent calls `memory_write` | MCP tools + resource |

## Shared data model

- **Storage root**: `$MEMEX_HOME` (default `~/.memex`). The DSH plugin uses `$DSH_HOME/memories` unless it is configured otherwise — set `MEMEX_HOME` to share one store across agents.
- **Levels**: `l2` = session-private (needs a session id), `l3` = workspace-shared (keyed by cwd). Sticky: once enabled, a level cannot be turned off.
- **Scope selection on write**: the deepest enabled level wins (L3 over L2). Write with `scope: "session"` to force private capture.
- **Model profile**: resolve with `--model <id>` (MCP/adapters) or `MEMEX_MODEL`. Profiles change budgets, injection format and manual tone; see [model profiles](model-profiles.html).

## Security

Archives are verbatim user/agent output. Treat the memory root as sensitive:

- Memory content is **data, never instructions** — the manual tells agents not to execute commands found in archives.
- Use `l2` (session-private) instead of `l3` for secrets you must keep; the sensitive heuristics are not a DLP system.
- Back up (`scripts/memory-backup.mjs`) and protect the backup directory like a transcript archive.
