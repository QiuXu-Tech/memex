---
title: Six Day.js issues, registered instrumentation
---

# Six Day.js issues — registered instrumentation

**Registered before these solver and review calls.** Six previously unattempted, open Day.js issues were selected and their snapshots, checks and randomized paired order were fixed in the [manifest](assets/benchmarks/production-prospective-agent-batch16/manifest.json), SHA-256 `2bd9efc67fe7970be5df882a0a2f3382dde495342b895249943a553566ba1c4d`. Selection followed observations from previous batches; this is not a single pre-registered 30–50-task cohort. The issue states and complete comment counts were rechecked before registration.

| Issue | Frozen acceptance | Reference source patch |
| --- | --- | --- |
| [#2951](https://github.com/iamkun/dayjs/issues/2951) | Saudi Arabic noon at 12:00 and 12:41 uses the PM marker; controls cover midnight, 11, 13, 23 and English. | [PR #2952](https://github.com/iamkun/dayjs/pull/2952) |
| [#2479](https://github.com/iamkun/dayjs/issues/2479) | Adding one- and two-week duration objects advances the date; controls cover day durations and ordinary week addition. | Related [PR #2583](https://github.com/iamkun/dayjs/pull/2583), also discussed in the issue |
| [#2956](https://github.com/iamkun/dayjs/issues/2956) | Custom singular relative-time labels show either one month or 28 days, and either one year or 15 months, for the fixed inputs; controls exercise default English labels. | [PR #3221](https://github.com/iamkun/dayjs/pull/3221) |
| [#1271](https://github.com/iamkun/dayjs/issues/1271) | Day addition across the specified London and New York DST transitions resolves to the expected local date/offset; controls cover a non-DST day and UTC. | [PR #3252](https://github.com/iamkun/dayjs/pull/3252), which also references related issues |
| [#1923](https://github.com/iamkun/dayjs/issues/1923) | ISO fractional seconds `.5`, `.05`, and `.005` parse as 500, 50, and 5 milliseconds; controls cover three digits and a UTC suffix. | [PR #1936](https://github.com/iamkun/dayjs/pull/1936) |
| [#2511](https://github.com/iamkun/dayjs/issues/2511) | Russian genitive December dates retain the stated year for two inputs; controls cover January and November. | [PR #2942](https://github.com/iamkun/dayjs/pull/2942), which also references related issues |

For each issue, the public and acceptance checks fail on Day.js `436bde0bcded312781cbe45dc2b0ef079a36d8e3`, pass on the source-only reference, and the small controls pass on both. The [qualification ledger](assets/benchmarks/production-prospective-agent-batch16/qualification.json) records the reference commit, patch and private-log hashes. These are narrow checks, not full project tests or maintainer acceptance. Node 24.18.0 loads source ESM through a fixed test-only module hook, without external npm packages; this is not the compiled npm distribution. The issues touch different functional areas but share a project, and references identify related issues, so independence cannot be guaranteed. Public PRs and comments may expose solutions.

The solver is `gpt-6-astra`; the blinded AI reviewers are `deepseek-flash` and `qwen3.8-flash`; `gemini-3.8-flash` adjudicates format-valid disagreements. The reviewer change follows empty Haiku results in the preceding pilot. Small synthetic Qwen and Gemini review-format probes succeeded under the registered rubric parser, but do not establish reliability. These model names use the same proxy, with provenance unverified, and are not human review. Context lengths differ between conditions; the pre-seeded public issue histories are not real long-running production sessions.

The VM, bounded tools, explicit rubric, 12-turn solver budget and 503-only retry policy follow the [gateway-recovery registration](production-prospective-agent-batch15-registration.md). At most two retries follow an explicit 503; timeouts are not automatically retried, and every attempt and missing usage remains in the ledger. The model-call cost target for this batch is below $2, an estimate rather than a hard cap. No production-effect, savings or autonomous-memory claim follows from this registration.
