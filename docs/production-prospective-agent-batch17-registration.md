---
title: Four Moment and math.js issues, registered instrumentation
---

# Four Moment and math.js issues — registered instrumentation

**Registered before these solver and review calls.** Four additional open issues, their complete discussion snapshots, fixed checks and randomized paired order are bound in the [manifest](assets/benchmarks/production-prospective-agent-batch17/manifest.json), SHA-256 `32e6a65f911d732b23d845d97e56dc8c8b6854ca5a133a030bfc3213e4c83976`. These issues were selected after observing earlier results: this is not one pre-registered 30–50-task independent cohort. Public histories, related date behavior and common projects can introduce correlation or expose solutions.

| Issue | Frozen acceptance | Source-only reference |
| --- | --- | --- |
| [Moment #3980](https://github.com/moment/moment/issues/3980) | The stated February-to-March month differences remain monotonic and the reverse direction remains negative. | [PR #6454](https://github.com/moment/moment/pull/6454) |
| [Moment #4641](https://github.com/moment/moment/issues/4641) | A mixed-sign duration humanizes and takes absolute value consistently; ordinary duration controls remain unchanged. | [PR #6460](https://github.com/moment/moment/pull/6460) |
| [math.js #3600](https://github.com/josdejong/mathjs/issues/3600) | The specified 3×3 Schur result is quasi-upper triangular, reconstructs the input and has an orthogonal basis. | [PR #3634](https://github.com/josdejong/mathjs/pull/3634) |
| [math.js #3614](https://github.com/josdejong/mathjs/issues/3614) | Purely real and purely imaginary conversions omit redundant parentheses; ordinary real and genuinely complex formatting controls remain unchanged. | [PR #3628](https://github.com/josdejong/mathjs/pull/3628) |

For each, the fixed public example and acceptance check fail on the pinned baseline and pass on the source-only reference; controls pass on both. The [qualification ledger](assets/benchmarks/production-prospective-agent-batch17/qualification.json) binds reference patches and private raw logs. The tests are narrow and neither comprehensive upstream testing nor maintainer acceptance. Moment uses a test-only Node source ESM hook; math.js runtime packages use a generated lock installed without lifecycle scripts. The separate sandbox is network-disabled and source execution has a fixed time and memory budget.

The same registered paired randomization, isolated tool access and explicit rubric apply. Solver `gpt-6-astra` is limited to 12 turns and four tool calls per turn. The AI reviewers are `deepseek-flash` (700 output tokens) and `qwen3.8-flash` (2,048); `gemini-3.8-flash` (2,048) adjudicates differing format-valid scores. The larger budgets follow observed truncation and are not evidence of reliable evaluation. All names use one proxy and their provenance is unverified. Only explicit 503 responses can be retried, at most twice, with each attempt logged; timeouts are not retried. Stop a stage after provider failure or missing usage; preserve failures and unknown fees. Estimated model-call target is under $2, not a hard cap.

Short pre-seeded issue discussions are not long-running production tasks, context differs between arms, and these tests do not establish production impact, savings, or autonomous memory management.
