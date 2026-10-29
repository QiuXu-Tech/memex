---
title: Optimization findings
layout: default
---

# Optimization findings (v0.2.1 experiments)

Experiments run on the open-source repo at commit `4e9720d` (v0.2.1), offline harness + ad-hoc integration benches. **Environment note:** the machine was under very heavy load during these runs (load average ≈ 72, raw file+fsync ≈ 8.4 ms/op), so **wall-clock latencies below are not representative** — use the miss rates, relative costs and structural findings. Quiet-machine numbers remain in [evaluation](evaluation.html).

## P0 — hot-body facts are effectively unretrievable (fixed in 0.3.0)

**Fix:** every record now indexes its identifier-like body tokens into a
`record_terms(record_id, term_hash)` table (~1.5 rows/record on the test
fixture). When a query term never matched any card candidate and the query has
an identifier-like anchor (digits, hyphens, underscores, paths), the store runs
one indexed `GROUP BY` to rank body candidates by exact query-term count, reads
only those candidates, and adds `bodyHits × 5` to the rerank score. Measured on
the same fixture: hot-body hit@1/hit@5 **0% → 100%/100%** (40/40 probes),
identifier prefix confusion (`INC-1` vs `INC-161`) removed by boundary-aware
matching, and the DB grows only ~0.6 MB for the 10k-record synthetic pool.
Natural-language-only facts with no identifier anchor still rely on card
summaries / `memory_grep`; `PreCompact` now writes a searchable summary head for
this reason.

Original measurement (for the record):

**Fixture:** 200 distractor records whose title/summary match the topic words (`deployment retry budget incident INC-n`), 200 answer records whose *card is generic* and whose answer token lives only in the hot body, 100 cold answer records whose first ~1 KB is indexed as the cold abstract. 30 probes each.

| Probe class | hit@1 | hit@5 | p50 (loaded) |
|---|---|---|---|
| Answer only in **hot body** | **0%** | **0%** | 31 ms |
| Answer in **cold abstract** | 0% | **36.7%** | 20 ms |
| Control (title distractor) | 0% | **100%** | 19 ms |

Card legs fill the candidate limit, so the hot-body fallback never runs; and even when it does run, body matches only get the fallback base score. **Per-model rerank weights do not change this**: running the same cold probes under all 7 profile rerank variants (generic/claude/openai/gemini/deepseek/qwen/llama) produced identical hit@1 0% / hit@5 77.5% on that harder cold corpus. The bottleneck is evidence representation, not weight tuning.

**Implemented (0.3.0):** body-term index rescue with identifier anchors, a `body: 5` rerank weight, and a searchable `summary` head for Claude Code `PreCompact` archives. Acceptance met on the fixture; see the top of this section.

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

## P1 — MCP/adapters parity gaps (fixed in 0.3.0)

- ~~Tools: only 7~~ — MCP now also exposes `memory_list`, `memory_forget` and `memory_set_status` (10 tools total).
- **L2 session mismatch (verified, documented):** hooks write with the client session id while MCP tools use `default-session`; the Claude `init` now warns on L2-only setups and recommends `--levels l2,l3`/`l3` or `--session`. L3 remains the shared path.
- Compression: MCP/Codex support cold only; digest summaries remain a DSH-tool/agent responsibility.
- Codex has no hooks: no automatic transcript capture (manual `memory_write` only).

## P2 — model profile coverage & validation (partly fixed in 0.3.0)

- Added profiles for **xAI Grok, Cohere Command, Google Gemma, Microsoft Phi** (9 → 13 families); `nova-pro` and other unmapped ids still fall back to `generic`.
- Real Claude Code acceptance: `claude mcp list` in a generated project **recognizes the memex server**, but project-scoped `.mcp.json` requires a one-time interactive approval ("Pending approval — run claude to approve"). Codex client acceptance awaits community reports (the generated config is validated by TOML/parse tests).
- Windows/token ratios are conservative estimates, not vendor tokenizers.
- Rerank weights: currently no evidence they improve ranking on real data (see P0); consider validating on a real archive or reducing to 2–3 validated profiles.

## P2 — retrieval performance (open; needs a quiet-machine rerun)

