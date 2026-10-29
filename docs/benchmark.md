---
title: Benchmark report
layout: default
---

# Benchmark report: synthetic long-horizon retrieval on v0.5.0

This report reruns the public synthetic workloads against the exact v0.5.0
commit [`5d2746e`](https://github.com/QiuXu-Tech/memex/commit/5d2746e9307721a70df0bbc740a9086ef0a6426e)
on 2026-10-29. The machine was an Apple M4 (10 logical CPUs, 16 GiB), running
macOS 27.2 and Node 24.21.0. The test checkout was detached at that commit;
the report was prepared separately on a later `main`. These measurements do
not evaluate v0.5.1 or later code.

Two complete passes were run on the shared machine. The report and charts use
the second pass because it used a stricter quiet-start gate: two consecutive
five-second samples with CPU busy **23.6% / 24.0%** and one-minute load
**3.59 / 3.38** (thresholds ≤25% and ≤5). During longer stages, seven
five-second samples showed CPU busy **27.1%–38.8%** and one-minute load
**3.36–4.10**, including the benchmark itself. Samples can cross stage
boundaries; short stages may have no dedicated sample. This was not an
isolated machine. The [run metadata](assets/benchmarks/run-metadata.json),
[load samples](assets/benchmarks/results-load-samples.jsonl), and
[execution records](assets/benchmarks/results-execution.jsonl) document the
method and tested input hashes.

The [first complete pass](assets/benchmarks/results-v050-first-pass.json) is
preserved as well. Its two quiet-start samples were 28.6% / 30.0% CPU busy and
5.27 / 5.17 load, meeting the earlier ≤30% CPU / ≤10 load gate. Its two
search p50 values for 1M, 5M, and 10M were respectively 1.62 / 1.66,
24.61 / 24.25, and 52.91 / 53.48 ms. Two shared-machine passes do not isolate
all load effects or establish a latency distribution.

Earlier reports remain in Git history for
[v0.2.1](https://github.com/QiuXu-Tech/memex/blob/41b47e43f0f58b6d46dfe1cfe7baae1630c6a242/docs/benchmark.md),
[v0.2.2](https://github.com/QiuXu-Tech/memex/blob/8d5a6f2a93da5b838ef60f1a21853f4e388b62b5/docs/benchmark.md), and
[v0.3.0](https://github.com/QiuXu-Tech/memex/blob/0555d45b64d6de4c1001960187a5a87d1422b6d5/docs/benchmark.md).
These are separate shared-machine runs; timing differences alone do not
establish a version performance change.

**Result in brief:** in a synthetic 160K-token history with an 80K-token
window, 20/40 target facts were present in the retained tail and 24/40 were
present under the supplied summary-plus-tail baseline. Memex search returned
the target record for 40/40 probes at rank 1. For the 20 probes whose records
were outside the window, the corresponding counts were 0/20, 4/20 and 20/20.
The first two are availability checks; the third is a retrieval hit, not an
end-to-end model answer. No model was called for this benchmark.

## 1. Compaction and retrieval comparison

![All-probe and old-span counts for truncation, the saved summary, and Memex search](assets/benchmarks/fact-recall.png)

The fixture creates 107 synthetic turns (160,473 estimated tokens) with 40
evenly spaced probes. It retains a tail near 80K tokens; the older span contains
79,490 estimated tokens and 20 probes. Each question includes a unique
`CTX-…` cue, which also appears in the corresponding record's title; its
summary contains the cue-to-`FACT-…` pair.

| Strategy | All 40 probes | 20 probes in old span | What is counted |
|---|---:|---:|---|
| Truncate to retained tail | 20/40 (50%) | 0/20 (0%) | Target fact in the tail |
| Supplied summary + tail | 24/40 (60%) | 4/20 (20%) | Tail facts plus old probes matched in the summary |
| Memex search | 40/40 (100%) | 20/20 (100%) | Target record in search results; all were rank 1 |

The summary is the previously committed [compaction-summary.txt](assets/benchmarks/compaction-summary.txt).
No model was invoked to create a new summary in this rerun, and its original
model/provider and generation transcript are not recorded here. The script
counts an old probe if **either** its cue or value appears in the summary. An
independent check of this summary found both the cue and value for each of the
four counted old probes. That does not establish that an arbitrary summary
preserves the relationship between a cue and its value.

The summary's 570-token size and the history/window sizes are character-based
estimates, not measurements with a model tokenizer. The supplied summary is
one simulated baseline, not a run of DSH's native compaction implementation.

## 2. Scaling the synthetic history

![Window-to-history ratio and target-record hit rate at three history sizes](assets/benchmarks/recall-scaling.png)

| Estimated history | Records | Window / history | Search hit@5, both runs | Search p50, first / repeat |
|---|---:|---:|---:|---:|
| 1,000,811 tokens | 667 | 99.9% | 40/40 (100%) | 1.57 / 1.56 ms |
| 5,004,369 tokens | 3,333 | 20.0% | 40/40 (100%) | 23.72 / 23.60 ms |
| 10,011,439 tokens | 6,667 | 10.0% | 40/40 (100%) | 51.04 / 51.47 ms |

The window/history column is an arithmetic coverage ratio, not measured
no-memory recall and not a universal ceiling. Actual availability depends on
where queried facts occur. Each hit@5 is a search for a known synthetic cue;
the workload does not measure whether an agent chooses a useful query or
answers correctly.

## 3. Search time and estimated context cost

![Search medians at three scales and two repeated 160K runs](assets/benchmarks/cost-latency.png)

The 160K comparison's search p50 was **1.70 ms** on the first run and
**1.61 ms** on a repeat with the same fixture and supplied summary. Each p50
comes from 40 searches. The script selects sorted element `floor(n / 2)`;
for 40 observations this is the upper of the two middle values, rather than
their average. The scaling sweep was also repeated; these observations are not
a production latency distribution.

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
corpus. The two sizes use different cold target ratios to reproduce the prior
7M and 50M spill sizes.

| Pool | Write | Cold spill | Cold GC |
|---|---:|---:|---:|
| 1,000 records / 10M assigned tokens | 0.4 s | 700 records / 7M tokens in 0.32 s | 350 records / 3.5M tokens in 0.03 s |
| 10,000 records / 100M assigned tokens | 3.8 s | 5,000 records / 50M tokens in 3.03 s | 2,500 records / 25M tokens in 0.31 s |

In the 100M run, the SQLite index was 10.5 MiB after writing and 28.0 MiB
after cold spill; the original body files totalled 384.8 MiB. Cold spill moves
the records, while **cold GC deletes** the records it removes. Both were
exercised only on throwaway stores. These are single-run times under the sampled
load noted above.

The fixture's bodies consist only of repeated `x` characters. In v0.5.0,
`record_terms` also indexes numeric anchors from card fields. A separate
[two-record spot check](assets/benchmarks/results-body-index-probe.json),
using identical number-bearing cards, found two indexed hashes with an
`x`-only body and four when an identifier was added to the body. Thus these
capacity and index-size figures include card-field anchors but do **not**
represent the overhead of identifier-bearing real-world bodies.

## 5. Complementary offline checks

The public `recall-eval.mjs --suite all` run reported 80/80 synthetic probes
at hit@1 and hit@5, and 16/16 demo probes at hit@1 for both direct search and
the auto-recall query path. The synthetic identifiers use `Math.random()`;
the questions are synthetic, and the auto-recall path requests only three
results. See the [raw output](assets/benchmarks/results-recall.txt).

After the timing runs, the v0.5.0 bundle was built in the isolated checkout;
bundle parity passed and the offline harness reported [117/117 passed](assets/benchmarks/results-harness.txt),
including U20's cold natural-language anchor test. The earlier
[unbuilt-bundle run](assets/benchmarks/results-harness-unbuilt.txt) also
reported 117/117, with three bundle checks skipped. These checks are not a
live agent benchmark.

The earlier 95% hit@5 figure came from a private, curated 40-question archive.
It was **not rerun** here and cannot be independently reproduced from the
public fixtures. See [evaluation](https://github.com/QiuXu-Tech/memex/blob/main/docs/evaluation.md)
for its historical context.

## 6. Live A/B qualification

This offline benchmark does not rerun the separately published DeepSeek Flash
A/B. The historical v0.5.0 results reported 3/60 control and 57/60 treatment;
those are stored in the [v0.5.0 snapshot](https://github.com/QiuXu-Tech/memex/blob/5d2746e9307721a70df0bbc740a9086ef0a6426e/docs/assets/benchmarks/live-ab-deepseek-multiseed.json),
not in this benchmark's retrieval counts.

There **was** a reproducible problem in the A/B harness's retained-tail setup:
it archived older records (changing `updated_at`) and then selected the supposed
recent tail using `list()`'s updated-time order. In a reproduction of three
300-turn seeds, each generated context included turn 270 and omitted turn 285
instead of preserving the last 20 turns (see the [reproduction evidence](assets/benchmarks/results-live-ab-tail-check-v050.json)).

**v0.8.0 fixes this:** `scripts/live-ab.mjs` now saves the exact newest-tail
record ids (`tailIds`) and per-probe `inTail`/`evicted` flags in `plan.json`,
and builds the control prompt from exactly those rows. A fresh three-seed
DeepSeek Flash rerun is verified: control **3/60**, treatment **60/60**,
evicted subset **0/57 → 57/57** ([verified evidence](assets/benchmarks/live-ab-deepseek-multiseed.json)).
The original published A/B JSON does not preserve its actual tail or provider
transcripts, so those original prompt contents and the “evicted” subset cannot
be independently reconstructed from it. Its arithmetic counts remain
reported, but they should not be treated as a verified comparison against the
last 20 turns. A corrected harness, saved prompts/tail membership, and new
live calls are needed to establish that comparison. The snapshot's
`generatedAt` is 16:55 +08:00 while the commit containing it is timestamped
16:41:13 +08:00. The later [v0.5.1 snapshot](https://github.com/QiuXu-Tech/memex/blob/ce64e5c6c057557cfdc9774b0384712b518b3a23/docs/assets/benchmarks/live-ab-deepseek-multiseed.json)
says 18:30 +08:00, while its containing commit is timestamped 18:20:29 +08:00.
These timestamp discrepancies
also require reconciliation; they alone do not establish why the times differ.
The [live-testing report](https://github.com/QiuXu-Tech/memex/blob/main/docs/live-testing.md) retains its data with this caveat.

## Scope and limitations

- All measured searches here call `LocalStoreCore` with default rerank
  weights. They do not benchmark model-specific `AgentMemory` profiles,
  MCP/DSH integration, transcript capture, or an agent's end-to-end answers.
- Exact synthetic cues and prefilled card summaries make these retrieval
  probes easier to locate than many real project questions. The results do not
  establish recall on paraphrases, multi-hop tasks, or missing cues. The
  long-horizon fixture itself does not isolate the cold natural-language fix.
- Timings were collected on a shared machine after a quiet-start gate, with
  five-second load samples during longer stages; this is not full isolation.
  The capacity script prints a `p95` from only five samples using its own index
  rule; this report does not treat it as a reliable 95th percentile.
- The supplied summary is reused; no independent model-summary generation or
  private-archive test was performed. No live memory store was accessed.

## Reproduce

Use Node 24+ and a separate checkout of the tested commit. These commands
create dedicated temporary output directories; the scripts also create and
remove throwaway stores. The summary must be passed explicitly. Record load
separately if comparing shared-machine timings.

```bash
git clone https://github.com/QiuXu-Tech/memex.git memex-benchmark-v050
cd memex-benchmark-v050
git checkout --detach 5d2746e9307721a70df0bbc740a9086ef0a6426e
out_dir="$(mktemp -d "${TMPDIR:-/tmp}/memex-benchmark.XXXXXX")"
for run in first repeat; do
  node --import ./test/register.mjs scripts/long-horizon-eval.mjs --mode compaction \
    --tokens 160000 --window 80000 --summary docs/assets/benchmarks/compaction-summary.txt \
    --out "$out_dir/compaction-$run"
done
for run in first repeat; do
  node --import ./test/register.mjs scripts/long-horizon-eval.mjs --mode scale \
    --sizes 1000000,5000000,10000000 --window 1000000 --out "$out_dir/scale-$run"
done
node --import ./test/register.mjs scripts/scale-bench.mjs \
  --records 1000 --tokens 10000 --target 0.3 --gc 0.5
node --import ./test/register.mjs scripts/scale-bench.mjs \
  --records 10000 --tokens 10000 --target 0.5 --gc 0.5
node --import ./test/register.mjs scripts/recall-eval.mjs --suite all
node scripts/build-bundle.mjs
node scripts/check-bundle.mjs
node --import ./test/register.mjs test/run.mjs
```

The checked-in [compaction results](assets/benchmarks/results-compaction.json),
[repeat](assets/benchmarks/results-compaction-repeat.json),
[probe manifest](assets/benchmarks/results-probes.json),
[scaling results](assets/benchmarks/results-scale.json),
[scaling repeat](assets/benchmarks/results-scale-repeat.json),
[capacity data](assets/benchmarks/results-capacity.json), and raw capacity
outputs ([10M](assets/benchmarks/results-capacity-10m.txt),
[100M](assets/benchmarks/results-capacity-100m.txt)) are from the second pass.
Earlier results remain available in Git history. In a checkout containing this
report, install Matplotlib 3.10.7 and run `python scripts/plot-benchmarks.py`
to regenerate the PNGs. The plotting script reads the checked-in snapshot,
not a new temporary run.
