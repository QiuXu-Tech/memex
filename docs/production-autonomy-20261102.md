---
title: Cross-session memory and real-issue triage, 2026-11-02
layout: default
---

# Cross-session memory and real-issue triage

**IN PROGRESS.** This page is a dated snapshot, not evidence of a production correctness gain or cost saving. The tasks are real public issues, but their historical discussions were replayed in compressed sessions as source-backed triage; agents did not ship changes, and AI judges are not human reviewers. Snapshot: `2026-11-01T18:13:37.192363+00:00`.

[Machine-readable results](assets/benchmarks/production-autonomy-20261102/results.json) · [Calibration ledger](assets/benchmarks/production-autonomy-20261102/calibrations.json) · [Original 30-task registration](assets/benchmarks/production-autonomy-20261102/triage30-registration.json) · [Original review plan and evidence correction](assets/benchmarks/production-autonomy-20261102/triage30-review-plan-metadata-revision.json) · [Supplemental 30-task registration](assets/benchmarks/production-autonomy-20261102/supplement-triage-registration.json) · [Supplemental review plan](assets/benchmarks/production-autonomy-20261102/supplement-triage-review-plan-final.json)

![Task completion, AI review, token use and observed memory actions](assets/benchmarks/production-autonomy-20261102/autonomy-summary.svg)

## What changed

- Claude Code's installed hook event names now dispatch correctly. `Stop` checkpoints completed assistant responses without another model call, marks them untrusted, skips generic refusals and certain credential-like strings, and deduplicates identical outputs in the same client session. The filter is not a comprehensive secret detector.
- A stable L2 namespace no longer causes the current-session filter to hide checkpoints from other Claude sessions. Session startup injects a short notice instead of repeating the same titles later in recall; relevant previews remain available on matching prompts.
- The isolated pilot bridge accepts larger read windows, supports multiword same-file search with an explicit fallback label, and summarizes repeated reads and search snippets while retaining an explicit refresh option. The later recovery protocol permits one tool-free continuation of the **same** session after budget exhaustion; the next stage remains a distinct session.
- A further MCP change, evaluated in the separate recovery cohort, marks agent-written MCP records untrusted and shows bounded summaries and trust metadata in search/open results. Existing records are not relabeled. The label is not a fact checker. The original cohort used the earlier frozen version; do not attribute this later change to it.
- Reviewer parsing rejects missing scores, invalid evidence IDs, empty output and truncation. A review canary exposed omitted comment authors and dates in the anonymous packet; those public fields were restored before cohort ratings. A Gemini adjudication first truncated; a separately recorded low-effort retry completed. Both the failure and correction are retained.

## Frozen real-issue replays

| Protocol | Registered | Started | Finished | Complete paired two-session tasks | Valid AI-rated pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original | 30 | 30 | 30 | 10 | 5 |
| Supplemental recovery | 30 | 17 | 15 | 15 | 0 |

Each task has its own pinned public source revision, issue snapshot hash, issue-specific criteria and randomized arm order. Both arms receive the same issue, staged comments, read-only source tools and their own searchable prior handoffs. The Memex arm additionally receives actual Claude Code hooks and memory tools. A completed pair requires two successful, distinct client sessions in each arm. Failures, tool errors, incomplete sessions and unstarted tasks remain in the results.

The recovery cohort was selected and registered **after** observing budget exhaustion in the first cohort. It uses lower initial budgets, one tool-free same-session finalization when the initial budget is exhausted, the later MCP trust change and a revised pilot bridge. Treat the two cohorts separately; an observed difference between them is not a randomized comparison of those protocol changes.

- **Original:** 5 rated pairs; control higher 3, tie 2, Memex higher 0. Mean score, control / Memex: 1.20 / 0.60 on the 0–2 rubric.
- **Supplemental recovery:** no fully adjudicated pair is available in this snapshot.

Scores assess the supplied triage evidence against the frozen 0–2 rubric; they do not establish that a patch works, an issue is resolved, or a production task is correct. Reviewers are GPT-6.1 Sol and DeepSeek Flash; material disagreements are sent to Gemini Flash when both initial reviews are valid. An absent, truncated, invalid or unresolved review stays missing.

