# W48 follow-up on repeated compaction and local latency

The first priority is keeping long development sessions grounded through repeated compaction. DSH now makes earlier evidence eligible for injection again when a new compacted window starts. Session-local deduplication still suppresses identical repeats inside the same window. The regression reproduces a lost recall on the first compaction on the published PR head, and exercises catalog, recall and materialized-window injection across three boundaries after the change. The settings for the query-ranked experiment already exist and remain opt-in. [Evaluation, settings and mechanical results](../../../context-compaction-evaluation.md)

Two synthetic trajectories across three compactions each retained all 118 original shadowed events. At a common 1,200 estimated-token evidence ceiling, rolling summaries supplied 20/36 full reference receipts, search-and-open supplied 29/36, the chronological pager supplied 27/36, and query-ranked canonical paging supplied 36/36. Query-ranked context still showed a stale or unsupported statement alongside the true source in 16/36 probes. Two Codex respondents, each seeing a single opaque context per question, answered 12 paired questions. The summary had 6/12 correctly cited targets and six appropriate abstentions, while query-ranked paging had 12/12 correctly cited targets. Neither arm made an unsupported assertion. This checks a small synthetic workflow with scripted summaries. Native live-host compaction results and a rate of hallucination reduction remain unmeasured. [Paired answers and grading](answer-grades.json)

## Why the original timing moved

The six 512-record regressions in the first R2-to-R3 comparison all depended on the second worker pair. The R3 worker in that pair was slower across all ten cases compared with the first R3 worker, including standalone and denied opens. It had 12/120 timed requests above 10 ms and six in one sweep. Its p95 was about 15.4 ms. The analogous repeat worker had a p95 of about 4.2 ms and a maximum of about 4.6 ms. Neither run recorded sufficient scheduler, I/O or garbage-collection telemetry to attribute the original worker shift to one of those mechanisms. The original mixed median fell among 12-record requests, so it could improve alongside the 512-record regressions.

The revised benchmark retains the ten request classes and both fixture sizes. It restarts four independent pairs per size, alternates startup order, and dispatches adjacent same-case RPCs in alternating order with at most one request in flight. After 24 warmup sweeps, it retains 32 timed sweeps per worker. The two same-code runs showed +0.09% and +0.73% mixed median reductions, a largest absolute pair shift of 1.12%, and zero guard crossings. This met the thresholds fixed before candidate timing. All comparisons use the same fixture and request digests and compare complete tool replies. [Paired measurements and raw file checksums](latency.json)

## Final runtime candidate

| Reference | Mixed endpoint median reduction | 512-record search-only reduction |
| --- | ---: | ---: |
| W47, first run | 40.33% | 28.24% |
| W47, repeat | 40.12% | 28.23% |
| Published PR #6, first run | 32.27% | 22.04% |
| Published PR #6, repeat | 31.92% | 22.03% |

The 30% mixed target passed twice against each reference. None of the 80 final per-run strata exceeded its regression guard. The 512-record search-only subset stayed below 30%. These are warm stdio calls on one machine with Node 25.9.0 and synthetic stores. The mixed workload includes standalone opens and access-denied requests, and the median is sensitive to their weights.

The final change skips cold-only search legs when a query-local lookup shows an empty cold tier. A partial SQLite index keeps this lookup from scanning the entire records table. A 100,000-row, all-hot diagnostic measured a 1.183 ms median table scan and a 0.00021 ms indexed lookup in an in-memory SQLite fixture. This isolated lookup is separate from request timings. The migration creates the index after adding the cold column to legacy archives. The hot fallback reads only ID and path for the candidate list, and the store reuses prepared statements for repeated reads with the current parameters. File bodies continue to be read from disk. An initial raw-text cache candidate was faster but failed review because path replacement between metadata probes could associate the wrong body with a file identity. Its measurements remain recorded. The first indexed variant put the index before legacy column migration and was superseded before delivery.

Local verification passed 365 tests, build and bundle parity, synthetic recall and a 1,000-record scale smoke test. Whole-search and connection-lifecycle differentials passed. A separate 48-case replay matched full hot/cold search outputs on records with tied timestamps across scoped queries. [Validation receipt](validation.json)

Reproduce the final comparison with bootstrapped source checkouts and independent output paths.

```sh
node scripts/mcp-latency-study.mjs /path/to/reference . /path/to/local-samples.json --paired
```

Raw local evidence includes the frozen protocols, failures, all per-request timings and response digests, model response receipts, final validation logs, and the historical run identifiers.
