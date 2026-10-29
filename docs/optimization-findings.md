---
title: Optimization findings
layout: default
---

# Optimization findings (v0.2.1 experiments)

Experiments run on the open-source repo at commit `4e9720d` (v0.2.1), offline harness + ad-hoc integration benches. **Environment note:** the machine was under very heavy load during these runs (load average ≈ 72, raw file+fsync ≈ 8.4 ms/op), so **wall-clock latencies below are not representative** — use the miss rates, relative costs and structural findings. Quiet-machine numbers remain in [evaluation](evaluation.html).

## P0 — hot-body facts are effectively unretrievable (open)

**Fixture:** 200 distractor records whose title/summary match the topic words (`deployment retry budget incident INC-n`), 200 answer records whose *card is generic* and whose answer token lives only in the hot body, 100 cold answer records whose first ~1 KB is indexed as the cold abstract. 30 probes each.

| Probe class | hit@1 | hit@5 | p50 (loaded) |
|---|---|---|---|
| Answer only in **hot body** | **0%** | **0%** | 31 ms |
| Answer in **cold abstract** | 0% | **36.7%** | 20 ms |
| Control (title distractor) | 0% | **100%** | 19 ms |

Card legs fill the candidate limit, so the hot-body fallback never runs; and even when it does run, body matches only get the fallback base score. **Per-model rerank weights do not change this**: running the same cold probes under all 7 profile rerank variants (generic/claude/openai/gemini/deepseek/qwen/llama) produced identical hit@1 0% / hit@5 77.5% on that harder cold corpus. The bottleneck is evidence representation, not weight tuning.

**Recommended fixes (in order):**
1. **Searchable write-summary**: when a record is created by an adapter, put a bounded excerpt of the body (first 400–900 chars) into `summary` so card retrieval can see it. Already applied to Claude Code `PreCompact` archives (was: generic summary → unsearchable; now: transcript head summary, covered by harness U6).
2. **Bloom-filtered body rescue**: store a 64-bit body bloom per record; when a query term is unmatched by card fields, scan blooms (no file reads), read only selective candidates, and add a `bodyHits` rerank term (e.g. `+0.9 × matched terms`). Acceptance: body probes hit@5 ≥ 80% with ≤ 10 ms p50 added at 10k records.
3. If a full solution slips: manual guidance to put facts in title/summary and use `memory_grep` for identifiers.

## P0 — PreCompact failed on transcripts > 8 MB (fixed in 0.2.2)

An 8 MB+ transcript was clipped to exactly the store limit **then** a marker was appended, so `normalize()` rejected the record (`record body is too large`); the hook emitted no receipt and archived nothing (observed `outBytes: 0`). Fixed by clipping to `MEMORY_TEXT_LIMITS.body − marker.length`; new harness **U11** archives a > limit transcript and asserts the marker and size bound.

## P1 — transcript archives were unsearchable (fixed in 0.2.2)

Claude Code `PreCompact` stored a generic summary ("Verbatim Claude Code transcript…"), so a later query about the transcript **content** could not hit the card fields (body-only gap, P0). The hook now writes the first 900 chars of the transcript (whitespace-normalized) as `summary`; U6 asserts a content phrase is retrievable.

## P1 — injection budgets overflowed by wrapper tokens (fixed in 0.2.2)

`clipForForm()` clipped the *text* to the profile budget, then the formatter added XML/Markdown wrapper tokens: measured e.g. Claude catalog **1410 > 1400**, DeepSeek **906 > 900**. Now the wrapper overhead is reserved (16/12/8 tokens by style): all profiles report **≤ budget** (e.g. 1394/1400). Harness **U12** checks every profile with an oversized catalog/recall and the MCP version follows `package.json`.

## P1 — Codex adapter gaps (fixed in 0.2.2)

- `init` crashed with `ENOENT` when the `--project` directory did not exist; it now creates it.
- Config path ignored `CODEX_HOME`; now `CODEX_HOME` overrides `~/.codex`.
- Verified: `config.toml` snippet parses with Python `tomllib`, including paths with spaces; `--write-config` creates a `.bak` and is idempotent (second run reports the block already exists).

## P1 — MCP/adapters parity gaps (open)

- Tools: only `memory_search/open/grep/write/index/restore/compress`. Missing parity tools: `memory_list`, `memory_forget`, `memory_set_status` (DSH has them).
- **L2 session mismatch (verified):** a Claude hook writes with the client's `session_id` (`session-AAA`); the MCP server in the same project has no session id and defaults to `default-session`, so session-scoped records are invisible to MCP tools unless the server is started with `--session` (tested: match → 1 hit; mismatch → no hits). Recommendation: default MCP captures to L3, or pass a session id via project config/env; document the limitation.
- Compression: MCP/Codex support cold only; digest summaries remain a DSH-tool/agent responsibility.
- Codex has no hooks: no automatic transcript capture (manual `memory_write` only).

## P2 — model profile coverage & validation (open)

- 32 real model ids tested: `grok-4`, `command-r-plus`, `phi-4`, `gemma-3-27b`, `nova-pro` fall back to `generic` (matching is family-name based); decide whether to add xAI/Cohere/Microsoft/Gemma profiles or document the generic fallback.
- Windows/token ratios are conservative estimates, not vendor tokenizers.
- Rerank weights: currently no evidence they improve ranking on real data (see P0); consider validating on a real archive or reducing to 2–3 validated profiles.

## P2 — retrieval performance (open; needs a quiet-machine rerun)

Loaded-machine observations (relative only): long ASCII queries pay the LIKE leg (~52 ms at 2k records, 375 ms via MCP at 11k); body fallback is expensive (~82 ms p50 at 2k); `memory_index` aggregates facets + 3 lists (400 ms p50 at 11k under load). Candidate optimizations:
1. LIKE leg: only for terms `<3` chars (CJK bigrams) or cap to 4 terms × title/summary/abstract; measure recall delta.
2. Body fallback: early exit once enough matches are found; cap candidates (currently scans 400 hot records and reads bodies).
3. Facets: cache hot/cold accounting or combine COUNT queries; catalog currently recomputes facets per call.
4. Re-run `scripts/scale-bench.mjs` on a quiet machine to confirm the published 10k numbers (search 16.7–28.8 ms, write 2.8 s).

## P2 — process startup

Plain-node (no test loader) startup: `session-start` hook **282–413 ms**, MCP `initialize` **234 ms**; the offline loader adds ~150–800 ms (development only). Hooks are short-lived processes fired per event; if this matters, ship a small pre-bundled hook entry (fewer imports) or keep the MCP server warm.

## MCP protocol robustness (verified, no action)

Malformed JSON → `-32700`; unknown method → `-32601`; unknown tool → `isError` text; missing args → `isError`; unknown resource → `-32602`; duplicate `initialize` accepted; no crashes observed.

## Suggested backlog

| Priority | Item | Acceptance |
|---|---|---|
| P0 | Bloom-filtered body rescue + body rerank weight | body probes hit@5 ≥ 80%, ≤ 10 ms p50 added at 10k |
| P0 | Ship the PreCompact/budget/Codex fixes (done in 0.2.2) | harness 110/110 |
| P1 | MCP parity tools + session handling | list/forget/status work; documented L2 behavior |
| P1 | Real-client Claude Code / Codex acceptance | PreCompact archive + SessionStart catalog observed live |
| P2 | Retrieval perf pass (LIKE/fallback/facets) | quiet-machine p50 search < 50 ms at 10k |
| P2 | Profile coverage/validation | all main families map; rerank validated or simplified |
