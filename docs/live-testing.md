---
title: Live endpoint A/B
layout: default
---

# Live endpoint A/B: help us collect multi-model data

Offline validation (retrieval, profiles, cold start, 100M scale) is complete. The next step needs **real usage data from many people running many models**: quality and token-usage differ per model family, and we want to validate and tune the dedicated profiles (Claude 5.5 series, GPT-6.1 series, GPT-6 Astra, DeepSeek Flash, and the family profiles) against actual model behavior rather than synthetic proxies.

Tracking request and discussion: [issue #1](https://github.com/QiuXu-Tech/memex/issues/1).

## DeepSeek Flash results (2026-10-29)

### A. Evidence-in-prompt A/B

Two independent fresh-context calls on **DeepSeek Flash** (via DSH's DeepSeek Account route), synthetic 120-turn fixture, 8 deep-fact questions (7 outside the retained tail):

| Condition | Overall | Evicted-fact subset |
|---|---|---|
| control (recent tail only) | **1/8 (12.5%)** | **0/7 (0%)** |
| treatment (tail + memex evidence) | **8/8 (100%)** | **7/7 (100%)** |

The only control success was a fact still inside the retained tail; every evicted fact was answered correctly only with memex evidence.

### B. Multi-seed replication (3 seeds × 300-turn history × 20 probes)

| Condition | Overall | Evicted records (excluding the one tail fact) | Cold-tier natural-language subset (turns 0–135) |
|---|---|---|---|
| control | **3/60 (5%)** | **0/57 (0%)** | 0/30 |
| treatment | **30/60 (50%)** | **27/57 (47.4%)** | **0/30** |

All three seeds showed the same pattern. Hot-region probes (turns 150+) and the tail probe were answered; **all 30 failures are cold-tier facts queried with natural language and no identifier-like anchor** — a concrete retrieval gap this validation exposed.

### C. Full agent loop (tools, n=1)

A mediated tool protocol: the model emits JSON tool calls, the harness executes them against the real memex MCP server.

- control (no tools): `UNKNOWN` — wrong.
- treatment: `memory_search` (noisy query) → refined `memory_search` (expected record at rank 10) → `memory_open` → **`FACT-025-r6h18`** — correct, 3 tool calls, 4 turns.

This shows the loop can search, refine, open and answer end-to-end; n=1 is a mechanism check, not a statistical result.

Raw data: [evidence-in-prompt 8 probes](assets/benchmarks/live-ab-deepseek.json) · [multi-seed](assets/benchmarks/live-ab-deepseek-multiseed.json) · [agent loop](assets/benchmarks/live-ab-deepseek-agent-loop.json).

**Caveats:** one model; synthetic fixtures; multi-seed runs are agent-mediated (no provider usage tokens captured); the cold-tier gap in B is a real limitation to fix, not a scoring artifact — the model correctly reported `UNKNOWN` rather than hallucinating.

## How to contribute

1. Clone and run the dry-run sanity check (no network):

   ```bash
   git clone https://github.com/QiuXu-Tech/memex.git
   cd memex
   node --import ./test/register.mjs scripts/live-ab.mjs --dry-run --probes 4 --out /tmp/live-ab-dry.json
   ```

2. Run the harness with your own provider access **in your own environment**, for one or more models:

   ```bash
   ANTHROPIC_API_KEY=... node --import ./test/register.mjs scripts/live-ab.mjs --provider anthropic --model claude-opus-5-5 --probes 6 --out /tmp/live-ab-opus55.json
   OPENAI_API_KEY=...    node --import ./test/register.mjs scripts/live-ab.mjs --provider openai    --model gpt-6.1-sol --probes 6 --out /tmp/live-ab-gpt61.json
   DEEPSEEK_API_KEY=... node --import ./test/register.mjs scripts/live-ab.mjs --provider deepseek --model deepseek-flash --probes 6 --out /tmp/live-ab-dsflash.json
   ```

3. Share the produced JSON (comment on [issue #1](https://github.com/QiuXu-Tech/memex/issues/1) or open a PR adding it under `docs/assets/benchmarks/live-ab-<model>.json`).

**Privacy:** the fixtures are synthetic — no private conversations are sent or stored. When sharing results, remove API keys, auth headers, and any local paths you do not want public; the harness output contains only prompts from the synthetic fixture, model answers, usage, and timings. Never paste provider keys into the repository or an issue.

## What the harness measures

For each synthetic long-horizon question it runs two conditions on the same model:

- **control** — only the most recent tail is in context; older facts are evicted;
- **treatment** — tail + Memex `memory_search`/`memory_open` evidence for that question.

Answers are graded by exact `FACT-###` token. The output reports per-probe `correct`, latency, provider usage, and aggregate `accuracy.control` / `accuracy.treatment`.

A contribution template and the current dry-run plan live at [`docs/assets/benchmarks/live-ab.json`](assets/benchmarks/live-ab.json).

## What we do with the data

- Validate whether the dedicated profiles (Claude 5.5 / GPT-6.1 / DeepSeek Flash) actually improve long-horizon answers.
- Calibrate `charsPerToken`, catalog/recall/open budgets, and rerank weights per family with real token usage.
- Publish an aggregated table in this document (no contributor-identifying data unless explicitly offered).
