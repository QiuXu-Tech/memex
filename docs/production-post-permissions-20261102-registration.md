---
title: Post-permissions repair smoke registration, 2026-11-02
layout: default
---

# Post-permissions repair smoke registration

This separate two-issue smoke was frozen after discovering and fixing the POSIX SQLite permissions problem, but before these solver or review calls. It is a small functional follow-up, not a randomized estimate of the permission repair itself. The issues use new repository owners absent from the earlier registered cohorts.

The tested source commit is `e24bc06af255c648017cb7895905ef53f4e95a56`. Issue snapshots and pinned source archives are retained privately; the registration contains their hashes. Public material may be in model training, and pinned source may postdate discussion.

[Machine-readable registration](assets/benchmarks/production-post-permissions-20261102/registration.json) · [Frozen review plan](assets/benchmarks/production-post-permissions-20261102/review-plan.json) · [Anonymous packet and salted-label commitments](assets/benchmarks/production-post-permissions-20261102/packet-commitments.json) · [Source selection exclusions](assets/benchmarks/production-post-permissions-20261102/source-rejections.json)

| Public issue | Discussion span | Frozen acceptance focus |
| --- | ---: | --- |
| [zloirock/core-js #1556](https://github.com/zloirock/core-js/issues/1556) | 38 days | Explain the reported npm allow-scripts warning for the postinstall donation message, the npm fund tradeoff, and the later deny-scripts command correction without treating proposed behavior as independently verified. |
| [localForage/localForage #1101](https://github.com/localForage/localForage/issues/1101) | 308 days | Explain the reported _tryReconnect null database error and the insufficient environment information in the discussion; propose an initialization and browser-storage reproduction. |

Each paired task uses randomized arm order and two distinct Claude Code sessions per arm. Both conditions receive the same issue, staged public discussion, pinned source-reading tools and their own prior handoff; the treatment also has Memex hooks and MCP. The same targeted-lookup prompts and blinded AI grading rubric as the long-discussion cohort apply. Source-only triage is not a shipped patch or a live production outcome.

The initial per-session client list-price limit is $0.10 with one tool-free same-session continuation of up to an additional $0.04. The aggregate solver reservation is $1.50 in client list prices, excluding reviewers; in-flight requests can exceed session limits, and actual gateway charges are separate. Failed, missing and unstarted sessions, reviewer failures, usage gaps and unallocated costs remain visible.

One prior candidate exceeded the source-size limit; another appeared in a prior baseline-only screen and was excluded to preserve independence. Their partial and screened snapshots are retained privately. No solver or review call on these two issues had been made at registration; completed results are reported separately in the [integrity follow-up](production-integrity-followup-20261102.html).
