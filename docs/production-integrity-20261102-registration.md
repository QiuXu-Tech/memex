---
title: Registered integrity follow-up, 2026-11-02
layout: default
---

# Registered integrity follow-up

This registration was frozen before solver and review calls. It specifies an initial eight-task follow-up, not a completed 30-task evaluation. The eight open-source issues come from different organizations and were not in the two preceding 30-task triage cohorts. Selection occurred after observing those cohorts, so this is a separately selected follow-up.

[Machine-readable registration](assets/benchmarks/production-integrity-20261102/registration.json) · [Frozen review plan](assets/benchmarks/production-integrity-20261102/review-plan.json)

The compared version is commit `af610afa30a77e56f69bc1379ebd76b66760e6f4`. Issue snapshots and source tarballs are retained privately with the SHA-256 values in the registration. The source revision can postdate the issue discussion, and public issue material may be present in model training.

| Public issue | Frozen acceptance focus |
| --- | --- |
| [avajs/ava #3343](https://github.com/avajs/ava/issues/3343) | Explain the awaited Axios/JSDOM error and reported serialization or reporting failures; distinguish the suggested Concordance cause from a demonstrated cause and propose a diagnostic. |
| [graphql/graphql-js #4834](https://github.com/graphql/graphql-js/issues/4834) | Explain the GraphQL diagnostics channel and Cloudflare Tail Worker structured-cloning report; distinguish successful requests, logging failures, environment-side investigation and the temporary-disable proposal. |
| [hapijs/hapi #4582](https://github.com/hapijs/hapi/issues/4582) | Explain the difference between handler and validator Boom error data, the Joi shared-error mutation discussion, and the fresh-error workaround without declaring an unverified fix. |
| [postcss/postcss #2133](https://github.com/postcss/postcss/issues/2133) | Explain the version-dependent BOM behavior and the distinction between PostCSS preserving an input BOM and bundlers concatenating multiple files; discuss uncertainty about removing internal U+FEFF. |
| [preactjs/preact #4994](https://github.com/preactjs/preact/issues/4994) | Explain the core-versus-compat JSX type mismatch using the SVG property example, and identify a TypeScript check that distinguishes the two configurations. |
| [sequelize/sequelize #18253](https://github.com/sequelize/sequelize/issues/18253) | Explain the requested native UUIDv7 generation, the discussion that UUIDv7 support already exists, and the separate Node/PostgreSQL version and dependency tradeoff. |
| [typicode/json-server #1709](https://github.com/typicode/json-server/issues/1709) | Explain why an array of primitive strings causes the reported id-assignment error, the object-array workaround and its compatibility cost, and a minimal reproduction. |
| [fastify/fastify #6454](https://github.com/fastify/fastify/issues/6454) | Explain the getSchema/addSchema reference or copying performance concern, compare the proposed Symbol and WeakSet approaches, and identify a regression or benchmark needed before claiming improvement. |

Each pair uses separate randomized arm order and two distinct Claude Code sessions per arm in an isolated, disposable repository workspace. Both conditions receive the same issue, staged public discussion, source-reading tools and their own prior handoff; the Memex condition also gets hooks and memory tools. The first two tasks run before the remaining six so infrastructure and budget can be inspected. The 0–2 AI review and evidence-ID rules were frozen separately; failed, empty and unresolved reviews stay missing. Candidate labels are randomized and obvious Memex identifiers are redacted, but wording can still reveal the condition.

The per-session initial client list-price limit is $0.10, with at most one same-session, tool-free continuation using an additional $0.04 after budget exhaustion. The aggregate solver reservation is $4.50 in client list prices; AI review is separate. These figures are not a gateway invoice. Actual charges and missing usage will be reported from available evidence, with unresolved amounts marked unknown.

These are compressed historical triage replays, not shipped patches, a full production benchmark, or evidence of cost savings. The candidate selection, prior results, tool restrictions, continuation protocol, incomplete tasks and later changes must remain visible in the result report.
