---
title: Four additional ESLint and Prettier task checks
---

# Four additional ESLint and Prettier task checks

**Registered before these task calls and after earlier batches were observed.** These four open issues form a further separate instrumentation batch, not one pre-registered 30–50-task cohort. The [manifest](assets/benchmarks/production-prospective-agent-batch9/manifest.json) has SHA-256 `7122ae66a226c7e402d401b2c65cbf98c0e6e08b4322de0945b017e777de5566` and fixes the source, issue snapshots, checks and paired order.

| Issue | Frozen issue check | Positive reference |
| --- | --- | --- |
| [ESLint #21361](https://github.com/eslint/eslint/issues/21361) | All four reported mismatched function/property names, including astral letters, must be reported. | Source hunks of closed, unmerged [PR #21372](https://github.com/eslint/eslint/pull/21372), head `c5af10174410bdad39fa90a6791ce5c331d7ea82` |
| [ESLint #21422](https://github.com/eslint/eslint/issues/21422) | Five reported `finally` cases reached after break or continue must not be flagged unreachable. | Source hunks of [PR #21426](https://github.com/eslint/eslint/pull/21426), head `776f4137e1ddda457fa25f92a3ae91289dbddd7a` |
| [Prettier #20307](https://github.com/prettier/prettier/issues/20307) | The reported chain formats idempotently at widths 81, 100 and 116 and retains the same normalized Babel program. | Source hunks of [PR #20320](https://github.com/prettier/prettier/pull/20320), head `b868f66488e6ad3702f682d63f3eca8763a655da` |
| [Prettier #20306](https://github.com/prettier/prettier/issues/20306) | The reported delete expression and a second type-comment example are idempotent, retain the type-comment marker and preserve normalized Babel program structure. | Source hunks of [PR #20344](https://github.com/prettier/prettier/pull/20344), head `8204a3307dfb5bb6e0b394a12ef70ca5c9ddc54d` |

Every custom issue check fails on the pinned baseline and passes on its source-only reference, and public examples have the same baseline/reference result. The #21361 original upstream rule suite passes 219/219 cases on baseline and reference; the #21422 `no-unreachable` and `getter-return` rule suites pass 151/151 combined on both. These are selected original suites executed by the recorded harness, not the complete ESLint suite or a full code-path-analysis audit. The Prettier regression checks cover three simple examples each, not the full formatting suite. Normalization deliberately excludes source positions and comment attachment, so the AST comparison does not prove JSDoc semantics or comprehensive formatting safety.

The discussion histories contain only one or two comments. In #20306 both retrieval methods select the same single comment; the arms therefore do not represent a long-session memory challenge. The #21422 issue body itself discusses a possible fix and the maintainer suggests an alternative, and public PRs may be accessible to the models. These factors limit independence and any interpretation of the comparison.

The pinned runtime, isolated tools, two randomized contexts, 12-turn limit, solver, explicit scoring rubric, two blinded AI reviewers, solver-family adjudication and stopping rules follow the [mixed batch protocol](production-prospective-agent-batch6-registration.md). The two ESLint rule suites receive separately staged dependency copies only after solving. The estimated batch target is under $2, not a hard cap. Failed, incomplete and missing results or charges remain visible. These checks cannot establish production correctness, savings, human review, or autonomous memory management.
