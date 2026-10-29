# Installing dsh-memory into a DSH profile

dsh-memory is a **bundle** for DeepSeek Harness `0.2.1-rc.3`. It is installed into a DSH profile as a linked local package; it is not published to npm.

## 1. Build the runtime modules

```bash
git clone https://github.com/QiuXu-Tech/dsh-memory.git
cd dsh-memory
node scripts/build-bundle.mjs   # writes packages/dsh-memory/modules + @qiuxu/* symlinks
node scripts/check-bundle.mjs   # sources and generated modules must match
```

`packages/dsh-memory/modules/` and `packages/dsh-memory/node_modules/` are generated; do not commit or edit them.

## 2. Register the bundle

Use your DSH profile's plugin manager to install the **bundle package path**:

```
/absolute/path/to/dsh-memory/packages/dsh-memory
```

The profile links the package and reads its `dsh.bundle.patch` (`packages/dsh-memory/cordis.patch.yml`), which contributes eight rows:

| Row | Module | Purpose |
|---|---|---|
| `memory` | `@qiuxu/dsh-memory/local` | backend (`ctx.memory`) |
| `memory-checkpoint` | `@qiuxu/dsh-memory/checkpoint` | archive/receipt/catalog/recall, capacity notice |
| `memory-tools` | `@qiuxu/dsh-memory/tools` | seven model tools + manual section |
| `memory-evict` | `@qiuxu/dsh-memory/evict` | L1 eviction policy |
| `memory-compress` | `@qiuxu/dsh-memory/compress` | cold/digest compression |
| `memory-api` | `@qiuxu/dsh-memory/api` | nine `/api/memory.*` routes |
| `memory-ui` | `@qiuxu/dsh-memory/ui` | Web panel + ring bridge |
| `memory-commands` | `@qiuxu/dsh-memory/commands` | `/memory` command |

If your client-plugin loader requests a manifest whose package name must match the row specifier, some local DSH builds need the UI row addressed as a file URL instead of the subpath:

```yaml
- id: memory-ui
  name: 'file:///absolute/path/to/dsh-memory/packages/dsh-memory/modules/memory-ui/index.js'
  config: {}
```

## 3. Reload and enable

Reload the profile (or restart DSH). In a session:

1. Open the composer context ring → “额外上下文” → enable **L2 本会话** and/or **L3 工作区** (sticky once on, both off by default).
2. The memory panel button (“记忆”) appears in the composer tool row; the `/memory` command is available.
3. Optional config lives in the bundle patch per-row (see README) — override it in your profile patch to tune eviction ratios, compression batches, or notice thresholds.

## 4. Verify

- `/memory status` shows the two pools, cold counts and compression history.
- `node --import ../dsh-memory/test/register.mjs ../dsh-memory/test/run.mjs` from the repo passes 98/98.
- Data lives under `$DSH_HOME/memories` (`index.db`, `records/`, `cold/`).
