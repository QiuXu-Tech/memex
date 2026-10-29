---
title: Evaluation
layout: default
---

# Evaluation

The public synthetic workloads were rerun on v0.9.1 plus the tail-order fix, commit
[`72ba8fc`](https://github.com/QiuXu-Tech/memex/commit/72ba8fc338e79e46121d44c8757594c773ed3b6b),
on 2026-10-29. The Apple M4 / Node 24.21.0 machine met a quiet-start gate;
it remained shared and load was sampled during the longer stages. See the
[benchmark report](https://github.com/QiuXu-Tech/memex/blob/main/docs/benchmark.md)
for methodology, load samples, raw results, charts and reproduction commands.

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
public.

**Reported v0.5.1 re-check (same private 40-question archive):** hit@1
**68%**, hit@3 **90%**, hit@5 **93%**, cold recall **94%**, p50 **1.5 ms**.
These private-archive numbers cannot be independently reproduced from the
public fixture. The separate reported DeepSeek multi-seed results have a
[retained-tail methodology caveat](https://github.com/QiuXu-Tech/memex/blob/main/docs/live-testing.md#deepseek-flash-results-2026-10-29).

## Capacity and storage

| Synthetic pool | Write | Cold spill | Cold GC |
|---|---:|---:|---:|
| 1,000 records / 10M assigned tokens | 0.4 s | 700 records / 7M in 0.30 s | 350 records / 3.5M in 0.03 s |
| 10,000 records / 100M assigned tokens | 4.5 s | 5,000 records / 50M in 2.66 s | 2,500 records / 25M in 0.29 s |

The 100M run used 384.8 MiB of original body files and a 10.5 MiB SQLite index
after writing, growing to 28.0 MiB after cold spill. Token counts are assigned
synthetic values. The x-only bodies do not measure identifier-body index
overhead; numeric anchors in the card fields are indexed in v0.5.0. Cold GC
deletes the removed records. The read-path timings and raw output are included
in the [benchmark report](https://github.com/QiuXu-Tech/memex/blob/main/docs/benchmark.md).

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
- The offline harness passed 122/122 tests at the tested commit after building
  the bundle; this validates its test cases, not production or real-agent
  performance.
