---
title: Claude Code
layout: default
---

# Claude Code

```bash
node packages/memex-claude/bin/cli.mjs init --model claude-sonnet-5-5
# or: --model claude-opus-5-5  (1M context, adaptive thinking)
# or: --project /path/to/project  --root ~/.memex --levels l2,l3
```

`init` is idempotent and writes three things in the project:

| File | What it does |
|---|---|
| `.mcp.json` | registers `memex` MCP server (`memory_search`, `memory_open`, `memory_grep`, `memory_write`, `memory_index`, `memory_restore`, `memory_compress` + `memory://catalog`) |
| `.claude/settings.json` | merges `SessionStart`, `UserPromptSubmit`, `PreCompact`, `Stop`, `SessionEnd` hooks (keeps your existing hooks) |
| `CLAUDE.md` | appends a model-tailored memory manual in a `<!-- memex:start -->…<!-- memex:end -->` section |

## How the hooks behave

- **SessionStart** — injects a bounded memory catalog (no-op when the store is empty).
- **UserPromptSubmit** — searches the visible levels with the user's prompt and injects a `<memory-recall>` block when there are hits (cheap: one search, no LLM).
- **PreCompact** — reads `transcript_path`, archives the raw JSONL as one record before Claude Code compacts (clipped at the store body limit). PreCompact does not inject context. This is the key difference from built-in compaction: details survive.
- **Stop** — automatically stores the assistant’s completed response as an untrusted episode (minimum 32 characters), without another model call. Repeated identical responses in the same session are deduplicated. High-confidence credential patterns are skipped; this is not a complete sensitive-data detector. The record follows the enabled L2/L3 scope, so L3 makes it visible to later sessions in the same workspace.
- **SessionEnd** — no injection; keeps cleanup cheap.

Auto-recall excludes Stop records from the current session to avoid repeating text already in context; they remain available through explicit memory search. Later sessions receive bounded summary previews and can open the full record when needed. Re-run `memex-claude init` to add the Stop hook to an existing installation.

Hooks never break a session: failures are logged to stderr and the exit code stays 0.

## Recommended settings

- Use `--levels l2,l3` for both session-private and project-shared memory, or `l3` for shared project memory only.
- Set `--model` to the model you actually run (e.g. `claude-sonnet-5-5`, `claude-opus-5-5`) so budgets/manual match the family. The dedicated 5.5 profiles use the current 2.6 chars/token estimate and Opus/Sonnet-specific budgets; older ids keep the base `claude` profile.
- Restart Claude Code after `init` so the MCP server and hooks load (check `/mcp`).
- Project-scoped `.mcp.json` servers require a **one-time approval**: `claude mcp list` shows `memex … Pending approval (run claude to approve)` until you run `claude` in the project and approve it. This is Claude Code's security gate, not a config error.
- L2-only setups: hooks use the client session id, MCP tools use `default-session`; `init` prints a warning. Prefer `--levels l2,l3` or `l3` (shared project memory), or start hooks/MCP with the same `--session`.

## Manual workflows

Ask Claude to "remember this" (it calls `memory_write`), or run:

```bash
node packages/memex-claude/bin/cli.mjs status
node packages/memex-claude/bin/cli.mjs print-manual --model claude-sonnet-4
```

The shared core means memory written through Claude Code is visible to the DSH plugin, Codex and any MCP client when they use the same root (default `~/.memex`; point DSH at it with `MEMEX_HOME`).
