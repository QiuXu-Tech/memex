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
node --import ./test/register.mjs ./test/run.mjs   # 98/98
```

Install the built bundle into a DSH profile: [install guide](install.html).

## Documentation

- [Architecture and behavior](architecture.html) — levels, eviction seam, retrieval, compression, API/UI.
- [Evaluation](evaluation.html) — recall and scale benchmarks with methodology.
- [Benchmark report](benchmark.html) — long-horizon A/B vs no extra context, with charts.
- [Install guide](install.html) — profile registration, config rows, local fallback.

## Highlights

| | |
|---|---|
| **L1 eviction** | Uses the shipped `compaction/prune` + surface-replace seam — no custom session events, no replacement of the compaction backend. |
| **Sticky L2/L3** | Session-private vs workspace-shared archives; capture deepest enabled level; capacities 10M/100M. |
| **Hybrid recall** | Shared query-term extractor, FTS + cold abstracts + lexical rerank; real-archive recall@5 **95%** vs 67% baseline, cold recall 100%. |
| **Capacity compression** | Cold tier (lossless, zero LLM) and bounded map-reduce digests (2-way concurrency, retry/fallback, `ids:` enforcement, quota GC) — after the model asks the user. |
| **Surfaces** | Seven model tools, `/memory` command set, nine `/api/memory.*` routes, Web panel + context ring, sensitive-content policy, backup/verify/restore. |

MIT licensed © QiuXu-Tech. Not affiliated with or endorsed by DeepSeek.
