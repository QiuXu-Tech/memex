# Three-round exact materialization results

2026-11-16. Local synthetic benchmark on macOS arm64 / Node v25.9.0. Each round is cumulative against the same audit foundation `c3fa508e53043e40eb1022d3606f0d467219a6e2`; it is not a paired measurement of one round against the preceding round. The foundation cleanup commit changes documentation only. Audit fixes are not counted as speed gains.

Final wide-window paired median speedup: **11.563x**. The >=2x target passed. Small-window paired median difference: -0.1598 ms, against an allowed increase of 0.200 ms. All measured outputs matched; source hashes were stable before/after every run.

| Fixed workload | R1 ordered heads | R1 + R2 indexes | R1 + R2 + R3 lengths |
| --- | ---: | ---: | ---: |
| order-singletons | 61.049x | 63.189x | 62.894x |
| order-streams | 5.075x | 5.031x | 5.089x |
| materialize-wide | 4.032x | 4.074x | 11.563x |
| materialize-tight | 1.360x | 1.310x | 2.275x |
| materialize-small | 1.558x | 1.545x | 2.223x |
| materialize-custom | 1.061x | 1.077x | 1.101x |
| materialize-tools | 1.203x | 1.293x | 2.492x |

All numbers above are medians of ten paired-worker wall-time ratios. Five seeds, two pairs per seed, AB/BA order, one warmup and three measured calls per worker/case. They are not task success rates or token savings. R2 did not isolate its incremental benefit; differences between separate round runs may include noise.

## Final timing and resource detail

| Workload | Baseline median ms | Candidate median ms | Paired median speedup 95% interval | Paired median delta ms | CPU geomean speedup | Baseline / candidate pooled p95 ms |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| order-singletons | 128.0167 | 2.0305 | [60.524, 64.507] | -125.4778 | 55.027x | 144.7200 / 2.9764 |
| order-streams | 6.3969 | 1.2538 | [5.058, 5.171] | -5.1292 | 4.322x | 7.5739 / 1.4436 |
| materialize-wide | 258.2836 | 22.3689 | [11.443, 11.684] | -236.1683 | 8.750x | 265.4380 / 24.3083 |
| materialize-tight | 27.7360 | 12.2588 | [2.246, 2.287] | -15.5119 | 1.837x | 32.2478 / 15.1274 |
| materialize-small | 0.2870 | 0.1308 | [2.151, 2.389] | -0.1598 | 2.191x | 0.3437 / 0.1653 |
| materialize-custom | 6.3243 | 5.7887 | [1.064, 1.129] | -0.5767 | 1.054x | 6.9035 / 6.1732 |
| materialize-tools | 31.8745 | 12.8295 | [2.449, 2.537] | -19.0469 | 2.438x | 34.3005 / 13.5912 |

Intervals use the preregistered hierarchical bootstrap and describe this small fixed synthetic corpus. Pooled p95 is descriptive. CPU uses process user+system time. Zero CPU samples would be undefined, not zero speedup. The benchmark console log prints a geometric mean adjacent to an interval for the paired median; use the JSON pairedMedianSpeedup as the primary result.

| Final worker resource | Baseline | Candidate |
| --- | --- | --- |
| Peak RSS KiB (whole worker) | median 149536.00; range 149360.00–149792.00 | median 130728.00; range 129936.00–131808.00 |
| Observed 1-minute load average | median 1.60; range 1.48–1.65 | median 1.60; range 1.48–1.62 |

Peak RSS is cumulative for a whole worker across seven cases, not a per-case memory claim. Raw records also retain end-of-case RSS, CPU samples, runtime versions, load, worker exits/stdout/stderr, complete per-sample output fingerprints, fixture identities and all 17 core source hashes. Measurements are warm and include guard/index/cache overhead; process restarts do not establish disk-cold conditions.

## Verification and version binding

- R1 source commit: `6c460d7f9e23f60237edd870fe36b64b47a02684`. Raw results and version receipts are in [evidence](evidence/).
- R2 source commit: `b270c77e6fbf090058620660d8d01a3d848cab3c`. Raw results and version receipts are in [evidence](evidence/).
- R3 source commit: `5fda3fbc764ffa914bb6c755a5adb6dcc77c94a6`. Raw results and version receipts are in [evidence](evidence/).

Author tests and separate technical review passed for all three rounds. Independent review is AI engineering review, not human blind evaluation. R1 additionally exercised 2,000 independent short ordering cases; R2 added 2,000 full-output/exception cases; R3 results and probes are in the linked review. Frozen reference modules reconstruct their original source hashes in the differential suite.

Final local gates passed on Node v25.9.0 and v24.22.1: bundle build/parity, core 196, SQLite 38, integrity 50, audit/clean-install 43, expanded materializer differential tests, synthetic recall threshold 0.9, and 1,000-record scale smoke. Exact counts, normalized command arguments, exit statuses and hashes of locally retained logs are in the final validation receipt. Full validation logs are retained in the local delivery archive; they are not included in the public repository. GitHub checks are reported by the PR; these local checks do not establish all-platform or client acceptance.

The safe optimized domain is ordinary stable scalar data. Dynamic objects, custom counters and unsafe/coercible values use the preserved scan/render route as applicable. Standard Node builtins are assumed intact. Custom counter call text/order and exceptions remain part of the hard contract. The default chars/4 estimator remains a heuristic; this change does not make it an exact model tokenizer.

## Reproduce and interpret

From a clean checkout of the final research branch with Node >=24, create a separate baseline checkout at the foundation SHA, then run:

```sh
git worktree add --detach ../memex-frozen-baseline c3fa508e53043e40eb1022d3606f0d467219a6e2
node scripts/materializer-bench.mjs --baseline ../memex-frozen-baseline --candidate . --out ../memex-reproduction/results.json
npm run test:materializer
```

Choose a new output directory so prior evidence remains intact. Do not edit either source tree while measuring. Source drift or output mismatch invalidates a run; retain partial/failure files. The raw results here are observations of this machine, not promised results on another host.

No task-quality benchmark, real client workflow, model inference, provider billing, rented GPU or production deployment was measured. Engineering and review used existing Codex chats; no extra paid model endpoint was invoked. Local compute and Codex allowance consumption are not a measured monetary saving. Historical failed/UNKNOWN experiments remain unchanged. See [research discussion](RESEARCH.md) and the frozen [protocol](PROTOCOL.md).
