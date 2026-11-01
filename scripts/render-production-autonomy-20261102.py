#!/usr/bin/env python3
"""Render a dated report from the sanitized, reconciled evaluation snapshot."""
import json,pathlib
root=pathlib.Path(__file__).resolve().parent.parent
f=root/'docs/assets/benchmarks/production-autonomy-20261102/results.json';d=json.loads(f.read_text());a=d['original'];b=d['supplement']
def fmtrow(label,x):
 return f"| {label} | {x['registered']} | {x['started']} | {x['finished']} | {x['completePairs']} | {x['validRatedPairs']} |"
def scoreline(label,x):
 n=x['validRatedPairs'];v=x['scoreDirections']
 if not n:return f"- **{label}:** no fully adjudicated pair is available in this snapshot."
 return f"- **{label}:** {n} rated pairs; control higher {v.get('baselineHigher',0)}, tie {v.get('tie',0)}, Memex higher {v.get('memexHigher',0)}. Mean score, control / Memex: {x['meanScore']['baseline']:.2f} / {x['meanScore']['memex']:.2f} on the 0–2 rubric."
def usage_rows(label,x):
 return '\n'.join(f"| {label} | {model} | {u['calls']} | {u['promptTokens']:,} | {u['completionTokens']:,} | {u['missingUsageOrFailedAttempts']} |" for model,u in x.get('reviewUsageByModel',{}).items()) or f'| {label} | Pending | 0 | 0 | 0 | 0 |'
