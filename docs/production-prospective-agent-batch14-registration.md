---
title: Two unstarted tasks on a separate model route
---

# Two unstarted tasks on a separate model route

**Registered after repeated 503 responses on the previous solver route, before these task calls.** Both arms of [#17213](https://github.com/prettier/prettier/issues/17213) and [#15537](https://github.com/prettier/prettier/issues/15537) were `NOT_RUN_AFTER_STOP` in batches 12 and 13, and neither batch's solver log contains a start event for those four slots. The failed #18066 and #9955 requests are not retried. The [manifest](assets/benchmarks/production-prospective-agent-batch14/manifest.json) has SHA-256 `764124b5aea171946f3a4dab92459b863b12aa492c6c2af5b69034c31bf05efa` and fixes a fresh paired order.

The source, issue checks, small regression controls and related caveats remain as in the [six-issue registration](production-prospective-agent-batch12-registration.md). Both retrieval arms select the same single comment for #17213 and both select the same two comment IDs for #15537. These short contexts do not represent independent long-running production tasks.

The solver is now `deepseek-flash`, with its thinking mode disabled. A separate four-call synthetic search/edit/test diagnostic passed before registration; that is not a real task outcome or guarantee of availability. The blinded AI reviewers are `gpt-6-astra` and `claude-haiku-4-5`; the AI adjudicator is `gpt-6.1-sol`. These are distinct model names through the same proxy, not independent human assessors. Earlier Haiku reviews returned empty output and the Sol route returned 503; any such failures here remain missing and retain their unknown usage or fee. The explicit rubric, 12-turn budget, isolated tools, stop-on-provider-error within each stage and no automatic retry remain unchanged. The estimated target is below $1, not a hard cap.

This selection and model change follow observed failures, so the batch is not a randomized comparison of solvers or part of one pre-registered cohort. Public source exposure and partial checks preclude a production correctness, cost-savings or autonomous memory claim.
