---
title: v0.4.0 experiments
layout: default
---

# v0.4.0 experiments: rename, adapter defaults, live readiness

Post-rename validation and experiments for **Memex 0.4.0** (2026-10-29). Every number below was produced in this repository; live model results are being collected from the community across model families (see [live testing](live-testing.html)).

## 1. Rename + defaults verification

| Check | Result |
|---|---|
| Offline harness after rename | **115/115 passed** (added U17 adapter defaults, U18 storage-root/env fallbacks) |
| Bundle build/parity | `build-bundle` + `check-bundle` clean (10 runtime modules, 8 DSH rows) |
| Fresh clone from `github.com/QiuXu-Tech/memex` | build + check + harness **115/115** (clean checkout, no `node_modules`) |
| Claude init defaults | writes `.mcp.json` with `--model claude-sonnet-5-5`; prints `Model profile: claude-sonnet-5-5` and recommended alternatives |
| Codex init defaults | emits `gpt-6.1-sol` config and recommends `gpt-6.1-terra` / `gpt-6-astra` |
| MCP profile discovery | `memex-mcp --list-profiles` → `deepseek-flash`, `claude-sonnet-5-5`, `gpt-6.1-sol`, `claude-opus-5-5` |
| Storage/env compatibility | `MEMEX_HOME` wins, `DSH_MEMORY_HOME` legacy fallback, `~/.dsh-memory` legacy dir migrated-by-detection to `~/.memex` |

## 2. Real-archive recall after body rescue + perf pass

40 curated real-archive questions (private archive, copied to a temp root):

| Metric | v0.2.1 baseline | v0.4.0 |
|---|---|---|
| hit@1 | 73% | **70%** |
| hit@3 | 90% | 90% |
| hit@5 | 95% | **95%** |
| cold recall | 100% | **100%** |
| p50 | 0.95 ms | 1.37 ms (load ≈3) |

The hit@1 delta is the body-rescue tie-break trade-off documented in the optimization report; hit@5/cold recall are unchanged.

## 3. Profile validation (post-rename rerun)

12 comparison profiles on the seeded hot/cold/title fixture (`docs/assets/benchmarks/profile-validation.json`):

- **Cold start:** MCP `initialize` 45–50 ms p50, first `memory_search` 2–3 ms — dedicated profiles add no startup regression.
- **Retrieval parity:** hot-body/cold/title hit@5 identical at 100% / 63% / 95%; dedicated Claude 5.5 profiles keep 100% hot-body hit@1 while base `claude` loses rank-1 (0%) due to its lower body weight.
- **Long-horizon overhead:** catalog injection 340–520 tokens/turn; 50 turns = 17k–26k tokens (1.7–2.6% of a 1M window). Catalog budgets are caps, not targets.

## 4. Live data collection

### DeepSeek Flash validation (first live data)

| Experiment | Result |
|---|---|
| Evidence-in-prompt, 8 probes / 120 turns | control **1/8** (evicted **0/7**) → treatment **8/8** (evicted **7/7**) |
| Multi-seed (3 seeds × 20 probes / 300 turns) | control **3/60 (5%)**; treatment **60/60 (100%)**; evicted **0/57 → 57/57 (100%)** |
| Cold-tier natural-language subset (30 probes) | control 0/30; treatment **30/30 (100%)** after the v0.5.0 cold-context fix |
| Hot body-only Q19 (turn 285) | v0.5.1 body-rescue numeric anchor recovers it; no residual miss |
| Full agent loop (n=1) | control `UNKNOWN`; treatment: 3 real MCP tool calls → correct `FACT-025-r6h18` |
| Anchor-free natural-language (n=3, v0.6.0) | control **0/3**; treatment **3/3** (generic card titles, body-only facts, bounded hot-body scan) |

**Finding (fixed in v0.5.0/v0.5.1):** card-field tokens and bare numbers are now indexed in `record_terms`; cold rescue uses exact anchors, and **body rescue now treats unmatched bare numbers as anchors and attaches body evidence to already-candidate rows**. Cold natural-language probes went 0/30 → 30/30; Q19 (hot body, turn 285) is now recovered; treatment overall **60/60**. The concept is now explicitly **extra-context**, not a notes store — see docs/context-layer.md.

