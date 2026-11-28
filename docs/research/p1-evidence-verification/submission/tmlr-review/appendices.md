The following appendices are part of the expanded working draft and are separate from its main argument.

# Acceptance Conditions

These conditions are acceptance requirements, not statements that the implementation passes.

| Area | Minimum evidence required before confirmation |
|---|---|
| Input separation | A trace shows the deployment process receives no `case.claims`, hidden answer values, gold source IDs, fixed correct event index, or evaluator-derived lineage |
| Claim discovery | An independently labeled set measures omissions and false candidates from natural requests and exposed drafts |
| Source opening | Randomized event positions and paginated natural logs are opened through real tools; clipped and mismatched records are rejected |
| Typed semantics | Tests cover execution/completion, artifact binding, current-version authority, historical-time scope, revocation, conflict, and unknown states |
| Archive completeness | Certificates identify their view and replay coverage; candidate top-k results alone cannot certify absence of invalidation |
| Freshness | Old unexpired grant followed by revocation is rejected; same-head missed revocation, scheduled transition, dropped notification, out-of-order arrival, restart, and head races are exercised |
| Reuse | A no-reopen path records current head/object checks and does not silently fall back to TTL |
| Host delivery | Payload hash and a supported host receipt demonstrate actual delivery after the relevant compaction boundary |
| Final decisions | The evaluator separately verifies action behavior, obligatory claims, source eligibility, abstention, and model consumption |
| Baseline fidelity | Raw-RAG configuration and delivered text are auditable; close-method reproductions and approximations are clearly distinguished |
| Resource accounting | All extraction, verification, acquisition, metadata, preprocessing, model, and failure costs are retained |

# Required Evidence for a Submission-Ready Paper

The following gaps remain material:

1. **A deployed-interface implementation.** Eliminate the old structured-claim and fixed-location dependencies, implement complete lifecycle qualification and head validation, and provide an auditable boundary between public runtime data and hidden labels.
2. **Independent freshness validation.** Demonstrate that the known counterexample and the additional failure modes in Section 6.6 are addressed. Record finite test scope rather than claiming universal correctness.
3. **Strong and close comparisons.** Run B under a frozen faithful adaptation, assess a governance implementation, and freeze the TierMem or sufficiency-only comparison. A self-written approximation is not evidence of reproducing another paper.
4. **Natural, independent tasks.** Collect licensed workflows in which post-compaction decisions matter, with repository and event-family separation. Retire the old 24 fixtures from formal estimation.
5. **A justified sample size.** Complete the pilot, power and precision analyses, and a substantive justification for the H2 margin. Freeze the hierarchy before outcome access.
6. **Paired confirmatory continuations.** Execute the frozen design, retain failures, verify actual evidence delivery, and obtain independent behavioral and source-based scores.
7. **Incremental mechanism evidence.** Show what qualification changes when candidate evidence is identical, and what certified reuse changes when the acquisition pipeline is identical.
8. **Total-cost evidence.** Estimate the joint quality and cost criterion with all relevant overhead. If the criterion is not met, report the limits without replacing the endpoint.
9. **External validity and failure analysis.** Report every planned host/model configuration, including adverse or uncertain results, and distinguish continuation replay from full natural runs.
10. **An independently reviewable manuscript and artifact.** Recompute each table from released or access-controlled records, verify every citation and license, resolve authorship and AI disclosure, and obtain human approval of the final claims.

Meeting these conditions makes the empirical claim reviewable; it does not guarantee a positive result or acceptance by a venue. If the principal increment is absent, a revised paper should state that finding and its uncertainty rather than retaining an unsupported methods claim.

# Provenance of the Existing Project Observations

The draft's development statements refer to the following inspected materials. The legacy source revision is `revision withheld in review draft`.

