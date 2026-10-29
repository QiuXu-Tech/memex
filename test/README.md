# Offline harness

`run.mjs` exercises every layer of the subsystem without a DSH installation:

- **Core/store**: schema migration, hot/cold tiers, FTS search (hybrid legs), cold abstracts, restore/GC, compression history, query terms.
- **Policies**: checkpoint archiving/receipt/catalog/recall, capacity notices (bilingual), L1 eviction (including sensitive-content routing and image/oversized guards).
- **Compression**: `memory_compress` cold/digest strategies, bounded batches, retry/fallback, ids enforcement, quota GC.
- **Surfaces**: tools row, `/memory` command, nine `/api/memory.*` routes, Web client module strings, bundle patch/module parity.
- **Operations**: backup/verify/restore scripts.

The host packages (`@deepseek-ai/cordis`, `schemastery`, `dsh-llm`, `dsh-tools`, `dsh-home-paths`, `dsh-compaction`) are replaced by ESM loader stubs in `stubs/`; the fixture session/agent/measurement fakes live in `fake-ctx.mjs` / `fixtures.mjs`. Nothing touches `$DSH_HOME` — every test uses a throwaway temp root.

```bash
node --import ./test/register.mjs ./test/run.mjs
```

Expected output ends with `# 98/98 passed`. The suite prints one `ok <id> …` line per test.
