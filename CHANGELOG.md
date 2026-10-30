# Changelog

**Measurement note:** v0.8.0 recorded tail membership but could still reorder
same-millisecond records by random ID. Earlier counts remain historical; see
[docs/live-testing.md](docs/live-testing.md#deepseek-flash-results-2026-10-29).

## 0.15.1

### Fixed — DSH rc.4/rc.5 compatibility
- Relaxed the bundle's `engines.dsh` requirement from exact `0.2.1-rc.3` to `>=0.2.1-rc.3 <0.2.2`, so it satisfies the nightly rc.5 update as well as the currently installed rc.3.
- Rebuilt the `@local/dsh-memory` compatibility bundle for the active profile.
- Backup/rollback of the pre-update app, profile, branding files and compat bundle: `~/Documents/deepseek-harness/default-workspace/backups/dsh-rc3-20261030-122547/`.
- Harness **130/130**.

## 0.15.0

### Fixed — SQLite/file consistency
- Serialize file-backed record mutations with SQLite, retain staged data across interrupted operations, and never overwrite a cold file after a failed move. Missing legacy bodies now raise an explicit error.
- Snapshot backups under the writer lock, include retained recovery files, and rebase restored record paths to the destination after validating them.
- Added multi-process lock, interruption, retry, backup and recovery tests. Process-crash recovery is covered; sudden power-loss durability is not established.

### Added — A-route GPU validation (vLLM paged-KV prefix cache)
- Connected to an NVIDIA RTX PRO 6000 Blackwell Server Edition (96GB, driver 590.44.01); torch 2.8.0+cu128 / CUDA 12.8 / compute capability (12,0).
- Installed and ran **vLLM 0.10.2** with Qwen2.5-0.5B-Instruct and `--enable-prefix-caching`.
- Two requests sharing a ~2,498-token materialized stable prefix: vLLM metrics reported **prefix_cache_queries_total=4997**, **prefix_cache_hits_total=2480** → **99.2% second-request prefix hit ratio**.
- Added `training/vllm_prefix_cache_eval.py` and `docs/assets/benchmarks/vllm-prefix-cache.json`; docs/context-materialization.md updated.
- **Boundary:** vLLM-native prefix caching, not a custom external paged-KV connector yet; small model/single run.
- Harness **130/130**; SQLite consistency **36/36**.

## 0.14.1

### Fixed
- `LocalMemoryStore.materializeContext()` was missing its `materializeStoreContext` import in the generated bundle, so the runtime materializer silently failed and fell back to the old catalog/recall path. Fixed; U33 now mounts the checkpoint with `materializer: timeline-exact` and asserts a real `materialized-context` injection.
- Added `recordMaterialization` trace to the local backend: enabled injections append to `<memory-root>/materializer-trace.jsonl` for live verification; checkpoint records session/workspace/form/text (best-effort).
- Harness **130/130**.

### Note
- The DSH profile uses a compatibility package named `@local/dsh-memory` that points at the upgraded bundle; this avoids changing the profile's bundle/row names (which caused the earlier disappearance when the profile was switched to `@qiuxu/memex`). Restart DSH after updating the link.

## 0.14.0

### Changed — materializer is now the default DSH injection path
- The bundle's checkpoint row now ships `materializer: timeline-exact` (plus `materializerMaxTokens: 1800`). The pre-step injects a materialized resident window instead of catalog+recall; receipts and capacity notices remain. Set `materializer: off` to restore the old behavior.
- The materialized window contains canonical event content when available, otherwise rendered record bodies, with a stable index prefix and explicit budget/omission metadata.
- Harness **129/129**; bundle patch updated (reinstall/rebuild the bundle to apply).

### Still external (not claimed)
- Production transformer training on live traces/GPU and per-family adapters; the shipped transformer is a small synthetic-data reference.
- Native vLLM/SGLang/DSH KV-cache integration; the paged-KV host is a runnable reference, not a model runtime.

## 0.13.0

### Implemented — materialization runtime + specialists
- **DSH runtime injection switch**: checkpoint config `materializer: 'off' | 'timeline-exact' | 'edge-attention'` (default off); when enabled the pre-step injects a materialized resident window instead of catalog+recall, while receipts/capacity notices remain. Config validated and documented.
- **Trained transformer context encoder reference**: `training/context_encoder.py` trains a tiny 2-head self-attention encoder on synthetic page/query pairs; weights + metrics exported; `context-transformer.js` reproduces Python logits in JS (U31 parity + ranking). Validation accuracy/ranking 1.0 on its synthetic set; explicitly a reference, not a production model.
- **Runnable paged-KV/prefix host**: `PagedKvContextHost` (bounded paged blocks, LRU eviction, prefix map, page table) plus `scripts/context-kv-host.mjs` HTTP reference service; U32 covers paging/prefix/eviction. True KV tensors still require an inference runtime.
- Structural fidelity eval remains green; harness **129/129**.
- **Explicit external work**: production training on live traces/GPUs, native vLLM/DSH KV-cache integration, enabling the materializer by default.

## 0.12.0

### Implemented — context materialization steps 1–5
- **Canonical events**: `context-events.js` (role/type/content/tool-call/tool-result/attachment, checksum, DSH adapter), `context_events` store table + `append/listContextEvents`, checkpoint capture alongside rendered cards, seam/local backend forwarding. U27.
- **Pager/materializer**: `context-pager.js` selects resident pinned/open/recent pages, prefers canonical events, and materializes through `context-materializer.js`; `AgentMemory.materializeContext()` API. U28.
- **Encoder baseline**: `context-encoder.js` feature extractor + heuristic and trainable linear logistic encoder sharing the transformer `score()/rank()` interface; offline training test. U29. (Not a trained transformer.)
- **KV/prefix host seam**: `context-kv.js` explicit capability contract, negotiation, mock paged-KV host, fail-closed text fallback; no undocumented host probing/induction. U30.
- **Structural fidelity eval**: `scripts/context-fidelity-eval.mjs` → `docs/assets/benchmarks/context-fidelity.json`; canonical round-trip, chronology, stable prefix, pager canonical coverage, KV mock path all pass.
- Harness **127/127**.
- Explicitly pending: runtime DSH injection switch, real transformer encoder/assembler training, real KV/prefix-cache host.

## 0.11.0

### Added — context materialization direction + transformer specialist interface
- **Direction locked**: extra context becomes a context virtualizer/materializer (exact ordered, budgeted window), not only a retrieval layer. New design doc: `docs/context-materialization.md`.
- `packages/memex-core/lib/context-materializer.js`:
  - deterministic chronological materialization with stable index prefix (`stablePrefixHash`) and prompt-cache-friendly layout;
  - variants: `timeline-exact`, `edge-attention`, and `context-specialist-v1` (declares `requiresKV: true`, heuristic fallback);
  - budgeted inclusion, pinned-page forcing, explicit `omittedIds`, role/sequence metadata.
- Transformer context-specialist variants specified as pluggable components: **context encoder** (learned salience), **context assembler** (budgeted packing), **KV/paged-attention specialist** (native-context path). Not trained/wired yet; interface and deterministic baseline first.
- **U26** covers chronology, stable prefix determinism, budget/pinning, and specialist contract; harness **123/123**.
- Explicit boundary documented: token/text materialization can approach true context structurally; attention/KV-level fidelity requires host paging and is called out as the remaining gap.

## 0.10.0

### Fixed — A/B tail-order
- The live A/B fixture now archives and selects records in actual write order; U25 deterministically covers tied timestamps, reverse IDs, empty tails and tails longer than the history. Offline harness: **122/122**.
- A fresh GPT-6.1 Sol A/B reported control **3/60**, treatment **60/60**, evicted **0/57 → 57/57**. All three saved prompts and plans were checked against turns 280–299 in order. This is a synthetic, evidence-in-prompt comparison.

### Added — Claude real tool-calling loop
- `scripts/claude-tool-loop.mjs`: native OpenAI-style tool definitions (`memory_search`, `memory_open`), model-chosen tool calls, execution against the **real memex MCP server**, final exact-FACT grading, usage capture.
- Claude Sonnet 5.5 (3 probes): control **0/3** (no tools), treatment **3/3**; the model searched, refined queries, opened cold records and answered. Usage **15,649 tokens / 12 API calls**.
- First end-to-end tool-calling validation (not evidence pre-injected); dataset `docs/assets/benchmarks/live-ab-claude-tool-loop.json`; summary docs/live-testing.md §I.
- Real-archive guard unchanged.

## 0.9.1

### Added — Claude 5.5 family completion
- **claude-fable-5-1** and **claude-haiku-5-5** run through the pre-tail-order-fix APIMaster batch bridge (3 seeds × 20 probes each): control **3/60 (5%)**, treatment **60/60 (100%)**, reported evicted **0/57 → 57/57**. Full chronological tails were not saved.
- Gateway-reported usage: Fable **40,663 tokens**, Haiku **39,677 tokens** (6 calls each); all four Claude models total **161,689 tokens** across 24 calls. Monetary cost is unknown.
- Datasets: `docs/assets/benchmarks/live-ab-claude-fable51.json`, `live-ab-claude-haiku55.json`; summary docs/live-testing.md §H.
- Harness **121/121**; real-archive guard unchanged.

## 0.9.0

### Added — Claude 5.5 live validation (APIMaster)
- Added `scripts/claude-ab.mjs`: batch Claude runner over an OpenAI-compatible gateway, fixed-tail fixture, exact-FACT grading, per-call usage capture, no keys stored.
- **claude-sonnet-5-5** and **claude-opus-5-5** (3 seeds × 20 probes each, APIMaster): control **3/60 (5%)**, treatment **60/60 (100%)**, reported evicted **0/57 → 57/57**. The full chronological tail was not saved in these pre-fix runs.
- **Gateway-reported token usage: 40,673 (Sonnet) / 40,676 (Opus)**, 6 calls each; monetary cost is unknown.
- Datasets: `docs/assets/benchmarks/live-ab-claude-sonnet55.json`, `live-ab-claude-opus55.json`; summary in docs/live-testing.md §H.
- Harness **121/121**; real-archive guard unchanged from 0.8.1.

## 0.8.1

### Added — GPT family comparison
- Ran **gpt-6.1-terra** through the v0.8.0 Codex bridge (3 seeds × 20 probes): control **3/60 (5%)**, treatment **60/60 (100%)**, reported evicted **0/57 → 57/57** with saved IDs/flags; full chronological tail records were not saved.
- GPT family comparison on the synthetic fixture: Sol (pre-fix report, overall 3/60 → 60/60) vs Terra (3/60 → 60/60); neither historical report establishes the full chronological tail.
- Dataset: `docs/assets/benchmarks/live-ab-codex-terra.json`; summary in docs/live-testing.md §F.
- Harness **121/121**; real-archive guard unchanged from 0.8.0.

## 0.8.0

### Changed — retained-tail membership + multi-seed rerun
- `scripts/live-ab.mjs` records selected tail IDs (`tailIds`, `tailRecords`) and per-probe `inTail`/`evicted` flags in `plan.json`; ties in creation time could still reorder turns until the unreleased fix above.
- DeepSeek Flash 3-seed rerun: control **3/60 (5%)**, treatment **60/60 (100%)**, reported evicted **0/57 → 57/57**. Two recorded tails did not exactly match the newest 20 turns. Evidence: `docs/assets/benchmarks/live-ab-deepseek-multiseed.json`.
- The older GPT-6.1 Sol report (v0.7.1) predates the fix; its overall answers are preserved and its cold subset stays caveated.

### Added — cold partial/synonym anchor-free recall
- Morphology-lite matching (`decide` ↔ `decision`), cold-only FTS prefix variants, cold abstract prefix LIKE candidates, stopword-filtered content terms, and a default partial-coverage cold boost (`coldPartial: 2`).
- Live DeepSeek cold anchor-free morphology/synonym/partial run (n=3): control **0/3**, treatment **3/3** (`FACT-BILL-OK`, `FACT-AUTH-30D`, `FACT-CACHE-LRU`). Evidence: `docs/assets/benchmarks/live-ab-deepseek-cold-partial.json`.
- **U24** covers morphology + partial coverage; harness **121/121**.
- Trade-off documented: real-archive hit@1 **68% → 65%**, hit@5 **93%**, cold recall 94%, p50 ~2.9 ms; set `coldPartial: 0` for precision-first behavior.

## 0.7.1

### Added — Codex/GPT live dataset
- **Codex CLI / GPT-6.1 Sol live A/B (contributed)**: 3 seeds × 20 probes; control **3/60 (5%)**, treatment **60/60 (100%)**; reported cold subset 3/57 → 57/57. This is the second model family reproducing the evidence-in-prompt pattern (DeepSeek Flash also 3/60 → 60/60).
- Dataset: `docs/assets/benchmarks/live-ab-codex-gpt.json`; summary in docs/live-testing.md section F.
- Retained-tail caveat retained: the reported cold subset is not a verified recently-evicted subset until the harness ordering issue is fixed.

## 0.7.0

### Added — cold-side anchor-free recall
- **Cold-only FTS candidate leg** for anchor-free queries: when the primary candidate pool is dominated by hot cards, fetch cold pages whose abstracts match the query, without reading cold bodies.
- **Full-abstract-coverage cold rescue boost**: only cold rows whose abstract covers *every* meaningful query term receive the cold-abstract boost; partial keyword overlap is ignored so precise hot cards are not displaced.
- Live DeepSeek Flash cold anchor-free run (n=3): control **0/3**, treatment **3/3** for body-only decisions archived cold (`FACT-BILL-OK`, `FACT-AUTH-30D`, `FACT-CACHE-LRU`).
- **U23** cold anchor-free retrieval test; harness **120/120**.
- Real-archive guard unchanged: hit@5 **93%**, cold recall **94%**, p50 ~**2.0 ms** (cold-only FTS leg; up from 1.7 ms).
- Limits: full-term coverage required; morphology matches exactly (no stemming); cold bodies are not scanned.

## 0.6.1

### Added — Codex/GPT contribution bridge
- `scripts/codex-ab.mjs`: generates the synthetic fixture via `live-ab.mjs --emit-prompts`, runs `codex exec` (read-only sandbox, isolated work dirs) for control/treatment, grades exact FACT ids, and writes a shareable JSON report. No API key read or stored.
- Docs: docs/live-testing.md "Run it with Codex CLI (GPT models)" with the one-command contribution path; README pointer.
- Output includes per-seed rows, control/treatment/cold accuracy, raw reply tails and explicit caveats. Requires Node >= 22 and a logged-in `codex` CLI.

## 0.6.0

### Added — anchor-free natural-language recall
- New **hot-body coverage rescue**: when a query has no number/ID anchor and no card field shares a meaningful query term, scan at most 240 hot bodies and page in the records with the best query-term coverage. Cold anchor-free facts continue to use abstract FTS/card summaries.
- Live DeepSeek Flash anchor-free run (n=3): control **0/3**, treatment **3/3** for body-only decisions with generic card titles (`FACT-BILL-OK`, `FACT-AUTH-30D`, `FACT-CACHE-LRU`).
- **U22** covers anchor-free hot-body recall; harness **119/119**.
- Real-archive guard unchanged: hit@5 **93%**, cold recall **94%**, p50 **1.7 ms**.

## 0.5.1

### Fixed
- **Hot body-only facts with bare-number anchors**: body rescue now triggers on unmatched numeric anchors and attaches body evidence to rows that are already card candidates (only when the anchor appears in the body). This closes the last DeepSeek multi-seed miss: Q19 (turn 285) is recovered, treatment **60/60 (100%)** across 3 seeds; evicted records **0/57 → 57/57**.
- Cold natural-language subset remains **30/30**; U20/U21 cover cold card-anchor and hot body-anchor retrieval. Harness **118/118**. Real-archive guard: hit@5 **93%**, cold recall **94%**, p50 **1.5 ms** (was 95%/100%/1.3 ms before the anchor rework — an explicit trade-off for cold natural-language coverage 0/30 → 30/30).

### Changed
- **Extra-context terminology synced to UI/site**: panel title/trigger/aria use "额外上下文 / 上下文页"; homepage title and description position Memex as *the extra-context layer for AI agents*, with the context hierarchy/paging explanation and updated live numbers.
- Package descriptions updated (root/core/local).

## 0.5.0 — extra-context layer + cold natural-language retrieval

### Changed — concept
- Repositioned the project as an **extra-context layer between agent history and the model window**, not a notes/memory app: context hierarchy (L1 → L2/L3 → cold), context paging, context budgets, context ring. New concept doc: `docs/context-layer.md`; README/manual wording updated; project remains **Memex**.

### Fixed — cold natural-language retrieval
- `record_terms` now indexes **card fields and bare turn numbers** in addition to identifier-like body tokens, and cold-anchor rescue uses exact term anchors from `record_terms` instead of a broad abstract LIKE scan.
- Live DeepSeek Flash multi-seed after the fix: control **3/60 (5%)**, treatment **57/60 (95%)**; evicted records **0/57 → 54/57 (94.7%)**; cold-tier natural-language subset **0/30 → 30/30**. Residual: one Q19 evidence-query miss per seed (turn 285), correctly reported as not found.
- `scripts/live-ab.mjs` archiving fixed for fixtures >100 turns (DB-driven archive, exact tail).
- Harness **117/117** (U20 cold natural-language retrieval).

## 0.4.3

### Validation
- **DeepSeek Flash multi-seed live A/B** (3 seeds × 300-turn history × 20 probes): control **3/60 (5%)** vs treatment **30/60 (50%)**; evicted records **0/57 → 27/57 (47.4%)**. Raw: `docs/assets/benchmarks/live-ab-deepseek-multiseed.json`.
- **Full agent-loop validation** (n=1): model emitted `memory_search` → refined search → `memory_open`; harness executed the calls against the real memex MCP server; treatment answered correctly where control answered `UNKNOWN`. Raw: `docs/assets/benchmarks/live-ab-deepseek-agent-loop.json`.
- **Finding:** all multi-seed treatment failures are cold-tier facts queried in natural language without an identifier anchor (0/30 cold subset); hot/tail facts are recovered. This is now the top retrieval improvement target.
- `scripts/live-ab.mjs` gained `--seed`, `--turns`, `--tail`, and earlier `--emit-prompts`; docs/live-testing.md and docs/experiments-v040.md updated with the live results and caveats.

## 0.4.2

### Validation
- **First live A/B data point (DeepSeek Flash)**: two fresh-context calls on the 120-turn synthetic fixture, 8 deep-fact probes. Control (recent tail only) answered 1/8 overall and **0/7 evicted facts**; treatment (tail + memex evidence) answered **8/8 overall and 7/7 evicted facts**. Raw answers in `docs/assets/benchmarks/live-ab-deepseek.json`; summary in `docs/live-testing.md` and `docs/experiments-v040.md`.
- `scripts/live-ab.mjs` gained `--emit-prompts <dir>` for agent-mediated validation (used for this run).
- Caveats kept explicit: n=8, single model/run, agent-mediated route, usage not captured; more model families welcome via issue #1.

## 0.4.1

### Fixed / improved
- **Cold-body recall 63% → 100%**: cold-anchor rescue (identifier terms scan the bounded cold `abstract`, with a `coldAnchor: 30` evidence bonus) enters only for identifier-like queries; profile validation cold hit@5 is now 100% for all profiles while real-archive hit@5 stays 95%.
- **Catalog budgets are now used**: catalog depth scales with `maxChars`/profile budget (18 fixed cards → up to 48 scaled cards); injected catalog 893–1439 tokens vs 340–524 before.
- **L2 session alignment**: `memex-claude init --session <id>` writes the same session into `.mcp.json` and all hooks; hooks prefer the explicit session. U19 covers it.
- **Approval UX**: `init` prints the one-time MCP approval hint.
- U18 storage/env fallbacks; harness **116/116**.

### Verification
- Quiet-machine 100M benchmark: write 3.4 s, facets 6.5 ms, catalog 13.8 ms, search 6.7–8.3 ms, compression 2.94 s, cold GC 0.28 s (DB 26.7 MiB).
- Live A/B: multi-model usage data collection open (issue #1); tokenizer calibration will follow the first contributions.

## 0.4.0 — project renamed to Memex

### Changed
- **Renamed the project from `dsh-memory` to `Memex`** (repository `QiuXu-Tech/memex`): packages are now `@qiuxu/memex*`, adapter binaries `memex-claude` / `memex-codex` / `memex-mcp`, storage default `~/.memex` (legacy `~/.dsh-memory` and legacy `DSH_MEMORY_*` env vars still work), docs/Pages URLs updated.
- **Adapter defaults now write recommended dedicated profiles**: Claude Code defaults to `claude-sonnet-5-5` (recommended: opus-5-5 / fable-5-1 / haiku-5-5), Codex defaults to `gpt-6.1-sol` (recommended: terra / astra), and `memex-mcp --list-profiles` lists MCP recommendations.
- U17 covers the defaults and advertisement; U18 covers storage-root/env fallbacks (115 tests).
- `scripts/live-ab.mjs` live endpoint A/B harness (Anthropic / OpenAI / DeepSeek, dry-run supported) + `docs/live-testing.md`.
- `docs/experiments-v040.md`: post-rename verification, real-archive recall re-check (hit@5 95%, cold 100%), profile validation rerun and improvement points.

### Added
- `RECOMMENDED_PROFILES` registry in the core; `init`/`help` print the resolved profile.

## 0.3.3

### Added
- **More dedicated profiles**: `claude-fable-5-1`, `claude-haiku-5-5`, `gpt-6.1-terra`, `gpt-6-astra` (8 variants / 21 profiles total), each with vendor-verified context/output limits, tokenizer estimates, budgets, rerank weights and reasoning-mode guidance.
- **Profile validation report** `docs/profile-validation.md` + committed fixture script `scripts/profile-validation.mjs` and raw data `docs/assets/benchmarks/profile-validation.json`: cold-start parity (45–50 ms init, 2–3 ms first search), long-horizon retrieval parity, token overhead per 50 turns, and the Fable 5.1 body/useWhen tie-break fix discovered by the A/B.
- Harness U16 extended to 8 variants (113 tests).

## 0.3.2

### Added
- **Dedicated current-model profiles** (checked before family bases, with vendor-verified specs):
  - `gpt-6.1` — GPT-6.1 Sol: 1,050,000 context / 922k max input / 128k output (Codex default 500k), reasoning effort low→max, Responses-API tooling, 1800/700 budgets.
  - `claude-opus-5-5` — Claude Opus 5.5: 1M context, adaptive thinking always on (default medium), current tokenizer estimate 2.6 chars/token, 2000/800 budgets, XML injection + archive-first compaction guidance.
  - `claude-sonnet-5-5` — Claude Sonnet 5.5: 1M context, adaptive thinking (default high), 1600/650 budgets for the speed/intelligence balance.
  - `deepseek-flash` — DeepSeek Flash: model id `deepseek-flash` (legacy `deepseek-v4-flash`), 1M context / 384k output, thinking/non-thinking default thinking, latency-sensitive bilingual profile, 1200/500 budgets.
- Variant registry (`MODEL_VARIANTS`) + resolution precedence; overrides (`profileOverrides`) still win. Docs table with vendor sources; harness U16 covers resolution/precedence/budgets/manual/digest (113 tests).

## 0.3.1

### Performance
- **Adaptive LIKE leg**: trigram FTS covers substrings for terms ≥3 chars, so the 4-field leading-wildcard OR-scan only runs when the FTS leg is sparse; CJK terms always keep LIKE.
- **One-pass facets**: 7 aggregate scans → 1 `GROUP BY kind,status,scope,cold` pass folded in JS.
- **Single-read body fallback**: candidates read once with a precompiled regex (no `grep()` per row); cap 400 → 200.
- Measured on a 10k-record mixed store (quiet pass): facets **−47%**, catalog **−27%**, long-ASCII search **−48%**, generic search **−50%**, rescue search **−46%**, body fallback **−10%**; CJK unchanged. Real-archive hit@5 **95% → 95%**, cold **100%**, hit@1 73% → 70% (rescue tie-break); synthetic/demo 100%. Raw: `docs/assets/benchmarks/perf-optimization.json`.

## 0.3.0

### Added
- **Hot-body rescue**: identifier-like body tokens are indexed in `record_terms`; a rare-anchor rescue query ranks body candidates by exact query-term count and a `body: 5` rerank weight ranks them. Hot-body hit@1/@5 on the controlled fixture went **0%/0% → 100%/100%** (U13). Boundary-aware term matching fixes `inc-1` matching `inc-161`.
- **MCP parity tools**: `memory_list`, `memory_forget`, `memory_set_status` (10 tools total) + manual entries (U14).
- **Model profiles for xAI Grok, Cohere Command, Google Gemma, Microsoft Phi** (13 families); tables in docs/model-profiles.
- **Real Claude Code check**: `claude mcp list` recognizes the generated server (project-scoped approval is required by Claude Code); docs updated.
- Test harness now **112/112** (U13 body rescue, U14 MCP parity).

### Changed
- Claude `init` warns when configured L2-only (hooks vs MCP session-id mismatch).
- `docs/optimization-findings.md` rewritten with the fixed P0/P1 items and the remaining backlog.

## 0.2.2

### Fixed
- **Claude Code PreCompact** failed on transcripts larger than the 8 MB store body limit (no receipt, no archive). It now clips to the limit including the marker; harness U11 covers a > limit transcript.
- **PreCompact archives were unsearchable** (generic summary only, content lived in the body): the hook now stores a 900-char whitespace-normalized transcript head as `summary`; U6 asserts content search.
- **Injection budgets** overflowed by the wrapper tokens (catalog 1410/1400 for Claude, etc.); the formatter now reserves wrapper space so every profile stays within its budget (U12).
- **Codex adapter**: `init` crashed when `--project` did not exist (now creates it); config path now honours `CODEX_HOME`; TOML snippet verified with `tomllib` (spaces included), `--write-config` backup/idempotency verified.
- **Version drift**: MCP/Claude/Codex version strings now come from their `package.json` (were hard-coded 0.2.0 while packages were 0.2.1).

### Docs
- `docs/optimization-findings.md`: experiment report with measured recall gaps, fixed bugs and a prioritized backlog (body-only retrieval is the top remaining issue).

## 0.2.1

### Added
- **Model-specific retrieval reranking**: profiles now carry rerank weights (title/tags/summary/useWhen/abstract/recency/coldPenalty/bm25) that the MCP server, Claude Code hooks and Codex adapter pass into `store.search`, plus `queryTerms.maxTerms` (16–24). `AgentMemory` accepts `profileOverrides` so an integration can tune ranking without forking a profile.
- Tests U9–U10 cover the rerank merge and the engine → store propagation (108 tests total).

### Fixed
- (none)

## 0.2.0

### Added
- **Agent-agnostic core** `@qiuxu/memex-core` (no host dependencies): vocabulary, workspace identity, query terms, markdown+SQLite store with hot/cold tiers, hybrid retrieval, capacity compression, `AgentMemory` facade, model profiles and model-tailored manual. The DSH seam now re-exports it.
- **Universal MCP server** `@qiuxu/memex-mcp`: dependency-free stdio JSON-RPC; 7 tools, `memory://catalog` resource, profile `instructions`.
- **Claude Code adapter** `@qiuxu/memex-claude`: `init` writes `.mcp.json`, merges `.claude/settings.json` hooks (`SessionStart`, `UserPromptSubmit`, `PreCompact`, `SessionEnd`), injects a model-tailored `CLAUDE.md`; `PreCompact` archives the raw transcript verbatim.
- **Codex adapter** `@qiuxu/memex-codex`: `AGENTS.md` manual, `codex mcp add` command and `config.toml` writer with backup.
- **Model profiles** for Claude, GPT/o-series, Gemini, DeepSeek, Qwen, Kimi, GLM, Llama and a generic fallback: windows, token-estimation ratios, injection formats (XML/Markdown/plain), catalog/recall/open budgets, bilingual CJK manuals, digest prompts.
- Offline coverage: U1–U8 test the core/DSH parity, profile resolution, MCP JSON-RPC end-to-end, Claude init/hooks (incl. transcript archiving), Codex init/config, and cold compression through MCP (106 tests total).
- Docs: integrations matrix, Claude Code / Codex / generic MCP guides, model profiles, README repositioned as universal memory.

### Fixed
- Catalog now reports cold-only stores instead of claiming "no archived records" when every record is in the cold tier.

## 0.1.0

Initial open-source release.

- L1 → L2/L3 eviction through the shipped `compaction/prune` + surface-replace seam; sticky session-private L2 (10M) and workspace-shared L3 (100M) archives; capture policy and capacity notices with user consent.
- Lossless hot/cold tiers: bounded cold abstracts, restore (回热), cold GC and `coldQuotaTokens`; backup/verify/restore scripts.
- Hybrid retrieval: shared `memoryQueryTerms` extractor, FTS + LIKE legs, cold abstracts, lexical rerank; real-archive recall@5 95% (baseline 67%), cold recall 100%.
- Capacity compression: `memory_compress` with lossless cold spill and bounded map-reduce digests (2-way concurrency, retry/fallback, `ids:` enforcement, compression history).
- Surfaces: seven model tools, `/memory` command set, nine `/api/memory.*` routes, Web memory panel and context-ring integration; sensitive-content eviction policy.
- Offline harness: 98 tests with ESM host stubs; scale and recall benchmarks.
