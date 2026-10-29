# Changelog

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
