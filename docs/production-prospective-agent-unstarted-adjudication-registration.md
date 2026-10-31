---
title: Post-hoc review of previously unstarted disagreements
---

# Post-hoc review of previously unstarted disagreements

**Registered after a timeout stopped the original adjudication stage, before these additional AI calls.** In batch 11, five valid reviewer disagreements had no original adjudication request launched after the first timeout. This follow-up selects only those five unstarted items. It does not retry the timed-out request, the three earlier invalid-JSON adjudications, or any completed adjudication. The [manifest](assets/benchmarks/production-prospective-agent-unstarted-adjudication/manifest.json) has SHA-256 `53e0eb0c26eb5c68e817ab37a27fcf86231f2449a7219dd4d79448346b034df8` and binds the selected packets, a new blinded mapping, rubric and runner.

`claude-haiku-4-5` is the new AI adjudicator, a distinct model name from the original batch's solver and reviewers; proxy model provenance is not independently verified. The explicit correctness and side-effect scale is the same direction as the original batch. This model choice and selection occurred after seeing the timeout, so the results are a **post-hoc follow-up**, not the prespecified original adjudications or independent human review. Earlier Haiku reviews returned empty responses; invalid or missing outputs here remain missing.

At most five calls are made, with no automatic retry; after a provider error or missing usage the stage stops launching calls. Original failures, unstarted statuses and possible charges remain in the original ledger. Short public issue histories, potentially exposed solutions, partial checks, model correlation and lack of human assessment limit all conclusions.
