---
title: Benchmark report
layout: default
---

# Benchmark report: synthetic long-horizon retrieval on v0.9.1 with the tail-order fix

The public synthetic workloads were run against commit
[`72ba8fc`](https://github.com/QiuXu-Tech/memex/commit/72ba8fc338e79e46121d44c8757594c773ed3b6b),
which uses the v0.9.1 release's package code plus the post-release A/B
tail-order fix. The [v0.9.1 tag](https://github.com/QiuXu-Tech/memex/tree/v0.9.1)
itself predates that fix. The package tree and three offline benchmark scripts
are identical between the tag and tested commit; the A/B fixture differs.
When this work began, repository `main` was already on v0.12.0 and advanced
further during reporting. This report does not measure those later releases.

On 2026-10-29 the test machine was an Apple M4 (10 logical CPUs, 16 GiB),
running macOS 27.2 and Node 24.21.0. Before starting, two consecutive five-second
samples showed CPU busy **24.8% / 21.6%** and one-minute load **3.25 / 3.39**
(quiet-start thresholds ≤25% and ≤5). During longer stages, seven five-second
samples showed CPU busy **23.2%–35.7%** and one-minute load **3.04–3.23**,
including the benchmark itself. Samples can cross stage boundaries; short
stages may have no dedicated sample. This was a shared machine, not an isolated
host. The [run metadata](assets/benchmarks/run-metadata.json),
[load samples](assets/benchmarks/results-load-samples.jsonl), and
[execution records](assets/benchmarks/results-execution.jsonl) record the
method and tested input hashes.

The earlier [v0.8.1 + tail-fix report](https://github.com/QiuXu-Tech/memex/blob/72ba8fc338e79e46121d44c8757594c773ed3b6b/docs/benchmark.md),
[v0.5.0 report](https://github.com/QiuXu-Tech/memex/blob/4ab6d6b35d643ce38e638769c1332e2d56a0b807/docs/benchmark.md),
and [v0.3.0 report](https://github.com/QiuXu-Tech/memex/blob/0555d45b64d6de4c1001960187a5a87d1422b6d5/docs/benchmark.md)
remain available. Separate shared-machine timings do not isolate version or
load effects and do not establish a performance change.

**Result in brief:** in a synthetic 160K-token history with an 80K-token
window, 20/40 target facts were present in the retained tail and 24/40 were
present under the supplied summary-plus-tail baseline. Memex search returned
the target record for 40/40 probes at rank 1. For the 20 probes whose records
were outside the window, the corresponding counts were 0/20, 4/20 and 20/20.
The first two are availability checks; the third is a retrieval hit, not an
end-to-end model answer. No model was called for these offline measurements;
the separate live Codex A/B is described in section 6.

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
| 1,000,811 tokens | 667 | 99.9% | 40/40 (100%) | 2.01 / 1.92 ms |
| 5,004,369 tokens | 3,333 | 20.0% | 40/40 (100%) | 24.26 / 25.60 ms |
| 10,011,439 tokens | 6,667 | 10.0% | 40/40 (100%) | 52.37 / 52.17 ms |

The window/history column is an arithmetic coverage ratio, not measured
no-memory recall and not a universal ceiling. Actual availability depends on
where queried facts occur. Each hit@5 is a search for a known synthetic cue;
the workload does not measure whether an agent chooses a useful query or
answers correctly.

## 3. Search time and estimated context cost

![Search medians at three scales and two repeated 160K runs](assets/benchmarks/cost-latency.png)

The 160K comparison's search p50 was **2.15 ms** on the first run and
**2.11 ms** on a repeat with the same fixture and supplied summary. Each p50
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
| 1,000 records / 10M assigned tokens | 0.4 s | 700 records / 7M tokens in 0.30 s | 350 records / 3.5M tokens in 0.03 s |
| 10,000 records / 100M assigned tokens | 4.5 s | 5,000 records / 50M tokens in 2.66 s | 2,500 records / 25M tokens in 0.29 s |

In the 100M run, the SQLite index was 10.5 MiB after writing and 28.0 MiB
after cold spill; the original body files totalled 384.8 MiB. Cold spill moves
the records, while **cold GC deletes** the records it removes. Both were
exercised only on throwaway stores. These are single-run times under the sampled
load noted above.

The fixture's bodies consist only of repeated `x` characters. In this version,
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

The bundle was built in the isolated checkout; bundle parity passed and the
Node 24 offline harness reported [122/122 passed](assets/benchmarks/results-harness.txt),
including U25's fixed-timestamp, reverse-ID tail-order test. Before the fix,
that test [failed as expected](assets/benchmarks/results-tail-regression.json).
These checks are not a live agent benchmark.

The earlier 95% hit@5 figure came from a private, curated 40-question archive.
It was **not rerun** here and cannot be independently reproduced from the
public fixtures. See [evaluation](https://github.com/QiuXu-Tech/memex/blob/main/docs/evaluation.md)
for its historical context.

## 6. Codex A/B and retained-tail verification

![Codex A/B exact-answer counts for all probes and evicted probes](assets/benchmarks/codex-ab.png)

A separate live run used `gpt-6.1-sol` through Codex CLI, with three synthetic
300-turn histories and 20 probes each. The bridge used Node 25.9.0 and Codex
CLI 0.165.0-alpha.1.2. The quiet-start gate and load samples above apply to
the offline workloads; load was not recorded separately for the Codex calls.
The control received the titles and
summaries of the 20 recent tail records, not their full conversation bodies;
the treatment received the same cards plus evidence selected and opened by the
fixture before the model call. This tests answers given pre-retrieved evidence,
not whether a model autonomously chooses memory tools.

| Condition | All probes | 57 evicted probes |
|---|---:|---:|
| Control: tail titles and summaries | 3/60 (5%) | 0/57 (0%) |
| Treatment: tail cards + retrieved evidence | 60/60 (100%) | 57/57 (100%) |

**Interrupted run and recovery:** the original bridge completed the first two
seeds but exited while generating the third seed with SQLite `ERR_SQLITE_ERROR`
(code 5, `database is locked`). No third-seed model call had started. We kept
the failed temporary database, plans and answers, generated seed 3 in a new
temporary directory, and ran only its two missing calls with the same Codex
arguments. The cause of the database lock is **unknown**. The bridge did not
write a final report, so the displayed aggregate was reconstructed from the
saved plans and exact answers; it is not an uninterrupted bridge run.

The four original calls' process exit codes were not retained; their local
Codex session logs contain `task_complete` events and final messages matching
the saved answer files. Both recovery calls exited zero and have matching
completion events. The [reconstructed result](assets/benchmarks/live-ab-codex-sol-v091.json)
records those distinctions and the failure. The [fixture evidence](assets/benchmarks/live-ab-codex-sol-v091-evidence.json)
contains each actual plan and both synthetic prompts. All three tails are
**turns 280–299 in order**, both prompt contexts match their recorded tail,
and all 57 evicted-probe flags match that tail. The six recorded Codex sessions
contain no model-issued tool calls; this observation is limited to those logs.

The six local Codex `token_count` events report **157,473 input tokens**
(including 79,104 cached input), **1,838 output tokens**, and **159,311 total**.
The 846 reasoning-output tokens are included in output, not additional. These
are local session usage counts, not a provider billing receipt; monetary cost
is **unknown**. Diagnostics for the initial four calls were not retained; the
two recovery calls reported initialization warnings. Recovery diagnostics may
contain sensitive data and remain local, with hashes in the published result.
The failed original run's diagnostic tail and SQLite files also remain local.

The earlier [v0.8.1 + tail-fix Codex result](https://github.com/QiuXu-Tech/memex/blob/72ba8fc338e79e46121d44c8757594c773ed3b6b/docs/assets/benchmarks/live-ab-codex-sol-tail-fixed.json)
remains in Git history; it is a separate run.

### Historical tail-order limitation

The original harness first selected `list()` by updated time after archiving.
v0.8.0 improved membership recording but still sorted by `created_at, id`:
records written in the same millisecond can be reordered by their random IDs.
The fixed fixture uses the order in which `store.write` returned each ID for
both archiving and constructing the tail. U25 freezes the clock and reverses
IDs to reproduce the defect deterministically.

In the earlier v0.8.0 Codex run, saved prompts for two seeds included turn
278 or 279 and omitted turn 281. The previously published DeepSeek tail records
also differ from turns 280–299 in two seeds. The historical result counts are
preserved, but the full old DeepSeek provider prompts were not saved, and the
published Terra and Claude results have tail IDs without all tail record
titles, so exact chronological tails cannot be established for those calls. See the
[historical tail audit](assets/benchmarks/results-tail-history-v080.json) and
[prior Codex prompt evidence](assets/benchmarks/results-tail-history-v080-codex-prompts.json).

The old v0.5.0 and v0.5.1 result snapshots also contain `generatedAt` values
later than their respective Git commit timestamps. The reason remains unknown;
those historical time discrepancies are not evidence of when calls occurred.


## Scope and limitations

- The offline search timings call `LocalStoreCore` with default rerank weights;
  they do not benchmark model-specific `AgentMemory` profiles, MCP/DSH
  integration, transcript capture, or an agent's end-to-end answers. The
  separate Codex A/B uses a model-specific profile to construct evidence.
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
git clone https://github.com/QiuXu-Tech/memex.git memex-benchmark-tail-fix
cd memex-benchmark-tail-fix
git checkout --detach 72ba8fc338e79e46121d44c8757594c773ed3b6b
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

With a logged-in Codex CLI, a new live A/B attempt can be run from the same
checkout with the command below. It makes live model calls; the reconstructed
run above includes a separate recovery of seed 3.

```bash
node scripts/codex-ab.mjs --model gpt-6.1-sol --keep --out "$out_dir/codex-ab.json"
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
report, install Matplotlib 3.10.7 and run `python scripts/plot-benchmarks.py`
to regenerate the PNGs. The plotting script reads the checked-in snapshot,
not a new temporary run.
