---
title: Benchmark report
layout: default
---

# Benchmark report: synthetic long-horizon retrieval on v0.3.0

This report reruns the published synthetic workloads against commit
[`3373ec6`](https://github.com/QiuXu-Tech/dsh-memory/commit/3373ec6ed46ea3b571a798c95714bd5d226f1ddb)
on 2026-10-29. The machine was an Apple M4 (10 logical CPUs, 16 GiB), running
macOS 27.2 and Node 24.21.0. Before starting, two consecutive five-second
samples met the quiet-start gate: CPU busy **16.4% / 25.5%** and one-minute
load **1.81 / 1.90**. During the longer benchmark stages, six samples showed
one-minute load **2.39–3.49** and CPU busy **26.7%–36.8%**, including the
benchmark itself. Sampling intervals can cross stage boundaries; short stages
may have no dedicated sample. The machine was shared, not isolated. The
[run metadata](assets/benchmarks/run-metadata.json) and
[load samples](assets/benchmarks/results-load-samples.jsonl) record the method,
tested commit and input hashes.

The execution checkout was `8d5a6f2`, a report-only descendant of v0.3.0;
its package and test trees and the three benchmark scripts matched `3373ec6`.
GitHub `main` advanced to v0.3.1 during this work; these measurements do not
evaluate v0.3.1.

The earlier [v0.2.1 report](https://github.com/QiuXu-Tech/dsh-memory/blob/41b47e43f0f58b6d46dfe1cfe7baae1630c6a242/docs/benchmark.md)
and [v0.2.2 report](https://github.com/QiuXu-Tech/dsh-memory/blob/8d5a6f2a93da5b838ef60f1a21853f4e388b62b5/docs/benchmark.md)
remain in Git history. These were separate shared-machine runs, so their timing
differences alone do not establish a version performance change.

**Result in brief:** in a synthetic 160K-token history with an 80K-token
window, 20/40 target facts were present in the retained tail and 24/40 were
present under the supplied summary-plus-tail baseline. The dsh-memory search
returned the target record for 40/40 probes at rank 1. For the 20 probes
whose records were outside the window, the corresponding counts were 0/20,
4/20 and 20/20. The first two numbers are availability checks; the third is a
retrieval hit, not an end-to-end model answer.

## 1. Compaction and retrieval comparison

![All-probe and old-span counts for truncation, the saved summary, and dsh-memory search](assets/benchmarks/fact-recall.png)

The fixture creates 107 synthetic turns (160,473 estimated tokens) with 40
evenly spaced probes. It retains a tail near 80K tokens; the older span contains
79,490 estimated tokens and 20 of the probes. Each question includes a unique
`CTX-…` cue, which also appears in the corresponding record's title; its
summary contains the cue-to-`FACT-…` pair.

| Strategy | All 40 probes | 20 probes in old span | What is counted |
|---|---:|---:|---|
| Truncate to retained tail | 20/40 (50%) | 0/20 (0%) | Target fact in the tail |
| Supplied summary + tail | 24/40 (60%) | 4/20 (20%) | Tail facts plus old probes matched in the summary |
| dsh-memory search | 40/40 (100%) | 20/20 (100%) | Target record in search results; all were rank 1 |

The summary is the previously committed [compaction-summary.txt](assets/benchmarks/compaction-summary.txt).
No model was invoked to create a new summary in this rerun, and its original
model/provider and generation transcript are not recorded here. The script
counts an old probe if **either** its cue or value appears in the summary. An
independent check of this particular summary found both the cue and value for
each of the four counted old probes. This does not establish that an arbitrary
summary preserves the relationship between a cue and its value.

The summary's 570-token size and the history/window sizes are character-based
estimates, not measurements with a model tokenizer. The supplied summary is
one simulated baseline, not a run of DSH's native compaction implementation.

## 2. Scaling the synthetic history

![Window-to-history ratio and target-record hit rate at three history sizes](assets/benchmarks/recall-scaling.png)

| Estimated history | Records | Window / history | Search hit@5, both runs | Search p50, first / repeat |
|---|---:|---:|---:|---:|
| 1,000,811 tokens | 667 | 99.9% | 40/40 (100%) | 1.63 / 1.65 ms |
| 5,004,369 tokens | 3,333 | 20.0% | 40/40 (100%) | 15.74 / 15.62 ms |
| 10,011,439 tokens | 6,667 | 10.0% | 40/40 (100%) | 33.00 / 31.36 ms |

The window/history column is an arithmetic coverage ratio, not measured
no-memory recall and not a universal ceiling. Actual availability depends on
where queried facts occur. Each hit@5 is a search for a known synthetic cue;
the workload does not measure whether an agent chooses a useful query or
answers correctly.

## 3. Search time and estimated context cost

![Search medians at three scales and two repeated 160K runs](assets/benchmarks/cost-latency.png)

The 160K comparison's search p50 was **1.78 ms** on the first run and
**1.73 ms** on a repeat with the same fixture and supplied summary. Each p50 is
the median of 40 searches. The scaling sweep was also repeated; two runs on a
shared machine are not enough to establish a latency distribution or
production performance.

The script estimates **1,693 tokens per probe** for result cards plus one
assumed target-record body. It does not call `memory_open` or measure model
reasoning. Comparing this estimate with the 79,490-token old span yields
approximately **47×** (79,490 / 1,693), as a token-count proxy, not a measured
cost saving. Search timing excludes record opening and model execution. Catalog
and auto-recall injection costs were not measured in this rerun.

## 4. Synthetic capacity and cold operations

![Synthetic 100M-token storage footprint and operation times](assets/benchmarks/capacity.png)

The capacity fixture assigns 10,000 estimated tokens to each record and uses
repeated-character bodies; it is not a tokenizer-derived natural-language
corpus. The two runs use different cold target ratios to reproduce the prior
7M and 50M spill sizes.

| Pool | Write | Cold spill | Cold GC |
|---|---:|---:|---:|
| 1,000 records / 10M assigned tokens | 0.4 s | 700 records / 7M tokens in 0.33 s | 350 records / 3.5M tokens in 0.03 s |
| 10,000 records / 100M assigned tokens | 3.2 s | 5,000 records / 50M tokens in 2.50 s | 2,500 records / 25M tokens in 0.31 s |

In the 100M run, the SQLite index was 9.0 MiB after writing and 26.6 MiB after
cold spill; the original body files totalled 384.8 MiB. Cold spill moves the
records, while **cold GC deletes** the records it removes. Both were exercised
only on throwaway stores. These are single-run times under the sampled load
noted above.

The fixture's bodies consist only of repeated `x` characters. A separate
[one-record spot check](assets/benchmarks/results-body-index-probe.json)
produced zero `record_terms` rows for that body. These capacity and index-size
figures therefore do not measure the overhead of indexing identifier-bearing
real-world bodies introduced in v0.3.0.

## 5. Complementary recall suite

The public `recall-eval.mjs --suite all` run reported 80/80 synthetic probes
at hit@1 and hit@5, and 16/16 demo probes at hit@1 for both direct search and
the auto-recall query path. The synthetic identifiers use `Math.random()`;
the questions are synthetic, and the auto-recall path requests only three
results. See the [raw output](assets/benchmarks/results-recall.txt).

The earlier 95% hit@5 figure came from a private, curated 40-question archive.
It was **not rerun** here and cannot be independently reproduced from the
public fixtures. See [evaluation](https://github.com/QiuXu-Tech/dsh-memory/blob/main/docs/evaluation.md) for its historical context.

The v0.3.0 offline harness also passed [U13](https://github.com/QiuXu-Tech/dsh-memory/blob/3373ec6ed46ea3b571a798c95714bd5d226f1ddb/test/run.mjs#L3849),
a separate hot-body identifier-rescue test. Its assertions require at least
24/30 hit@1 and 27/30 hit@5 and check identifier boundaries; the actual counts
are not printed, and this is not a latency benchmark.

## Scope and limitations

- All measured searches here call `LocalStoreCore` with default rerank
  weights. They do not benchmark v0.3.0's model-specific `AgentMemory`
  profiles, MCP/DSH integration, transcript capture, or an agent's end-to-end
  answers. The offline tests cover some of those code paths but are not an
  agent benchmark.
- Exact synthetic cues and prefilled card summaries make these retrieval
  probes easier to locate than many real project questions. The results do not
  establish recall on paraphrases, multi-hop tasks, or missing cues. The
  long-horizon fixture itself does not isolate the new hot-body rescue path.
- Timings were collected on a shared machine after the quiet-start gate, with
  five-second load samples during longer stages; this is not full isolation.
  The capacity script prints a `p95` from
  only five samples using its own index rule; this report does not treat that
  field as a reliable 95th percentile or declare the former p95 target passed.
- The supplied summary is reused; no independent model-summary generation or
  private-archive test was performed. No live memory store was accessed.

## Reproduce

Use Node 24+ and a separate checkout of the tested commit. The commands below
create dedicated temporary output directories; the scripts also create and
remove throwaway stores. The summary must be passed explicitly for the
comparison.

```bash
git clone https://github.com/QiuXu-Tech/dsh-memory.git dsh-memory-benchmark-v030
cd dsh-memory-benchmark-v030
git checkout --detach 3373ec6ed46ea3b571a798c95714bd5d226f1ddb
out_dir="$(mktemp -d "${TMPDIR:-/tmp}/dsh-benchmark.XXXXXX")"
node --import ./test/register.mjs scripts/long-horizon-eval.mjs --mode compaction \
  --tokens 160000 --window 80000 --summary docs/assets/benchmarks/compaction-summary.txt \
  --out "$out_dir/compaction"
node --import ./test/register.mjs scripts/long-horizon-eval.mjs --mode scale \
  --sizes 1000000,5000000,10000000 --window 1000000 --out "$out_dir/scale"
node --import ./test/register.mjs scripts/scale-bench.mjs \
  --records 1000 --tokens 10000 --target 0.3 --gc 0.5
node --import ./test/register.mjs scripts/scale-bench.mjs \
  --records 10000 --tokens 10000 --target 0.5 --gc 0.5
node --import ./test/register.mjs scripts/recall-eval.mjs --suite all
```

The checked-in [compaction results](assets/benchmarks/results-compaction.json),
[repeat](assets/benchmarks/results-compaction-repeat.json),
[probe manifest](assets/benchmarks/results-probes.json),
[scaling results](assets/benchmarks/results-scale.json),
[scaling repeat](assets/benchmarks/results-scale-repeat.json),
[capacity data](assets/benchmarks/results-capacity.json), and raw capacity
outputs ([10M](assets/benchmarks/results-capacity-10m.txt),
[100M](assets/benchmarks/results-capacity-100m.txt)),
[execution records](assets/benchmarks/results-execution.jsonl), and
[load samples](assets/benchmarks/results-load-samples.jsonl) are from this run.
Earlier results remain available in Git history. In a checkout containing this
report, install Matplotlib 3.10.7 in a Python environment and run
`python scripts/plot-benchmarks.py` to regenerate the PNGs. That script reads
the checked-in snapshot, not a new temporary run.
