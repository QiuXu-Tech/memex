---
title: Live endpoint A/B
layout: default
---

# Live endpoint A/B: help us collect multi-model data

Offline synthetic retrieval, profile, cold-start, and 100M-scale checks have been run. The next step needs **real usage data from many people running many models**: quality and token-usage differ per model family, and we want to validate and tune the dedicated profiles (Claude 5.5 series, GPT-6.1 series, GPT-6 Astra, DeepSeek Flash, and the family profiles) against actual model behavior rather than synthetic proxies.

Tracking request and discussion: [issue #1](https://github.com/QiuXu-Tech/memex/issues/1).

## DeepSeek Flash results (2026-10-29)

**Methodology warning for sections A and B and the current harness:** the
published runs report model answers, but the harness does not reliably construct the stated most-recent tail. It archives
older records and then selects the tail by updated time, which archiving also
changes. A [three-seed offline reproduction](assets/benchmarks/results-live-ab-tail-check-v050.json)
of the 300-turn v0.5.0 fixture included turn 270 and omitted turn 285 from all
three generated contexts. The original actual tail and provider transcripts
were not saved in the result JSON, so their exact membership cannot be verified
from that file. The reported “evicted” subsets and comparisons with the last
20 turns require a corrected harness and a new live run. See the
[benchmark report](https://github.com/QiuXu-Tech/memex/blob/main/docs/benchmark.md#6-live-ab-qualification) for the scope and
timestamp discrepancy. The corrected live run has **not** been performed.

### A. Evidence-in-prompt A/B

Two fresh-context calls on **DeepSeek Flash** (via DSH's DeepSeek Account route), synthetic 120-turn fixture and 8 deep-fact questions. The result file classifies seven as outside the tail; actual tail membership was not saved.

| Condition | Overall | Reported evicted-fact subset |
|---|---|---|
| control (recent tail only) | **1/8 (12.5%)** | **0/7 (0%)** |
| treatment (tail + memex evidence) | **8/8 (100%)** | **7/7 (100%)** |

The classification of the single control success and the seven reported evicted facts is subject to the warning above.

### B. Multi-seed replication (3 seeds × 300-turn history × 20 probes)

| Condition | Overall | Reported evicted records (excluding one fact per seed) | Reported cold-tier natural-language subset (turns 0–135) |
|---|---|---|---|
| control | **3/60 (5%)** | **0/57 (0%)** | 0/30 |
| treatment | **60/60 (100%)** | **57/57 (100%)** | **30/30 (100%)** |

The first multi-seed run exposed a cold-tier natural-language gap (0/30). After the **v0.5.0 cold-context fix** (card fields + bare turn numbers in `record_terms`, exact anchors for cold rescue) every cold probe is recovered. **v0.5.1** extends the same idea to hot bodies: a bare number can trigger body rescue and enrich an already-candidate row with body evidence, so Q19 (turn 285) is now recovered too. Treatment is **60/60** across the three seeds.

### C. Full agent loop (tools, n=1)

A mediated tool protocol: the model emits JSON tool calls, the harness executes them against the real memex MCP server.

- control (no tools): `UNKNOWN` — wrong.
- treatment: `memory_search` (noisy query) → refined `memory_search` (expected record at rank 10) → `memory_open` → **`FACT-025-r6h18`** — correct, 3 tool calls, 4 turns.

This shows the loop can search, refine, open and answer end-to-end; n=1 is a mechanism check, not a statistical result.

Raw data: [evidence-in-prompt 8 probes](assets/benchmarks/live-ab-deepseek.json) · [multi-seed](assets/benchmarks/live-ab-deepseek-multiseed.json) · [agent loop](assets/benchmarks/live-ab-deepseek-agent-loop.json).

**Caveats:** one model; synthetic fixtures; multi-seed runs are agent-mediated and did not capture provider usage tokens or raw provider transcripts. The v0.5.0 data recorded Q19 as a miss; the later v0.5.1 result file records an answer for it. Tail membership and the “evicted” classification remain unverified as explained above.

### D. Anchor-free natural-language recall (n=3)

Questions contain **no turn numbers or IDs**; the three facts live only in hot bodies whose card titles/summaries are generic (`release note N`).

| Condition | Result |
|---|---|
| control (recent tail only) | **0/3** — all UNKNOWN |
| treatment (memex evidence) | **3/3** — `FACT-BILL-OK`, `FACT-AUTH-30D`, `FACT-CACHE-LRU` |

This exercises the new **anchor-free hot-body coverage rescue**: it runs only when no card field shares a meaningful query term, then scans at most 240 hot bodies. Cold anchor-free facts still rely on abstract FTS/card summaries. Raw: [evidence](assets/benchmarks/live-ab-deepseek-anchor-free.json).

### E. Cold anchor-free natural-language recall (n=3)

Questions contain **no turn numbers or IDs** and the answer-bearing records are **archived cold**, with generic card titles (`decision record N`). The retrieval path used is the v0.7.0 cold rescue: a cold-only FTS candidate leg + full-abstract-coverage boost, without reading cold bodies.

| Condition | Result |
|---|---|
| control (recent tail only) | **0/3** — all UNKNOWN |
| treatment (memex evidence) | **3/3** — `FACT-BILL-OK`, `FACT-AUTH-30D`, `FACT-CACHE-LRU` |

Limits kept explicit: the boost requires the cold abstract to cover **every** meaningful query term (partial overlap is ignored), and morphology must match (`decision`, not `decide`). Raw: [evidence](assets/benchmarks/live-ab-deepseek-cold-anchor-free.json).

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

## Run it with Codex CLI (GPT models)

If you use Codex CLI with GPT models, you can contribute without an OpenAI API key. The bridge generates the same synthetic fixture, asks `codex exec` for the control and treatment answers, grades exact FACT ids, and writes a shareable JSON report (no keys, no private data):

```bash
git clone https://github.com/QiuXu-Tech/memex.git
cd memex
node scripts/codex-ab.mjs --model gpt-6.1-sol
```

Requirements: Node >= 22 (`node -v`; `npx -y node@22 scripts/codex-ab.mjs ...` works as a fallback) and a logged-in `codex` CLI. Options: `--model gpt-6.1-terra`, `--seeds 3`, `--probes 20`, `--turns 300`, `--out /tmp/codex-ab.json`, `--keep` (keep prompts). The script prints the report path; attach that JSON to [issue #1](https://github.com/QiuXu-Tech/memex/issues/1) or open a PR under `docs/assets/benchmarks/`.

The control/treatment prompts are synthetic; review the `raw` replies before publishing. Codex has its own tools, so the prompts ask it not to use them — the per-run work directories are isolated and `--sandbox read-only` is used.

The generated prompts inherit the [retained-tail issue](#deepseek-flash-results-2026-10-29) described above; they should not be interpreted as a verified recent-tail comparison until it is fixed.

## What the harness measures

The intended comparison for each synthetic long-horizon question uses two conditions on the same model. The current retained-tail construction has the limitation described above:

- **control** — only the most recent tail is in context; older facts are evicted;
- **treatment** — tail + Memex `memory_search`/`memory_open` evidence for that question.

Answers are graded by exact `FACT-###` token. The output reports per-probe `correct`, latency, provider usage, and aggregate `accuracy.control` / `accuracy.treatment`.

A contribution template and the current dry-run plan live at [`docs/assets/benchmarks/live-ab.json`](assets/benchmarks/live-ab.json).

## What we do with the data

- Validate whether the dedicated profiles (Claude 5.5 / GPT-6.1 / DeepSeek Flash) actually improve long-horizon answers.
- Calibrate `charsPerToken`, catalog/recall/open budgets, and rerank weights per family with real token usage.
- Publish an aggregated table in this document (no contributor-identifying data unless explicitly offered).
