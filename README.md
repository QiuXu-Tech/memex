# dsh-memory

[![CI](https://github.com/QiuXu-Tech/dsh-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/QiuXu-Tech/dsh-memory/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Lossless long-horizon memory for [DeepSeek Harness](https://github.com/deepseek-ai).** dsh-memory adds an extra-context layer to an agent session: when the native context window fills up, older spans are moved out verbatim into sticky L2/L3 archives, capacity is managed through a lossless cold tier plus bounded batch digests, and the model can retrieve anything later with cheap hybrid search.

> Status: **0.1.0** — nine packages, 98/98 offline tests, nine HTTP routes, seven model tools, a Web panel, and a context-ring integration. Built for DSH `0.2.1-rc.3`; no telemetry, everything stays on your machine.

## Why

Long conversations and long-running projects hit the same wall: the native context window is finite. The usual answers are lossy — truncate, or summarize and lose the details that turn out to matter later. dsh-memory treats conversation history like a cache hierarchy instead:

| Level | What it is | Capacity | Semantics |
|---|---|---|---|
| **L1** | The model's native context window | model window | untouched; eviction removes the oldest balanced span |
| **L2** | Session-private archive | 10M tokens / session | only this conversation can read it |
| **L3** | Workspace-shared archive | 100M tokens / cwd | every session in the working directory can read it |

- **L2 and L3 are independent, sticky switches** — once enabled a level cannot be turned off (recorded context never silently disappears).
- **Lossless by default**: raw conversation/tool output is stored verbatim (markdown files + SQLite index) — no LLM summarization on the critical path.
- **Capacity compression on demand**: when a pool is near full the model asks the user first; compression then applies a **cold tier** (lossless, zero-LLM) and optionally **bounded map-reduce digests** (batched, resumable, never one giant prompt).
- **Cheap recall**: hybrid keyword retrieval (FTS + card fields + bounded cold abstracts + lexical rerank), ~1–5 ms on realistic archives, tens of tokens per hit.

## Features

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

![dsh-memory panel and compression flow](docs/assets/demo.gif)

*A condensed illustration of the context-ring popover, the capacity notice, a lossless compression run, and the memory panel (rendered animation, not a screen recording).*

## Architecture (short version)

```
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

Full design: [docs/architecture.md](docs/architecture.md). Measured results: [docs/evaluation.md](docs/evaluation.md). Hosted docs: <https://qiuxu-tech.github.io/dsh-memory/>. Security policy: [SECURITY.md](SECURITY.md). Upstreaming plan: [docs/upstream.md](docs/upstream.md).

## Repository layout

| Path | Purpose |
|---|---|
| `packages/dsh-memory` | installable DSH bundle (patch + exports; `modules/` is generated and git-ignored) |
| `packages/dsh-memory-seam` | Cordis-free service API, record vocabulary, shared query-term extractor |
| `packages/dsh-memory-local` | SQLite + markdown store: hot/cold tiers, FTS, compression history |
| `packages/dsh-memory-checkpoint` | checkpoint policy: archive/receipt/catalog/recall, capacity notice |
| `packages/dsh-memory-tool` | seven model tools + the stable memory manual prompt section |
| `packages/dsh-memory-command` | `/memory on|off|status|compress|restore|gc|search|remember|pin|…` |
| `packages/dsh-memory-evict` | L1 → L2/L3 eviction policy (sensitive-content aware) |
| `packages/dsh-memory-compress` | capacity compression (cold + digest) and compression history |
| `packages/dsh-memory-api` | nine `/api/memory.*` HTTP routes for the panel |
| `packages/dsh-memory-ui` | Web client half: panel + context-ring bridge |
| `test/` | offline harness (98 tests, no `node_modules`; stubs for host packages) |
| `scripts/` | build/check bundle, scale & recall benchmarks, backup/verify/restore |

## Requirements

- **DeepSeek Harness `0.2.1-rc.3`** (the host runtime; this repo is an extension, not a fork).
- **Node.js 24+** (`node:sqlite`, ESM).
- No npm dependencies for the offline test suite.

## Install (local bundle)

dsh-memory ships as a DSH **bundle** (a patch plus runtime modules). It is not published to npm; install it as a linked local bundle in a DSH profile:

```bash
git clone https://github.com/QiuXu-Tech/dsh-memory.git
cd dsh-memory
node scripts/build-bundle.mjs        # generates packages/dsh-memory/modules
node scripts/check-bundle.mjs        # verifies generated modules match sources
```

1. Register `packages/dsh-memory` as an installed bundle in your DSH profile (see [docs/install.md](docs/install.md) for the profile/plugin-manager and manual-patch options).
2. Reload the profile. It contributes eight rows (`memory`, `memory-checkpoint`, `memory-tools`, `memory-evict`, `memory-compress`, `memory-api`, `memory-ui`, `memory-commands`) with the config in `packages/dsh-memory/cordis.patch.yml`.
3. Open a session: the composer context ring gains an “额外上下文” popover row with **L2 / L3** switches (off by default; sticky once on).

> Some local DSH builds require the client row to be addressed by a `file:` URL instead of the `@qiuxu/dsh-memory/ui` subpath; docs/install.md has the fallback row.

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
| Real natural-language recall (40 curated questions) | hit@5 **95%** (baseline 67%), cold-record recall **100%**, p50 1.3 ms |
| Synthetic recall suite | 100% |
| 10k records / 100M tokens (synthetic) | write 2.8 s; facets 11 ms, catalog 18 ms, search 17–29 ms, grep 15 ms; compression of 5,000 records/50M tokens 2.6 s; cold GC 2,500 records/25M 0.3 s |
| FTS storage (body-less card+abstract index) | 100M-token pool ≈ 9–27 MiB index vs GB-scale trigram-body indexing |

**A/B against no extra context** (160K-token history, 80K window): fact recall **100%** with dsh-memory vs **60%** with a model-written compaction summary (+tail) and **50%** with plain truncation; at 10M tokens the no-memory window covers only 10% of history while retrieval stays at 100% hit@5. Full charts and methodology: **[docs/benchmark.md](docs/benchmark.md)**.

Reproduce: `node --import ./test/register.mjs scripts/recall-eval.mjs --suite all`, `node --import ./test/register.mjs scripts/scale-bench.mjs --records 10000 --tokens 10000`, and `node --import ./test/register.mjs scripts/long-horizon-eval.mjs --mode compaction` / `--mode scale`. Details in [docs/evaluation.md](docs/evaluation.md).

## Privacy

- All data stays local: `$DSH_HOME/memories` (SQLite index + markdown files + `cold/` tier). No telemetry, no network calls except the DSH model you already use.
- Archives are raw conversation/tool output — treat them with the same care as your transcripts. L3 is intentionally shared across sessions in the same working directory; sensitive-looking spans are routed to L2 when possible.
- Backup files contain the same data: store them securely (`scripts/memory-backup.mjs` writes a sha256 manifest).

## Development

```bash
node scripts/build-bundle.mjs                        # generate bundle modules
node scripts/check-bundle.mjs                        # source/bundle parity
node --import ./test/register.mjs ./test/run.mjs     # offline harness (98 tests)
node --import ./test/register.mjs scripts/recall-eval.mjs --suite all
node --import ./test/register.mjs scripts/scale-bench.mjs
```

The test harness stubs the host packages (`@deepseek-ai/*`) with ESM loader hooks, so it needs no `node_modules` and no DSH install. See [test/README.md](test/README.md) and [CONTRIBUTING.md](CONTRIBUTING.md). Upstream package export: `node scripts/export-upstream.mjs` (see [docs/upstream.md](docs/upstream.md)).

## License

[MIT](LICENSE) © QiuXu-Tech. Not affiliated with or endorsed by DeepSeek; DeepSeek Harness is a separate project and is not bundled here.
