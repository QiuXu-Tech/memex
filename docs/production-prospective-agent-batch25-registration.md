---
title: Three validator.js and Chart.js issues, registered instrumentation
---

# Three validator.js and Chart.js issues — registered instrumentation

**Registered before these solver and review calls.** Three additional open issues, complete discussion snapshots, fixed checks and randomized paired order are bound by the [manifest](assets/benchmarks/production-prospective-agent-batch25/manifest.json), SHA-256 `a3d3cd003c85f709ed1fe695788693027e7f4b3839159b2e99fd5cb1ecdc355b`. The issues were selected after earlier outcomes; separate adaptive batches and shared projects do not form one pre-registered independent cohort.

| Issue | Frozen acceptance | Source-only reference |
| --- | --- | --- |
| [validator.js #2497](https://github.com/validatorjs/validator.js/issues/2497) | The two example Macedonian mobile formats described by the reference PR are accepted, while a too-short number and ordinary controls are handled as specified. This checks examples, not the full official numbering plan. | [PR #2687](https://github.com/validatorjs/validator.js/pull/2687) |
| [validator.js #912](https://github.com/validatorjs/validator.js/issues/912) | `thousands_separator_mode: 'required'` requires a separator for amounts of at least 1,000 in the fixed USD and European examples; smaller amounts and default behavior remain valid. | [PR #2667](https://github.com/validatorjs/validator.js/pull/2667). **The option name comes from the PR source; its prose uses a different name.** The criterion was chosen after inspecting that source and should not be interpreted as independent product acceptance. |
| [Chart.js #12191](https://github.com/chartjs/Chart.js/issues/12191) | A single-argument `splice` synchronizes listener and controller metadata for two positions; ordinary removal and insertion controls remain valid. | [PR #12249](https://github.com/chartjs/Chart.js/pull/12249). The test uses the real array listener and a mocked controller insertion method; it is not a full browser rendering test. |

**No-history negative control:** #12191 had no discussion records at snapshot time. Its arms receive different empty-result messages, but no historical records; it cannot demonstrate a retrieval or memory effect. The issue identifies a problematic source line, which may make the task easier. All histories are public and short; comments and linked PRs can disclose solutions or appear in model training.

The [qualification ledger](assets/benchmarks/production-prospective-agent-batch25/qualification.json) records baseline failures and source-reference passes for public and acceptance checks, with controls passing on both. These are partial checks, not project acceptance. Validator uses Node source-module hooks; Chart.js uses a test-only TypeScript hook and dependency lock installed without lifecycle scripts. The currency option criterion was revised during qualification after the PR prose and code disagreed.

The VM, paired randomization, bounded tools, rubric, model budgets and logged 503-only retries follow the [validator registration](production-prospective-agent-batch21-registration.md). No timeout is retried; provider failure or missing usage stops each stage. The AI adjudicator has the same model name as the solver, selected after earlier failures, and is not independent. All AI names share one proxy with unverified provenance. Estimated model-call target is below $2, not a hard cap. These results do not establish production effects, savings or autonomous memory management.
