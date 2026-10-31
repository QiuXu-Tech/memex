---
title: Post-hoc adjudication of five unresolved AI disagreements
---

# Post-hoc adjudication of five unresolved AI disagreements

**Registered before these five calls.** This follow-up selects five blinded candidate attempts from four earlier issue pairs, each with two format-valid but conflicting AI ratings and a completed, format-invalid prior adjudication. The [manifest](assets/benchmarks/production-prospective-agent-adjudication-v33/manifest.json), SHA-256 `2298d680e123c6173461bcdb599400c86d67a681b9d92c26d408d5b734ec597a`, fixes the source hashes, anonymized packets, selection, randomized order, model and call limit. One candidate also had a completed, format-invalid earlier fallback; that record is included in its source hashes. No timed-out adjudication is replayed. The original ratings, invalid outputs and all earlier fallback records remain separate.

The adjudicator receives only the issue, candidate diff and response, partial checks and the two ratings, without an experimental-arm field. It uses `gpt-6.1-sol`, up to five calls, and a 1,200-token requested output limit. Only explicit HTTP 503 may be retried, at most twice; timeouts are not retried and provider failure or missing usage stops the stage. The expected charge is small but not a hard cap; reported usage and actual billing gaps will be preserved.

This is a post-hoc attempt to recover adjudication coverage, selected after observing failed formats. Distinct AI model names share a proxy with unverified provenance; they are not independent human reviewers. A format-valid opinion does not establish factual accuracy or maintainer acceptance, and no original result is overwritten.
