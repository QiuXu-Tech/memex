---
title: Registered long-discussion follow-up, 2026-11-02
layout: default
---

# Registered long-discussion follow-up

This separate 25-task cohort was registered before solver or review calls, after inspecting earlier cohorts. Each issue has at least seven days between creation and the last captured comment, from a distinct repository owner absent from the earlier 60-task cohorts and the initial eight-task integrity follow-up. A discussion time span does not establish continuous work.

The tested Memex commit is `c47e4456451d3e9990be40ce52bfbe6fda6cc7cc`. Public issue snapshots and pinned source archives are retained privately; their SHA-256 hashes and individual acceptance criteria are in the registration. Source revisions can postdate the discussion, and the public material may appear in model training.

[Machine-readable registration](assets/benchmarks/production-long-integrity-20261102/registration.json) · [Frozen review plan](assets/benchmarks/production-long-integrity-20261102/review-plan.json) · [Source selection rejections](assets/benchmarks/production-long-integrity-20261102/source-rejections.json)

| Public issue | Discussion span | Frozen acceptance focus |
| --- | ---: | --- |
| [SBoudrias/Inquirer.js #1783](https://github.com/SBoudrias/Inquirer.js/issues/1783) | 338 days | Explain the select prompt rendering only one option in PowerShell and Git Bash despite working keyboard navigation; distinguish the maintainer’s TTY and shell-environment hypotheses and propose a reproducible terminal check. |
| [actions/checkout #2484](https://github.com/actions/checkout/issues/2484) | 35 days | Explain the intermittent unexpected-end-of-JSON parse during parallel checkout, identify the relevant context input and distinguish a concurrency hypothesis from an established cause. |
| [brianc/node-postgres #3700](https://github.com/brianc/node-postgres/issues/3700) | 102 days | Explain the CJS pg entry resolving pg-protocol as ESM under the Cloudflare/Vite worker-test setup, the packaging/version discussion and an environment-specific reproduction. |
| [chaijs/chai #1728](https://github.com/chaijs/chai/issues/1728) | 33 days | Explain the deprecation warning when inspecting process with truncateThreshold zero, distinguish object-property traversal from an independently confirmed Chai defect, and propose a plain Node reproduction. |
| [grpc/grpc-node #3068](https://github.com/grpc/grpc-node/issues/3068) | 107 days | Explain the reported graceful GOAWAY, keepalive PING and draining RPC interaction, including the discussion separating HTTP/2 peer behavior from Node client session behavior. |
| [jimp-dev/jimp #1402](https://github.com/jimp-dev/jimp/issues/1402) | 186 days | Explain the published 1.6.1 empty browser entry versus a successful local build, its impact on named exports, and a package-contents verification. |
| [less/less.js #4371](https://github.com/less/less.js/issues/4371) | 148 days | Explain the Less parser error on CSS attr(width type(<number>)) and identify a minimal regression that preserves ordinary attr syntax; keep a candidate fix unverified. |
| [nock/nock #2919](https://github.com/nock/nock/issues/2919) | 284 days | Explain the Nock v14 ClientRequest.setTimeout failure, the Axios impact and maintainer discussion of v15 beta, including a minimal native-API verification. |
| [node-red/node-red #5852](https://github.com/node-red/node-red/issues/5852) | 7 days | Explain the first-character loss when replacing selected text in the function editor on Firefox, distinguish the suspected upstream Monaco issue from a confirmed Node-RED root cause, and propose a reproduction. |
| [stylelint/stylelint #9297](https://github.com/stylelint/stylelint/issues/9297) | 29 days | Explain why an embedded root in referenceRoots can be double-counted, how source.input.from absolute-path comparison might identify it, and what to do for unknown paths. |
| [terser/terser #1724](https://github.com/terser/terser/issues/1724) | 58 days | Explain the reported 5.51.0 empty-arrow call regression, the reduce_vars/unused interaction and the 5.51.2 rollback discussion without asserting an unverified fix. |
| [typestack/class-validator #2677](https://github.com/typestack/class-validator/issues/2677) | 157 days | Explain the reported nested validation behavior and the distinction between ValidateNested and IsDefined for missing child properties, with a minimal check. |
| [vitest-dev/vitest #11019](https://github.com/vitest-dev/vitest/issues/11019) | 12 days | Explain the missing --reporter value becoming boolean true and leading to an internal-looking loader error; distinguish the proposed CLI validation from the documentation discussion. |
| [cucumber/cucumber-js #2912](https://github.com/cucumber/cucumber-js/issues/2912) | 23 days | Explain the reported high-parallelism worker startup delay, the staggered-start proposal and the maintainer’s request for profiling before attributing the bottleneck. |
| [nodejs/undici #5500](https://github.com/nodejs/undici/issues/5500) | 86 days | Explain how importing Undici v8 may redirect Node 22 bundled fetch through the global dispatcher and expose a Content-Length validation mismatch; distinguish Undici’s own fetch. |
| [tapjs/tapjs #1049](https://github.com/tapjs/tapjs/issues/1049) | 537 days | Explain the reported workspace module-resolution failure with the TypeScript plugin, distinguish tsc from the ts-node fork, and mention the type-strip-only workaround as reported. |
| [nestjs/nest #13158](https://github.com/nestjs/nest/issues/13158) | 981 days | Explain the buffer-based upload memory concern, configured Readable alternatives, and the compatibility and documentation tradeoffs of changing the default. |
| [helmetjs/helmet #460](https://github.com/helmetjs/helmet/issues/460) | 11 days | Explain the deprecated block-all-mixed-content directive, the maintainer’s legacy-browser reason for retaining it and the requested ability to disable it. |
| [jasmine/jasmine #2075](https://github.com/jasmine/jasmine/issues/2075) | 371 days | Explain the proposed clock operation to advance to the last current timer, including the discussion of timers scheduled during execution and relevant compatibility checks. |
| [mqttjs/MQTT.js #1939](https://github.com/mqttjs/MQTT.js/issues/1939) | 719 days | Explain the reported missing error event for packet/stream errors, distinguish a close event and debug logging from a surfaced error, and propose an isolated check. |
| [google/zx #876](https://github.com/google/zx/issues/876) | 29 days | Explain the reported difference between global process.cwd and zx within-local working-directory state after cd(), and distinguish documented behavior from the proposed implementation change. |
| [mswjs/msw #2635](https://github.com/mswjs/msw/issues/2635) | 251 days | Explain the reported loss of request interception after a hidden tab, the worker inactivity and active-client state discussion, and limitations of reload or reactivation workarounds. |
| [socketio/socket.io #5512](https://github.com/socketio/socket.io/issues/5512) | 122 days | Explain the proposed Standard Schema event contract, the distinction between runtime validation and TypeScript inference, and the tradeoff with an existing userland helper. |
| [webpack/webpack #20536](https://github.com/webpack/webpack/issues/20536) | 229 days | Explain the reported module concatenation bailout with shared parent chunks and identify a focused chunk-graph investigation without treating the speculative processing-order cause as confirmed. |
| [open-telemetry/opentelemetry-js #6816](https://github.com/open-telemetry/opentelemetry-js/issues/6816) | 83 days | Explain the request to supply a clock to instrumentation and the discussion of API scope, propagation and compatibility; distinguish proposals from established behavior. |

## Protocol and limits

Each randomized pair uses two separate Claude Code sessions per arm, in a disposable read-only source environment. Both arms receive the same staged public discussion, repository tools and their own prior handoff; the Memex arm also receives actual Claude hooks and MCP tools. The prompt directs both arms to use targeted lookups and stop searching once the relevant evidence suffices. This prompt was chosen after inspecting earlier execution and before this cohort; it is not a randomized comparison of the prompt change.

Run two tasks first and inspect execution, then the remaining 23. The initial per-session Claude client list-price limit is $0.10, with at most one tool-free continuation using an additional $0.04. The aggregate solver reservation is $9.00 in client list prices, excluding reviewers. Individual API calls can cross a session limit before the client stops; these values are not a hard invoice cap. Missing usage, failures and unrun tasks remain visible.

Two AI models score anonymous outputs using the frozen evidence-ID rubric; material disagreement goes to a third model. Packet labels are randomized and obvious identifiers removed, though wording can still reveal the condition. Publish packet and salted mapping commitments before reviewer calls. AI grading is not human review.

These are compressed historical issue-triage replays, not live production work, completed patches, executable verification, or a production correctness or cost claim. Client list prices differ from gateway wallet charges; machine time, labor and unallocated charges are not assumed to be zero.
