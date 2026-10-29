---
title: Evaluation
layout: default
---

# Evaluation

The public synthetic workloads were rerun on v0.2.1, commit
[`4e9720d`](https://github.com/QiuXu-Tech/dsh-memory/commit/4e9720d6ba61f88126fde3f5ce62baab20758c22),
on 2026-10-29. The Apple M4 / Node 24.21.0 machine was heavily loaded; timings
are observations from that run, not controlled comparisons with the historical
figures. See the [benchmark report](https://github.com/QiuXu-Tech/dsh-memory/blob/main/docs/benchmark.md) for the full methodology,
raw results, charts and reproduction commands.

## Retrieval quality

| Suite | Probes | Target-record hit@1 | Target-record hit@5 |
|---|---:|---:|---:|
| Synthetic card cues and body facts | 80 | 100% | 100% |
| Demo direct search | 16 | 100% | 100% |
| Demo auto-recall query | 16 | 100% | 100% (only 3 results requested) |

These are synthetic search tests, not end-to-end answer tests. The synthetic
suite generates identifiers with `Math.random()`; its results are reported in
the [raw output](assets/benchmarks/results-recall.txt). The demo suite's
`cold recall` field can credit a hot hit for a probe whose acceptable set also
contains a cold record, so it is not evidence of cold-record retrieval.

A previous run against a private, curated 40-question archive reported hit@1
73%, hit@3/hit@5 95%, cold recall 100%, and search p50 1.3 ms; a prior
baseline was reported as 67% hit@5. That archive and its raw probes are not
public, and the run was **not repeated** for v0.2.1. These historical numbers
cannot be independently reproduced using the public fixture.

## Capacity and storage

| Synthetic pool | Write | Cold spill | Cold GC |
|---|---:|---:|---:|
| 1,000 records / 10M assigned tokens | 6.5 s | 700 records / 7M in 7.35 s | 350 records / 3.5M in 0.62 s |
| 10,000 records / 100M assigned tokens | 59.2 s | 5,000 records / 50M in 41.77 s | 2,500 records / 25M in 1.15 s |

The 100M run used 384.8 MiB of original body files and a 9.0 MiB SQLite index
after writing, growing to 26.6 MiB after cold spill. Token counts are assigned
synthetic values. Cold GC deletes the removed records. The read-path timings
and raw output are included in the [benchmark report](https://github.com/QiuXu-Tech/dsh-memory/blob/main/docs/benchmark.md).

An older private 1.9M-token archive was reported to shrink from 18.19 MB to
0.25 MB after the body-less FTS migration and `VACUUM`. That migration was not
rerun here; it should be treated as a historical observation rather than a
current public-fixture measurement.

## Measurement limits

- The long-horizon and scale runs use `LocalStoreCore` with default rerank
  weights and synthetic fixtures; they do not measure model-specific profiles,
  MCP/DSH integration, or an agent answering a task.
- The capacity helper's printed `p95` is based on five samples and selects the
  second-largest value. It is not a reliable 95th percentile. This rerun does
  not establish that the former `p95 < 50 ms` target is met.
- The offline harness passed 108/108 tests at the tested commit after building
  the bundle; this validates its test cases, not production or real-agent
  performance.
