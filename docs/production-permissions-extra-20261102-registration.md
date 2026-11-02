---
title: Additional post-permissions issue registration, 2026-11-02
layout: default
---

# Additional post-permissions issue registration

This single new owner-disjoint issue was added after observing incomplete Claude pairs and before any call on this issue. Its results must be reported separately from earlier preregistered samples. The pinned Memex commit is `b93d798441b4b25d3f0fad9e40a4b961e64e8648`.

[Machine-readable registration](assets/benchmarks/production-permissions-extra-20261102/registration.json) · [Frozen AI review plan](assets/benchmarks/production-permissions-extra-20261102/review-plan.json) · [Anonymous packet and salted-label commitments](assets/benchmarks/production-permissions-extra-20261102/packet-commitments.json)

| Public issue | Discussion span | Frozen acceptance focus |
| --- | ---: | --- |
| [cheeriojs/cheerio #3457](https://github.com/cheeriojs/cheerio/issues/3457) | 81 days | Explain the reported adjacent text concatenation and expected spacing, the regex workaround and its limitations, and propose a minimal whitespace regression without treating comparative library behavior as verified. |

The randomized paired arms each use two distinct Claude Code sessions, the same pinned public source, staged discussion, and their own prior handoff; only the treatment adds Memex. The issue and source snapshots are retained privately with public hashes. Public history may be in model training, and the source revision may postdate the discussion.

The initial per-session client list-price limit is $0.10, with at most one tool-free same-session continuation using an additional $0.04. The aggregate solver reservation is $1.00 in client list prices, excluding AI review; an in-flight request can exceed the nominal session limit. Failures and unknown usage or charges remain visible. This is historical read-only triage, not proof of production correctness or a deployed fix.