The client integration is verified (Claude Code parses the generated config): `claude mcp list` after `memex-claude init`:

```
memex: node .../memex-mcp/bin/server.mjs --root ... --model claude-sonnet-5-5 --levels l2,l3 --cwd ... - ⏸ Pending approval
```

The renamed client config is recognized; the one-time project approval is expected. We are now collecting **multi-model usage data** from contributors: run the [live A/B harness](live-testing.html) with your own model access and share the anonymized results (issue #1). The synthetic dry-run plan is committed.

## 5. v0.4.1 improvements (executed in order)

### P1 cold-body recall: 63% → 100%
- Added **cold-anchor rescue**: when a query has identifier-like anchors (digits/hyphens/paths), the bounded cold `abstract` column is scanned directly and matching cold records join the rerank with a `coldAnchor` evidence bonus (default 30).
- Profile validation after the change: **cold hit@5 = 100% for all 12 comparison profiles** (was 63%); hot-body hit@1 100% for dedicated Claude 5.5 profiles; title hit@5 100%.
- Real-archive guard: hit@5 **95%** and cold recall **100%** preserved; hit@1 70% (unchanged from the pre-fix measurement).
- The rescue only triggers for identifier-like queries, so ordinary natural-language searches pay no extra scan.

### P2 catalog budgets: now actually used
- Catalog depth scales with the caller's `maxChars` (profile catalog budget × chars/token) instead of a fixed 18 cards.
- Injected catalog tokens per session: **893–1439** (previously 340–524); 50-turn cumulative catalog tokens 44.9k–72.0k ≈ **4.5–7.2% of a 1M window**.
- Trade-off is explicit: larger profiles (Opus/Fable/GPT-6 Astra) spend more prompt space for deeper catalog visibility; Haiku/Terra keep compact budgets. All still clipped by `maxChars`.

### P2 session alignment
- `memex-claude init --session <stable-id>` now writes the same `--session` into `.mcp.json` **and** every hook command; hooks prefer the explicit session over the client payload.
- U19 proves an L2 project-session record written by the hook path is visible through the aligned namespace and invisible without `--session`.
- `init` now prints the MCP approval hint (`claude mcp list` / approve once).

### P3 tokenizer calibration
- Still pending: needs a live provider response with usage numbers; the harness reports usage when keys are available.

### Quiet-machine 100M benchmark (load ≈4.4)
- write 10,000 records / 100.0M tokens in **3.4 s**; DB 9.0 MiB, bodies 384.8 MiB.
- facets **6.5 ms**, list 7.0 ms, catalog **13.8 ms**, search 6.7–8.3 ms (CJK 2.3 ms), grep 16.2 ms, get 0.05 ms.
- `compressCold` 5,000 records / 50M tokens in **2.94 s**; cold GC 2,500 / 25M in **0.28 s**; post-cold search 14.0 ms / catalog 15.6 ms; DB 26.7 MiB.
- Harness **116/116** (U19 added; U18 env fallbacks).

## 6. Improvement points found this round

| Priority | Finding | Status |
|---|---|---|
| P1 | Live endpoint A/B: need multi-model usage data | open — first DeepSeek Flash data point landed (0/7 → 7/7 on evicted facts); more models/repeats welcome in issue #1 |
| P1 | Cold-body recall stuck at 63% | **fixed in v0.4.1** (cold-anchor rescue; 100% on the profile fixture, real hit@5 95%) |
| P2 | Catalog budgets underused | **fixed in v0.4.1** (depth scales with budget; 893–1439 injected tokens) |
| P2 | MCP `default-session` vs hook session id | **fixed in v0.4.1** (`init --session` aligns hooks+MCP; U19) |
| P3 | One-time MCP approval easy to miss | **fixed** (init prints approval hint) |
| P3 | Tokenizer estimates unverified | open — needs live provider usage |
| P2 | 100M pool quiet rerun | **done** (write 3.4 s, search 6.7–14.0 ms, compression 2.94 s; load ≈4.4) |
