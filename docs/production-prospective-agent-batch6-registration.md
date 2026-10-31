---
title: Five-issue Pino and Prettier instrumentation registration
---

# Five-issue Pino and Prettier instrumentation registration

**Registered before this batch's model calls, after inspecting earlier batches.** This batch extends the separate open-source instrumentation trials; it is not a pre-registered 30–50-task study. These public issues were open with complete comment snapshots when selected. The frozen [manifest](assets/benchmarks/production-prospective-agent-batch6/manifest.json) has SHA-256 `9d20a82ff992a6eeb47d0a215829fdad9e08974c453820391fa24be1f5383f69` and records the randomized paired order, scripts and checks.

| Issue | Frozen issue-specific criterion | Reference for a positive control |
| --- | --- | --- |
| [Pino #2057](https://github.com/pinojs/pino/issues/2057) | Browser error-with-cause serializer preserves the nested cause and ordinary error serialization still works. | [PR #2438](https://github.com/pinojs/pino/pull/2438) |
| [Prettier #19427](https://github.com/prettier/prettier/issues/19427) | The specified nested SCSS comment and function have the expected indentation, and formatting is idempotent. | [PR #19439](https://github.com/prettier/prettier/pull/19439) |
| [Prettier #19847](https://github.com/prettier/prettier/issues/19847) | Formatting the specified indented Markdown table examples is idempotent. | [PR #20233](https://github.com/prettier/prettier/pull/20233) |
| [Prettier #20047](https://github.com/prettier/prettier/issues/20047) | The specified wrapped inline HTML comment remains in its paragraph, and formatting is idempotent. | [PR #20106](https://github.com/prettier/prettier/pull/20106) |
| [Prettier #20293](https://github.com/prettier/prettier/issues/20293) | The two supplied YAML examples preserve parsed structure and are idempotent. | [PR #20297](https://github.com/prettier/prettier/pull/20297) |

Each frozen issue check fails on the pinned baseline and passes with its public reference patch; the additional custom regression controls pass on both. These checks cover examples, not complete project acceptance. Pino and Prettier are pinned to commits `b29dbe97820630e7128e464c50263b427965ec99` and `bed4edbb1cf2a9db4004215b0ce5707cdb02b5d9`. Runtime dependency lock hashes are in the manifest; installed dependency trees are not individually attested. The agent can read upstream tests and a public issue example but cannot inspect the frozen issue check or custom regression controls.

`gpt-6-astra` solves each issue twice in independently isolated copies, with the same bounded code tools and either keyword retrieval or a pre-seeded Memex pager of public issue comments. This is not a real long-running session or autonomous memory lifecycle. Each assignment has at most 12 tool turns, four tool calls per turn, and one forced short final response. Complete final responses and passing both frozen checks are required for the runner's instrumented pass; this remains weaker than maintainer acceptance. The runtime uses a disposable Linux VM and a network-disabled process sandbox; these controls are not a security certification.

Two blinded AI reviewers, `deepseek-flash` and `gpt-6.1-sol`, use an explicit scale: correctness 0 = wrong/unresolved, 1 = partial/insufficient, 2 = supported by the supplied evidence; side effects 0 = demonstrated serious regression, 1 = plausible risk or material uncertainty, 2 = no material regression identified. Either field may be null for insufficient evidence. This rubric is fixed before these calls and differs from earlier batches, whose numeric direction was not specified. For disagreements between two valid ratings, `gpt-6-astra` adjudicates; its model family matches the solver, and neither the review nor adjudication is independent human assessment. Blinding may be imperfect when the evidence itself reveals the condition.

Each stage stops launching calls after a provider failure, malformed provider response, or missing usage; no automatic retry is permitted. Invalid and missing ratings, incomplete assignments, failed requests and unreported charges remain visible. The batch has an estimated target below $2, not a hard spending cap. Public discussions and linked PRs may have been seen by the models, the custom checks are partial, and the tasks were chosen after previous outcomes. No production correctness, cost-savings, or autonomous memory-management conclusion follows from this batch.
