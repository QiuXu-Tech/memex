---
title: Three previously unstarted tasks after a gateway 503
---

# Three previously unstarted tasks after a gateway 503

**Registered after batch 12 stopped on a 503, before these task calls.** Both arms of [#9955](https://github.com/prettier/prettier/issues/9955), [#17213](https://github.com/prettier/prettier/issues/17213) and [#15537](https://github.com/prettier/prettier/issues/15537) were recorded as `NOT_RUN_AFTER_STOP`; the original call log contains no start event for any of those six slots. The failed #18066 request and its issue are not retried. The [new manifest](assets/benchmarks/production-prospective-agent-batch13/manifest.json) has SHA-256 `171e118d7ee221b23c4340204403a2aaccfc385f243f95ddbdfeca3b2d9c1eb4` and fixes a fresh paired random order.

The same source, frozen issue checks, custom controls and limitations as the [six-issue registration](production-prospective-agent-batch12-registration.md) apply. #9955 shares a reference patch and possibly a cause with two other GraphQL samples, while both #17213 retrieval arms select the same single comment. These are not independent long-session production tasks.

One separate, minimal `gpt-6.1-sol` tool-route health probe returned a valid tool call after the 503; this does not guarantee subsequent availability and is not a retry of the failed request. Solver, two blinded AI reviewers, third-model AI adjudicator, explicit rubric, 12-turn limit, per-stage stopping and no automatic retry remain as registered for batch 12. The estimated target is below $1.50, not a hard cap. The post-observation selection and re-registration, failed request's unknown usage or charge, public solution exposure, partial tests and AI-only review remain visible; no production effect or cost-savings conclusion follows.
