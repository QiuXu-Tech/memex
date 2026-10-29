---
title: Benchmark report
layout: default
---

# Benchmark report: synthetic long-horizon retrieval on v0.2.1

This report reruns the published synthetic workloads against commit
[`4e9720d`](https://github.com/QiuXu-Tech/dsh-memory/commit/4e9720d6ba61f88126fde3f5ce62baab20758c22)
on 2026-10-29. The machine was an Apple M4 (10 logical CPUs, 16 GiB), running
macOS 27.2 and Node 24.21.0. It was heavily loaded: sampled one-minute load
averages ranged from 57 to 114. Timings describe these runs, not a controlled
comparison with earlier versions. The [run metadata](assets/benchmarks/run-metadata.json)
records the tested commit and input hashes.

GitHub `main` advanced to v0.2.2 after this measurement. The results below are
for v0.2.1 and do not measure v0.2.2.

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
| 1,000,811 tokens | 667 | 99.9% | 40/40 (100%) | 20.8 / 7.5 ms |
| 5,004,369 tokens | 3,333 | 20.0% | 40/40 (100%) | 229.1 / 110.3 ms |
| 10,011,439 tokens | 6,667 | 10.0% | 40/40 (100%) | 289.9 / 177.2 ms |

The window/history column is an arithmetic coverage ratio, not measured
no-memory recall and not a universal ceiling. Actual availability depends on
where queried facts occur. Each hit@5 is a search for a known synthetic cue;
the workload does not measure whether an agent chooses a useful query or
answers correctly.

## 3. Search time and estimated context cost

![Search medians at three scales and two repeated 160K runs](assets/benchmarks/cost-latency.png)

The 160K comparison's search p50 was **22.0 ms** on the first run and
**6.3 ms** on a repeat with the same fixture and supplied summary. Each p50 is
the median of 40 searches. The scaling sweep was also repeated; both sets of
measurements show why shared-machine timings should not be treated as a stable
performance estimate.

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
| 1,000 records / 10M assigned tokens | 6.5 s | 700 records / 7M tokens in 7.35 s | 350 records / 3.5M tokens in 0.62 s |
| 10,000 records / 100M assigned tokens | 59.2 s | 5,000 records / 50M tokens in 41.77 s | 2,500 records / 25M tokens in 1.15 s |

In the 100M run, the SQLite index was 9.0 MiB after writing and 26.6 MiB after
cold spill; the original body files totalled 384.8 MiB. Cold spill moves the
records, while **cold GC deletes** the records it removes. Both were exercised
only on throwaway stores. These are single-run times under the load noted above.

## 5. Complementary recall suite

The public `recall-eval.mjs --suite all` run reported 80/80 synthetic probes
at hit@1 and hit@5, and 16/16 demo probes at hit@1 for both direct search and
the auto-recall query path. The synthetic identifiers use `Math.random()`;
the questions are synthetic, and the auto-recall path requests only three
results. See the [raw output](assets/benchmarks/results-recall.txt).

The earlier 95% hit@5 figure came from a private, curated 40-question archive.
It was **not rerun** here and cannot be independently reproduced from the
public fixtures. See [evaluation](https://github.com/QiuXu-Tech/dsh-memory/blob/main/docs/evaluation.md) for its historical context.

## Scope and limitations

- All measured searches here call `LocalStoreCore` with default rerank
  weights. They do not benchmark v0.2.1's model-specific `AgentMemory`
  profiles, MCP/DSH integration, transcript capture, or an agent's end-to-end
  answers. The offline tests cover some of those code paths but are not an
  agent benchmark.
- Exact synthetic cues and prefilled card summaries make these retrieval
  probes easier to locate than many real project questions. The results do not
  establish recall on paraphrases, multi-hop tasks, or missing cues.
- Timings, including the two repeated 160K results, were collected on a
  shared, heavily loaded machine. The capacity script prints a `p95` from
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
git clone https://github.com/QiuXu-Tech/dsh-memory.git dsh-memory-benchmark-v021
cd dsh-memory-benchmark-v021
git checkout --detach 4e9720d6ba61f88126fde3f5ce62baab20758c22
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
[100M](assets/benchmarks/results-capacity-100m.txt)) are from this run.
Earlier results remain available in Git history. In a checkout containing this
report, install Matplotlib 3.10.7 in a Python environment and run
`python scripts/plot-benchmarks.py` to regenerate the PNGs. That script reads
the checked-in snapshot, not a new temporary run.
