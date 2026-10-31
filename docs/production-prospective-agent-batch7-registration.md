---
title: Two further Prettier task checks
---

# Two further Prettier task checks

**Registered before these task calls and after inspecting prior batches.** These two additional open issues are separate from earlier registrations, not a pre-registered 30–50-task study. Their [frozen manifest](assets/benchmarks/production-prospective-agent-batch7/manifest.json) has SHA-256 `5e53c07679c582279738a4ef8d3d33044096706c9c9e9dcb47c14266ef805e5b` and binds the randomized paired order, scripts, checks, issue snapshots and contexts.

| Issue | Frozen criterion | Positive reference used only for check validation |
| --- | --- | --- |
| [Prettier #19955](https://github.com/prettier/prettier/issues/19955) | Five parenthesized arrow/comment examples, including the four reported cases, must format idempotently and retain the indicated comments. | Source hunks of [PR #20008](https://github.com/prettier/prettier/pull/20008), head `be7c77345641a959fa4b4fccda3ba1ffd59ba936` |
| [Prettier #19968](https://github.com/prettier/prettier/issues/19968) | Two reported TypeScript return-type examples and the discussion's union-return example must format idempotently. | Source hunks of [PR #19970](https://github.com/prettier/prettier/pull/19970), head `9e105df0f7cf034f63ae5a01094611e4e4aaec4a` |

On pinned Prettier commit `bed4edbb1cf2a9db4004215b0ce5707cdb02b5d9`, the #19955 issue check failed four of five cases and the #19968 check failed all three. Each corresponding source-only reference patch passed its issue check; both baseline and reference passed the small custom regression controls. Public examples also failed on the baseline and passed on the reference. This does not establish full project behavior or upstream acceptance. The discussion of #19955 includes detailed proposed solutions, and the #19968 discussion compares existing PRs; the solver can see retrieved comments, so prior solution exposure is a material confound.

The protocol, explicit AI scoring rubric, restricted VM tools, stage stopping rules and cost limitations are the same as the [five-issue batch](production-prospective-agent-batch6-registration.md), with a separately randomized order, two new issues, at most 12 tool turns per assignment and an estimated batch target below $1 rather than a hard cap. `gpt-6-astra` is the solver and adjudicator, `deepseek-flash` and `gpt-6.1-sol` are the blinded AI reviewers. Missing and invalid results remain missing; the human-review, production, cost-effectiveness and autonomous-memory claims remain unverified.
