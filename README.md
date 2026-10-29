# Memex

[![CI](https://github.com/QiuXu-Tech/memex/actions/workflows/ci.yml/badge.svg)](https://github.com/QiuXu-Tech/memex/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Persistent, lossless long-horizon memory for any coding agent.** Memex adds an extra-context layer to an agent session: when the native context window fills up, older spans are moved out verbatim into sticky L2/L3 archives, capacity is managed through a lossless cold tier plus bounded batch digests, and the model can retrieve anything later with cheap hybrid search.

It started as a DeepSeek Harness plugin and is now **agent-agnostic**:

| Agent | Integration |
|---|---|
| **DeepSeek Harness** | native Cordis bundle (L1 eviction seam, Web panel, 9 HTTP routes, 7 tools) |
| **Claude Code** | MCP server + `SessionStart` / `UserPromptSubmit` / `PreCompact` hooks + `CLAUDE.md` manual |
| **OpenAI Codex** | MCP server + `AGENTS.md` manual + `config.toml` snippet |
| **Gemini CLI, Cursor, Cline, Windsurf, Zed, …** | one stdio MCP server (`packages/memex-mcp`), 7 tools + catalog resource |
| **Any HTTP agent** | the same core can be embedded (`@qiuxu/memex-core`) |

> Status: **0.4.1 (Memex)** — agent-agnostic core, MCP server, hot-body rescue, Claude Code/Codex adapters, **21 model profiles** (13 family bases + dedicated **GPT-6.1 Sol/Terra/GPT-6 Astra, Claude Opus 5.5/Sonnet 5.5/Fable 5.1/Haiku 5.5, DeepSeek Flash** variants), 116/116 offline tests. DSH `0.2.1-rc.3` for DSH mode; any MCP-capable agent otherwise. No telemetry, everything stays on your machine.

## Why

Long conversations and long-running projects hit the same wall: the native context window is finite. The usual answers are lossy — truncate, or summarize and lose the details that turn out to matter later. memex treats conversation history like a cache hierarchy instead:

| Level | What it is | Capacity | Semantics |
|---|---|---|---|
| **L1** | The model's native context window | model window | untouched; eviction removes the oldest balanced span |
| **L2** | Session-private archive | 10M tokens / session | only this conversation can read it |
| **L3** | Workspace-shared archive | 100M tokens / cwd | every session in the working directory can read it |

- **L2 and L3 are independent, sticky switches** — once enabled a level cannot be turned off (recorded context never silently disappears).
- **Lossless by default**: raw conversation/tool output is stored verbatim (markdown files + SQLite index) — no LLM summarization on the critical path.
- **Capacity compression on demand**: when a pool is near full the model asks the user first; compression then applies a **cold tier** (lossless, zero-LLM) and optionally **bounded map-reduce digests** (batched, resumable, never one giant prompt).
- **Cheap recall**: hybrid keyword retrieval (FTS + card fields + bounded cold abstracts + lexical rerank), ~1–5 ms on realistic archives, tens of tokens per hit.
- **Model-specific adaptation**: profiles tuned per model family — context window, chars/token ratio, injection format (XML/Markdown/plain), catalog/recall budgets, digest prompt style, bilingual CJK guidance **and retrieval rerank weights** (title/tags/summary/useWhen/abstract/body/recency/bm25) passed into hybrid search. 13 family bases plus **dedicated GPT-6.1 Sol / Claude Opus 5.5 / Claude Sonnet 5.5 / DeepSeek Flash** profiles with vendor-current context limits and reasoning-mode guidance. See [docs/model-profiles.md](docs/model-profiles.md) and the [cold-start + long-horizon profile validation](docs/profile-validation.md).
- **Hot-body rescue**: identifier-like body tokens are indexed (`record_terms`) so facts that never made it into a title/summary are still found when card matches fill the limit; a `body` rerank weight ranks them. On the controlled fixture this took hot-body hit@1/@5 from **0%/0% to 100%/100%**.

## Features

- **Agent-agnostic core** (`@qiuxu/memex-core`): markdown + SQLite store, hot/cold tiers, hybrid retrieval and capacity compression with zero host dependencies. DSH, MCP and CLI adapters share one record vocabulary.
- **MCP server** (`@qiuxu/memex-mcp`): stdio JSON-RPC, **10 tools** (`memory_search/open/grep/write/index/list/forget/set_status/restore/compress`) + `memory://catalog` resource, model-tailored `instructions`.
- **Claude Code adapter** (`@qiuxu/memex-claude`): one command writes `.mcp.json`, merges `.claude/settings.json` hooks and injects a model-tailored `CLAUDE.md` manual; `PreCompact` archives the raw transcript verbatim before summary loss, `UserPromptSubmit` auto-recalls relevant records.
- **Codex adapter** (`@qiuxu/memex-codex`): `AGENTS.md` manual + `codex mcp add` / `config.toml` entry.
- **Model profiles**: per-family windows, token-estimation ratios, injection budgets and digest prompts; overridable by the integration.
- **L1 eviction** through the shipped `compaction/prune` + surface-replace seam; no custom session events, no replacement of the compaction backend.
- **Sticky L2/L3 levels** with a session-private/shared split, capture policy (deepest enabled level wins) and per-level capacities.
- **Hybrid retrieval** shared by `memory_search` and auto-recall: latin identifiers, quoted spans, CJK n-grams, stopword filtering, FTS + LIKE legs, bounded cold abstracts, lexical rerank with recency.
- **Cold tier + compression**: `memory_compress` with `cold` (lossless, zero LLM) and `digest` (bounded batched summaries, 2-way concurrency, retry/fallback, `ids:` enforcement, cold quota GC).
- **Capacity consent protocol**: `[EXTRA CONTEXT CAPACITY]` notice at 80% hot usage tells the model to ask the user before compressing.
- **Sensitive-content policy**: secret-looking spans (keys/tokens/passwords) are forced into private L2, or eviction is skipped when only L3 is available.
- **Observability**: `compression_runs` history, `GET /api/memory.metrics`, `/memory status`, `memory_index`.
- **Operations**: restore/回热, cold GC, backup/verify/restore (SQLite `VACUUM INTO` + sha256 manifest).
- **UI**: composer context-ring inner arc (teal = L2 capture, blue = L3), a popover mode row, a full memory panel with compression/restore buttons and capacity warnings.

## Demo

![memex panel and compression flow](docs/assets/demo.gif)

*A condensed illustration of the context-ring popover, the capacity notice, a lossless compression run, and the memory panel (rendered animation, not a screen recording).*

## Architecture (short version)

```
Any agent (DSH · Claude Code · Codex · Cursor · …)
 ├─ adapters: DSH bundle / MCP server / Claude hooks / Codex CLI
 │      • one shared agent-agnostic core, one record vocabulary
 │      • model profile → budgets, injection format, manual, digest prompt
 │
DSH agent session
 ├─ L1 (native window) ── evict oldest balanced span ──► extra context
 │      • compaction/prune shadow price + user/message surfaceOp replace
 │      • receipt message keeps the model oriented
 ├─ L2 session archive (10M)  ─┐
 ├─ L3 workspace archive (100M)┘   sticky, verbatim, scoped
 │
 ├─ retrieval: memory_search / memory_grep / memory_open (hybrid FTS + cold abstracts)
 ├─ capacity: hot/cold accounting, memory_compress (cold/digest), quota GC
 └─ Web: context ring + memory panel via /api/memory.* (9 owner-scoped routes)
```

Full design: [docs/architecture.md](docs/architecture.md). Measured results: [docs/evaluation.md](docs/evaluation.md). Hosted docs: <https://qiuxu-tech.github.io/memex/>. Security policy: [SECURITY.md](SECURITY.md). Upstreaming plan: [docs/upstream.md](docs/upstream.md).

## Repository layout

| Path | Purpose |
|---|---|
| `packages/memex` | installable DSH bundle (patch + exports; `modules/` is generated and git-ignored) |
| `packages/memex-core` | **agent-agnostic core**: vocabulary, query terms, store/retrieval/compression, model profiles, manual + engine facade |
| `packages/memex-mcp` | **universal MCP stdio server** (Claude Code, Codex, Gemini CLI, Cursor, Cline, …) |
| `packages/memex-claude` | Claude Code integration: `init` (MCP+hooks+CLAUDE.md) and hook handlers |
| `packages/memex-codex` | Codex integration: `AGENTS.md` manual + MCP config snippet/writer |
| `packages/memex-seam` | DSH `ctx.memory` service over the core (re-exports its vocabulary) |
| `packages/memex-local` | SQLite + markdown store: hot/cold tiers, FTS, compression history |
| `packages/memex-checkpoint` | checkpoint policy: archive/receipt/catalog/recall, capacity notice |
| `packages/memex-tool` | seven model tools + the stable memory manual prompt section |
| `packages/memex-command` | `/memory on|off|status|compress|restore|gc|search|remember|pin|…` |
| `packages/memex-evict` | L1 → L2/L3 eviction policy (sensitive-content aware) |
| `packages/memex-compress` | capacity compression (cold + digest) and compression history |
| `packages/memex-api` | nine `/api/memory.*` HTTP routes for the panel |
| `packages/memex-ui` | Web client half: panel + context-ring bridge |
| `test/` | offline harness (106 tests, no `node_modules`; stubs for host packages) |
| `scripts/` | build/check bundle, scale & recall benchmarks, backup/verify/restore |

## Requirements

- **Node.js 24+** (`node:sqlite`, ESM) — for every integration.
- **DeepSeek Harness `0.2.1-rc.3`** only for DSH mode (this repo is an extension, not a fork).
- **An MCP-capable agent** for universal mode (Claude Code, Codex, Gemini CLI, Cursor, Cline, Windsurf, Zed, …).
- No npm dependencies for the offline test suite; the MCP server and adapters need only the core package.

## Quick start — any MCP agent

```bash
git clone https://github.com/QiuXu-Tech/memex.git
cd memex
node scripts/build-bundle.mjs        # only needed for DSH mode; MCP/adapters read the source packages

# Claude Code: registers MCP + hooks + CLAUDE.md manual in this project
node packages/memex-claude/bin/cli.mjs init --model claude-sonnet-5-5

# Codex: writes AGENTS.md + prints/installs the MCP config
node packages/memex-codex/bin/cli.mjs init --model gpt-6.1-sol --write-config

# Any MCP client: point it at the stdio server
node packages/memex-mcp/bin/server.mjs --root ~/.memex --model deepseek-flash --levels l3
```

See [docs/integrations.md](docs/integrations.md), [Claude Code](docs/integrations/claude-code.md), [Codex](docs/integrations/codex.md), [generic MCP clients](docs/integrations/mcp.md) and [model profiles](docs/model-profiles.md).

## Install (DSH local bundle)

memex ships as a DSH **bundle** (a patch plus runtime modules). It is not published to npm; install it as a linked local bundle in a DSH profile:

```bash
git clone https://github.com/QiuXu-Tech/memex.git
cd memex
node scripts/build-bundle.mjs        # generates packages/memex/modules
node scripts/check-bundle.mjs        # verifies generated modules match sources
```

1. Register `packages/memex` as an installed bundle in your DSH profile (see [docs/install.md](docs/install.md) for the profile/plugin-manager and manual-patch options).
2. Reload the profile. It contributes eight rows (`memory`, `memory-checkpoint`, `memory-tools`, `memory-evict`, `memory-compress`, `memory-api`, `memory-ui`, `memory-commands`) with the config in `packages/memex/cordis.patch.yml`.
3. Open a session: the composer context ring gains an “额外上下文” popover row with **L2 / L3** switches (off by default; sticky once on).

> Some local DSH builds require the client row to be addressed by a `file:` URL instead of the `@qiuxu/memex/ui` subpath; docs/install.md has the fallback row.

## Use

- **Enable**: ring popover / memory panel → `L2 本会话` or `L3 工作区`; or `/memory on l2|l3|both`. Levels are sticky.
- **Use memory**: the model has `memory_search`, `memory_open`, `memory_grep`, `memory_write`, `memory_index`, `memory_restore`, `memory_compress`; automatic catalog/recall injections keep it oriented.
- **Capacity**: at 80% hot usage the model receives a bilingual capacity notice and asks the user first; `/memory compress [l2|l3] [ratio]` or the panel button runs the lossless cold compression; `memory_compress strategy=digest` additionally produces bounded batch summaries.
- **Maintain**: `/memory status` (hot/cold/history), `/memory restore <id>`, `/memory gc <keepTokens>`, `node --import ./test/register.mjs scripts/memory-backup.mjs backup|verify|restore`.

## Configuration (row config via the bundle patch)

| Row | Config fields |
|---|---|
| `memory` (backend) | `root`, `capacityTokens` (L3, 100M), `sessionCapacityTokens` (L2, 10M), `defaultLevels` (`none|l2|l3|both`), `settingsTtlDays` (90) |
| `memory-checkpoint` | `autoArchive`, `autoRecall`, `catalogMaxChars`, `recallMaxChars`, `cardModel`, `capacityNoticeRatio` (0.8), `capacityNoticeCooldownMs` (10 min) |
| `memory-evict` | `evictAtRatio` (0.6), `retainRatio` (0.35), `maxChars` (250k), `captureLevel` (`deepest|l2`), `sensitivePolicy` (`auto|off`) |
| `memory-compress` | `batchRecords` (20), `batchChars` (120k), `maxBatches` (6), `minAgeMs` (1h), `minDigestTokens` (2000), `coldQuotaTokens` (0 = unlimited) |

HTTP API: `GET /api/memory.index|record|search|metrics`, `POST /api/memory.status|level|compress|restore|gc` (owner-scoped by the host; document-relative paths).

## Evaluation

| Metric | Result |
|---|---|
| Historical private archive (40 curated questions; not rerun) | reported hit@5 **95%** (baseline 67%); not reproducible from the public fixture |
| Synthetic recall suite (v0.3.0 rerun) | 80/80 target-record hits at rank 1 |
| 10k records / 100M assigned tokens (v0.3.0, synthetic, quiet-start gate) | write 3.2 s; cold spill 5,000 records/50M tokens in 2.50 s; cold GC 2,500 records/25M tokens in 0.31 s |
| FTS storage (body-less card+abstract index) | Synthetic v0.3.0 100M-token pool: 9.0 MiB after writing, 26.6 MiB after cold spill; x-only bodies do not measure identifier-index overhead |

**Synthetic 160K history / 80K window, on v0.3.0:** the retained tail made 20/40 target facts available; the previously supplied summary plus tail made 24/40 available. memex search returned the target record for 40/40 probes. These are availability and retrieval checks, not end-to-end answer accuracy. Full charts, timing conditions and methodology: **[docs/benchmark.md](docs/benchmark.md)**. Recent experiments and the optimization backlog: [docs/optimization-findings.md](docs/optimization-findings.md). Post-rename verification and improvement points: [docs/experiments-v040.md](docs/experiments-v040.md). Live endpoint A/B harness/status: [docs/live-testing.md](docs/live-testing.md).

Reproduction commands, including the required saved summary and cold target ratios, are in [docs/benchmark.md](docs/benchmark.md). Additional context is in [docs/evaluation.md](docs/evaluation.md).

## Privacy

- All data stays local: `$DSH_HOME/memories` (SQLite index + markdown files + `cold/` tier). No telemetry, no network calls except the DSH model you already use.
- Archives are raw conversation/tool output — treat them with the same care as your transcripts. L3 is intentionally shared across sessions in the same working directory; sensitive-looking spans are routed to L2 when possible.
- Backup files contain the same data: store them securely (`scripts/memory-backup.mjs` writes a sha256 manifest).

## Development

```bash
node scripts/build-bundle.mjs                        # generate bundle modules
node scripts/check-bundle.mjs                        # source/bundle parity
node --import ./test/register.mjs ./test/run.mjs     # offline harness (116 tests)
node --import ./test/register.mjs scripts/recall-eval.mjs --suite all
node --import ./test/register.mjs scripts/scale-bench.mjs
```

The test harness stubs the host packages (`@deepseek-ai/*`) with ESM loader hooks, so it needs no `node_modules` and no DSH install; it spawns the MCP server and adapter CLIs to test the universal path end-to-end. See [test/README.md](test/README.md) and [CONTRIBUTING.md](CONTRIBUTING.md). Upstream package export: `node scripts/export-upstream.mjs` (see [docs/upstream.md](docs/upstream.md)).

## License

[MIT](LICENSE) © QiuXu-Tech. Not affiliated with or endorsed by DeepSeek; DeepSeek Harness is a separate project and is not bundled here.
