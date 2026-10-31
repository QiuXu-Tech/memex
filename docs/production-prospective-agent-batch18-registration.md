---
title: Three Day.js and math.js issues, registered instrumentation
---

# Three Day.js and math.js issues — registered instrumentation

**Registered before these solver and review calls.** Three additional open issues, their complete discussion snapshots, fixed checks and randomized paired order are bound in the [manifest](assets/benchmarks/production-prospective-agent-batch18/manifest.json), SHA-256 `090aa8016f6bf4bd55d0c1f468b733b4b3e799aa9fa3b72bc8671218304a9cdc`. They were selected after earlier outcomes and share repositories with other batches; these observations are not a single pre-registered or statistically independent 30–50-task cohort.

| Issue | Frozen acceptance | Source-only reference |
| --- | --- | --- |
| [Day.js #3062](https://github.com/iamkun/dayjs/issues/3062) | Uzbek locale week numbering for 2020-12-31 and 2021-01-01 is 53; controls include English and a midyear Uzbek date. | Closed, unmerged [PR #3100](https://github.com/iamkun/dayjs/pull/3100), which also addresses related issues |
| [math.js #3528](https://github.com/josdejong/mathjs/issues/3528) | A nested derivative of `x * derivative("e^x", "x")` evaluates to the expected value at two inputs; controls cover ordinary derivatives. | [PR #3715](https://github.com/josdejong/mathjs/pull/3715) |
| [math.js #3563](https://github.com/josdejong/mathjs/issues/3563) | Two sums of pure percentages evaluate as sums of fractions; controls cover modulus and relative percentage addition. | [PR #3573](https://github.com/josdejong/mathjs/pull/3573) |

The [qualification ledger](assets/benchmarks/production-prospective-agent-batch18/qualification.json) records that the public and acceptance checks fail on the baseline and pass on the source-only references, while controls pass on both. Candidate checks were developed and revised before registration; the Day.js control was adjusted during qualification after initially testing another affected boundary. The frozen checks are partial, not full upstream tests or maintainer acceptance. Public issue discussions and proposed patches can disclose solutions or appear in model training.

The pinned VM, source/runtime, randomized paired conditions, bounded tools, rubric, model budgets and logged 503-only retries follow the [previous registration](production-prospective-agent-batch17-registration.md). No timeout is retried. The estimated model-call target is below $2, not a hard cap. All AI model names share a proxy with unverified provenance. Short seeded issue discussion is not a real long-running production session, and no production effectiveness, savings or autonomous-memory conclusion follows.
