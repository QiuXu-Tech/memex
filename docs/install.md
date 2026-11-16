---
title: Install guide
layout: default
---

# Local source installation

memex is installed from a local checkout; it is not published to npm. Use Node.js 24+ and npm with a POSIX shell. The installation regression is exercised locally with Node.js 25.9.0; it does not establish Windows compatibility or every Node.js minor version.

## 1. Link the source packages

```bash
git clone https://github.com/QiuXu-Tech/memex.git
cd memex
npm run bootstrap              # creates node_modules/@qiuxu/* links to this checkout's packages
```

`bootstrap` is repeatable and links the core, MCP server, Claude Code and Codex adapters and sibling workspace packages. It does not download registry dependencies or call a model. These source entry points do not need DSH, a provider key, a generated bundle, or `test/register.mjs`. A bundle build alone does not create the repository-root links needed by source entry points.

Keep this checkout at its installed path: generated configurations contain absolute Node and entry paths. If you move it, regenerate or update the client configuration and inspect any existing Memex entry retained by the adapter.

Choose the [Claude Code](integrations/claude-code.md), [Codex](integrations/codex.md), or [generic MCP](integrations/mcp.md) integration. For DSH, continue below.

## 2. Build the DSH bundle

The DSH integration is a **bundle** for DeepSeek Harness `0.2.1-rc.3`, installed into a DSH profile as a linked local package. After the common bootstrap step:

```bash
node scripts/build-bundle.mjs   # writes packages/memex/modules + @qiuxu/* symlinks
node scripts/check-bundle.mjs   # sources and generated modules must match
```

`packages/memex/modules/` and `packages/memex/node_modules/` are generated; do not commit or edit them.

## 3. Register the DSH bundle

Use your DSH profile's plugin manager to install the **bundle package path**:

```
/absolute/path/to/memex/packages/memex
```

The profile links the package and reads its `dsh.bundle.patch` (`packages/memex/cordis.patch.yml`), which contributes eight rows:

| Row | Module | Purpose |
|---|---|---|
| `memory` | `@qiuxu/memex/local` | backend (`ctx.memory`) |
| `memory-checkpoint` | `@qiuxu/memex/checkpoint` | archive/receipt/catalog/recall, capacity notice |
| `memory-tools` | `@qiuxu/memex/tools` | four core tools + optional maintenance tools and manual section |
| `memory-evict` | `@qiuxu/memex/evict` | L1 eviction policy |
| `memory-compress` | `@qiuxu/memex/compress` | cold/digest compression |
| `memory-api` | `@qiuxu/memex/api` | nine `/api/memory.*` routes |
| `memory-ui` | `@qiuxu/memex/ui` | Web panel + ring bridge |
| `memory-commands` | `@qiuxu/memex/commands` | `/memory` command |

The `memory-tools` row exposes search, open, write and set-status by default. To expose the existing grep, index and restore tools as well, set `advancedTools: true` in that row’s config. Compression is registered separately by `memory-compress`.

If your client-plugin loader requests a manifest whose package name must match the row specifier, some local DSH builds need the UI row addressed as a file URL instead of the subpath:

```yaml
- id: memory-ui
  name: 'file:///absolute/path/to/memex/packages/memex/modules/memory-ui/index.js'
  config: {}
```

## 4. Reload and enable DSH

Reload the profile (or restart DSH). In a session:

1. Open the composer context ring → “额外上下文” → enable **L2 本会话** and/or **L3 工作区** (sticky once on, both off by default).
2. The memory panel button (“记忆”) appears in the composer tool row; the `/memory` command is available.
3. Optional config lives in the bundle patch per-row (see README) — override it in your profile patch to tune eviction ratios, compression batches, or notice thresholds.

## 5. Verify

From the repository root, run the installation regression without a test loader:

```bash
node --test test/audit-install.mjs
```

It starts from a separate source copy with no `node_modules`, runs `npm run bootstrap`, initializes adapters under empty temporary user directories with provider credentials absent, and launches fresh MCP processes from the generated Claude JSON and Codex TOML entries. It verifies initialize, tools/list, write, search, open, set-status and restart persistence, plus preservation of unrelated configuration/manual content. All projects and records are synthetic. It does not launch an actual Claude/Codex agent, exercise client approval UI, or verify a live DSH profile.

In DSH, check `/memory status` after registration and reload. Data lives under `$DSH_HOME/memories` (`index.db`, `records/`, `cold/`). The existing loader-based offline suite is a separate check of host behavior, not an installation prerequisite or proof of live profile registration.
