---
title: Profile validation
layout: default
---

# Dedicated profile validation: cold start + long-horizon A/B

This report validates the dedicated current-model profiles (GPT-6.1 Sol / Terra / GPT-6 Astra, Claude Opus 5.5 / Sonnet 5.5 / Fable 5.1 / Haiku 5.5, DeepSeek Flash) against their family base profiles, at the **integration layer** (MCP server cold start, retrieval, injection budgets, token accounting). It does not call live model endpoints; true answer-quality A/B remains a manual follow-up.

Raw data: [`docs/assets/benchmarks/profile-validation.json`](assets/benchmarks/profile-validation.json) · reproduce: `node --import ./test/register.mjs scripts/profile-validation.mjs docs/assets/benchmarks/profile-validation.json` (12 profiles, seeded throwaway store, load ≈3.5–5).

## Fixture

- 120 distractor records (topic words + `INC-<n>` in title/summary), 120 hot-body answer records (answer token only in the body), 60 title/summary decision facts with unique `CUE-<n>`.
- 90 cold records (60 body answers + 30 title facts archived to the cold tier).
- Probes: **40 hot-body** (`incident INC-60…99 …`), **30 cold-body**, **40 title/card** (`… CUE-<n>`).
- Per profile: its own `rerank` weights and `queryTerms.maxTerms`; token estimates via its `charsPerToken`; catalog injection clipped by its budget; cold start = fresh MCP process `initialize` + first `memory_search`, median of 3.

## Cold start (fresh MCP process, same 330-record archive)

| Profile | init p50 | first search p50 | first search result chars |
|---|---|---|---|
| `claude` (base) | 47 ms | 2 ms | 382 |
| `claude-opus-5-5` | 48 ms | 2 ms | 700 |
| `claude-sonnet-5-5` | 46 ms | 2 ms | 382 |
| `claude-fable-5-1` | 46 ms | 2 ms | 700 |
| `claude-haiku-5-5` | 46 ms | 2 ms | 310 |
| `openai` (base) | 46 ms | 2 ms | 346 |
| `gpt-6.1` | 45 ms | 2 ms | 700 |
| `gpt-6.1-terra` | 47 ms | 2 ms | 346 |
| `gpt-6-astra` | 45 ms | 2 ms | 700 |
| `deepseek` (base) | 46 ms | 2 ms | 346 |
| `deepseek-flash` | 47 ms | 2 ms | 382 |
| `generic` | 50 ms | 3 ms | 346 |

**Result:** dedicated profiles add **no cold-start regression** (45–50 ms init, 2–3 ms first search). Result size is the only difference, driven by recall budget.

## Long-horizon retrieval parity

| Profile | hot-body hit@1 | hot-body hit@5 | cold hit@5 | title hit@5 | tokens/answer |
|---|---|---|---|---|---|
| `claude` (base) | 0% | 100% | 63% | 95% | 58 |
| `claude-opus-5-5` | **100%** | 100% | 63% | 95% | 80 |
| `claude-sonnet-5-5` | **100%** | 100% | 63% | 95% | 80 |
| `claude-fable-5-1` | **100%** | 100% | 63% | 95% | 80 |
| `claude-haiku-5-5` | **100%** | 100% | 63% | 95% | 80 |
| `openai` (base) | 100% | 100% | 63% | 95% | 52 |
| `gpt-6.1` / `terra` / `astra` | 100% | 100% | 63% | 95% | 52 |
| `deepseek` (base) | 100% | 100% | 63% | 95% | 61 |
| `deepseek-flash` | 100% | 100% | 63% | 95% | 69 |
| `generic` | 100% | 100% | 63% | 95% | 52 |

**Findings**
- **No recall regressions** from dedicated tuning: hot-body/cold/title hit@5 are identical (100% / 63% / 95%).
- The dedicated Claude 5.5 profiles **fix the base `claude` rank-1 weakness**: base body weight (4.5) let card-heavy distractors outrank body evidence (0% hit@1), while the 5.5 variants (body 4.6–5.2) reach 100%. This is the main measurable long-horizon gain.
- Token estimates differ by tokenizer profile: Claude 5.5 uses 2.6 chars/token (vendor: ~2.5M Unicode chars / 1M tokens), so the *same* injected text accounts for ~38% more tokens than the old 3.6 estimate — intentionally conservative.
- Cold-body recall stays at 63% for every profile: cold bodies are only reachable through the bounded abstract / `memory_grep`, not profile-tunable (documented limitation).

## Long-horizon overhead (50 checkpoint turns)

| Profile | catalog tokens/turn | manual tokens | 50-turn catalog tokens |
|---|---|---|---|
| `claude` (base) | 379 | 749 | 18,950 |
| `claude-opus-5-5` | 524 | 1,055 | 26,200 |
| `claude-sonnet-5-5` | 524 | 1,017 | 26,200 |
| `claude-fable-5-1` | 524 | 1,073 | 26,200 |
| `claude-haiku-5-5` | 524 | 1,014 | 26,200 |
| `openai` (base) | 337 | 658 | 16,850 |
| `gpt-6.1` | 337 | 669 | 16,850 |
| `gpt-6.1-terra` | 337 | 648 | 16,850 |
| `gpt-6-astra` | 337 | 678 | 16,850 |
| `deepseek` (base) | 396 | 740 | 19,800 |
| `deepseek-flash` | 449 | 842 | 22,450 |
| `generic` | 337 | 640 | 16,850 |

**Findings**
- Catalog budgets are **caps, not targets**: the current catalog content is ~340–520 tokens, below all configured budgets (900–2,200), so larger budgets do not inflate overhead today. They only matter for unusually large catalogs (many pinned records) or long recall lists.
- 50 turns of catalog injection cost **17k–26k tokens** — 1.7–2.6% of a 1M window, acceptable for long-horizon sessions. Claude 5.5's higher token accounting is the driver, not extra content.
- Manual size differs by profile (640–1,073 tokens) and is injected once per session by adapters (MCP `initialize.instructions`, Claude `CLAUDE.md`), not per turn.

## Tuning change found by this validation

`claude-fable-5-1` initially lost rank-1 on hot-body probes because `useWhen 1.9` let the `read when continuing deployment retry budget work` hint outweigh body evidence. Adjusted to `useWhen 1.8`, `recency 0.25`, `body 5.2` — hit@1 is now 100% with the rest unchanged. This is exactly the kind of per-model tie-break the dedicated profiles exist for.

## Limitations

- **Retrieval-layer proxy, not live-model A/B.** We measure what memory surfaces and how many tokens it costs, not the model's final answer quality. Real A/B needs live Opus 5.5 / Fable 5.1 / GPT-6.1 / DeepSeek Flash endpoints.
- Cold start was measured with the repo dev layout (ESM loader, linked packages); installed-package startup may differ slightly, but the relative parity across profiles holds.
- Rerank weights are hand-tuned and validated on synthetic fixtures only; a real-archive A/B should re-check them.
- Vendor context/tokenizer numbers are from 2026-10-29 docs; `profileOverrides` can adjust windows (e.g. GPT-6.1's 500k Codex default).
