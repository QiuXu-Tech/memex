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
if n:
 bt=a['tokenTotals']['baseline'];mt=a['tokenTotals']['memex']
 cache_read=mt['cacheRead']-bt['cacheRead'];cache_write=mt['cacheWrite']-bt['cacheWrite']
 tokens+=f" The difference comprises {cache_read:+,} cache-read, {cache_write:+,} cache-creation and {mem-base-cache_read-cache_write:+,} uncached input tokens; token counts are not wallet charges."
prices=a['completePairClientListPriceUsd'];pa=prices['baseline'];pm=prices['memex']
paired_price=(f"For those {a['completePairs']} complete original pairs, client list prices were ${pa:.4f} control and ${pm:.4f} Memex ({(pm/pa-1)*100:+.1f}%)." if pa and pm is not None else 'A complete original-pair list-price comparison is unavailable.')
bc=a['completeTokenPairMessageContexts']['baseline'];mc=a['completeTokenPairMessageContexts']['memex']
context_note=(f"Those input totals reconcile to {bc['messageIds']} / {mc['messageIds']} distinct assistant message IDs, averaging {bc['inputTokens']/bc['messageIds']:,.0f} / {mc['inputTokens']/mc['messageIds']:,.0f} input tokens per message. This points to larger per-message context in this sample, but does not isolate which context component caused it." if bc and mc else 'Per-message context counts could not be reconciled to the full reported input totals.')
bf=a['completeTokenPairFirstSessionInitialContexts']['baseline'];mf=a['completeTokenPairFirstSessionInitialContexts']['memex']
if bf and mf:context_note+=f" Before any model tool result in the first session, the first assistant messages averaged {bf['inputTokens']/bf['sessions']:,.0f} / {mf['inputTokens']/mf['sessions']:,.0f} input tokens (control / Memex). Tool schemas, hooks and other initial context differ, so this does not isolate one cause."
status='IN PROGRESS' if any(x['status']!='FINISHED' or x.get('reviewStatus')!='FINISHED' for x in (a,b)) else 'RUNS FINISHED; GAPS AND POST-HOC REVIEWS SHOWN BELOW'
closing=('The retained records preserve incomplete results and unknown charges; an absent result is not a zero-cost success.' if status.startswith('RUNS FINISHED') else 'This report will be refreshed from the same retained evidence as the registered work completes. An absent result is not a zero-cost success.')
asset=root/'docs/assets/benchmarks/production-autonomy-20261102'
commitments=(' · [Supplemental blind packet commitments](assets/benchmarks/production-autonomy-20261102/supplement-triage-packet-commitments.json)' if (asset/'supplement-triage-packet-commitments.json').exists() else '')
if (asset/'supplement-triage-packet-unblinding.json').exists():commitments+=' · [Post-review unblinding](assets/benchmarks/production-autonomy-20261102/supplement-triage-packet-unblinding.json)'
billing_path=asset/'supplement-review-cost-reconciliation.json'
billing=json.loads(billing_path.read_text()) if billing_path.exists() else None
billing_note=(f"For supplemental reviews and post-hoc rescue, {billing['matchedCalls']}/{billing['successfulCalls']} successful calls uniquely matched visible wallet rows by model, input/output tokens and finish time (within three seconds); displayed amounts sum to **${billing['displayedWalletUsd']:.6f}**. This is a heuristic match, not request-ID proof or the entire study cost. The two timed-out calls and solver charges remain unallocated. [Per-call reconciliation](assets/benchmarks/production-autonomy-20261102/supplement-review-cost-reconciliation.json)." if billing else 'Gateway wallet costs for review calls have not yet been reconciled.')
canary_path=asset/'discussion-recall-canary-results.json'
canary=json.loads(canary_path.read_text()) if canary_path.exists() else None
if canary:
 old_open=sum(t['originalMemexLaterDiscussion']['openedLaterComment'] for t in canary['tasks'])
 new_open=sum(t['arms']['memex']['laterDiscussion']['openedLaterComment'] for t in canary['tasks'])
 canary_note=f"After the recall-notice change, a separately registered follow-up replayed two deliberately selected issues that had previously claimed no discussion. Their Memex second sessions opened a later-stage comment in **{old_open}/2 before and {new_open}/2 on the follow-up**. One still did not open later discussion; this does not establish a reliable fix or generalize beyond the selected cases. The new answers were not subjected to another blind quality review. Its Claude client list price was **${canary['clientListPriceUsd']:.6f}**, not an allocated gateway charge. [Registration](assets/benchmarks/production-autonomy-20261102/discussion-recall-canary-registration.json) · [Results](assets/benchmarks/production-autonomy-20261102/discussion-recall-canary-results.json)."
