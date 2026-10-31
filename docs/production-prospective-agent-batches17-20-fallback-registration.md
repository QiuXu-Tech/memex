---
title: Alternate AI adjudications for batches 17–20
---

# Alternate AI adjudications for batches 17–20

**Registered after observing the original responses, before these additional calls.** Twelve candidates from batches 17–20 have two format-valid but different original AI ratings and a completed, format-invalid Gemini adjudication. Only those twelve are selected; failed or timed-out adjudications and missing reviews are not retried. The re-blinded packets and original source hashes are bound in the [manifest](assets/benchmarks/production-prospective-agent-batches17-20-fallback/manifest.json), SHA-256 `2d84a2dab8b47891560ed2ea710333d474407dea0dea8e57efb16581ebf6e07c`.

The supplementary adjudicator is `gpt-6-astra`, with at most 1,200 output tokens and twelve logical calls. Only explicit 503 may be retried, at most twice; timeouts are not retried and provider failure or missing usage stops the stage. Original invalid Gemini outputs remain invalid and unchanged. Any missing or invalid supplementary result also stays visible.

The alternate model and selection were chosen after the failures. The adjudicator shares the solver's model name and all AI names use one proxy with unverified provenance, so this is **not independent human adjudication**. Format validity checks the schema and allowed reference labels, not factual support, maintainer acceptance, production effects or savings.
