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

- **SessionStart** — injects a short availability notice (no-op when the store is empty); use `memory_index` when a catalog is needed.
- **UserPromptSubmit** — searches the visible levels with the user's prompt and injects a `<memory-recall>` block when there are hits (cheap: one search, no LLM).
- **PreCompact** — copies the raw JSONL into one or more untrusted L2 records keyed to the actual Claude client session. The records include part numbers and a SHA-256; retrying the same transcript fills missing parts without duplicating completed ones. With L2 disabled or no client session id, the hook skips this copy and leaves the original transcript in place. The copy is complete only when all parts are present and match the digest. PreCompact does not inject context.
- **Stop** — automatically stores the assistant’s completed response as an untrusted episode (minimum 32 characters), without another model call. Repeated identical responses in the same session are deduplicated, and generic refusal-only replies are skipped. High-confidence credential patterns are skipped; this is not a complete sensitive-data detector. The record follows the enabled L2/L3 scope, so L3 makes it visible to later sessions in the same workspace.
- **SessionEnd** — no injection; keeps cleanup cheap.

Auto-recall excludes Stop records from the current Claude client session to avoid repeating text already in context; they remain available through explicit memory search. An explicit `--session` selects the L2 namespace and therefore makes that namespace visible to any client using the same id. Raw PreCompact transcripts still use the actual client session rather than that override. Later sessions receive bounded summary previews and can open records visible to them. Re-run `memex-claude init` to update an existing installation.

MCP `memory_write` records are marked untrusted because an agent's assertion is not verification. Search previews and opened records show that label; check consequential claims against current evidence. Existing records are not relabeled, and the label itself does not determine whether a claim is true.

Hooks never break a session: failures are logged to stderr and the exit code stays 0.

## Recommended settings

- Use `--levels l2,l3` for both session-private and project-shared memory, or `l3` for shared project memory only.
- Set `--model` to the model you actually run (e.g. `claude-sonnet-5-5`, `claude-opus-5-5`) so budgets/manual match the family. The dedicated 5.5 profiles use the current 2.6 chars/token estimate and Opus/Sonnet-specific budgets; older ids keep the base `claude` profile.
- Restart Claude Code after `init` so the MCP server and hooks load (check `/mcp`).
- Project-scoped `.mcp.json` servers require a **one-time approval**: `claude mcp list` shows `memex … Pending approval (run claude to approve)` until you run `claude` in the project and approve it. This is Claude Code's security gate, not a config error.
- Without `--session`, hooks use the client session id while the MCP server gets its own random id. MCP cannot open a hook's L2 transcript automatically; the integration has no verified host-provided binding between these processes. An explicitly shared `--session` aligns ordinary hook/MCP L2 writes but is shared by every client configured with that id and does not bind the private PreCompact copy. Use L3 for memories intended to be shared between sessions.
- Project initialization pins hook and MCP workspace identity to the same project directory, including when a hook runs in a subdirectory. For `--user`, hooks prefer `CLAUDE_PROJECT_DIR` and otherwise use the hook payload; the MCP process workspace must agree. User-level MCP registration is in `~/.claude.json` and its manual is in `~/.claude/CLAUDE.md`.
- The [Claude Code memory documentation](https://code.claude.com/docs/en/memory) describes the user manual location; the [hooks reference](https://code.claude.com/docs/en/hooks) describes `CLAUDE_PROJECT_DIR`.
- Existing malformed JSON configurations cause `init` to stop before changing its files. Co-located non-Memex hooks and existing configuration symlinks are retained. Each file replacement is atomic, but the three files are not a single transaction. Existing archives are not automatically reclassified or erased by these changes.

## Manual workflows

Ask Claude to "remember this" (it calls `memory_write`), or run:

```bash
node packages/memex-claude/bin/cli.mjs status
node packages/memex-claude/bin/cli.mjs print-manual --model claude-sonnet-4
```

The shared core means memory written through Claude Code is visible to the DSH plugin, Codex and any MCP client when they use the same root (default `~/.memex`; point DSH at it with `MEMEX_HOME`).