The original cohort also has a **post-hoc sensitivity view** of 10 rated pairs: control higher 4, tie 4, Memex higher 2. This supplements the original primary view; it includes deterministic revalidation where judges cited a visible `limits` field, a different-model replacement after one timeout, and a separately registered retry of a malformed adjudication. The initial outcomes remain in the JSON. [Reference correction](assets/benchmarks/production-autonomy-20261102/triage30-limits-revalidation-registration.json) · [Reviewer rescue](assets/benchmarks/production-autonomy-20261102/triage30-review-rescue-registration.json)

## Memory behavior and cost

Across all started tasks, the original cohort has **18** tasks with an observed successful agent `memory_write`; **14** have an agent-written record explicitly opened in the next session. The Stop hook saved a first-session checkpoint in **17** tasks, and a checkpoint was opened in the next session in **15**. For the supplemental cohort, those corresponding counts are **2**, **0**, **16**, and **16**. These are observed operations, not proof that the content was correct or necessary; categories overlap.

In the 10 original-protocol complete pairs with reported usage, control used 1,741,774 input tokens and Memex 2,173,899 (+24.8%). Input totals include uncached, cache-read and cache-creation tokens, following [Anthropic's usage definition](https://platform.claude.com/docs/en/build-with-claude/prompt-caching). Output tokens are reported separately in the JSON. In recovered sessions, individual attempt usage is retained, but a full session total is **UNKNOWN** when the client may omit usage from a budget-failed request; zero is not substituted.

In the original 10 complete pairs, the control / Memex arms made **264 / 231** tool attempts, of which **2 / 2** repeated the identical tool and arguments within a single session. Overlapping source ranges and semantically repeated searches are not included in that narrow count. Fewer attempts alongside more input tokens does not by itself identify the cause: repeated context, cache traffic and output size require separate investigation.

The reported Claude client list-price totals for completed and failed session attempts are **$7.0025** for the original cohort and **$4.2815** for the supplemental cohort; sessions with missing client costs: **0** and **0** respectively. These figures are not APIMaster wallet charges and exclude the separate canaries, reviewers, machine time and labor. Gateway attribution and any missing fees are not assumed to be zero.

The following reviewer usage is reported by the gateway for terminal attempts with complete usage; failed or usage-missing attempts remain a separate gap. It is not a dollar invoice.

| Cohort | Model | Attempts | Known prompt tokens | Known output tokens | Failed or usage missing |
| --- | --- | ---: | ---: | ---: | ---: |
| Original | gpt-6.1-sol | 10 | 164,754 | 5,098 | 1 |
| Original | deepseek-flash | 10 | 125,041 | 3,909 | 0 |
| Original | gemini-3.8-flash | 11 | 165,259 | 5,046 | 0 |
| Original | gpt-6.1-terra | 1 | 10,589 | 373 | 0 |
| Supplemental | Pending | 0 | 0 | 0 | 0 |

## Retained calibration failures

The initial synthetic hook smoke was contaminated by inherited stdin and failed. A second clean-input attempt failed because the model did not repeat the supplied fact in its answer; a third, clearer synthetic attempt succeeded across two processes. These are mechanism checks, not independent real tasks. [Initial registration](assets/benchmarks/production-autonomy-20261102/hook-smoke-registration.json) · [First retry](assets/benchmarks/production-autonomy-20261102/hook-smoke-retry-registration.json) · [Clarified retry](assets/benchmarks/production-autonomy-20261102/hook-smoke-clarified-registration.json) · [MCP trust smoke](assets/benchmarks/production-autonomy-20261102/mcp-trust-smoke-registration.json)

The new [Axios #6690](https://github.com/axios/axios/issues/6690) calibration reproduced the read-only inherited `toJSON` failure, while a separate inherited-setter regression check passed initially. Both original arms and both separately registered retries exhausted their first-session budgets without a final patch. Their AI reviews scored only the missing artifacts; this cannot compare solving ability. [Registration and fixed criteria](assets/benchmarks/production-autonomy-20261102/axios-6690-registration.json) · [Post-hoc retry registration](assets/benchmarks/production-autonomy-20261102/axios-6690-retry-registration.json) · [Blind packet](assets/benchmarks/production-autonomy-20261102/axios-6690-blind-packet.json)

This report will be refreshed from the same retained evidence as the registered work completes. An absent result is not a zero-cost success.
