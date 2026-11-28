# P1 execution ledger

Updated **2026-11-28 (Asia/Shanghai)**. Base commit: `49e772bbf60532682771874b7ec96958f4a179e3`. Research branch: `research/p1-evidence-verification`. A dedicated clone isolates this work from existing checkouts.

## Outcome of this execution batch

The first paper now has a publicly reviewable English methods/protocol manuscript, a live-state research prototype, a frozen execution/cost/scoring controller, a pinned strong-baseline adapter, sixteen real source candidates and two actual base-to-fix reproductions. **The end-to-end proposed method, independent real-task pilot, confirmatory experiment and manuscript submission are not completed.** No result table has been filled with engineering tests or historical synthetic results. Public research branch and [draft PR #9](https://github.com/QiuXu-Tech/memex/pull/9) are created under the user's explicit public-disclosure authorization.

The manuscript's editable sources and PDF are in this directory. Its build and presentation checks are recorded in [BUILD.md](BUILD.md). [PROTOCOL.md](PROTOCOL.md) defines the research input boundary, task acquisition, scoring, failure denominator and freezing rules. [BASELINE.md](BASELINE.md) records the official Raw-RAG adaptation and actual dependency checks.

## Completed implementation

| Component | What is implemented | Boundary |
|---|---|---|
| Candidate extraction | Observable-input whitelist, versioned instruction, strict grounding/schema validation; actual auxiliary-model component calls retained | First real output missed a prerequisite; generic prompt v2 passed one same-family retest; no natural-task accuracy estimate |
| Original-source storage | Real Memex L2 ingestion, dynamic locators, paginated original open, immutable identifiers, durable catalog | Trusted single-writer complete normalized snapshots; general lifecycle projection absent |
| Typed verification | Test execution/version qualification, current-version evidence, historical authorization, expiry/effective time, conflict/missing-head/race checks | No action permission is granted; complete source coverage must come from the host observer |
| Reuse and live state | Policy/claim/version/epoch/view binding, trusted head content commitment, current selected-file/environment observation and execution binding | Current Node test target only; no atomic filesystem or arbitrary external-world coverage |
| Native event parsing | Narrow Node/TAP grammar; real exit/completion/test count; captured version equality | Unsupported relevant events invalidate completeness; not a general semantic parser |
| Raw-RAG adapter | Direct official add/search; fixed upstream commit and exact tokenizer; original request; faithful/full-turn and separately named budget display | Provider calls, reader and quality comparison unrun |
| Analysis | Frozen schedule left join, first-attempt policy, failure-inclusive task denominator, replicate averaging, hierarchical bootstrap, H1/H2 gates | Requires independently acquired tasks, valid labels, freeze and complete cost accounting |
| Execution and measurement | `freeze → dispatch → score-inputs → join`, hash-chained first-attempt ledger, frozen input/runner identity, complete component seals, evaluator score binding | Actual all-arm deployment, trace-derived complete billing and shared reference budget remain unrun |
| Native smoke and replay | Actual native compaction and resumed continuation; real terminal-event replay through L2 and verifier; same public archive accepted by Raw-RAG validator | One synthetic development workflow; manual offline version mapping and claims; no paired method result |

The historical `scripts/evidence-check-gate.mjs` and old experiment driver are unchanged. Their predefined claims and convenient source positions cannot be relabeled as the new automatic method or strong Raw-RAG.

## Fresh verification evidence

### Second batch after public authorization

| Check | Actual observed result | Evidence |
|---|---|---|
| Complete research suite | Exit 0; **65 Node + 119 Python = 184 passes**, no failures/skips | [phase2 suite](artifacts/checks/phase2/paper1-phase2-suite.txt) |
| Live-state / broker | Real local Node execution → live binding → actual L2 → unchanged reuse → changed bytes rejected → later failure reported; 15 live-state and 9 broker tests | [LIVE_STATE.md](LIVE_STATE.md), [LIVE_HOST.md](LIVE_HOST.md) |
| Controller review | 37 tests; cross-run scoring, false zero costs, file-mode/empty-directory drift fixed and independently rechecked | [EXPERIMENT.md](EXPERIMENT.md), [REVIEW.md](REVIEW.md) |
| Native online attempt | Actual MCP read succeeded; test call blocked by required approval; 1 generation turn, 0 executions/compactions/decisions | [attempt-01](artifacts/live-native/attempt-01/summary.json) |
| Actual model extraction components | First schema-valid output omitted test obligation; prompt v2 produced one test claim on a same-family retest; 2 generation turns | [live-native record](artifacts/live-native/README.md) |
| Real task acquisition | 16 traceable candidates / 8 projects; 0 accepted or frozen P1 workflows | [acquisition](tasks/acquisition/README.md) |
| Real program reproduction | Flask 1 fail/59 pass → 60 pass; Requests 2 fail/201 pass/11 skip → 203 pass/11 skip | [reproduction](tasks/reproduction/README.md) |

This batch has three new generation-turn starts in total and no new native compaction. The previous batch's native compaction is not reused as evidence of this online method. Raw notifications are retained without summing repeated cumulative snapshots; actual spend and full standardized cost remain unknown. Unit tests, source candidates, pytest items and development retries are not independent P1 task counts.

### Earlier preserved snapshot

| Check | Actual observed result | Evidence |
|---|---|---|
| `npm run test:paper1` | Exit 0; **41 Node tests + 74 Python tests = 115 passes**, zero failures/skips | [paper1-suite.txt](artifacts/checks/paper1-suite.txt) |
| Existing `npm test` | Exit 0; runner says `197/197 passed (4 skipped: bundle not built)`: **193 executed passes and 4 skips** | [baseline-suite.txt](artifacts/checks/baseline-suite.txt) |
| Official Raw-RAG offline constructor/tokenizer/hooks | Passed; official commit clean, 9 files verified; **0 model requests, 0 dispatches, 0 attempted network operations** | [runtime report](artifacts/checks/rawrag-runtime-check-final.json) |
| Native host | **One native compaction** and a successfully resumed synthetic workflow; all six final checks true | [native summary](artifacts/native-smoke/native-smoke-02-resumed-final/summary.json) |
| Real-log replay | Two actual TAP events preserved; five verifier calls; old version rejected, later failure reported as failure; both public archives accepted | [replay report](artifacts/replay/native-smoke-02/REPORT.md) |
| Protocol authoring contracts | Two Draft 2020-12 schemas and their documented input examples checked | [schemas](schemas/) |

Local test environment: Node 24.22.3, Python 3.12.14, NumPy 2.3.5. Native smoke environment: Codex 0.153.0, Node 25.9.0, Python 3.14.3, requested/resolved model `gpt-5.6-sol`. A post-run hash check matched the remote smoke, parser and legacy host-helper scripts to the saved source; it is not a hash attestation for earlier failed script versions. See [environment.json](artifacts/native-smoke/environment.json).

The Raw-RAG runtime check constructed real SDK clients and attached hooks, but did not exercise those hooks over HTTP or authenticate a provider. The default retrieval preflight still reports missing embedding/reranker credentials. [Credential presence](artifacts/checks/credential-presence.json) records process-variable names only in the local and authorized Mac runtimes; no credential stores or values were read.

## Failures retained and fixed

- Local Codex 0.172.0-alpha.2 initialization failed in a read-only managed runtime. An isolated supported SQLite-state path did not resolve all runtime writes. No permissions, credentials or managed controls were altered; the existing authorized Mac host supplied the bounded native check.
- The first native attempt combined commands in a shell and did not provide a valid standalone TAP receipt. Its failed state is retained. Later attempts completed the original test and actual native compaction but stopped at a foreign-thread fork metadata notification. A strict routing fix, including warning preservation, allowed a supported resume of the original thread.
- Across native attempts there were four new generation-turn starts and one native compaction; resumed summaries inherit prior counts. They must not be summed as independent trials or used as billing totals. Actual spend is unknown and remains null.
- The first offline Raw-RAG constructor check failed because the isolated SDK environment lacked socksio; installing that dependency through the normal package path resolved it. Proxy configuration was unchanged and the first failure report remains in the artifact directory.
- Independent review exposed a critical quality/cost coupling defect plus cache authenticity, parser, source-contract and documentation mismatches. They were corrected and tested; [REVIEW.md](REVIEW.md) records the concrete defects and limitations. Failing-before-fix regressions are retained separately from the final passing suite.

## Decisions for the remaining research

1. **Keep the novelty claim narrow.** Selective reopening and provenance already have close predecessors. The empirical question is incremental decision value beyond faithful Raw-RAG and neighboring sufficiency/governance methods under native compaction.
2. **Preserve input fairness.** Faithful B uses the original user request. C/D and claim-driven ablations share the extractor. A claim-expanded B is a distinct future adaptation, with its own frozen cost and name.
3. **Freeze a real shared budget.** The current 5,000-token Raw-RAG display adaptation and per-claim verifier defaults are not yet a frozen matched total budget. Addition of TierMem/sufficiency T changes the old run and cost plan.
4. **Complete the host integration.** The current-state binder and bounded broker exist, but native write-tool approval still blocks the online continuation path. Add a supported approval-capable client and preserve the actual user's decisions; do not falsely mark tools read-only. General source coverage and extraction-omission scoring remain necessary.
5. **Accept the real workflows.** Sixteen traceable source candidates exist, with two reproduced environments; zero P1 tasks are accepted/frozen. Build public/hidden workflow packages, independent annotation and behavioral checks before counting them. Eight development workflow packages still need full acceptance.
6. **Run the actual strong baseline and paired pilot.** The first external resource blocker is usable embedding and reranker service configuration. Do not substitute lexical retrieval or dummy embeddings, or put keys in Git/chat. Credentials alone do not satisfy the remaining task/method gates.
7. **Only then choose formal N and complete the paper.** Use pilot evidence for power/precision, freeze the full protocol and cost model, run confirmation and external validation, and write the result-supported submission version. Human authorship and the chosen venue's current requirements remain to be finalized.

No new paid service account or GPU allocation was opened in this batch. The existing authenticated native host was used for the bounded development check. No journal/conference submission, public preprint, main-branch merge, or paper acceptance is asserted.

## Preservation and publication status

The earlier push was rejected by automatic approval review because public disclosure of the unpublished research had not yet been explicitly authorized. On **2026-11-28**, the user stated **“授权公开，并继续补齐缺失流程步骤”**. That authorization resolved the public-disclosure restriction.

The research branch was then published through the authenticated GitHub connector after local Git lacked HTTPS credentials. The initial API-created commit is `f7cda0c4af886e6bfb37340d5126cd1c748e91b6`; its tree `e96b94036ace72f3a4cb6c503698410ee95e957f` exactly matched the local reviewed snapshot. [Draft PR #9](https://github.com/QiuXu-Tech/memex/pull/9) is open against main. Subsequent updates preserve the same research branch and draft status. No main merge, journal submission or public preprint submission was performed. [PR_DRAFT.md](PR_DRAFT.md) holds the review description, not a new request for public authorization.

The separate native MCP execution-approval issue and missing embedding/reranker services are technical/runtime dependencies; public-disclosure permission does not silently override either.
