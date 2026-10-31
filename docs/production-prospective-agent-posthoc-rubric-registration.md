---
title: Post-hoc explicit-rubric AI re-review registration
---

# Post-hoc explicit-rubric AI re-review registration

**Registered after observing the initial batch results, but before these re-review calls.** Earlier reviewer prompts specified scores in `0`, `1`, `2` or `null` without defining the direction of the numerical scale. Their original responses and format-validity records remain preserved; their scores must not be pooled or interpreted as a common numerical scale. The separately frozen [re-review manifest](assets/benchmarks/production-prospective-agent-posthoc-rubric/manifest.json) has SHA-256 `fe39b7462fc05e7da2bd6744234aab2eaee4b5b71ddff6235ecd120b4e5a6982`.

This re-review selects the six attempts from batches 1–5 with a nonempty code diff. It does not review unchanged or interrupted attempts and therefore cannot represent all assigned tasks. The candidates receive fresh blinded identifiers; the private manifest binds the packets and mapping by hash while public candidate/result hashes permit identity checks. Blindness is not guaranteed if a candidate's own evidence reveals its experimental condition.

Correctness means: 0 = the change does not resolve the issue or is demonstrably wrong; 1 = partial or plausibly useful but insufficient; 2 = the supplied evidence supports the requested behavior. Side effects mean: 0 = a concrete serious regression is demonstrated; 1 = plausible risk or material uncertainty remains; 2 = no material regression is identified in the supplied evidence. `null` means the evidence does not support a score. These are AI opinions about partial evidence, not maintainer acceptance.

Every candidate is reviewed by `deepseek-flash` and one other AI model distinct from the solver family. For `gpt-6-astra` solver attempts, `gpt-6.1-sol` replaces the earlier `claude-haiku-4-5` reviewer because that earlier route returned empty outputs; for Haiku solver attempts, the second reviewer is `gpt-6-astra`. A disagreement between two valid reviews receives a further AI assessment by the solver model family, so adjudication is not independent human review. Missing, invalid, and failed assessments remain missing. The script stops launching requests within a stage after the first provider error, malformed response, or absent token usage; it does not automatically retry. Usage and fee gaps remain visible.

This is a post-hoc correction and model substitution, not the original planned assessment or a basis for replacing missing original results. Public issue and PR exposure, partial checks, a small selected sample, model correlation, and unverified reviewer reasoning limit interpretation. It cannot establish a production effect or savings.
