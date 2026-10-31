---
title: Post-hoc AI review citation normalization
---

# Post-hoc AI review citation normalization

**Added after the initial review responses were observed.** In the [three-issue instrumentation batch](production-prospective-agent-batch1-registration.md), two of four returned AI reviews failed the predeclared reference-label schema. The original evaluations and their invalid statuses are retained. The registered adjudication therefore found no pair with two valid scores and made no call.

For an explicitly separate post-hoc analysis, a deterministic formatter accepts only exact known evidence labels, labels explicitly followed by a colon and explanation, and the aliases `candidateDiff` → `candidate`, `acceptance` → `checks`, and `upstreamRegression` → `checks`. Unknown labels, malformed JSON, truncated output and invalid scores remain invalid. Other fields and original responses are preserved. This recovers two format-invalid outputs; **it does not establish that any citation supports its claim** and does not retroactively make the original schema-validity rate four of four.

The frozen [post-hoc manifest](assets/benchmarks/production-prospective-agent-batch1/posthoc-manifest.json) has SHA-256 `56b405c486f96f762c5511788df7d8f54b42d79a834ffe83c9e899035127209f`. After normalization, one pair disagrees on side-effect risk and is eligible for one additional AI adjudication. The adjudicator uses the solver's model family; it is neither independent human review nor proof of correctness. This decision and any resulting call are reported separately from the original registered analysis.
