---
title: Additional issue after invalid adjudication, 2026-11-02
layout: default
---

# Additional issue after invalid adjudication

One new owner-disjoint issue was selected after a prior long-cohort adjudication returned malformed JSON. The invalid adjudication remains missing under the original review plan; this additional issue is separately registered before any calls on it and must not be pooled as if it were part of the original fixed cohort. The tested Memex source commit is `62441b70513a3f1123b88c55b04a0b6cf0998274`.

[Machine-readable registration](assets/benchmarks/production-permissions-rescue-20261102/registration.json) · [Frozen AI review plan](assets/benchmarks/production-permissions-rescue-20261102/review-plan.json)

| Public issue | Discussion span | Frozen acceptance focus |
| --- | ---: | --- |
| [markedjs/marked #4099](https://github.com/markedjs/marked/issues/4099) | 21 days | Explain the reported quadratic unmatched-emphasis scan and a targeted scaling reproduction; distinguish worker isolation from a parser fix, record the proposed early-exit PR as unverified, and identify CommonMark delimiter-compatibility checks without treating reported timings as confirmed. |

The randomized paired arms each use two distinct Claude Code sessions, the same pinned public source, staged discussion, and their own prior handoff; only the treatment adds Memex. Issue and source snapshots are retained privately with public hashes. Public history may be in model training and the source revision may postdate the discussion. This compressed read-only triage is not proof of a deployed production outcome.

The initial per-session client list-price limit is $0.10, with at most one tool-free same-session continuation using an additional $0.04. The aggregate solver reservation is $1.00 in client list prices, excluding AI review; an in-flight request can exceed the nominal session limit. Failures and unknown usage or charges remain visible.
