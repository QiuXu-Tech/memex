---
title: Previously unstarted Chart.js pair, registered follow-up
---

# Previously unstarted Chart.js pair — registered follow-up

**Registered after a transport failure, before these new calls.** Batch 25 stopped after a solver connection error in a different issue. Both assignments for [Chart.js #12191](https://github.com/chartjs/Chart.js/issues/12191) were recorded `NOT_RUN_AFTER_STOP`; the selection check confirms neither slot has a solver-call start. The [new manifest](assets/benchmarks/production-prospective-agent-batch26/manifest.json), SHA-256 `b93eee9f75f63e37db0b609b63f73ab47f452911629565474c18c0f8e236cae4`, binds the previous manifest and solver-log hashes, unstarted result hashes, unchanged checks and a newly randomized arm order. The failed request in batch 25 is not retried, and all original statuses remain visible.

The same source, test-only TypeScript hook, dependency lock, narrow mocked-controller checks, AI rubric, solver, reviewers, non-independent adjudicator and 503-only retry policy follow the [original registration](production-prospective-agent-batch25-registration.md). Stop the stage after provider failure or missing usage; do not retry timeouts. A new three-model short-request health probe succeeded after the transport error, which does not establish long-request reliability.

This is one **previously unstarted issue**, not an additional distinct issue. It has no historical discussion records, so both conditions receive different empty-result messages and cannot demonstrate a memory effect. Selection after failure, source disclosure, partial tests and common-proxy AI limit inference. Estimated model-call target is below $1, not a hard cap; unknown charges remain unknown.
