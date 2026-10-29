---
title: Evaluation
layout: default
---

# Evaluation

All numbers below are reproducible with the scripts in `scripts/`. They were measured on a 10-core Apple Silicon machine with Node 24, SQLite `node:sqlite`, and synthetic or throwaway archives (never the live store).

## Recall (retrieval quality)

| Suite | hit@1 | hit@3 | hit@5 | cold recall | p50 |
|---|---|---|---|---|---|
| Synthetic, 40 cue probes + 40 fact probes (master run) | 100% | 100% | 100% | 100% | ~1.9 ms |
| Demo natural-language suite (`scripts/recall-eval.mjs`) | see output | | | | |
| Real archive, 40 curated natural-language questions (private archive, pre-merge baseline) | 73% | 95% | **95%** | **100%** | 1.3 ms |

Baseline before hybrid retrieval was **67% recall@5** on the same style of natural-language probes. The improvement came from: shared query-term extraction (`memoryQueryTerms`), an FTS leg over card fields plus a bounded **cold abstract**, a LIKE leg for CJK bigrams/short terms, and a lexical rerank (title/tags/useWhen weights + recency, small cold penalty).

Reproduce:

```bash
node --import ./test/register.mjs scripts/recall-eval.mjs --suite all
node --import ./test/register.mjs scripts/recall-bench.mjs   # long-horizon probe class table
```

## Scale (`scripts/scale-bench.mjs`)

| Config | Write | DB | Read paths | Compression | GC |
|---|---|---|---|---|---|
| 1,000 records × 10k tokens (10M) | 0.3 s | 1.0 MiB | facets 0.6 ms, catalog 1.2 ms, search 1.2–5.6 ms, grep 4.5 ms | 700 rec / 7M tokens in 0.10 s | 350 rec / 0.02 s |
| 10,000 records × 10k tokens (100M) | 2.8 s | 9.0 MiB (26.6 MiB after cold abstracts) | facets 11.3 ms, list 5.8 ms, catalog 17.5 ms, search 16.7–28.8 ms, grep 14.6 ms, get 0.04 ms | 5,000 rec / 50M tokens in 2.6 s | 2,500 rec / 25M in 0.31 s |

Acceptance targets for the 100M-token pool: card search p95 < 50 ms, `grep` < 2 s — both met (the body scan is bounded to the hot tier, cold bodies are reached through `memory_grep`/`memory_open`).

Note: records are written as real markdown files (384.8 MiB for the 100M-token run); the SQLite index stays small because bodies are not trigram-indexed — cards plus a bounded cold abstract are.

## Storage (FTS body removal)

Removing bodies from the FTS index and replacing them with card fields plus a 1 KB cold abstract shrank a real 1.9M-token archive's DB from **18.19 MB to 0.25 MB (−98.6%)** after migration + `VACUUM`, and made ASCII-heavy searches ~3× faster (45 ms → ~15 ms on that archive). Cold bodies remain retrievable by `memory_open`/`memory_grep`; only automatic substring search is bounded.

## Methodology notes

- Probes in the synthetic/demo suites are deterministic; the "real archive" numbers came from a private archive and are reported here for context, not as a reproducible benchmark.
- Latencies are medians of repeated runs on a warm SQLite connection; the first open includes one-time migration work.
- Compression runs are measured end-to-end including file renames (`cold`) or mock LLM calls (`digest`); digest latency is dominated by the provider.
- The harness itself runs 98 assertions covering the same behaviors offline (`node --import ./test/register.mjs ./test/run.mjs`).
