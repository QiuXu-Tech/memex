---
title: Two batch 17 reviews never started, registered follow-up
---

# Two batch 17 reviews never started — registered follow-up

**Registered after the original batch and before these follow-up calls.** The original review stage stopped after a timeout on B04. Its log and output inventory show that neither reviewer started on B05 or B06. Both candidates completed, and each is re-blinded before the two original reviewer model names are asked to assess it. The [manifest](assets/benchmarks/production-prospective-agent-batch17-unstarted-reviews/manifest.json), SHA-256 `b231744bfc0a66a0723141dd5776eea438fc6884a733911479fd29c5732107c1`, binds the original call log, candidate inputs, blinded packets and runner.

There are at most four review calls and, if the two valid ratings disagree, at most two Astra adjudications. The gateway can retry an explicit HTTP 503 at most twice; any other provider failure or missing usage stops that stage. **The timed-out B04 request is not retried.** The requested output limits are not verified hard cost caps. Every attempt and unknown fee will be preserved.

These are post-hoc, separately selected follow-up reviews. Original unstarted and failed outcomes remain unchanged. Astra has the solver model name and is not independent of it; all model names share a proxy with unverified provenance. A format-valid score checks the schema and reference labels, not factual correctness or maintainer acceptance. This follow-up cannot turn the adaptive short-history issue batches into an independent production study.
