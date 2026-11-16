# Exact materialization, less repeated work

Status: protocol frozen before measuring optimized candidates, 2026-11-16.
Research baseline: `c3fa508e53043e40eb1022d3606f0d467219a6e2` (the separately committed audit foundation on remote-main baseline `af389c3`). The audit fixes are prerequisites and are **not** counted as this week's performance improvement. No provider/model invocation, rented GPU or agent task trial is in this experiment.

## Question and three rounds

Can deterministic context assembly become substantially faster without changing any selected content, byte, ordering, budget result or custom-counter call?

1. R1: preserve the current sequence-first stream semantics, but maintain the sorted heads by stable lower-bound reinsertion; consider a single-sort singleton-stream fast path. Preserve legacy fallback outside the safe value domain. An initial stream ordinal heap tie-break and filtering one global ordering are explicitly rejected by counterexamples.
2. R2: replace repeated selected/dependency/retrieved membership scans with request-local indexes, preserving strict-equality edge cases, traversal order and callback behavior.
3. R3: avoid rebuilding long strings for default `chars/4` budget probes through exact rendered-length accounting. Count the whole UTF-16 length and one final ceiling, including format and final trim. Arbitrary custom counters retain full rendering, call order and exception behavior; unusual coercible inputs use the legacy route.

Every round is implemented, measured, independently reviewed and adjusted before the next. No Store/database or learned-selection changes are bundled into this performance PR. A rejected optimization remains in the experiment record, not in accepted runtime.

## Frozen workloads and resources

`scripts/materializer-bench.mjs` and `test/materializer-fixtures.mjs` define seven fixed strata: order 5,000 singleton streams; order 5,000 pages/64 streams; wide materialization 512 pages/512-code-unit bodies; tight materialization 2,048 pages/64 streams/2,400-token budget; typical 24-page window; custom-counter 128-page window; tool-heavy 512-page window. Wide budget deliberately permits all pages and is reported separately from ordinary bounded windows.

Seeds are `[11,29,47,83,101]`. Each seed has two separate paired worker replications. Predetermined AB/BA order alternates per pair. Each worker uses one warmup and three measured calls per stratum. No baseline/candidate workers run concurrently. A worker has a 60-second hard limit, with failure/partial records retained. Three rounds are capped at 30 minutes of benchmark worker wall time; local implementation/review and ordinary tests are separate. No extra paid API, GPU or dependency model downloads.

Primary outcome: median of paired-worker wall-time speedup ratios on wide materialization, final cumulative target >=2x. R1 target: >=25% decrease on singleton-stream ordering. Small-window regression bound: no more than max(10%, 0.2ms) increase in the median paired-worker difference. Report all strata and CPU, RSS and load; a winning stratum cannot hide a regression. Correctness takes precedence over speed.

All raw samples remain available. The primary summary is the median paired-worker ratio; geometric mean is supplementary. Each worker first takes the conventional median (two middle values averaged for even counts). Small-window bounds use paired worker differences. A deterministic two-level bootstrap resamples five seed clusters then paired workers, with 2,000 replicates. Five synthetic seeds remain a small, fixed corpus; intervals are descriptive and do not establish production statistical significance. P95 from the pooled 30 measured calls/version is descriptive, not a production tail guarantee. Peak RSS is per whole worker, not attributable to one case. Warm measurements do not represent disk-cold startup.

## Correctness and stopping

Use immutable legacy algorithm snapshots from the foundation, five seeds of at least 100 differential cases each, and explicit stable-tie/Unicode/clock-skew/tool-dependency cases. Compare full materializer return objects, input/reference preservation, custom callback traces and exception behavior. Counter inputs include non-additive, non-monotone and stateful functions. Tests cover hard/soft pinned and core budgets, reserve, omissions, duplicate IDs, unusual session/tool IDs, excerpts, empty text and trailing Unicode whitespace.

Benchmark fixture (all parameters plus named counter variant) and per-sample full V8-serialized output SHA-256 must match baseline/candidate in every pair. Independent deep-strict differential tests are the semantic gate, including callback traces. Snapshot the full core dependency closure and harness before and after measurement; any drift invalidates the run. Persist raw worker exits/stdout/stderr and partial results after each child, before parsing or parity checks. Any mismatch blocks acceptance. Stop an unsafe/over-limit run and preserve evidence; do not reduce an input after observing a losing result. Ordinary core, SQLite, integrity, audit, recall and bundle checks remain required before proposing merge.

Local assembly acceleration is the only measured benefit. It does not establish retrieval quality improvement, real model-token reduction, billed-cost savings, true-agent success, GPU KV correctness or client production acceptance. Legacy failures, UNKNOWN edits and incomplete historical A/B/C are unchanged.

Protocol amendment before the first optimized measurement: independent benchmark review required durable raw failure records, every-sample output fingerprints, paired statistics, and full-core before/after identities. These are corrected in the frozen harness. Each round is benchmarked from a separate immutable core snapshot, not from an actively edited tree.
