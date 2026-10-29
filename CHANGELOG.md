# Changelog

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
