# Changelog

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
