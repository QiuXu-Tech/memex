# Changelog

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
- **Agent-agnostic core** `@qiuxu/dsh-memory-core` (no host dependencies): vocabulary, workspace identity, query terms, markdown+SQLite store with hot/cold tiers, hybrid retrieval, capacity compression, `AgentMemory` facade, model profiles and model-tailored manual. The DSH seam now re-exports it.
- **Universal MCP server** `@qiuxu/dsh-memory-mcp`: dependency-free stdio JSON-RPC; 7 tools, `memory://catalog` resource, profile `instructions`.
- **Claude Code adapter** `@qiuxu/dsh-memory-claude`: `init` writes `.mcp.json`, merges `.claude/settings.json` hooks (`SessionStart`, `UserPromptSubmit`, `PreCompact`, `SessionEnd`), injects a model-tailored `CLAUDE.md`; `PreCompact` archives the raw transcript verbatim.
- **Codex adapter** `@qiuxu/dsh-memory-codex`: `AGENTS.md` manual, `codex mcp add` command and `config.toml` writer with backup.
- **Model profiles** for Claude, GPT/o-series, Gemini, DeepSeek, Qwen, Kimi, GLM, Llama and a generic fallback: windows, token-estimation ratios, injection formats (XML/Markdown/plain), catalog/recall/open budgets, bilingual CJK manuals, digest prompts.
- Offline coverage: U1–U8 test the core/DSH parity, profile resolution, MCP JSON-RPC end-to-end, Claude init/hooks (incl. transcript archiving), Codex init/config, and cold compression through MCP (106 tests total).
- Docs: integrations matrix, Claude Code / Codex / generic MCP guides, model profiles, README repositioned as universal memory.

### Fixed
- Catalog now reports cold-only stores instead of claiming "no archived records" when every record is in the cold tier.

## Unreleased

### Added
- Long-horizon A/B benchmark report (`docs/benchmark.md`, charts) + `scripts/long-horizon-eval.mjs`: dsh-memory 100% fact recall vs 60% compaction and 50% truncation (160K-token history, 80K window); 100% vs 10% window availability at 10M tokens.
- Animated demo (`docs/assets/demo.gif`) and social preview image (`.github/social-preview.png`).
- GitHub Pages documentation site (`docs/index.md` + Jekyll config): <https://qiuxu-tech.github.io/dsh-memory/>.
- Issue forms (bug/feature), PR template, and `SECURITY.md` with private vulnerability reporting.
- Upstream export tool `scripts/export-upstream.mjs` and [docs/upstream.md](docs/upstream.md) (DSH-shaped package tree + PR checklist).

## 0.1.0

Initial open-source release.

- L1 → L2/L3 eviction through the shipped `compaction/prune` + surface-replace seam; sticky session-private L2 (10M) and workspace-shared L3 (100M) archives; capture policy and capacity notices with user consent.
- Lossless hot/cold tiers: bounded cold abstracts, restore (回热), cold GC and `coldQuotaTokens`; backup/verify/restore scripts.
- Hybrid retrieval: shared `memoryQueryTerms` extractor, FTS + LIKE legs, cold abstracts, lexical rerank; real-archive recall@5 95% (baseline 67%), cold recall 100%.
- Capacity compression: `memory_compress` with lossless cold spill and bounded map-reduce digests (2-way concurrency, retry/fallback, `ids:` enforcement, compression history).
- Surfaces: seven model tools, `/memory` command set, nine `/api/memory.*` routes, Web memory panel and context-ring integration; sensitive-content eviction policy.
- Offline harness: 98 tests with ESM host stubs; scale and recall benchmarks.