Re-ran on the same loaded machine (load avg ~14–32; still not a quiet baseline): 10k/100M-token pool wrote in **60.5 s** vs the published 2.8 s quiet-machine number, search 101–165 ms, catalog 118 ms, `compressCold` 23.8 s, cold GC 2.57 s. Relative bottlenecks identified earlier (loaded): long ASCII queries pay the LIKE leg (~52 ms at 2k; 375 ms via MCP at 11k), body fallback ~82 ms p50 at 2k, `memory_index` aggregates facets + 3 lists. Candidate optimizations:
1. LIKE leg: only for terms `<3` chars (CJK bigrams) or cap to 4 terms × title/summary/abstract; measure recall delta.
2. Body fallback: early exit once enough matches are found; cap candidates (currently scans 400 hot records and reads bodies).
3. Facets: cache hot/cold accounting or combine COUNT queries; catalog currently recomputes facets per call.
4. Re-run `scripts/scale-bench.mjs` on a quiet machine to confirm the published 10k numbers (search 16.7–28.8 ms, write 2.8 s).

## P2 — process startup

Plain-node (no test loader) startup: `session-start` hook **282–413 ms**, MCP `initialize` **234 ms**; the offline loader adds ~150–800 ms (development only). Hooks are short-lived processes fired per event; if this matters, ship a small pre-bundled hook entry (fewer imports) or keep the MCP server warm.

## MCP protocol robustness (verified, no action)

Malformed JSON → `-32700`; unknown method → `-32601`; unknown tool → `isError` text; missing args → `isError`; unknown resource → `-32602`; duplicate `initialize` accepted; no crashes observed.

## Performance pass (v0.3.1)

Measured on the **same seeded 10,000-record store** (mixed ASCII/CJK cards, ~1.5 KB bodies) on a quiet pass (load avg ≈3), medians of 7 runs, CPU and wall time agreeing. Before/after:

| Operation | Before | After | Δ |
|---|---|---|---|
| `facets` | 9.82 ms | **5.18 ms** | −47% |
| `catalog` | 16.32 ms | **11.87 ms** | −27% |
| search: long ASCII | 20.65 ms | **10.70 ms** | −48% |
| search: short ASCII | 13.33 ms | **5.69 ms** | −57% |
| search: generic NL | 20.92 ms | **10.45 ms** | −50% |
| search: rescue (id anchor) | 23.87 ms | **12.92 ms** | −46% |
| search: body fallback | 14.92 ms | **13.42 ms** | −10% |
| search: CJK 2/3-char | 4.58 / 11.96 ms | 4.63 / 11.99 ms | ~0 |

Changes:
1. **Adaptive LIKE leg** — trigram FTS already matches substrings for terms ≥3 chars, so the 4-field leading-wildcard LIKE OR-scan only runs when the FTS leg is sparse; CJK terms always keep LIKE (no word boundaries in Chinese).
2. **One-pass facets** — the 7 separate aggregate scans were replaced by a single `GROUP BY kind,status,scope,cold` pass folded in JS.
3. **Single-read body fallback** — reads each candidate file once and reuses a precompiled regex instead of calling `grep()` per row; candidate cap 400 → 200.
4. **Body-term rescue** is now anchored to identifier terms only (v0.3.0) — no full body scans.

Recall guard (same 40-question real-archive suite): hit@5 **95% → 95%**, cold recall **100% → 100%**, hit@1 73% → 70% (a rescue-hit tie-break trade-off; synthetic/demo suites stay 100%). Raw numbers: [`docs/assets/benchmarks/perf-optimization.json`](assets/benchmarks/perf-optimization.json).

Remaining perf work: LIKE/facets are now cheap relative to FTS bm25 ranking; the next candidates are caching facets per store epoch and a quiet-machine 100M-pool rerun.

## Suggested backlog

| Priority | Item | Acceptance |
|---|---|---|
| P0 | ~~Body rescue + body rerank~~ (0.3.0) | hot-body hit@1/@5 0% → 100% on fixture; U13 |
| P0 | PreCompact/budget/Codex fixes (0.2.2) | harness 110/110 |
| P1 | MCP parity tools + session handling (0.3.0) | 10 tools; L2 warning; U14 |
| P1 | Real-client acceptance | Claude Code recognizes the MCP server (approval pending); Codex usage reports welcome |
| P2 | Retrieval perf pass (LIKE/fallback/facets) — **done in 0.3.1**: facets −47%, long search −48%, real hit@5 95% preserved | 100M-pool quiet rerun still open |
| P2 | Profile coverage/validation | 13 families covered; rerank weights still unvalidated on real data |
