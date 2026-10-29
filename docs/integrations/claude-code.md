---
title: Claude Code
layout: default
---

# Claude Code

```bash
node packages/dsh-memory-claude/bin/cli.mjs init --model claude-sonnet-4
# or: --project /path/to/project  --root ~/.dsh-memory --levels l2,l3
```

`init` is idempotent and writes three things in the project:

| File | What it does |
|---|---|
| `.mcp.json` | registers `dsh-memory` MCP server (`memory_search`, `memory_open`, `memory_grep`, `memory_write`, `memory_index`, `memory_restore`, `memory_compress` + `memory://catalog`) |
| `.claude/settings.json` | merges `SessionStart`, `UserPromptSubmit`, `PreCompact`, `SessionEnd` hooks (keeps your existing hooks) |
| `CLAUDE.md` | appends a model-tailored memory manual in a `<!-- dsh-memory:start -->…<!-- dsh-memory:end -->` section |

## How the hooks behave

- **SessionStart** — injects a bounded memory catalog (no-op when the store is empty).
- **UserPromptSubmit** — searches the visible levels with the user's prompt and injects a `<memory-recall>` block when there are hits (cheap: one search, no LLM).
- **PreCompact** — reads `transcript_path`, archives the raw JSONL **verbatim** as one record before Claude Code compacts, and injects a receipt with the record id. This is the key difference from built-in compaction: details survive.
- **SessionEnd** — no injection; keeps cleanup cheap.

Hooks never break a session: failures are logged to stderr and the exit code stays 0.

## Recommended settings

- Use `--levels l2,l3` for both session-private and project-shared memory, or `l3` for shared project memory only.
- Set `--model` to the model you actually run (e.g. `claude-sonnet-4`, `claude-opus-4`) so budgets/manual match the family.
- Restart Claude Code after `init` so the MCP server and hooks load (check `/mcp`).

## Manual workflows

Ask Claude to "remember this" (it calls `memory_write`), or run:

```bash
node packages/dsh-memory-claude/bin/cli.mjs status
node packages/dsh-memory-claude/bin/cli.mjs print-manual --model claude-sonnet-4
```

The shared core means memory written through Claude Code is visible to the DSH plugin, Codex and any MCP client when they use the same root (default `~/.dsh-memory`; point DSH at it with `DSH_MEMORY_HOME`).
