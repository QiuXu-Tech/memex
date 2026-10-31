---
title: Post-outage pilot replication registration
layout: default
---

# Post-outage pilot replication registration

The [first follow-up](production-pilot-followup-registration.md) encountered a gateway outage: four HTTP 503 responses and subsequent network errors resulted in 31 `model_failure` answers and one `continuation_model_failure` among its 60 assigned runs. All outputs and failures remain preserved; no failed call is silently retried. After three separately metered synthetic connectivity checks, this additional replication was planned and registered **after observing the outage** but before its own trial calls. The first cohort remains in the report and its costs are not replaced by this replication.

The replication reuses the exact same 12 frozen historical questions, evidence, fixed arm ordering and task order from the first follow-up. Its private manifest has SHA-256 `c4c6d467c13ef3cfee382d703e966a4fa557c29d0186158f44a84cd466c0d125`, and code is pinned to [`5494768`](https://github.com/QiuXu-Tech/memex/commit/549476890f0741591ad6ae005d77f87220eb438f). Five arms, models, reviewer prompts, budgets and privacy boundaries otherwise match the [first registration](production-pilot-followup-registration.md). Three synthetic checks and all original attempted calls are accounted separately; failed provider calls may still have unreported usage or charges.

The scheduler now stops a shard on a model/runner failure and ceases scheduling further shards after any shard fails; up to two already-running shards may finish. It records attempted results without retries and does not claim the planned 60 runs are complete if stopped early. This failure-containment change does not alter the configured task, answer or review prompts. If the replication completes, both cohorts and their distinct missingness will be reported; this is an outage-triggered rerun of selected historical tasks, not a new independent sample, held-out study, production outcome or basis for statistical significance. The actual invoice and complete costs remain UNKNOWN.
