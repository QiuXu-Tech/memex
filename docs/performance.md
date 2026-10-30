# Performance pass — 2026-10-31

Environment: Apple M4, 16 GiB, macOS arm64, Node **v24.21.0** (harness runtime). Measurements are single-process, local, no network unless explicitly noted.

## 1. Materializer microbenchmark

Synthetic pages (~80 tokens each), 20 repetitions per cell. `hybrid` = query + learnedTopK 8 + pageTokenCap 400 + diversity; `rule` = chronology/pinned only. All runs returned `budgetStatus=ok` and ≤1,800 tokens.

| pages | rule p50 | rule p95 | hybrid p50 | hybrid p95 |
|---:|---:|---:|---:|---:|
| 100 | 0.62 ms | 4.62 ms | 1.55 ms | 5.49 ms |
| 1,000 | 4.95 ms | 6.63 ms | 12.97 ms | 16.51 ms |
| 5,000 | 25.24 ms | 37.46 ms | 65.47 ms | 69.13 ms |

CJK vs English vs mixed queries were within noise for rule; hybrid ranged ~10–65 ms depending on page count. RSS after the run: ~300 MiB; heapUsed ~31 MiB.

## 2. Real replay workload

28 provisional replay episodes, L1 cards, 1,800 budget, `pageTokenCap=400`, 50 repetitions each:

| config | p50 | p95 | mean | avg pages | avg tokens |
|---|---:|---:|---:|---:|---:|
| rule + core | 0.076 ms | 0.189 ms | 0.089 ms | 33.9 | 1,643 |
| hybrid + core | 6.55 ms | 9.23 ms | 6.18 ms | 33.9 | 1,681 |

Real pager candidate sets are ~34 pages; hybrid selection costs ~6 ms per materialization.

## 3. Store scale benchmark

Synthetic 500 records × 5,000 tokens (2.5M tokens), throwaway DB:

- write 500 records / 2.5M tokens: **0.5 s**
- DB after write **0.6 MiB**; records dir **9.7 MiB**
- reads: get 0.03 ms; facets 0.23 ms; list 0.33 ms; catalog 0.59 ms; CJK search 0.11 ms; title search 1.04 ms; ASCII search 1.57 ms; body grep 3.17 ms
- compressCold: 350 records / 1.75M tokens in **0.48 s**; after cold search 4.48 ms, catalog 0.48 ms
- gcCold: 175 records / 0.88M tokens in **0.11 s**

## 4. Recall benchmark

200 records (100 cold), 40 probes:

- baseline L1-only: **0%** recoverable
- card probes via `memory_search`: **100% hit@1/3/5**, median 2.21 ms
- hot body-only probes: **100%**, median 2.22 ms
- cold body-only probes via `memory_grep`: **100%**, median 3.55 ms
- cost: catalog 640 tokens/step when changing; one `memory_open` ≈116 tokens; one result card ≈35 tokens

## 5. Active runtime

Latest trace: `budget=1800`, `budgetStatus=ok`, `overBudgetBy=0`, `formatTokens` present, rule/hybrid tokens within 1,800. Materializer trace does not yet record duration; only token/status metadata.

## Bottlenecks and optimization directions

1. **Hybrid materializer scales superlinearly with candidate count** (5k pages ≈65 ms). The pager usually supplies ~34 rows, but scoring all candidates for each turn is the main CPU cost. Direction: FTS/BM25 prefilter to top-M candidates before the materializer, or cache query→page scores.
2. **Repeated render/cost recomputation** for each candidate makes hybrid ~10–70× rule. Direction: incremental prefix/page accounting, or a cheaper fit check plus one final render.
3. **Cold search is slower** (4.5 ms) than hot search; acceptable, but a large cold pool would benefit from segmenting/batch queries.
4. **External model latency dominates** end-to-end: APIMaster measurements were 5–47 s vs ~0.1–6 ms local materialization. Local CPU optimization helps throughput, not wall-clock answer latency, unless materialization is on the critical path at scale.
5. **Rule remains the safe low-latency path**; hybrid should stay optional until quality and p95 budgets are validated.

Raw measurements: `docs/assets/benchmarks/performance-full-20261031.json`.
