---
title: Post-hoc alternate blind reviews after invalid output
---

# Post-hoc alternate blind reviews after invalid output

**Registered before these calls.** Six completed attempts in batches [31](production-prospective-agent-batch31-registration.md) and [32](production-prospective-agent-batch32-registration.md) have a valid DeepSeek rating and a Qwen response that completed but failed the format check. The [manifest](assets/benchmarks/production-prospective-agent-review-v34/manifest.json), SHA-256 `65286818dfddd2188d88369d2dcf68711a72ba453610603fde270f17ce2add26`, freezes the selected attempts, source and anonymized packet hashes, randomized order and model limits. Missing or failed/timeout reviews are excluded; original ratings and failed outputs remain separate.

A new `gpt-6.1-sol` blind review is planned for each of the six attempts. If that review and the original DeepSeek rating are valid but disagree, `gpt-6-astra` is asked to adjudicate. Each stage stops on provider failure or missing usage; only an explicit HTTP 503 can receive bounded retries, never a timeout. Requested output is 1,200 tokens per call, not a hard gateway spending limit. A candidate with a missing or invalid new response remains missing or invalid.

This selection and model substitution are post hoc. The adjudicator has the solver's model label and is not independent of it; all model labels share a proxy with unverified provenance. None is a human reviewer, and format validity is not proof of factual correctness or project acceptance.
