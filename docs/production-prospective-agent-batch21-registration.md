---
title: Two validator.js issues, registered instrumentation
---

# Two validator.js issues — registered instrumentation

**Registered before these solver and review calls.** Two previously unattempted open validator.js issues, complete discussion snapshots, checks and randomized paired order are bound by the [manifest](assets/benchmarks/production-prospective-agent-batch21/manifest.json), SHA-256 `58a4537aca3557a1e8f70e3a143915e14b3a9e3d209596c792e9b90046d30ae0`. Selection followed prior results. The two tasks share a repository and are not guaranteed independent; the separate adaptive registrations are not one pre-registered 30–50-task cohort.

| Issue | Frozen acceptance | Reference |
| --- | --- | --- |
| [#2295](https://github.com/validatorjs/validator.js/issues/2295) | Unknown hash algorithms throw by default and return false with `validateAlgorithm: false`; known algorithms and invalid input controls remain valid. | Source-only [PR #2843](https://github.com/validatorjs/validator.js/pull/2843); the default follows the issue discussion. |
| [#1309](https://github.com/validatorjs/validator.js/issues/1309) | With `allow_exponential: true`, the issue's decimal and a second exponential example pass, malformed multiple-exponent strings fail, and ordinary/default decimal controls remain valid. | Source-only [PR #1750](https://github.com/validatorjs/validator.js/pull/1750) plus a manual rejection of multiple `e` separators. The original PR source failed that acceptance check; both patch versions are preserved. |

The [qualification ledger](assets/benchmarks/production-prospective-agent-batch21/qualification.json) records baseline failures and selected source-reference passes for public and acceptance checks, with controls passing on both. Checks are partial and not maintainer acceptance. Node module hooks load the pinned source without npm dependencies; this is not the distributed package. Public discussions and PRs can disclose solutions or appear in model training.

The randomized paired arms, bounded tools, reviewer rubric and 503-only retry policy follow the [previous registration](production-prospective-agent-batch18-registration.md). No timeout is retried; provider failure or missing usage stops the stage. After repeated Gemini truncation, the registered adjudicator is `gpt-6-astra` at 700 output tokens; this is the **same model name as the solver**, selected after earlier failures and not independent adjudication. `deepseek-flash` and `qwen3.8-flash` remain the blinded reviewers; all names share a proxy with unverified provenance. Estimated model-call target is below $1, not a hard cap. Short seeded issue histories do not establish production effectiveness, savings or autonomous memory management.
