---
title: Alternate AI adjudication for batch 16 disagreements
---

# Alternate AI adjudication for batch 16 disagreements

**Registered after observing the original and budgeted failures, before these calls.** Five candidates have two valid, different scores after the original reviews and the separately registered Qwen replacements. Each has an invalid budgeted Gemini adjudication. These five packets are re-blinded and bound by hashes in the [manifest](assets/benchmarks/production-prospective-agent-batch16-fallback/manifest.json), SHA-256 `8e0ffce9cc0678ff5140d820f3ecabe1b03dbe6aaa08e952a04d68e4e05b458c`.

The supplementary adjudicator is `gpt-6-astra`, at most 1,200 output tokens and five logical calls. The 503-only bounded retry policy applies; timeouts are not retried, and provider failure or missing usage stops further calls in this stage. Original and budgeted Gemini outcomes stay invalid and are never overwritten.

This model has the same name as the solver and all models use the same proxy with unverified provenance: **this is not independent human adjudication**. Candidate selection and model replacement are post-hoc. Format-valid output only satisfies schema and reference-label checks, not factual or project-level acceptance.
