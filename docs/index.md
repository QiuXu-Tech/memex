---
title: dsh-memory
layout: default
---

# dsh-memory

Lossless long-horizon memory for **DeepSeek Harness**.

[![CI](https://github.com/QiuXu-Tech/dsh-memory/actions/workflows/ci.yml/badge.svg)](https://github.com/QiuXu-Tech/dsh-memory/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/QiuXu-Tech/dsh-memory/blob/main/LICENSE)

![dsh-memory demo](assets/demo.gif)

An extra-context layer for agent sessions: when the native context window fills up, older spans are moved out verbatim into sticky **L2 (10M, session-private)** / **L3 (100M, workspace-shared)** archives; capacity is managed through a lossless cold tier plus bounded batch digests; and anything can be retrieved later with cheap hybrid search.

## Quick start

```bash
git clone https://github.com/QiuXu-Tech/dsh-memory.git
cd dsh-memory
node scripts/build-bundle.mjs && node scripts/check-bundle.mjs
node --import ./test/register.mjs ./test/run.mjs   # offline harness (110 tests)
```

Install the built bundle into a DSH profile: [install guide](install.html).

## Documentation

- [Architecture and behavior](architecture.html) — levels, eviction seam, retrieval, compression, API/UI.
- [Evaluation](evaluation.html) — recall and scale benchmarks with methodology.
- [Benchmark report](benchmark.html) — long-horizon A/B vs no extra context, with charts.
- [Integrations](integrations.html) — Claude Code, Codex, Gemini CLI, Cursor, Cline, Windsurf, DSH.
- [Model profiles](model-profiles.html) — per-family budgets, injection formats and digest prompts.
- [Optimization findings](optimization-findings.html) — retrieval/perf experiments, fixed issues, backlog.
- [Profile validation](profile-validation.html) — cold-start + long-horizon A/B for the dedicated model profiles.
- [Claude Code](integrations/claude-code.html) · [Codex](integrations/codex.html) · [Generic MCP clients](integrations/mcp.html)
- [Install guide](install.html) — profile registration, config rows, local fallback.

## Highlights

| | |
|---|---|
| **L1 eviction** | Uses the shipped `compaction/prune` + surface-replace seam — no custom session events, no replacement of the compaction backend. |
| **Sticky L2/L3** | Session-private vs workspace-shared archives; capture deepest enabled level; capacities 10M/100M. |
| **Hybrid recall** | Shared query-term extractor, FTS + cold abstracts + lexical rerank. A historical private-archive run reported recall@5 **95%** vs a 67% baseline; that archive was not rerun in the public benchmark. |
| **Capacity compression** | Cold tier (lossless, zero LLM) and bounded map-reduce digests (2-way concurrency, retry/fallback, `ids:` enforcement, quota GC) — after the model asks the user. |
| **Surfaces** | Seven model tools, `/memory` command set, nine `/api/memory.*` routes, Web panel + context ring, sensitive-content policy, backup/verify/restore. |

MIT licensed © QiuXu-Tech. Not affiliated with or endorsed by DeepSeek.
