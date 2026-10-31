---
title: ESLint suggestion task registration
---

# ESLint suggestion task registration

**Registered before these task calls and after earlier outcomes were observed.** [ESLint #21122](https://github.com/eslint/eslint/issues/21122) is open and marked accepted. The [manifest](assets/benchmarks/production-prospective-agent-batch8/manifest.json) has SHA-256 `e5a9a66a85a9218cc68056cb95f0a77bce9651cb185623f8aff38eae13939ce7` and binds the source, input snapshots, isolated tools, checks and paired random order.

The issue-specific check requires strict-null and, where safe, null-or-undefined suggestions for equality and inequality. It checks reversed operands and avoids a compound suggestion when repeating a call, property access, increment or shadowed `undefined` could change behavior. The public check exercises a single suggestion; separate regression controls check existing rule reports and cases that should not be reported. On ESLint commit `12cbff4125db3f6446f72fa0c48c46b92b120427`, the baseline fails the issue and public checks and passes the regression controls. A reference derived from the closed, unmerged [PR #21439](https://github.com/eslint/eslint/pull/21439), head `bc55433a1e95d977affae246b676f04307382235`, passes all three custom checks. This is a positive control, not an accepted upstream fix.

The original five-case upstream rule suite passes on the baseline. On the reference, three cases fail because the test expectations do not declare the newly introduced suggestions; the suite was not silently counted as passing or replaced with modified upstream expectations. The custom rule-reporting controls are partial and cannot establish full regression safety.

The restricted Linux VM, two randomized contexts, `gpt-6-astra` solver, 12-turn limit, `deepseek-flash` and `gpt-6.1-sol` blind AI reviewers, explicit rubric, solver-family adjudication and stopping rules match the [mixed batch protocol](production-prospective-agent-batch6-registration.md). This is one additional issue chosen after prior results. Its history discusses a proposed solution, so leakage or prior exposure is possible. The cost target is below $1 but is not a hard cap. This cannot establish production correctness, cost savings, independent human review or autonomous memory management.
