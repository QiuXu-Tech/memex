---
title: Two additional math.js issues, registered instrumentation
---

# Two additional math.js issues — registered instrumentation

**Registered before these solver and review calls.** Two additional open issues, complete discussion snapshots, fixed checks and randomized paired order are bound by the [manifest](assets/benchmarks/production-prospective-agent-batch20/manifest.json), SHA-256 `aca9a7327a630a7825ef40faafc7ddd9f0d845201adbc6600097a5f90774d506`. Selection followed prior results; this is not one pre-registered 30–50-task independent cohort.

| Issue | Frozen acceptance | Source-only reference |
| --- | --- | --- |
| [#3644](https://github.com/josdejong/mathjs/issues/3644) | Splitting one- and two-meter units into feet and inches through the expression parser returns the specified two components; direct unit splitting and conversion remain valid. | [PR #3671](https://github.com/josdejong/mathjs/pull/3671) |
| [#1905](https://github.com/josdejong/mathjs/issues/1905) | `help(not)` evaluates and returns help text; ordinary logical negation and `help(and)` remain valid. | Closed [PR #3470](https://github.com/josdejong/mathjs/pull/3470) |

The [qualification ledger](assets/benchmarks/production-prospective-agent-batch20/qualification.json) records baseline failures and reference passes for public and acceptance checks, with controls passing on both. The #3644 test was corrected during candidate qualification to handle an array result before freezing. These are partial checks, not upstream acceptance. The two issues touch different behaviors but share a repository and source areas with earlier tasks; independence cannot be assumed. Public comments and patches can disclose solutions or appear in model training.

The VM, runtime, paired randomization, tools, rubric, model budgets and 503-only retry policy follow the [previous registration](production-prospective-agent-batch18-registration.md). No timeout is retried; provider failure or missing usage stops each stage. The estimated cost target is below $2, not a hard cap. Same-proxy AI reviews and short seeded issue discussions do not establish production effectiveness, savings or autonomous memory management.
