# W48 local MCP search latency study

25 November 2026, Asia/Shanghai. The starting point is `ece03e38e9e70c6ea57111bc1991b58987b1ae1d` from PR #5. The study measures a local stdio server and synthetic persisted archives. The planned 30% reduction in mixed warm request latency was **not achieved**.

## Three rounds

| Round | What changed or was learned | Paired median reduction |
| --- | --- | ---: |
| R1 | Measured real MCP search, preview and open. Sparse queries in the 512-record archive read about 100 different files. The common-term query read none. | A/A variability check |
| R2 | Located the first matching line in the same file without allocating every line separately. Compared with the starting point. | 4.30% |
| R3 | Preserved file traversal for LF-only alternatives and reused at most 32 prepared search statements for the active SQLite connection. Compared with the starting point. | 8.56% and 13.85% |

Each run consisted of eight local processes, 960 timed requests and 320 warmups across 20 strata. All timed candidate replies matched their same-run references. The primary metric is the median of two paired reductions computed from the pooled per-worker blocks. SQLite and archive stages were profiled separately. The benchmark used Node 25.9.0 and SQLite 3.51.3 on macOS arm64. [Protocol](PROTOCOL.md)

The final A/A run's mixed pair estimates ranged from a 47.73% slowdown to a 15.20% reduction on identical source. In R3's two comparisons with the initial baseline, no strata exceeded the planned regression guard. R3 compared directly with R2 exceeded the guard in six 512-record strata on the first run, and in zero strata on the repeat. The range leaves the repeatable acceleration unresolved. The branch retains the candidate for review and the gain target remains unmet.

## Behavior and scope

The first matching line retains the original `/i` literal matching and LF boundaries. The four-term cap applies before excluding terms that contain LF. R3 preserves traversal and error propagation for a query whose eligible terms all contain LF. The statement cache is bounded, clears on close or connection change, and binds each request's current parameters. File reads, SQL execution and ranking take place on each request.

Node 24.22.3 passed 363 tests across core, SQLite, integrity, audit and materialization, plus bundle build and parity, synthetic recall and a 1,000-record smoke run. Node 25.9.0 passed the search differential and the targeted SQLite and audit regressions. [Validation receipt](validation.json)

The independent probe exercises ordered replies, snippets, quotes containing LF, scope, external body change, edit, expiry, reopen and deletion. The protocol benchmark exercises visible and hidden scopes and tool errors. This is an offline synthetic protocol study.

## Reproduction and evidence

From bootstrapped source checkouts, run the same script against the reference and candidate into a new file:

```sh
node scripts/mcp-latency-study.mjs ../memex-baseline . ../mcp-study-run.json
```

The measurement table retains sample timings, full response digests, source identities and checksums of the raw records. The local archive also retains worker stderr, the initial setup failure, original seven-case A/A and freeze, the subsequent ten-case reconciliation, and all candidate and repeat samples. The expanded ten-case A/A completed before candidate timing. A stale harness digest in the first launch did not stop that shell as intended. The first output was preserved as exploratory, and the R2 confirmation checked the final digest and frozen source before measuring. [Measurements](measurements.json)
