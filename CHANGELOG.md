# Changelog

**Measurement note:** v0.8.0 recorded tail membership but could still reorder
same-millisecond records by random ID. Earlier counts remain historical; see
[docs/live-testing.md](docs/live-testing.md#deepseek-flash-results-2026-10-29).

## Unreleased

### Fixed — MCP integration readiness
- Scope MCP open, status, restore and forget by visible workspace and session; reject undeclared write fields, including supplied record IDs, and reject writes or compression into disabled levels. These are tool-level boundaries, not operating-system access controls.
- Use a fresh default L2 session per MCP process, and stop pinning the initializing project in newly generated global Codex configurations. Existing entries and records are not automatically migrated.
- Honor line-based `memory_open` paging and expose character continuation for oversized line windows. Advertise accurate read-only and destructive MCP tool annotations.
- Record four synthetic Codex integration attempts, including a denied write, invalid fixture and later scripted writable-workspace cycle; no production task A/B or autonomous lifecycle was completed. See `docs/production-readiness-20261101.md`.

## 0.65.0

### Added — 10M-token controlled long-context experiment
- Synthetic 10,000,000-token archive (2,000×5,000; 50% cold), 40 probes; baseline tail vs memex retrieval vs same-size distractor.
- Both DeepSeek Flash and Claude Haiku: baseline **0/40**, memex **40/40**, distractor **0/40**; retrieval hit@1 100%, median 4.94 ms; storage write 1.65 s, cold 1.32 s, DB 6.0 MB.
- Memex used fewer prompt tokens than the tail baseline (234/216 vs 536/548) while answering correctly.
- Wilson 95% CI: memex 91.2–100%; baseline/distractor 0–8.8%. Exact FACT-id metric; synthetic one-seed pilot with declared limitations.
- Report: `docs/long-context-10m.md`; aggregate: `docs/assets/benchmarks/long-context-10m.json`; scripts: `scripts/long-context-10m.mjs`, `training/long_context_10m_ab.py`.
- README updated with the 10M experiment. Repo **147/147**; active **98/98**.

## 0.64.0

### Added — full performance pass
- Materializer: 100/1k/5k pages, rule vs hybrid, p50/p95; hybrid 1.55/12.97/65.47 ms, rule 0.62/4.95/25.24 ms; all windows ≤1,800 and ok.
- Real replay (28 episodes): rule+core 0.089 ms mean, hybrid+core 6.18 ms mean; ~34 candidate pages, ~1.68k tokens.
- Store 500×5k tokens: write 0.5 s, DB 0.6 MiB, cold compress 0.48 s, cold GC 0.11 s; reads 0.03–4.5 ms.
- Recall 200 records/40 probes: baseline 0%, search/cold-grep 100% hit; medians 2.21–3.55 ms.
- Bottlenecks: hybrid CPU scaling with candidate count; repeated cost/render computation; cold search; external model latency dominates.
- Directions: FTS/BM25 prefilter, incremental accounting, learned-score cache, keep rule low-latency default, instrument duration.
- Repo **147/147**; active **98/98**.

## 0.63.0

### Added — production pager archive cards
- Context pager projects oversized L1/episode rows into source-marked archive cards before materialization; record files remain intact.
- Cards reuse compacted-summary sections, with `> [archive card; source: id; original archive remains intact]` and `> [end archive card]`; U51 covers it.
- This addresses the replay finding that raw L1 rows are not card-sized pages; rule+core replay hit rate had risen from 7.1% to 32.1% with offline cards.
- Active pager synced; restart required. Repo **147/147**; active **98/98**; no default change.
## 0.62.0

### Added — L1 archive cards for replay selection
- `training/build_l1_cards.py` builds local source-marked cards from compacted-summary sections; original L1 archives untouched.
- Replay selection with cards (`pageTokenCap=400`): rule+core hit rate **32.1%** (from 7.1%), hybrid+core **42.9%**, all windows ≤1,800.
- L1 cards help rule notably but hybrid gains limited; labels provisional; no third-party transfer.
- Repo **146/146**; active **98/98**; no default change.

## 0.61.0

### Added — query-aware excerpts for oversized pages
- Oversized pages now excerpt around the earliest query term, with `> [truncated excerpt; source: id]` and unchanged archive; U50 covers it.
- Local replay selection (28 provisional episodes): hybrid+core+pageTokenCap400 relevant-record hit rate **46.4%** (from 42.9%), all windows ≤1,800; no over-budget.
- Active materializer synced; restart required to load the query-aware excerpt behavior.
- Labels remain provisional; L1 raw-archive episodes still mostly unselected because a full archive span is not a card-sized page.
- Repo **146/146**; active **98/98**; no default change.
## 0.60.0

### Added — replay selection test + source-marked page excerpts
- Ran local replay selection on 28 provisional episodes; no third-party API calls.
- Relevant-record hit rates: rule 3.6%, rule+core 7.1%, hybrid 28.6%, hybrid+core 32.1%; with `pageTokenCap=400` excerpts, hybrid+core **42.9%**, all windows ≤1,800 tokens.
- Materializer now turns oversized pages into source-marked excerpts, preserving the original archive; U49 tests truncation marker/source and no mutation.
- Active config adds `materializerPageTokenCap: 400`; requires DSH restart.
- Labels are provisional; this is selection, not answer quality. No default change.
- Repo **145/145**; active **98/98**.

## 0.59.0

### Added — local replay episode extraction
- `training/extract_replay_episodes.py`: extracts L1-eviction and exact `memory_write` episodes from a DSH session + memex records; no network calls.
- Outputs local `replay-episodes.json`, `replay-review.md`, `replay-labels.csv`.
- Labels remain provisional; one continuous session is not an independent benchmark.
- Current local extraction: 28 episodes (10 L1 eviction + 18 exact memory-write), waiting for human review.
- Docs: `docs/replay-evaluation.md`; repo harness **144/144**; active **98/98**.

## 0.58.0

### Added — per-model cost model + reference cost estimates
- `training/quality_ab_protocol.py` now supports per-answer-model and judge cost rates (`costModel.answer[model]`, `costModel.judge[judge]`), validates them unless `--exploratory`, and reports `null` cost when missing.
- Exploratory real-memory results annotated with post-hoc reference costs: DeepSeek rule ~$0.00174/hybrid ~$0.00219; Claude Haiku rule ~$0.03548/hybrid ~$0.03612; judge ~$0.0613; total ~$0.1369. Not billing.
- Rule recalled all labeled relevant records; hybrid recall 0.5 on architecture; no consistent hybrid win. No default change.
- Active runtime verified: 23:31 process, budget 1800, formatTokens 334, rule 1794 / hybrid 1759, status ok.
- Repo **144/144**; active **98/98**.

## 0.57.0

### Added — authorized exploratory real-memory quality A/B
- User authorized real memory content to APIMaster; 5 real queries, rule vs hybrid, DeepSeek/Claude answerers, GPT-6 judge, both orders.
- Rule recalled all labeled relevant records; hybrid recall 0.5 on architecture. No consistent hybrid win; rule won both orders on multi and Claude next/KV; hybrid won both on DeepSeek architecture and Claude DSH.
- Latency 5–47s; no pricing supplied, so cost is a zero placeholder and not a valid comparison.
- Labels provisional; exploratory only. **No default change**; rule+core remains safer provisional default, hybrid optional.
- Runtime verified separately: 23:31 process, budget 1800, formatTokens 334, rule 1794 / hybrid 1759.
- Repo **144/144**; active **98/98**.

## 0.56.0

### Fixed — formatTokens breakdown + protocol dry-run
- `formatTokens` now derives from final rendered text minus body and prefix tokens; prior loaded version could report 0. Active file updated.
- Runtime: process 89051 started 23:22; config 0.54 trace fields visible; latest trace `formatTokens=0` predates the fix; restart required to observe the corrected field.
- Quality protocol dry-run with mock API: 2 synthetic queries, both answer orders, condition mapping, selection recall, answer/judge cost captured; no real memory sent.
- No default strategy change. Repo **144/144**; active **98/98**.

## 0.55.0

### Fixed — active trace version/format fields
- Runtime check: process started 23:19:07, final materializer mtime 23:06:34 — final materializer loaded.
- Active checkpoint trace still said `0.51` and lacked `formatTokens`/`renderedChars`; patched to `0.54` and added breakdown fields.
- One more DSH restart is required to see updated trace; materializer itself is active.
- Active memory **98/98**; repo **144/144**.

## 0.54.0

### Fixed — final-order budget, negative sorting, pressure tests, protocol
- Budget checks now use the final chronological rendered text, including format/header/prefix; U47 order-sensitive custom counter regression. Non-forced overflow reason is `budget`, not `forced`.
- Learned ordering objective: relevance score first, cheaper page on ties; equal negative scores no longer favor larger pages (`U48`, `U46`).
- `U44` now has real selection pressure: budget fits one page; Chinese query selects the KV page, no-query control selects chronology page.
- `training/quality_ab_protocol.py` hardened: human-verified labels, disjoint train/test keys, explicit real-memory authorization, non-zero cost model, both answer orders, raw answers, judge rationale, latency, selection recall, answer+judge cost.
- No default strategy change. Runtime: process 22:20:49; final materializer mtime 23:06:34 not loaded — restart required.
- Repo **144/144 offline**, **36/36 SQLite**, active **98/98**.

## 0.53.0

### Fixed — final rendered budget contract + sorting/quality protocols
- Materializer now counts the **final rendered text** (format markers, headers, prefix) for budget enforcement, not just page+prefix estimates; exposes `formatTokens`, `renderedChars`, tokenizer metadata, explicit empty/exceeded status; final rendered count used for every candidate check.
- New U45 (final rendered count/custom tokenizer) and U46 (negative/tied scores, different page lengths, partial budget, Chinese/mixed selection) tests; U44 CJK selection.
- Added `training/quality_ab_protocol.py` and `docs/quality-evaluation-protocol.md`: record/session-isolated dataset, human-verified labels, randomized condition mapping, per-question answers, judge rationale, tokens and cost.
- No default strategy change: active remains experimental hybrid topK8/core; current process was verified to have loaded v0.51 config but **not** the final-rendered budget fix — restart required.
- Corrected outdated README test counts (140/140 offline, 36/36 SQLite), public benchmark v0.30.0 note, and a benchmark JSON timestamp.
- Repo harness **142/142**; active tests **98/98**.

## 0.52.0

### Added — multi-query answer-quality evaluation
- 5 query types x optimized materializer (core tier, 1,800, topK8) x APIMaster DeepSeek/Claude x blind GPT-6 judge, both orders.
- Hybrid not consistently preferred: rule won/tied most cases; DeepSeek favored hybrid on DSH query; Claude split. TopK8 preferred by DeepSeek, topK1 by Claude.
- Conclusion: core-fact tier is the main coverage win; topK8 hybrid adds noise in several queries. Rule+core is safer default; hybrid opt-in until selective gating is validated.
- Raw: `multiquery-answer-quality.json`; harness **140/140**; active **98/98**.

## 0.51.0

### Added — real budget semantics, CJK tokenization, trace metadata
- Budget now covers page content + index prefix (+ reserve); every candidate addition checks total; empty/forced-over-budget statuses explicit; `overBudgetBy`, `overBudgetReason`, `forcedIds`, `omittedIds`, tokenizer/estimator metadata exposed.
- U42/U43 cover empty/forced/estimator behavior; 60-combination regression reports **0 silent over-budget results**.
- CJK/mixed tokenizer adds CJK unigrams/bigrams/trigrams; U44; weights not yet retrained on CJK data.
- Active trace now records budget status, over-budget reason, omitted IDs, tokenizer, config version.
- Remaining: BGE/semantic reranker, CJK weight retraining + English/Chinese comparison, human-verified labels, full multi-query answer A/B.
- Repo harness **140/140**; active memory **98/98**. Active DSH restart required.

## 0.50.0

### Added — all materializer optimizations
- Core-fact tier (`alwaysIncludeIds`): architecture/KV/DSH/priorities summaries guaranteed.
- Budget-aware learned rerank by score/token; `learnedPageMaxTokens` skips oversized candidates.
- `enforceTotalBudget`: returned tokens <= budget; near-duplicate diversity guard.
- Multi-query matrix on 41 records: all core facts hit; optimized hybrid tokens 1,428–1,753.
- Optimized answer quality: DeepSeek 7/6/7, Claude 7/6/9 (coverage/correctness/focus).
- Remaining: BGE/semantic reranker, full multi-query answer A/B, human-verified labels.
- Active config synced; DSH restart required. Harness **137/137**; active **98/98**.

## 0.49.0

### Added — selection matrix + optimization directions
- 41 records, 5 query types, budgets 1,200/1,800/2,400, topK 1/4/8/16; key-record coverage non-monotonic.
- Multi query: 3/4 key records at 1,200–1,800/topK8, 0/4 at 2,400/topK8; KV hit everywhere; DSH/architecture query-specific; tokens overshoot 1–8% due prefix.
- Active config set to 1,800 + topK8.
- Directions: budget-aware rerank/per-page caps; core-fact always-include tier; diversity constraints; semantic/BGE reranker or query routing; multi-query human-verified benchmark.
- Raw: `selection-matrix.json`, `selection-matrix-optimization.json`; harness **134/134**.

## 0.48.0

### Changed — active DSH hybrid + learnedTopK
- Synced learnedTopK materializer to the active DSH bundle and wired `materializerLearnedTopK` through checkpoint config.
- Active config: 2,400 budget, hybrid rerank true, learnedTopK 8, live query passthrough.
- Active memory tests **98/98**; repo harness **134/134**.
- Requires DSH restart.

Definition: hybrid = rule/budget safety-net selection plus query-aware learned top-K candidates under one token budget; not a separate model.
## 0.47.0

### Added — learnedTopK + normal-selection quality A/B
- Materializer supports optional `learnedTopK`: multiple learned candidates enter before chronological fill; U38 added.
- Normal selection (41 real records, 1,800 budget, no pinning): rule vs hybrid topK=8; APIMaster DeepSeek/Claude answerers, blind GPT-6 judge, both orders.
- Hybrid won **4/4**; rule coverage 0, hybrid 6–7. Hybrid included KV/DSH/priority facts but still missed some architecture detail.
- `learnedTopK` is not yet synced to the active DSH bundle.
- Raw: `quality-ab-normal-selection.json`; harness **134/134**.

## 0.46.0

### Added — updated-memory quality A/B
- The v0.45 A/B showed both contexts missing KV/DSH facts. Added three real memory records: KV 7B results, DSH default model, next priorities.
- Rebuilt hybrid context with those records pinned. Old hybrid 16 records vs updated 9 records.
- APIMaster `deepseek-flash` + `claude-haiku-4-5`; blind `gpt-6-astra`, both answer orders: **updated context won 4/4**.
- Claude updated answer reached 10/10 coverage; DeepSeek improved to 4/6. Missing facts were mainly a memory-content gap.
- Raw: `quality-ab-updated-memory.json`; harness **133/133**.

## 0.45.0

### Added — answer-quality A/B for hybrid materializer
- Real memory pages, multi-topic query, rule vs hybrid contexts; two answerers (DeepSeek Flash, Claude Haiku) and blind GPT-6 judge with both answer orders.
- Judge preferred hybrid in **4/4** orderings; hybrid answers were longer and covered more memex architecture/priorities.
- Both conditions still missed KV 7B results and DSH default-model facts; hybrid improves breadth but not sufficient coverage.
- Raw: `quality-ab-materializer.json` (aggregate only); harness **133/133**.

## 0.44.0

### Added — long-horizon memex vs no-memex A/B proof
- Controlled synthetic benchmark: 60 archived decisions, recent tail only, 10 probes whose facts exist only in the archive; two real API models.
- Baseline **0/10**; memex materialized archive **10/10**; same-size decoy archive **0/10** for both models. The gain is content-specific, not merely extra prompt tokens.
- Prompt-token cost: +2.3k tokens (Claude Haiku) / +3.6k (GPT-6 Astra) on this synthetic run.
- Raw: `long-horizon-memex-ab.json`; script: `training/long_horizon_memex_ab.py`; harness **133/133**.

## 0.43.0

### Added — online materializer A/B trace
- Active checkpoint records rule-only and hybrid selections per materialized turn (`form: materializer-ab`): query, rule/hybrid IDs, tokens, added/removed IDs.
- Injected window unchanged; A/B trace is best-effort.
- Analysis helper: `scripts/materializer-ab-report.py`.
- Active memory tests **98/98**; repo harness **133/133**.
- Requires one final DSH restart to activate the trace code.

## 0.42.0

### Changed — production hybrid config at 2,400 tokens
- Active DSH bundle now uses the LLM-labeled lexical reranker weights.
- Active materializer budget raised 1,800 → **2,400**; hybrid rerank remains enabled.
- LLM-labeled real-query val: rule **0.348** → hybrid **0.783** at 2,400 tokens (23 groups).
- Active tests **98/98**; repo harness **133/133**.
- Requires DSH restart; rollback config/weights backups documented.

## 0.41.0

### Added — LLM-labeled real-query evaluation
- Extracted 99 real DSH session queries; labeled 52 against 36 real archive records with an LLM judge; record-disjoint val 23 groups / 6 records.
- Hybrid recall vs rule: 500 **0.087 vs 0.217**; 1,800 **0.522 vs 0.522**; 2,400 **0.783 vs 0.348**.
- Finding: lexical hybrid is budget-sensitive; not safe as default at 1,800 tokens; needs more labels and budget-aware reranking.
- Raw: `llm-labeled-real-query-eval.json`; harness **133/133**.

## 0.40.0

### Added — DSH live-query hybrid rerank integration
- Active memory-checkpoint now extracts the newest direct user message and passes it into `memory.materializeContext`.
- Added `materializerHybridRerank` config (default false); active bundle enables it.
- Existing default rule path remains available via the flag.
- Active memory tests **98/98**; repo harness **133/133**.
- Rollback: bundle backup + `materializerHybridRerank: false`.

## 0.39.0

### Added — production API wiring for hybrid rerank
- `materializeStoreContext` and `engine.materializeContext` accept optional `query` + `learnedRerank` and forward them through the pager.
- Default rule path unchanged when options are absent.
- **U37** validates pager forwarding; **U36** validates hook; harness **133/133**.
- Next deployment step: pass the live user query from DSH checkpoint into this API.

## 0.38.0

### Added — optional JS hybrid materializer hook
- `materializeContext` accepts optional `query` + `learnedRerank`; adds the learned top candidate before chronological fill.
- 18 held-out real session-query groups: rule 0.222 → hybrid **0.333** at 500 tokens; 0.722 → **0.833** at 1,000; 0.778 → **0.889** at 1,500–2,400.
- Learned reranker is a lexical-feature logistic model (`packages/memex-core/lib/lexical-reranker.json`); default rule path unchanged; U36 verifies the hook.
- Raw: `js-hybrid-materializer.json`; harness **132/132**.

## 0.37.0

### Added — hybrid rule + learned materializer evaluation
- Real session-query val (18 groups): rule recall **0.222**, learned top-1 **0.500**, **rule ∪ learned 0.667**.
- Manual real-query val (4 groups): rule **0.500**, learned top-1 **0.250**, **union 0.750**.
- Conclusion: learned ranking alone is unstable; hybrid additive policy improves recall while keeping rules as a safety net.
- Raw: `hybrid-materializer-eval.json`; offline only, not JS-integrated; harness **131/131**.

## 0.36.0

### Added — real-query materializer generalization test (negative)
- Extracted real user queries from DSH session logs; manually labeled 29 query groups over 36 real archive records; val positive records disjoint from train.
- Rule materializer val recall **0.50**; learned BGE cross-encoder **0.25 accuracy/ranking**; zero-shot BGE **0.25**.
- Conclusion: earlier templated-split 0.963 does not survive real-query/record-disjoint validation; learned materializer is not production-ready.
- Raw: `real-query-materializer-eval.json`; harness **131/131**.

## 0.35.0

### Added — learned materializer prototype
- Trained a BGE-small cross-encoder on real archive train groups; evaluated query-aware budgeted selection against the actual JS rule materializer (500-token budget, 27 val groups).
- Learned selector **positive recall 0.963 vs 0.518** for rule materializer; avg selected tokens 387.8 vs 326.9; **8.64ms/query** on GPU.
- This is first evidence a learned query-aware policy materially beats the rule/budget materializer on the archive split.
- Caveats: templated queries, record-shared split, small corpus; not integrated into JS/DSH yet.
- Raw: `learned-materializer-eval.json`; code: `training/learned_materializer_eval.py`; harness **131/131**.

## 0.34.0

### Added — learned real-trace cross-encoder
- Fine-tuned BGE-small as a cross-encoder on the real archive split (36 records, 108 groups, 27 val groups).
- Held-out: **0.963 sample accuracy / pairwise ranking** vs **0.5926** for the BGE bi-encoder.
- This demonstrates learnability, but the split shares records and templated queries; not production generalization.
- Raw: `real-trace-cross-encoder.json`; code: `training/real_trace_cross_encoder.py`.
- **Materializer remains rule/budget/template-driven**; learned selector integration is the next step.
- Harness **131/131**.

## 0.33.0

### Added — forced-cold external fallback + batch-load A/B
- Hybrid native+connector with native cache empty: first request external hit (1,488 tokens injected, **0.431s**), second native **0.025s**.
- Batch external load: sequential 0.414s vs parallel 0.384s (~7%, single run).
- gzip store overhead 3.334s; clean compressed cold-load comparison not completed.
- Raw: `kv-cold-fallback-batch-load.json`; harness **131/131**.

## 0.32.0

### Added — prefix-length crossover experiment
- Real 7B-AWQ, unique random prefixes, 2 requests per length, 50% GPU KV reservation.
- Second request: baseline 0.0385–0.1392s; native prefix cache **0.0175–0.0249s**; external connector 0.0339–0.1020s; hybrid 0.0169–0.0238s.
- Native wins at every tested length; external beats recompute (~27% at 2,833 tokens) with first-store overhead.
- Hybrid native-first validated for short prefixes; reliable cold external fallback was not observed and needs a forced-cold test.
- Raw: `kv-length-crossover.json`; harness **131/131**.

## 0.31.0

### Added — six connector optimizations
- Hybrid native-first routing: external KV skipped when native prefix cache already computed the prefix (`num_computed_tokens > 0`).
- `min_prefix_tokens` threshold for external KV; short prefixes stay native.
- Parallel per-request layer KV loads (`ThreadPoolExecutor(8)`) with manifest validation.
- Low GPU reservation (`--gpu-memory-utilization 0.5`): 50,103/97,887 MiB used; cold external 0.385s, native subsequent 0.028s.
- Cold-only compression policy: gzip on external/cold KV; hot native path uncompressed.
- Grouped external loads (per request, parallel across layers).
- Raw: `six-optimizations.json`; harness **131/131**.

## 0.30.0

### Added — production benchmark, DSH runtime path, improved real-trace encoder
- Production throughput on real 7B-AWQ + connector: 13.1 rps @1, ~19 rps @8–32; p50 75.6ms → 1637ms as concurrency rises; single-process bottleneck.
- DSH desktop profile: added `local-memex` provider (tunnel → remote vLLM + MemexKVConnector), set profile default model to `qwen-7b-awq`; validated long-prompt requests and external-hit delta. Restart required; profile backup exists.
- Real-trace encoder: pretrained **BGE-small + linear head 0.5926** vs scratch 0.518 vs TF-IDF 0.444; still limited by 36 records/templated queries.
- Raw: `production-throughput-benchmark.json`, `dsh-local-memex-integration.json`, `real-trace-encoder-pretrained.json`; harness **131/131**.

## 0.29.0

### Added — KV strategy comparison and optimization directions
- Compared real 7B-AWQ with: no cache, native vLLM prefix cache, and Memex external KV on the same 1,856-token prefix workload.
- Second request: no-cache 0.0924s, native prefix cache **0.0187s**, external KV 0.0583s (8/8 external hits, 654MiB disk).
- Conclusion: native hot cache wins; external KV beats recompute and provides persistence/isolation. Recommended hybrid routing, async/pinned loads, prefix-length crossover, lower GPU KV reservation, cold-only compression.
- Raw: `docs/assets/benchmarks/kv-strategy-comparison.json`; harness **131/131**.

## 0.28.0

### Added — real Qwen2.5-7B-AWQ connector result
- Real 7B-AWQ weights downloaded, validated with safetensors, and served by vLLM 0.10.2.
- 8 prefixes × 2 requests, native prefix caching disabled: **8/8 external hits**, **652MiB** external KV, GPU **89,023/97,887 MiB (~91%)**.
- Warmup first request 70.5s; steady-state **store 0.2263s → hit 0.1184s**.
- Raw: `vllm-memex-kv-connector-real-7b.json`; harness **131/131**.

## 0.27.0

### Added — tenant isolation + concurrency + gzip tuning
- gzip level1 vs level9: both **222MiB** for 8 prefixes, nearly identical latency (~3.6s store / 0.43s hit); compression level is not the lever.
- Tenant isolation: cache hash includes `tenant_id`, manifest validates it; tenantB did not reuse tenantA folders and hit its own stored prefix.
- 32-way concurrency: **32/32 OK**, max 15.147s, **0 invalid caches** (compressed path, single process).
- Raw: `vllm-memex-kv-connector-hardening2.json`; harness **131/131**.

## 0.26.0

### Added — 7B connector hardening
- gzip compression at 7B dummy scale: **222MiB vs 652MiB** (~66% disk reduction), 8/8 hits; latency overhead measured (store 3.63s / hit 0.43s vs uncompressed 0.27s / 0.14s).
- Eviction with 100MiB cap: 5 evictions, final 84MiB/3 folders, 8/8 hits.
- Per-prefix `manifest.json` with file sizes + gzip magic validation; corrupted KV is detected, invalid folder evicted, request falls back to recompute with **HTTP 200** instead of 500.
- Raw: `vllm-memex-kv-connector-7b-hardening.json`; harness **131/131**.

## 0.25.0

### Added — 7B concurrency + real materialized window
- 7B dummy-weight server: **8 concurrent requests** sharing a materialized prefix → **8/8 OK**, max 0.756s, **7 external hits**, no errors.
- Real `context-materializer` window (2,037 prompt tokens) through the 7B connector: store **0.204s**, second-request hit **0.088s**.
- Validates concurrent load/store at 7B architecture scale; dummy weights, quality out of scope.
- Raw: `vllm-memex-kv-connector-7b-concurrency.json`; harness 131/131.

## 0.24.0

### Added — 7B architecture connector scale test (dummy weights)
- Real 7B weights failed to download cleanly, so ran Qwen2.5-7B architecture with `--load-format dummy` (28 layers, 14.2GiB): **8/8 external hits**, **652MiB** external KV / 8 prefixes, GPU **~91%**, mean store 0.2673s → hit 0.1348s.
- This validates 7B-scale architecture/memory/connector mechanics, **not model quality**.
- Raw: `docs/assets/benchmarks/vllm-memex-kv-connector-7b-dummy.json`.
- Harness **131/131**.

## 0.23.0

### Added — KV compression + real-trace encoder baseline
- `MemexKVConnector` supports gzip-compressed KV (`compress: true`): 6.9MiB vs 12.0MiB for 8 prefixes (~42% disk reduction), 8/8 external hits (tiny model).
- Real archive encoder baseline: 36 real records, 108 groups/540 samples; held-out **accuracy 0.518 / pairwise ranking 0.518** (near chance). Negative result; dataset/queries are too small and templated.
- Raw: `vllm-memex-kv-connector-compression.json`, `real-trace-encoder-baseline.json`.
- Harness **131/131**.

## 0.22.0

### Added — connector eviction
- `MemexKVConnector` supports `max_cache_mib` with LRU eviction of oldest prefix folders.
- Probe with 2MiB cap: 8/8 external hits, **7 evictions**, final cache 1.5MiB; mean store 0.0807s → hit 0.0179s (tiny model).
- Raw: `docs/assets/benchmarks/vllm-memex-kv-connector-eviction.json`.
- Boundary: disk safetensors, no compression yet.

## 0.21.0

### Added — end-to-end materializer → vLLM connector
- Generated a real materialized window with `context-materializer` (13 pages, 7,585 chars, stable hash `1498be8fc3ceb951`) and used it as the prompt prefix.
- First request stored **1,488 KV tokens**; second request with a different final question got an **external cache hit** and injected 1,488 KV tokens in **0.018s** (first request includes warmup 48.8s).
- Native prefix caching disabled; connector-only path.
- Artifacts: `docs/assets/benchmarks/materialized-window-e2e.txt`, `vllm-materialized-window-e2e.json`.
- Tiny random Qwen2 model avoids network downloads; connector mechanics are model-size independent (3B run covers scale).
- Harness **131/131**.

## 0.20.0

### Added — connector scale-up to Qwen2.5-3B
- Ran `MemexKVConnector` with **Qwen2.5-3B-Instruct** (36 layers), 8 prefixes × 2 requests, native prefix caching disabled.
- **8/8 external hits**; external KV **420MB** for 8 prefixes; GPU utilization **88,933/97,887 MiB (~91%)**.
- Warmup first request 65.9s; steady-state **store 0.1553s → hit 0.0964s**.
- Raw: `docs/assets/benchmarks/vllm-memex-kv-connector-3b.json`.
- Boundary: prototype connector, fixed prefix length, disk KV, no eviction/compression.

## 0.19.0

### Added — GPU-scaled 2-layer context encoder
- Trained a **2-layer, dim-128, 4-head** transformer context encoder on GPU with 3,000 synthetic hard-negative groups (15k query/page pairs).
- Held-out validation: **accuracy 1.0 / pairwise ranking 1.0**.
- Exported weights (`context-encoder-gpu2-weights.json`, 14MB) + report.
- Extended `context-transformer.js` to multi-layer weights; **U34** verifies exact Python↔JS logit parity and ranking.
- Harness **131/131**; boundary: synthetic data, reference model, not production.

## 0.18.0

### Added — multi-prefix vLLM KV connector benchmark
- Ran the `MemexKVConnector` prototype with 8 independent materialized prefixes (2 requests each), native prefix caching disabled.
- **8/8 second requests external-cache hits**; disk 141MB for 8 prefix folders; mean latency store **0.0617s** → hit **0.0390s** in this run.
- Raw: `docs/assets/benchmarks/vllm-memex-kv-connector-multiprefix.json`.
- Boundary: fixed prefix length, disk safetensors, 0.5B model, no eviction/compression; prototype.

## 0.17.0

### Added — custom vLLM KV connector (prototype)
- `training/memex_kv_connector.py`: adapted from vLLM 0.10.2 `SharedStorageConnector`; keys external KV by configured materialized-prefix token length.
- On Qwen2.5-0.5B with native prefix caching disabled: first request stores **1,488 KV tokens × 24 layers** (~29MB safetensors), second request with same prefix + different question gets **external cache hit** and injects **1,488 KV tokens**.
- Evidence: `docs/assets/benchmarks/vllm-memex-kv-connector.json`; docs updated.
- **Boundary:** fixed prefix length, disk KV, debug connector semantics; no eviction/compression/multi-tenant hardening yet.
- Harness **130/130**.

## 0.16.0

### Added — custom KV block paging probe on GPU
- Cloned RTX PRO 6000 Blackwell instance (96GB) restored with vLLM 0.10.2, Qwen2.5-0.5B and the model cache; vLLM prefix-cache validation reproduced (4,997 queries / 2,480 hits).
- New `training/kv_block_probe.py`: real Qwen2.5-0.5B KV tensors, 7,680 context tokens, 24 layers, 256-token blocks = **720 blocks** paged CPU↔GPU; rebuilt `DynamicCache` and decoded.
- **Paged vs direct cache reuse: max logit diff 0.0** (exact); paged vs full-context max diff 0.65625 (bf16), same next token.
- Raw: `docs/assets/benchmarks/kv-block-paging.json`.
- **Boundary:** reference HuggingFace paging, not vLLM custom KV connector integration; vLLM native prefix cache remains the runtime path.
- Harness **130/130**.

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
