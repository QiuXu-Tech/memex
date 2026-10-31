---
title: Six additional Prettier issue checks
---

# Six additional Prettier issue checks

**Registered before these task calls and after prior batches and timeouts were observed.** The six issues were open with complete comment snapshots at selection. This is another separate instrumentation batch, not a pre-registered 30–50-task cohort. The [manifest](assets/benchmarks/production-prospective-agent-batch12/manifest.json) has SHA-256 `3b89ecfbd0610ec073bf826ae3d5d0f2f318ab635cc08e1b6c083ab924895eae` and fixes issue snapshots, checks, models and paired random order.

| Issue | Frozen issue criterion | Positive reference used only to validate the check |
| --- | --- | --- |
| [#20174](https://github.com/prettier/prettier/issues/20174) | Both reported TypeScript comment examples produce the stated stable output and preserve the normalized program. | Source hunks of [PR #20213](https://github.com/prettier/prettier/pull/20213), head `b48e15cde58e74418d4eea7f6281d1907977fe03` |
| [#15537](https://github.com/prettier/prettier/issues/15537) | The reported JavaScript expression is idempotent, retains both comments and preserves the normalized program. | Source hunks of [PR #20080](https://github.com/prettier/prettier/pull/20080), head `545827effc19998655f1363546572fc52186cca1` |
| [#17213](https://github.com/prettier/prettier/issues/17213) | The reported TypeScript loop is idempotent, retains the directive immediately before the following expression line, and preserves the normalized program. | Source hunks of [PR #19999](https://github.com/prettier/prettier/pull/19999), head `f2c3d19b86c1aec020e5daa5699ae7e7ecd651ba` |
| [#18066](https://github.com/prettier/prettier/issues/18066) | The reported Markdown list/comment example retains its stated formatting and is idempotent. | Source hunks of [PR #18883](https://github.com/prettier/prettier/pull/18883), head `b57ddf9558c42ed05b976ea7949985b2238e5a43` |
| [#9955](https://github.com/prettier/prettier/issues/9955) | The GraphQL example is idempotent, preserves its parsed document and retains the field comment before the selection set. | The [source-only port](assets/benchmarks/production-prospective-agent-batch11/reference-8182.patch.gz) of [PR #14838](https://github.com/prettier/prettier/pull/14838), head `ed986c4fcded561e6a0e28b20f59730611d13c48` |
| [#9112](https://github.com/prettier/prettier/issues/9112) | The first reported GraphQL query is idempotent, preserves its parsed document and retains both argument comments before the closing parenthesis. | The same source-only port of PR #14838 |

Each frozen issue/public check fails on pinned Prettier commit `bed4edbb1cf2a9db4004215b0ce5707cdb02b5d9` and passes on its source-only reference; two small ordinary-formatting controls pass on both. These narrow tests are not full project acceptance. The normalized program checks omit positions and comment attachment. In particular, #17213 does not run the external ESLint rule or prove that the directive suppresses the intended diagnostic. The three GraphQL issues #8182, #9955 and #9112 share a reference patch and may share a cause; they must not be treated as independent samples.

The restricted VM, 12-turn budget and two randomized pre-seeded contexts follow the [alternate-route protocol](production-prospective-agent-batch11-registration.md). For #20174, #17213 and #9112 both retrieval conditions select the same single comment; these are not long-session memory challenges. Public issue discussions and PRs can disclose proposed solutions.

The solver is `gpt-6.1-sol`, the blinded AI reviewers are `deepseek-flash` and `gpt-6-astra`, and the AI adjudicator is `claude-haiku-4-5`, a third model name chosen after observing the previous adjudication timeout. Model provenance through the proxy is not independently verified and none is a human reviewer. Two earlier Haiku reviews returned empty content; invalid or missing outputs here remain missing. Explicit scoring direction, per-stage stopping and no automatic retry remain as in the prior protocol. The estimated target is below $2, not a hard cap. These tasks do not establish production correctness, savings or autonomous memory management.
