---
title: Install guide
layout: default
---

# Installing memex into a DSH profile

memex is a **bundle** for DeepSeek Harness `0.2.1-rc.3`. It is installed into a DSH profile as a linked local package; it is not published to npm.

## 1. Build the runtime modules

```bash
git clone https://github.com/QiuXu-Tech/memex.git
cd memex
node scripts/build-bundle.mjs   # writes packages/memex/modules + @qiuxu/* symlinks
node scripts/check-bundle.mjs   # sources and generated modules must match
```

`packages/memex/modules/` and `packages/memex/node_modules/` are generated; do not commit or edit them.

## 2. Register the bundle

Use your DSH profile's plugin manager to install the **bundle package path**:

```
/absolute/path/to/memex/packages/memex
```

The profile links the package and reads its `dsh.bundle.patch` (`packages/memex/cordis.patch.yml`), which contributes eight rows:

| Row | Module | Purpose |
|---|---|---|
| `memory` | `@qiuxu/memex/local` | backend (`ctx.memory`) |
| `memory-checkpoint` | `@qiuxu/memex/checkpoint` | archive/receipt/catalog/recall, capacity notice |
| `memory-tools` | `@qiuxu/memex/tools` | seven model tools + manual section |
| `memory-evict` | `@qiuxu/memex/evict` | L1 eviction policy |
| `memory-compress` | `@qiuxu/memex/compress` | cold/digest compression |
| `memory-api` | `@qiuxu/memex/api` | nine `/api/memory.*` routes |
| `memory-ui` | `@qiuxu/memex/ui` | Web panel + ring bridge |
| `memory-commands` | `@qiuxu/memex/commands` | `/memory` command |

If your client-plugin loader requests a manifest whose package name must match the row specifier, some local DSH builds need the UI row addressed as a file URL instead of the subpath:

```yaml
- id: memory-ui
  name: 'file:///absolute/path/to/memex/packages/memex/modules/memory-ui/index.js'
  config: {}
```

## 3. Reload and enable

Reload the profile (or restart DSH). In a session:

1. Open the composer context ring → “额外上下文” → enable **L2 本会话** and/or **L3 工作区** (sticky once on, both off by default).
2. The memory panel button (“记忆”) appears in the composer tool row; the `/memory` command is available.
3. Optional config lives in the bundle patch per-row (see README) — override it in your profile patch to tune eviction ratios, compression batches, or notice thresholds.

## 4. Verify

- `/memory status` shows the two pools, cold counts and compression history.
- `node --import ../memex/test/register.mjs ../memex/test/run.mjs` from the repo passes 98/98.
- Data lives under `$DSH_HOME/memories` (`index.db`, `records/`, `cold/`).