| Material | Identifier | What it supports |
|---|---|---|
| Legacy results | Versioned November 26 results report at the pinned legacy commit | Reported synthetic-fixture counts, timing of intervention, and limitations |
| Legacy driver | Native evidence-recovery driver at the pinned legacy commit | Predefined claim list, structured source filter, fixed event opening, and read-only continuation |
| Legacy gate | Evidence-check gate at the pinned legacy commit | Local-evidence shortcut, type/status checks, and absence of a required current archive head |
| Local diagnostic record | `counterfactual-freshness.json` from the prior local audit, inspected 28 November 2026 | Recorded old-grant/later-revocation inputs and the observed no-search output |
| P1 planning document | P1 evidence-verification research plan, an internal working document | Proposed primary endpoint, statistical hierarchy, task plan, and resource assumptions |
| Live-state engineering | `LIVE_STATE.md` and the corresponding implementation and regression suite | Bounded current-workspace observations, execution and claim binding, finite test coverage, and explicit concurrency limits |
| Experiment controller | `EXPERIMENT.md` and its controller contract tests | Local freeze, first-attempt dispatch, evaluator join, component ledgers, and remaining review boundaries |
| Online development | `artifacts/live-native/` manifest, attempt summary, and both extraction records | One approval-blocked integration attempt, one semantic extraction miss, one same-family prompt retest, and unmeasured costs |
| Read-only continuation | `artifacts/readonly-native/` source snapshot, frozen configuration, first attempt and usage audit | Five generation starts, one actual compaction, three native forks, equal recorded recommendations, different source I/O, and unresolved full costs |
| Candidate acquisition | `tasks/acquisition/` manifests and source records | Sixteen source candidates, eight projects, fixed provenance, ancestry and label cautions, and unfilled P1 acceptance fields |
| Initial program reproduction | `tasks/reproduction/` commands, phase hashes, stdout, and JUnit reports | Two initial source/environment checks, four actual pytest invocations, fixed patches, observed outcomes, and retained failures |
| Qualification expansion | \path{tasks/reproduction-expansion/} summary, numbered receipts and rule revision | All 14 remaining candidates attempted, 10 additionally qualified, four bounded limitations, 29 retained attempts and 34 top-level test-phase calls |
| Task and review material | `TASKPACKS.md`, `ANNOTATION.md` and `tasks/workflows/` | Eleven unaccepted packages, eight synthetic development families, 22 unfilled review packets, and explicit unresolved acceptance gates |

The local diagnostic is not presented as a publicly archived dataset or a peer-reviewed source. Before submission it must be included in a reproducible, appropriately anonymized artifact with its own stable identifier. Statements about the legacy study are attributed to its report and inspected code; the entire legacy model experiment was not rerun for this draft.

# Verified Primary Sources and Comparison Notes

Checked on 28 November 2026. This is a focused overlap review, not an exhaustive systematic review. Full-text sections were inspected for the principal five requested works and for TierMem, MSS-Complement, and CompAct-Bench. Additional records below were checked at their primary abstract/metadata pages; their detailed implementation behavior should not be inferred beyond that inspected material.

| Reference | Primary source and inspected version | Relevant distinction for this draft |
|---|---|---|
| Raw-RAG | [Raw-RAG, v1](https://arxiv.org/html/2610.30755v1) | Strong raw-history retrieval is the primary challenge; full-turn expansion matters for budgets |
| GPM | [GPM, v2 record](https://arxiv.org/abs/2608.12476v2); [full paper](https://arxiv.org/pdf/2608.12476) | Source-bound stable-head release already exists; current claims must distinguish free-form continuation from deterministic service output |
| HELM | [ACL record](https://aclanthology.org/2026.emnlp-main.721/); [full paper](https://aclanthology.org/2026.emnlp-main.721.pdf) | Governance, tool status, versions, provenance, and memory-operation control directly overlap |
| Compaction-Friendly | [Compaction-Friendly, v2](https://arxiv.org/html/2610.31778v2) | Constraint loss despite task performance is established motivation |
| Folio | [Folio, v1](https://arxiv.org/html/2611.16627v1) | Stable handles, multiresolution retention, and recoverable original events are established |
| TierMem | [TierMem, v1](https://arxiv.org/html/2602.17913v1) | Selective escalation from summaries to raw logs is a close prior method |
| MSS-Complement | [MSS-Complement / SERBench, v3](https://arxiv.org/html/2609.20050v3) | State-conditioned sufficient evidence and separation of discovery from assembly are already explicit |
| CompAct-Bench | [CompAct-Bench, v1](https://arxiv.org/html/2611.25673v1) | Controlled continuation and downstream compaction effects are established evaluation designs |
| Agent Zero Memory | [Agent Zero Memory, v1](https://arxiv.org/abs/2608.29606v1) | Intent gating and citations restricted to opened evidence overlap |
| MemIR | [MemIR, v1](https://arxiv.org/abs/2605.25869v1) | Typed separation of evidence, cues, and claims overlaps |
| MemoRepair | [MemoRepair, v1](https://arxiv.org/abs/2605.07242v1) | Invalidation and validated republication are established |
| StateFuse | [StateFuse, v1](https://arxiv.org/abs/2607.05844v1) | Visible conflicts and auditable correction are established |
| Compaction Cliff | [Compaction Cliff, v1](https://arxiv.org/abs/2608.22752v1) | Type-dependent retention and repeated compaction are prior topics |
| Provenance laundering | [Provenance laundering, v1](https://arxiv.org/abs/2607.29167v1) | Preserving source authority is distinct from verifying historical authorization facts |
| Eywa | [Eywa, v1](https://arxiv.org/abs/2605.30771v1) | Immutable source evidence, typed support, and separation of retrieval from answer policy overlap |
