---
title: One-issue alternate-model agent instrumentation registration
---

# One-issue alternate-model agent instrumentation registration

**Registered before these calls and after observing earlier batches.** This separate, small instrumentation check uses [Lodash #5881](https://github.com/lodash/lodash/issues/5881), which appeared in prior registrations but was not attempted after those batches stopped. Its pinned source and acceptance/reference checks are the same as the [Lodash search-repair registration](production-prospective-agent-batch3-registration.md). The [manifest](assets/benchmarks/production-prospective-agent-batch5/manifest.json) has SHA-256 `894b0998ac0163528506f2070ce56d6ea068e2c02864957f5d4bd0e5cf0c34fc`.

The two paired, randomized arms use the same isolated tools and issue but a different solver, `gpt-6-astra`, to check whether the earlier model's incomplete work reflected a tool/model interaction. This is not a randomized comparison between models: the choice followed earlier results and the task differs. The pre-seeded keyword and Memex pager contexts, 16-turn tool budget, at most four tool calls per turn, frozen issue-specific check and custom regression controls are otherwise as in the preceding Lodash batch. If the tool budget is exhausted, the runner asks for a final answer in at most two sentences and permits up to 1,200 output tokens; incomplete or truncated replies remain visible.

Blind AI reviewers are `deepseek-flash` and `claude-haiku-4-5`; disagreements between valid ratings are reviewed by `gpt-6-astra`, the solver family, so adjudication is not independent human review. Stage-level stopping, no automatic retry and accounting rules are unchanged. The batch target is under $1 and is not a hard cap; failed calls and missing usage or fees remain UNKNOWN. A single public issue, with potential exposure to its discussion and public PRs, cannot establish production correctness, cost savings, or autonomous memory management.
