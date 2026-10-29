---
title: Upstreaming
layout: default
---

# Upstreaming dsh-memory

dsh-memory is currently a **standalone DSH bundle** (this repository). Upstreaming means contributing its nine packages in the shape the DSH runtime expects.

## Status (2026-10-29)

- The DSH runtime is distributed as an application; no public DSH monorepo was found on GitHub to open a package PR against.
- The community maintains a curated plugin list: [`web-casa/Awesome-DeepSeek-Harness-Plugins`](https://github.com/web-casa/Awesome-DeepSeek-Harness-Plugins). Listing the plugin there is the available public discovery path until an upstream package repo exists.
- This repository therefore ships an **export tool** that produces an upstream-shaped tree ready for review:

```bash
node scripts/export-upstream.mjs          # -> dist/upstream/ (git-ignored)
```

## Package mapping

| This repo | Upstream proposal | Role |
|---|---|---|
| `dsh-memory-seam` | `@deepseek-ai/dsh-memory-seam` | service contract, vocabulary, query-term extractor |
| `dsh-memory-local` | `@deepseek-ai/dsh-memory-local` | SQLite+markdown backend, hot/cold, FTS, history |
| `dsh-memory-checkpoint` | `@deepseek-ai/dsh-memory-checkpoint` | checkpoint policy + capacity notice |
| `dsh-memory-tool` | `@deepseek-ai/dsh-memory-tool` | seven model tools + prompt section |
| `dsh-memory-command` | `@deepseek-ai/dsh-memory-command` | `/memory` command set |
| `dsh-memory-api` | `@deepseek-ai/dsh-memory-api` | nine HTTP routes |
| `dsh-memory-ui` | `@deepseek-ai/dsh-memory-ui` | Web client half |
| `dsh-memory-evict` | `@deepseek-ai/dsh-memory-evict` | L1 eviction policy |
| `dsh-memory-compress` | `@deepseek-ai/dsh-memory-compress` | capacity compression |
| `dsh-memory` (bundle) | *stay local* | installable bundle patch for local profiles |

## PR checklist

1. Run `node scripts/export-upstream.mjs` and review `dist/upstream/README.md`.
2. Re-home the offline harness into the upstream test layout: per-package tests plus one integration smoke against a real host session.
3. Re-check licenses, `files`/`exports`, and peer-dependency versions (`@deepseek-ai/cordis`, `schemastery`, `dsh-llm`, `dsh-tools`, `dsh-compaction`) against the target DSH release.
4. Keep behavior contracts stable: L2/L3 stickiness, capacity-consent notice, digest `ids:` enforcement, nine routes, seven tools.
5. Add the plugin to the community list with a link to this repository and the demo GIF; attach the upstream tree as a branch or a patch in the PR description.

## What stays out of upstream

- The local **bundle patch** (`packages/dsh-memory/cordis.patch.yml`) — deployment-specific row wiring.
- The Web client row's `file:` URL fallback documented in [install](install.html).
- Private benchmark fixtures; only synthetic/demo suites are published.
