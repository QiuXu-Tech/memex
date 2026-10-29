---
title: Claude Code
layout: default
---

# Claude Code

```bash
node packages/dsh-memory-claude/bin/cli.mjs init --model claude-sonnet-5-5
# or: --model claude-opus-5-5  (1M context, adaptive thinking)
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
- Set `--model` to the model you actually run (e.g. `claude-sonnet-5-5`, `claude-opus-5-5`) so budgets/manual match the family. The dedicated 5.5 profiles use the current 2.6 chars/token estimate and Opus/Sonnet-specific budgets; older ids keep the base `claude` profile.
- Restart Claude Code after `init` so the MCP server and hooks load (check `/mcp`).
- Project-scoped `.mcp.json` servers require a **one-time approval**: `claude mcp list` shows `dsh-memory … Pending approval (run claude to approve)` until you run `claude` in the project and approve it. This is Claude Code's security gate, not a config error.
- L2-only setups: hooks use the client session id, MCP tools use `default-session`; `init` prints a warning. Prefer `--levels l2,l3` or `l3` (shared project memory), or start hooks/MCP with the same `--session`."")
p.write_text(s)

# ---------- test README ----------
p=pathlib.Path('test/README.md'); s=p.read_text()
s=s.replace('Expected output ends with `# 110/110 passed`.', 'Expected output ends with `# 112/112 passed`.').replace('**110/110 passed**','**112/112 passed**')
s=s.replace("- **Operations**: backup/verify/restore scripts.", "- **Operations**: backup/verify/restore scripts.
- **Hot-body rescue (0.3.0)**: identifier-only body-term index, rare-anchor rescue and boundary-aware term matching (U13); MCP parity tools list/forget/set-status (U14).")
p.write_text(s)

# ---------- architecture ----------
p=pathlib.Path('docs/architecture.md'); s=p.read_text()
s=s.replace(## 11.4 Hot-body rescue (v0.3.0)

Card retrieval legs only see title/summary/useWhen/tags/abstract, so a fact that lives only in a hot body could be invisible when card matches fill the candidate limit (measured 0% hit@5 on a controlled fixture). v0.3.0 adds:

- `record_terms(record_id, term_hash)` — an inverted index of **identifier-like** body tokens (digits, hyphens, underscores, paths); ~1.5 rows/record on the fixture, so the DB stays small.
- **Rare-anchor rescue** in `search()`: when query terms are missing from card candidates and the query has an identifier-like anchor, one indexed `GROUP BY` ranks body candidates by exact query-term count, only those bodies are read, and `bodyHits × body(5.0)` is added to the rerank score.
- **Boundary-aware term matching** (`termMatchesText`): `inc-1` no longer matches `inc-161`; CJK/paths keep substring semantics.
- `record_terms` is backfilled once on migration; adapter writes (`memory_write`, PreCompact) feed it automatically.

Acceptance: body-only probe hit@1/hit@5 0%/0% → **100%/100%**. Natural-language-only body facts (no identifier anchor) still rely on card summaries / `memory_grep`.

## 12. Agent-agnostic adapters (v0.2.0)

## Manual workflows

Ask Claude to "remember this" (it calls `memory_write`), or run:

```bash
node packages/dsh-memory-claude/bin/cli.mjs status
node packages/dsh-memory-claude/bin/cli.mjs print-manual --model claude-sonnet-4
```

The shared core means memory written through Claude Code is visible to the DSH plugin, Codex and any MCP client when they use the same root (default `~/.dsh-memory`; point DSH at it with `DSH_MEMORY_HOME`).
