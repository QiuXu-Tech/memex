---
title: Two Yup issues, registered instrumentation
---

# Two Yup issues — registered instrumentation

**Registered before these solver and review calls.** Two previously unattempted open Yup issues, complete discussion snapshots, fixed checks and randomized paired order are bound by the [manifest](assets/benchmarks/production-prospective-agent-batch24/manifest.json), SHA-256 `020df6808dfc97be2b2f6be563e3e2b863afd9acfadb9748e0ffcd7880d6d6bf`. Selection followed earlier outcomes; the issues share a project and separate registrations are not an independent 30–50-task cohort.

| Issue | Frozen acceptance | Source-only reference |
| --- | --- | --- |
| [#2150](https://github.com/jquense/yup/issues/2150) | Valid defaults for arrays of required numbers validate; an invalid default still fails and ordinary array validation remains valid. | [PR #2329](https://github.com/jquense/yup/pull/2329) |
| [#660](https://github.com/jquense/yup/issues/660) | Object validation accepts own `constructor` and `toString` data fields without treating inherited prototype members as schemas; ordinary schema validation remains valid. | [PR #2353](https://github.com/jquense/yup/pull/2353) |

The [qualification ledger](assets/benchmarks/production-prospective-agent-batch24/qualification.json) records baseline failures and source-reference passes for public and acceptance checks, with controls passing on both. The checks transpile pinned TypeScript source through a test-only hook and use a generated dependency lock installed without lifecycle scripts; they do not test the published bundle or provide full upstream acceptance. An initial ESM test hook failed to load a CommonJS dependency and was replaced during qualification, before registration. Public issue discussions or PRs may expose solutions.

The VM, paired randomization, bounded tools, rubric, model budgets and logged 503-only retries follow the [validator registration](production-prospective-agent-batch21-registration.md). No timeout is retried; provider failure or missing usage stops each stage. The AI adjudicator has the same model name as the solver, selected after previous failures, and is not independent. All AI names share one proxy with unverified provenance. Estimated model-call target is below $1, not a hard cap. Short seeded issue discussions do not establish production effects, savings or autonomous memory management.
