---
title: Three further Prettier idempotency checks
---

# Three further Prettier idempotency checks

**Registered before these task calls and after prior results and reference patches were inspected.** The three issues were open with complete discussion snapshots at selection. This is another separate instrumentation batch, not a pre-registered 30–50-task cohort. The [manifest](assets/benchmarks/production-prospective-agent-batch10/manifest.json) has SHA-256 `62853b4fa768341c33560396ff85bf6deeac251fa09914acc917ed444921dfa6` and fixes task snapshots, scripts, checks and paired order.

| Issue | Frozen issue check | Positive reference |
| --- | --- | --- |
| [Prettier #12649](https://github.com/prettier/prettier/issues/12649) | The reported MDX inline-tag example is idempotent, retains both named tags and preserves the normalized parsed tree. | Source hunks of closed, unmerged [PR #20255](https://github.com/prettier/prettier/pull/20255), head `6888113e99f76cbbda494215570f0bab727718a7` |
| [Prettier #10851](https://github.com/prettier/prettier/issues/10851) | The reported TypeScript example is idempotent, retains its type-checking comment marker and preserves the normalized Babel program. | Source hunks of closed, unmerged [PR #19882](https://github.com/prettier/prettier/pull/19882), head `23c7bcfc3d75dd6da155a1bfad77657a601a0155` |
| [Prettier #18080](https://github.com/prettier/prettier/issues/18080) | The reported JavaScript example is idempotent and preserves the normalized Babel program. | Source hunks of [PR #20320](https://github.com/prettier/prettier/pull/20320), head `b868f66488e6ad3702f682d63f3eca8763a655da` |

On pinned Prettier commit `bed4edbb1cf2a9db4004215b0ce5707cdb02b5d9`, each frozen issue and public check fails while its corresponding source-only reference passes; two small ordinary-formatting regression controls pass on baseline and reference. These are narrow examples, not complete project acceptance. The normalized tree checks omit locations, raw formatting and comment attachment. In particular, merely retaining `@ts-expect-error` does not prove that its attachment or type-checking effect is preserved.

The #18080 example becomes stable under the same reference patch used for #20307 in the preceding batch; these issues can share a cause and must not be treated as independent evidence. Existing public PRs and issue discussions can expose proposed solutions. The isolated tools, source, paired randomization, solver, 12-turn cap, explicit AI rubric, reviewers, solver-family adjudicator and stop rules follow the [earlier Prettier protocol](production-prospective-agent-batch7-registration.md). The estimated batch target is below $1.50 rather than a hard cap. Failed or missing calls, scores and fees remain visible; no production correctness, savings or autonomous memory-management claim follows.
