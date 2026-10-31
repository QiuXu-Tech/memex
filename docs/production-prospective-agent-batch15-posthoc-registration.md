---
title: Post-hoc blinded re-review of batch 15
---

# Post-hoc blinded re-review of batch 15

**Registered after observing the original reviews, before these additional model calls.** All three reviewable batch 15 candidates had a format-valid DeepSeek review and an empty or truncated Haiku response. The fourth attempt had neither a final answer nor a code diff and remains unreviewable. This follow-up re-blinds the three candidates and asks **both** DeepSeek and Qwen to review them again; Gemini will adjudicate any format-valid disagreements. The [manifest](assets/benchmarks/production-prospective-agent-batch15-posthoc/manifest.json), SHA-256 `e5146b1fcb9ab470671b85df2e67acc7a017c7aa5e4c8d5e317799c22adb504c`, binds the original review hashes, copied candidate results, issue and context snapshots, runner and scoring rubric.

The original valid and invalid ratings remain unchanged. This model replacement and candidate selection were chosen after seeing the failures, so these ratings are post-hoc observations and must not be substituted for the original planned ratings. Repeated DeepSeek reviews are separate calls, not independent human judgments. Qwen and Gemini each returned a format-valid response in a separate synthetic probe under the existing rubric parser; Gemini included Markdown fences accepted by that parser. All model names use the same proxy and their provenance is unverified.

The explicit rubric and bounded 503-only retry policy are inherited from the [batch 15 registration](production-prospective-agent-batch15-registration.md). There are at most six logical review calls and three logical adjudication calls, with at most two additional attempts per call after explicit 503s. Timeouts are not automatically retried. Missing, invalid and failed calls and unknown charges remain visible. The short public histories and partial checks do not establish production effects or savings.
