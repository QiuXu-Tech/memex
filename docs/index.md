---
title: Memex — the extra-context layer for AI agents
layout: default
---

# Memex — the extra-context layer for AI agents

A high-performance context hierarchy between an agent's history and its model window.

[![CI](https://github.com/QiuXu-Tech/memex/actions/workflows/ci.yml/badge.svg)](https://github.com/QiuXu-Tech/memex/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/QiuXu-Tech/memex/blob/main/LICENSE)

![memex demo](assets/demo.gif)

Memex treats context as a hierarchy, not a notes store: when the native context window fills up, older spans are moved out **verbatim** into sticky **L2 (10M, session-private)** / **L3 (100M, workspace-shared)** context pools; capacity is managed through a lossless cold tier plus bounded batch digests; and any context page can be paged back in with millisecond hybrid retrieval and per-model context budgets.

## Quick start

```bash
git clone https://github.com/QiuXu-Tech/memex.git
cd memex
node scripts/build-bundle.mjs && node scripts/check-bundle.mjs
node --import ./test/register.mjs ./test/run.mjs   # offline harness (129 tests)
```

Install the built bundle into a DSH profile: [install guide](install.html).

## Documentation

- [Architecture and behavior](architecture.html) — levels, eviction seam, retrieval, compression, API/UI.
- [Evaluation](evaluation.html) — recall and scale benchmarks with methodology.
- [Benchmark report](benchmark.html) — synthetic long-horizon availability and retrieval, with charts.
- [SQLite and file consistency](storage-consistency.html) — lock handling, interrupted-operation recovery and backup scope.
- [Extra context, not just memory](context-layer.html) — the concept: a context hierarchy between history and the model window.
- [Context materialization](context-materialization.html) — the direction: canonical events, pager/materializer + DSH switch, tiny trained transformer encoder, runnable paged-KV/prefix host, structural fidelity eval.
- [Integrations](integrations.html) — Claude Code, Codex, Gemini CLI, Cursor, Cline, Windsurf, DSH.
- [Model profiles](model-profiles.html) — per-family budgets, injection formats and digest prompts.
- [Optimization findings](optimization-findings.html) — retrieval/perf experiments, fixed issues, backlog.
- [Profile validation](profile-validation.html) — cold-start + long-horizon A/B for the dedicated model profiles.
- [Live endpoint A/B](live-testing.html) — harness, status and how to run it with provider keys.
- [v0.4.0 experiments](experiments-v040.html) — rename/defaults verification, recall re-check and improvement points.
- [Claude Code](integrations/claude-code.html) · [Codex](integrations/codex.html) · [Generic MCP clients](integrations/mcp.html)
- [Install guide](install.html) — profile registration, config rows, local fallback.

## Highlights

| | |
|---|---|
| **L1 eviction** | Uses the shipped `compaction/prune` + surface-replace seam — no custom session events, no replacement of the compaction backend. |
| **Sticky context pools** | Session-private L2 vs workspace-shared L3; capture deepest enabled level; capacities 10M/100M. |
| **Context paging** | Shared query-term extractor, FTS + cold abstracts + exact numeric/identifier anchors + lexical rerank; pages are injected only when budget allows. A private archive previously reported recall@5 **93%**, cold recall 94%, hit@1 65% (68% with `coldPartial: 0`), and p50 ~2.9 ms. In the [v0.26.0 synthetic Codex Sol A/B](live-testing.html#f-codex-cli--gpt-family-historical-results-and-fixed-sol-rerun), control answered **3/60**, treatment with pre-retrieved evidence **60/60**, and evicted probes **0/57 → 57/57**; all six calls exited zero and all three actual tails were checked in order. Earlier DeepSeek, Terra and Claude results have a [tail-order caveat](live-testing.html#deepseek-flash-results-2026-10-29); Claude Sonnet/Opus/Fable/Haiku each reported **60/60** with ~39.7–40.7k gateway-reported tokens per model. Small historical anchor-free runs reported **0/3 → 3/3** for hot, cold and cold partial/synonym cases; a real Claude tool loop answered **3/3** against the live MCP server. |
| **Capacity compression** | Cold tier (lossless, zero LLM) and bounded map-reduce digests (2-way concurrency, retry/fallback, `ids:` enforcement, quota GC) — after the model asks the user. |
| **Surfaces** | Seven model tools, `/memory` command set, nine `/api/memory.*` routes, Web panel + context ring, sensitive-content policy, backup/verify/restore. |

MIT licensed © QiuXu-Tech. Not affiliated with or endorsed by DeepSeek.
