---
title: Five distinct-project issue pairs, registered follow-up
---

# Five distinct-project issue pairs — registered follow-up

**Registered before these solver and review calls.** These five currently open issues were not used in the earlier instrumentation batches. Each has a complete nonempty comment snapshot; the keyword and Memex contexts retrieve different comment-ID sets. The snapshots, source commits, checks, randomized paired order, budgets and runner are bound by the [manifest](assets/benchmarks/production-prospective-agent-batch27/manifest.json), SHA-256 `d14c3a849a7583fcefd23bf4169f57046638bd2e0d95b9175616f4a79a930692`. The five repositories are distinct within this batch, but issue identities alone do not establish statistical independence.

| Open issue | Frozen partial acceptance | Proposed source-only reference |
| --- | --- | --- |
| [validator.js #2430](https://github.com/validatorjs/validator.js/issues/2430) | Scientific notation examples including `2e+21` and `-3.5E-8` are accepted; malformed exponents are rejected, and ordinary numeric and `no_symbols` controls remain valid. | [PR #2447](https://github.com/validatorjs/validator.js/pull/2447) |
| [Ramda #2137](https://github.com/ramda/ramda/issues/2137) | `assocPath` preserves own symbol properties on copied outer and nested objects without mutating the input; ordinary nested updates remain valid. | [PR #3506](https://github.com/ramda/ramda/pull/3506) |
| [date-fns #4096](https://github.com/date-fns/date-fns/issues/4096) | French abbreviated month inputs `jan`, `fev` and `aout` parse to the expected months; existing accented and invalid-input controls remain valid. | [PR #4119](https://github.com/date-fns/date-fns/pull/4119) |
| [math.js #3134](https://github.com/josdejong/mathjs/issues/3134) | Comparing 9 °C converted to °F, K or °R against 10 °C preserves ordering, equivalent temperatures compare equal, and ordinary length controls remain valid. | [PR #3705](https://github.com/josdejong/mathjs/pull/3705) |
| [Day.js #2281](https://github.com/iamkun/dayjs/issues/2281) | Lowercase localized formats work for a fixed locale without its own format table; English uppercase and plain-date controls remain valid. The locale is a controlled variant of the reported missing-format case. | [PR #3217](https://github.com/iamkun/dayjs/pull/3217) |

The [qualification ledger](assets/benchmarks/production-prospective-agent-batch27/qualification.json) records assertion failures on each pinned baseline, passes on each source-only reference, and controls passing on both under the network-disabled VM sandbox. The checks are narrow, proposed PRs are not maintainer acceptance, and the date-fns source is loaded with a test-only TypeScript hook. The issue discussions and public PRs can disclose proposed solutions, and can appear in model training.

Each pair uses a randomized arm order and the same bounded search/read/exact-edit/public-test tools. `gpt-6-astra` is the solver; `deepseek-flash` and `qwen3.8-flash` are blinded reviewers, with `gpt-6.1-sol` adjudicating valid score disagreements. These are distinct model **names** behind one proxy, not verified independent model providers or human assessors. The adjudicator was selected after a separate small route probe succeeded, which does not establish future availability. Only explicit HTTP 503 responses may receive at most two bounded retries; other failures and timeouts stop the stage and are retained. The target is below $1 for this batch, an estimate rather than a verified hard cap. Short seeded issue discussions do not establish long-running production effects or autonomous memory management.