n=a['fullTokenPairs'];base=a['tokenTotals']['baseline']['input'];mem=a['tokenTotals']['memex']['input']
tokens=(f"In the {n} original-protocol complete pairs with reported usage, control used {base:,} input tokens and Memex {mem:,} ({(mem/base-1)*100:+.1f}%)." if n and base else 'No complete original-protocol pairs have comparable input-token totals yet.')
status='IN PROGRESS' if any(x['status']!='FINISHED' or x.get('reviewStatus')!='FINISHED' for x in (a,b)) else 'RUNS FINISHED; GAPS AND POST-HOC REVIEWS SHOWN BELOW'
text=f'''---
title: Cross-session memory and real-issue triage, 2026-11-02
layout: default
---

# Cross-session memory and real-issue triage

**{status}.** This page is a dated snapshot, not evidence of a production correctness gain or cost saving. The tasks are real public issues, but their historical discussions were replayed in compressed sessions as source-backed triage; agents did not ship changes, and AI judges are not human reviewers. Snapshot: `{d['generatedAt']}`.

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
{fmtrow('Original',a)}
{fmtrow('Supplemental recovery',b)}

Each task has its own pinned public source revision, issue snapshot hash, issue-specific criteria and randomized arm order. Both arms receive the same issue, staged comments, read-only source tools and their own searchable prior handoffs. The Memex arm additionally receives actual Claude Code hooks and memory tools. A completed pair requires two successful, distinct client sessions in each arm. Failures, tool errors, incomplete sessions and unstarted tasks remain in the results.

The recovery cohort was selected and registered **after** observing budget exhaustion in the first cohort. It uses lower initial budgets, one tool-free same-session finalization when the initial budget is exhausted, the later MCP trust change and a revised pilot bridge. Treat the two cohorts separately; an observed difference between them is not a randomized comparison of those protocol changes.

{scoreline('Original',a)}
{scoreline('Supplemental recovery',b)}

Scores assess the supplied triage evidence against the frozen 0–2 rubric; they do not establish that a patch works, an issue is resolved, or a production task is correct. Reviewers are GPT-6.1 Sol and DeepSeek Flash; material disagreements are sent to Gemini Flash when both initial reviews are valid. An absent, truncated, invalid or unresolved review stays missing.

The original cohort also has a **post-hoc sensitivity view** of {a['posthocSensitivityRatedPairs']} rated pairs: control higher {a['posthocSensitivityDirections'].get('baselineHigher',0)}, tie {a['posthocSensitivityDirections'].get('tie',0)}, Memex higher {a['posthocSensitivityDirections'].get('memexHigher',0)}. This supplements the original primary view; it includes deterministic revalidation where judges cited a visible `limits` field, a different-model replacement after one timeout, and a separately registered retry of a malformed adjudication. The initial outcomes remain in the JSON. [Reference correction](assets/benchmarks/production-autonomy-20261102/triage30-limits-revalidation-registration.json) · [Reviewer rescue](assets/benchmarks/production-autonomy-20261102/triage30-review-rescue-registration.json)

## Memory behavior and cost

Across all started tasks, the original cohort has **{a['agentWrites']}** tasks with an observed successful agent `memory_write`; **{a['writtenRecordOpenedNext']}** have an agent-written record explicitly opened in the next session. The Stop hook saved a first-session checkpoint in **{a['automaticCheckpoints']}** tasks, and a checkpoint was opened in the next session in **{a['automaticCheckpointOpenedNext']}**. For the supplemental cohort, those corresponding counts are **{b['agentWrites']}**, **{b['writtenRecordOpenedNext']}**, **{b['automaticCheckpoints']}**, and **{b['automaticCheckpointOpenedNext']}**. These are observed operations, not proof that the content was correct or necessary; categories overlap.

{tokens} Input totals include uncached, cache-read and cache-creation tokens, following [Anthropic's usage definition](https://platform.claude.com/docs/en/build-with-claude/prompt-caching). Output tokens are reported separately in the JSON. In recovered sessions, individual attempt usage is retained, but a full session total is **UNKNOWN** when the client may omit usage from a budget-failed request; zero is not substituted.

The reported Claude client list-price totals for completed and failed session attempts are **${a['clientListPriceKnownUsd']:.4f}** for the original cohort and **${b['clientListPriceKnownUsd']:.4f}** for the supplemental cohort; sessions with missing client costs: **{a['clientListPriceMissingSessions']}** and **{b['clientListPriceMissingSessions']}** respectively. These figures are not APIMaster wallet charges and exclude the separate canaries, reviewers, machine time and labor. Gateway attribution and any missing fees are not assumed to be zero.

The following reviewer usage is reported by the gateway for terminal attempts with complete usage; failed or usage-missing attempts remain a separate gap. It is not a dollar invoice.

| Cohort | Model | Attempts | Known prompt tokens | Known output tokens | Failed or usage missing |
| --- | --- | ---: | ---: | ---: | ---: |
{usage_rows('Original',a)}
{usage_rows('Supplemental',b)}

## Retained calibration failures

The initial synthetic hook smoke was contaminated by inherited stdin and failed. A second clean-input attempt failed because the model did not repeat the supplied fact in its answer; a third, clearer synthetic attempt succeeded across two processes. These are mechanism checks, not independent real tasks. [Initial registration](assets/benchmarks/production-autonomy-20261102/hook-smoke-registration.json) · [First retry](assets/benchmarks/production-autonomy-20261102/hook-smoke-retry-registration.json) · [Clarified retry](assets/benchmarks/production-autonomy-20261102/hook-smoke-clarified-registration.json) · [MCP trust smoke](assets/benchmarks/production-autonomy-20261102/mcp-trust-smoke-registration.json)

The new [Axios #6690](https://github.com/axios/axios/issues/6690) calibration reproduced the read-only inherited `toJSON` failure, while a separate inherited-setter regression check passed initially. Both original arms and both separately registered retries exhausted their first-session budgets without a final patch. Their AI reviews scored only the missing artifacts; this cannot compare solving ability. [Registration and fixed criteria](assets/benchmarks/production-autonomy-20261102/axios-6690-registration.json) · [Post-hoc retry registration](assets/benchmarks/production-autonomy-20261102/axios-6690-retry-registration.json) · [Blind packet](assets/benchmarks/production-autonomy-20261102/axios-6690-blind-packet.json)

This report will be refreshed from the same retained evidence as the registered work completes. An absent result is not a zero-cost success.
'''
(root/'docs/production-autonomy-20261102.md').write_text(text)
readme=root/'README.md';s=readme.read_text();start='<!-- autonomy20261102:start -->';end='<!-- autonomy20261102:end -->'
block=f"{start}\n**Cross-session follow-up (2026-11-02; {status.lower()}):** Real public issues are being replayed in two separately registered, randomized Claude Code cohorts. At this snapshot, {a['completePairs']}/30 original and {b['completePairs']}/30 recovery-protocol pairs completed both sessions; blinded AI review is reported separately. Automatic and agent-initiated writes are distinguished, and missing usage is retained. [Results and limitations](docs/production-autonomy-20261102.md).\n\n![Cross-session issue replay progress](docs/assets/benchmarks/production-autonomy-20261102/autonomy-summary.svg)\n{end}"
if start in s and end in s:s=s[:s.index(start)]+block+s[s.index(end)+len(end):]
else:
 marker='## Prospective engineering canary (2026-10-31)'
 assert marker in s;s=s.replace(marker,block+'\n\n'+marker,1)
readme.write_text(s)
index=root/'docs/index.md';s=index.read_text();entry='- [Cross-session memory and issue triage (2026-11-02)](production-autonomy-20261102.html) — real-issue replay, agent and hook writes, blinded AI review, usage gaps and retained failures.\n'
if entry not in s:
 anchor='- [Agent memory overhead and three-session issue replay]';i=s.index(anchor);s=s[:i]+entry+s[i:]
index.write_text(s)
print('rendered',root/'docs/production-autonomy-20261102.md')