else:canary_note='A separately registered two-issue discussion-recall follow-up is pending.'
text=f'''---
title: Cross-session memory and real-issue triage, 2026-11-02
layout: default
---

# Cross-session memory and real-issue triage

**{status}.** This page is a dated snapshot, not evidence of a production correctness gain or cost saving. The tasks are real public issues, but their historical discussions were replayed in compressed sessions as source-backed triage; agents did not ship changes, and AI judges are not human reviewers. Snapshot: `{d['generatedAt']}`.

[Machine-readable results](assets/benchmarks/production-autonomy-20261102/results.json) · [Calibration ledger](assets/benchmarks/production-autonomy-20261102/calibrations.json) · [Original 30-task registration](assets/benchmarks/production-autonomy-20261102/triage30-registration.json) · [Original review plan and evidence correction](assets/benchmarks/production-autonomy-20261102/triage30-review-plan-metadata-revision.json) · [Supplemental 30-task registration](assets/benchmarks/production-autonomy-20261102/supplement-triage-registration.json) · [Supplemental review plan](assets/benchmarks/production-autonomy-20261102/supplement-triage-review-plan-final.json){commitments}

![Task completion, AI review, token use and observed memory actions](assets/benchmarks/production-autonomy-20261102/autonomy-summary.svg)

## What changed

- Claude Code's installed hook event names now dispatch correctly. `Stop` checkpoints completed assistant responses without another model call, marks them untrusted, skips generic refusals and certain credential-like strings, and deduplicates identical outputs in the same client session. The filter is not a comprehensive secret detector.
- A stable L2 namespace no longer causes the current-session filter to hide checkpoints from other Claude sessions. Session startup injects a short notice instead of repeating the same titles later in recall; relevant previews remain available on matching prompts.
- The isolated pilot bridge accepts larger read windows, supports multiword same-file search with an explicit fallback label, and summarizes repeated reads and search snippets while retaining an explicit refresh option. The later recovery protocol permits one tool-free continuation of the **same** session after budget exhaustion; the next stage remains a distinct session.
- A further MCP change, evaluated in the separate recovery cohort, marks agent-written MCP records untrusted and shows bounded summaries and trust metadata in search/open results. Existing records are not relabeled. The label is not a fact checker. The original cohort used the earlier frozen version; do not attribute this later change to it.
- After both registered cohorts, the default recall notice was updated to say that earlier memory can be incomplete or stale and to check current sources and later discussion before concluding information is absent. The registered cohorts used earlier commits; the change has an end-to-end hook regression test and a separate post-hoc follow-up, not 30 new independent evaluations.
- Reviewer parsing rejects missing scores, invalid evidence IDs, empty output and truncation. A review canary exposed omitted comment authors and dates in the anonymous packet; those public fields were restored before cohort ratings. A Gemini adjudication first truncated; a separately recorded low-effort retry completed. Both the failure and correction are retained.

## Frozen real-issue replays

| Protocol | Registered | Started | Finished | Complete paired two-session tasks | Valid AI-rated pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
{fmtrow('Original',a)}
{fmtrow('Supplemental recovery',b)}

Each task has its own pinned public source revision, issue snapshot hash, issue-specific criteria and randomized arm order. Both arms receive the same issue, staged comments, read-only source tools and their own searchable prior handoffs. The Memex arm additionally receives actual Claude Code hooks and memory tools. A completed pair requires two successful, distinct client sessions in each arm. Failures, tool errors, incomplete sessions and unstarted tasks remain in the results.

The issue discussions are historical public material that the models may already have seen; the pinned source revision can also postdate the discussion and contain subsequent fixes. This is a compressed replay of issue investigation, rather than a live long-running production workflow.

Original sessions not completed by final status: `{json.dumps(a['sessionOutcomes']['notCompletedByStatus'],sort_keys=True)}`; supplemental: `{json.dumps(b['sessionOutcomes']['notCompletedByStatus'],sort_keys=True)}`. In the supplemental protocol, {b['sessionOutcomes']['resumedAfterBudget']} budget-exhausted sessions had a same-session finalization attempt and {b['sessionOutcomes']['resumedAndCompleted']} completed; {b['sessionOutcomes']['unavailableToolAttempts']} nonexistent-tool attempts were explicitly rejected and retained. A `success` status can still fail the completion rule if an unapproved tool was attempted. These counts are sessions, not tasks.

The recovery cohort was selected and registered **after** observing budget exhaustion in the first cohort. It uses lower initial budgets, one tool-free same-session finalization when the initial budget is exhausted, the later MCP trust change and a revised pilot bridge. Treat the two cohorts separately; an observed difference between them is not a randomized comparison of those protocol changes.

{scoreline('Original',a)}
{scoreline('Supplemental recovery',b)}

Scores assess the supplied triage evidence against the frozen 0–2 rubric; they do not establish that a patch works, an issue is resolved, or a production task is correct. Reviewers are GPT-6.1 Sol and DeepSeek Flash; material disagreements are sent to Gemini Flash when both initial reviews are valid. Candidate labels are randomized and product names are removed, but the wording may still reveal the condition. An absent, truncated, invalid or unresolved review stays missing.

The first cohort published unsalted hashes of two-option label keys, which are enumerable. Earlier in-progress snapshots also exposed some supplemental answers by arm. The AI review requests did not include the arm mapping, but these publications mean allocation was not concealed from a determined outside observer. Supplemental packet keys use salted commitments; their salts are withheld until the reviews finish. Previous Git history remains available.

The original cohort also has a **post-hoc sensitivity view** of {a['posthocSensitivityRatedPairs']} rated pairs: control higher {a['posthocSensitivityDirections'].get('baselineHigher',0)}, tie {a['posthocSensitivityDirections'].get('tie',0)}, Memex higher {a['posthocSensitivityDirections'].get('memexHigher',0)}. This supplements the original primary view; it includes deterministic revalidation where judges cited a visible `limits` field, a different-model replacement after one timeout, and a separately registered retry of a malformed adjudication. The initial outcomes remain in the JSON. [Reference correction](assets/benchmarks/production-autonomy-20261102/triage30-limits-revalidation-registration.json) · [Reviewer rescue](assets/benchmarks/production-autonomy-20261102/triage30-review-rescue-registration.json)

The supplemental cohort's **post-hoc sensitivity view** covers {b['posthocSensitivityRatedPairs']} pairs: control higher {b['posthocSensitivityDirections'].get('baselineHigher',0)}, tie {b['posthocSensitivityDirections'].get('tie',0)}, Memex higher {b['posthocSensitivityDirections'].get('memexHigher',0)}. Two initial GPT-6.1 Sol requests timed out; separately registered GPT-6.1 Terra replacement reviews and Gemini adjudications were run on the unchanged blind packets. These replacements do not change the primary count, and any charge for the timed-out requests remains unknown. [Supplemental review rescue registration](assets/benchmarks/production-autonomy-20261102/supplement-triage-review-rescue-registration.json)

## Memory behavior and cost

Across all started tasks, the original cohort has **{a['agentWrites']}** tasks with an observed successful agent `memory_write`; **{a['writtenRecordOpenedNext']}** have an agent-written record explicitly opened in the next session. The Stop hook saved a first-session checkpoint in **{a['automaticCheckpoints']}** tasks, and a checkpoint was opened in the next session in **{a['automaticCheckpointOpenedNext']}**. For the supplemental cohort, those corresponding counts are **{b['agentWrites']}**, **{b['writtenRecordOpenedNext']}**, **{b['automaticCheckpoints']}**, and **{b['automaticCheckpointOpenedNext']}**. These are observed operations, not proof that the content was correct or necessary; categories overlap.

An exploratory check prompted by the low scores found that the supplemental second session opened a later-stage discussion comment in **{b['posthocDiscussionExposure']['baseline']['openedLaterComment']} / {b['posthocDiscussionExposure']['memex']['openedLaterComment']}** tasks (control / Memex). Counting a returned search excerpt as exposure gives **{b['posthocDiscussionExposure']['baseline']['exposedLaterComment']} / {b['posthocDiscussionExposure']['memex']['exposedLaterComment']}**. These are observed tool outputs, not proof the agent read, understood or used them, and this diagnostic was selected after seeing results.

{canary_note}

{tokens} Input totals include uncached, cache-read and cache-creation tokens, following [Anthropic's usage definition](https://platform.claude.com/docs/en/build-with-claude/prompt-caching). Output tokens are reported separately in the JSON. In recovered sessions, individual attempt usage is retained, but a full session total is **UNKNOWN** when the client may omit usage from a budget-failed request; zero is not substituted.

For supplemental budget-exhausted initial attempts, summed input usage in streamed assistant messages agrees with the client summary in {b['recoveryInputReconciliation']['matched']} cases, differs in {b['recoveryInputReconciliation']['different']}, and lacks usable evidence in {b['recoveryInputReconciliation']['missing']}. The difference cannot safely be filled in as a known billed total.

{context_note}

{paired_price} These are client list prices, not measured gateway wallet charges.

In the original {a['completePairs']} complete pairs, the control / Memex arms made **{a['completePairToolAttempts']['baseline']['total']} / {a['completePairToolAttempts']['memex']['total']}** tool attempts, of which **{a['completePairToolAttempts']['baseline']['exactRepeated']} / {a['completePairToolAttempts']['memex']['exactRepeated']}** repeated the identical tool and arguments within a single session. Overlapping source ranges and semantically repeated searches are not included in that narrow count. Fewer attempts alongside more input tokens does not by itself identify the cause: repeated context, cache traffic and output size require separate investigation.

The reported Claude client list-price totals for completed and failed session attempts are **${a['clientListPriceKnownUsd']:.4f}** for the original cohort and **${b['clientListPriceKnownUsd']:.4f}** for the supplemental cohort; sessions with missing client costs: **{a['clientListPriceMissingSessions']}** and **{b['clientListPriceMissingSessions']}** respectively. These figures are not APIMaster wallet charges and exclude the separate canaries, reviewers, machine time and labor. Gateway attribution and any missing fees are not assumed to be zero.

{billing_note} The gateway account's overall usage view was also checked; its account-wide amount cannot be uniquely assigned to this study and is retained privately. Infrastructure and labor remain UNKNOWN.

The following reviewer usage is reported by the gateway for terminal attempts with complete usage; failed or usage-missing attempts remain a separate gap. It is not a dollar invoice.

| Cohort | Model | Attempts | Known prompt tokens | Known output tokens | Failed or usage missing |
| --- | --- | ---: | ---: | ---: | ---: |
{usage_rows('Original',a)}
{usage_rows('Supplemental',b)}

## Retained calibration failures

The initial synthetic hook smoke was contaminated by inherited stdin and failed. A second clean-input attempt failed because the model did not repeat the supplied fact in its answer; a third, clearer synthetic attempt succeeded across two processes. These are mechanism checks, not independent real tasks. [Initial registration](assets/benchmarks/production-autonomy-20261102/hook-smoke-registration.json) · [First retry](assets/benchmarks/production-autonomy-20261102/hook-smoke-retry-registration.json) · [Clarified retry](assets/benchmarks/production-autonomy-20261102/hook-smoke-clarified-registration.json) · [MCP trust smoke](assets/benchmarks/production-autonomy-20261102/mcp-trust-smoke-registration.json)

The new [Axios #6690](https://github.com/axios/axios/issues/6690) calibration reproduced the read-only inherited `toJSON` failure, while a separate inherited-setter regression check passed initially. Both original arms and both separately registered retries exhausted their first-session budgets without a final patch. Their AI reviews scored only the missing artifacts; this cannot compare solving ability. [Registration and fixed criteria](assets/benchmarks/production-autonomy-20261102/axios-6690-registration.json) · [Post-hoc retry registration](assets/benchmarks/production-autonomy-20261102/axios-6690-retry-registration.json) · [Blind packet](assets/benchmarks/production-autonomy-20261102/axios-6690-blind-packet.json)

{closing}
'''
(root/'docs/production-autonomy-20261102.md').write_text(text)
readme=root/'README.md';s=readme.read_text();start='<!-- autonomy20261102:start -->';end='<!-- autonomy20261102:end -->'
v=b['scoreDirections'];summary=(f" In the supplemental primary AI ratings ({b['validRatedPairs']} pairs), control scored higher on {v.get('baselineHigher',0)}, tied on {v.get('tie',0)}, and Memex scored higher on {v.get('memexHigher',0)}." if b['validRatedPairs'] else '')
block=f"{start}\n**Cross-session follow-up (2026-11-02; {status.lower()}):** Real public issues were replayed in two separately registered, randomized Claude Code cohorts. At this snapshot, {a['completePairs']}/30 original and {b['completePairs']}/30 recovery-protocol pairs completed both sessions.{summary} These are historical triage replays assessed by AI, not live production correctness or cost-saving evidence. Automatic and agent-initiated writes, failures and missing usage are reported separately. [Results and limitations](docs/production-autonomy-20261102.md).\n\n![Cross-session issue replay progress](docs/assets/benchmarks/production-autonomy-20261102/autonomy-summary.svg)\n{end}"
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
