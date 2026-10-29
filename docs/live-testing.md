---
title: Live endpoint A/B
layout: default
---

# Live endpoint A/B: help us collect multi-model data

Offline synthetic retrieval, profile, cold-start, and 100M-scale checks have been run. The next step needs **real usage data from many people running many models**: quality and token-usage differ per model family, and we want to validate and tune the dedicated profiles (Claude 5.5 series, GPT-6.1 series, GPT-6 Astra, DeepSeek Flash, and the family profiles) against actual model behavior rather than synthetic proxies.

Tracking request and discussion: [issue #1](https://github.com/QiuXu-Tech/memex/issues/1).

## DeepSeek Flash results (2026-10-29)

**Tail-membership status:** v0.8.0 fixes the harness: the exact newest-tail
record ids are saved in `plan.json`, every probe carries `inTail`/`evicted`,
and the control prompt is built from those exact rows. A fresh three-seed
DeepSeek Flash rerun is now **verified**: control **3/60**, treatment **60/60**,
evicted subset **0/57 → 57/57**. Raw: [verified multi-seed evidence](assets/benchmarks/live-ab-deepseek-multiseed.json).

The older GPT-6.1 Sol contribution was collected before the fix; its overall
control/treatment answers are preserved, but its reported “cold” subset remains
unverified. Rerun `scripts/codex-ab.mjs` with the fixed bridge to verify it.
See the [benchmark report](https://github.com/QiuXu-Tech/memex/blob/main/docs/benchmark.md#6-live-ab-qualification) for the historical caveat.

### A. Evidence-in-prompt A/B

Historical pre-fix 8-probe run (the 3-seed rerun below supersedes it). Two fresh-context calls on **DeepSeek Flash** (via DSH's DeepSeek Account route), synthetic 120-turn fixture and 8 deep-fact questions. Actual tail membership was not saved; treat this table as historical.

| Condition | Overall | Reported evicted-fact subset (historical, unverified) |
|---|---|---|
| control (recent tail only) | **1/8 (12.5%)** | **0/7 (0%)** |
| treatment (tail + memex evidence) | **8/8 (100%)** | **7/7 (100%)** |

This 8-probe table is historical; the verified three-seed rerun is below.

### B. Multi-seed replication (3 seeds × 300-turn history × 20 probes)

| Condition | Overall | **Verified** evicted records (inTail=false) | Verified cold natural-language subset |
|---|---|---|---|
| control | **3/60 (5%)** | **0/57 (0%)** | 0/30 |
| treatment | **60/60 (100%)** | **57/57 (100%)** | **30/30 (100%)** |

Harness v0.8.0 saves the exact tail ids and probe `inTail`/`evicted` flags. In this verified rerun the newest tail contains one queried fact (turn 285), so controls answer exactly that one per seed (3/60); all **19 evicted probes per seed (57 total)** are answered only with memex evidence (57/57). The first multi-seed run had exposed the cold natural-language gap; the v0.5/v0.7 anchors and rescues close it on this fixture.

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

### F. Codex CLI / GPT family: Sol vs Terra

Two Codex CLI contributions on the same fixture (3 seeds × 20 probes):

| Model | Harness | Control | Treatment | Verified evicted subset |
|---|---|---|---|---|
| `gpt-6.1-sol` (v0.7.1) | pre-fix | 3/60 (5%) | 60/60 (100%) | not verified (pre-fix report) |
| `gpt-6.1-terra` (v0.8.1) | v0.8.0 fixed tail | **3/60 (5%)** | **60/60 (100%)** | **0/57 → 57/57** |

- **Terra verification:** exact tail ids and per-probe `inTail`/`evicted` flags are saved; controls answer only the one in-tail fact per seed (turn 285), and all 19 evicted probes per seed are recovered by memex evidence.
- **Family comparison:** Sol and Terra are indistinguishable on this synthetic fixture (both 5% → 100% overall); Terra provides the verified tail comparison. The Sol report predates the harness fix, so its cold subset remains caveated.
- Raw: [Sol](assets/benchmarks/live-ab-codex-gpt.json) · [Terra](assets/benchmarks/live-ab-codex-terra.json).

### G. Cold anchor-free morphology/synonym + partial coverage (n=3, v0.8.0)

Questions are anchor-free and the records are cold. They exercise morphology-lite (`decide` ↔ `decision`), synonym phrasing, and a partial-coverage case with an extra query term.

| Condition | Result |
|---|---|
| control (recent tail only) | **0/3** — all UNKNOWN |
| treatment (memex evidence) | **3/3** — `FACT-BILL-OK`, `FACT-AUTH-30D`, `FACT-CACHE-LRU` |

Mechanism: stopword-filtered content terms, prefix ≥4 loose matching, cold-only FTS variants + cold abstract prefix LIKE, and a cold partial-coverage boost (`coldPartial`) gated to protect fully-covered hot cards. Cold bodies are not read. Raw: [evidence](assets/benchmarks/live-ab-deepseek-cold-partial.json).

**Trade-off:** the partial boost is on by default and costs ~3pp real-archive hit@1 (68% → 65%) while hit@5 stays 93%; set `coldPartial: 0` in rerank for the precision-first behavior.

### H. Claude family: Sonnet 5.5 vs Opus 5.5 (verified, v0.9.0)

Both Claude 5.5 models were run through the **APIMaster** OpenAI-compatible gateway with the fixed batch bridge (`scripts/claude-ab.mjs`), 3 seeds × 20 probes, 6 calls each.

| Model | Control | Treatment | Verified evicted | Usage (6 calls) |
|---|---|---|---|---|
| `claude-sonnet-5-5` | **3/60 (5%)** | **60/60 (100%)** | **0/57 → 57/57** | **40,673 tokens** (prompt 39,025 / completion 1,648) |
| `claude-opus-5-5` | **3/60 (5%)** | **60/60 (100%)** | **0/57 → 57/57** | **40,676 tokens** (prompt 39,028 / completion 1,648) |

- Tail membership is saved (`tailIds` / per-probe `inTail`/`evicted`); the evicted subset is verified.
- The two Claude models are indistinguishable on this synthetic fixture, mirroring the Sol/Terra result.
- **Measured cost of a Claude validation: ~40.7k tokens per model** (6 batch calls), ~81.3k tokens for the Sonnet+Opus pair.
- Raw: [Sonnet](assets/benchmarks/live-ab-claude-sonnet55.json) · [Opus](assets/benchmarks/live-ab-claude-opus55.json).

Run it yourself (key is read from env, never committed):

```bash
APIMASTER_API_KEY=... node scripts/claude-ab.mjs --model claude-sonnet-5-5
```

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

The bridge now saves exact tail ids and probe `inTail`/`evicted` flags; reports are verified against the actual control prompt. Existing pre-fix reports (e.g. GPT-6.1 Sol v0.7.1) remain caveated.

## What the harness measures

The intended comparison for each synthetic long-horizon question uses two conditions on the same model. The v0.8.0 harness saves exact tail membership:

- **control** — only the most recent tail is in context; older facts are evicted;
- **treatment** — tail + Memex `memory_search`/`memory_open` evidence for that question.

Answers are graded by exact `FACT-###` token. The output reports per-probe `correct`, latency, provider usage, and aggregate `accuracy.control` / `accuracy.treatment`.

A contribution template and the current dry-run plan live at [`docs/assets/benchmarks/live-ab.json`](assets/benchmarks/live-ab.json).

## What we do with the data

- Validate whether the dedicated profiles (Claude 5.5 / GPT-6.1 / DeepSeek Flash) actually improve long-horizon answers.
- Calibrate `charsPerToken`, catalog/recall/open budgets, and rerank weights per family with real token usage.
- Publish an aggregated table in this document (no contributor-identifying data unless explicitly offered).
