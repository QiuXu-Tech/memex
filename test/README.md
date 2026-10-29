# Offline harness

`run.mjs` exercises every layer of the subsystem without a DSH installation:

- **Core/store**: schema migration, hot/cold tiers, FTS search (hybrid legs), cold abstracts, restore/GC, compression history, query terms.
- **Policies**: checkpoint archiving/receipt/catalog/recall, capacity notices (bilingual), L1 eviction (including sensitive-content routing and image/oversized guards).
- **Compression**: `memory_compress` cold/digest strategies, bounded batches, retry/fallback, ids enforcement, quota GC.
- **Surfaces**: tools row, `/memory` command, nine `/api/memory.*` routes, Web client module strings, bundle patch/module parity.
- **Operations**: backup/verify/restore scripts.
- **SQLite consistency**: multi-process lock contention, interrupted file transactions, recovery and independent backup/restore.
- **Universal adapters (v0.2.0)**: agent-agnostic core parity with the DSH seam, model-profile resolution/formatting/digest prompts, MCP stdio server end-to-end (init/tools/search/open/index/resources/compression), Claude Code init + hooks (catalog/recall/transcript archiving), Codex init/config, and cold compression through MCP.

The host packages (`@deepseek-ai/cordis`, `schemastery`, `dsh-llm`, `dsh-tools`, `dsh-home-paths`, `dsh-compaction`) are replaced by ESM loader stubs in `stubs/`; the fixture session/agent/measurement fakes live in `fake-ctx.mjs` / `fixtures.mjs`. Nothing touches `$DSH_HOME` — every test uses a throwaway temp root. The loader also resolves this repo's `@qiuxu/memex-*` packages (core, bundle subpaths) so the agent-agnostic path runs without `node_modules`.

```bash
node --import ./test/register.mjs ./test/run.mjs
node --import ./test/register.mjs --test ./test/sqlite-consistency.mjs
```

The offline harness prints one `ok <id> …` line per test; the SQLite suite reports its separate pass and failure counts.
