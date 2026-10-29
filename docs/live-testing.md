---
title: Live endpoint A/B
layout: default
---

# Live endpoint A/B: help us collect multi-model data

Offline validation (retrieval, profiles, cold start, 100M scale) is complete. The next step needs **real usage data from many people running many models**: quality and token-usage differ per model family, and we want to validate and tune the dedicated profiles (Claude 5.5 series, GPT-6.1 series, GPT-6 Astra, DeepSeek Flash, and the family profiles) against actual model behavior rather than synthetic proxies.

Tracking request and discussion: [issue #1](https://github.com/QiuXu-Tech/memex/issues/1).

## What data we need

| Data | Why it matters |
|---|---|
| `accuracy.control` vs `accuracy.treatment` per model | proves the memory layer's value on evicted facts |
| provider `usage` (input/output tokens) and latency | calibrates `charsPerToken`, catalog/recall budgets |
| exact model id + profile id used | attributes gains to the right dedicated profile |
| at least a few answers per model family | separates real signal from single-sample noise |

**Coverage targets** (any subset is useful):
`claude-opus-5-5`, `claude-sonnet-5-5`, `claude-fable-5-1`, `claude-haiku-5-5`, `gpt-6.1-sol`, `gpt-6.1-terra`, `gpt-6-astra`, `deepseek-flash`, `deepseek-v4-pro`, Gemini 2.5/3, Qwen 3, Kimi K2, GLM 4.6, Llama 4/Mistral, and older families for comparison.

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
