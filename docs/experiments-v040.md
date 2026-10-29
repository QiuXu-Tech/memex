---
title: v0.4.0 experiments
layout: default
---

# v0.4.0 experiments: rename, adapter defaults, live readiness

Post-rename validation and experiments for **Memex 0.4.0** (2026-10-29). Every number below was produced in this repository; live model calls are the one item blocked by credentials (see [live testing](live-testing.html)).

## 1. Rename + defaults verification

| Check | Result |
|---|---|
| Offline harness after rename | **115/115 passed** (added U17 adapter defaults, U18 storage-root/env fallbacks) |
| Bundle build/parity | `build-bundle` + `check-bundle` clean (10 runtime modules, 8 DSH rows) |
| Fresh clone from `github.com/QiuXu-Tech/memex` | build + check + harness **115/115** (clean checkout, no `node_modules`) |
| Claude init defaults | writes `.mcp.json` with `--model claude-sonnet-5-5`; prints `Model profile: claude-sonnet-5-5` and recommended alternatives |
| Codex init defaults | emits `gpt-6.1-sol` config and recommends `gpt-6.1-terra` / `gpt-6-astra` |
| MCP profile discovery | `memex-mcp --list-profiles` → `deepseek-flash`, `claude-sonnet-5-5`, `gpt-6.1-sol`, `claude-opus-5-5` |
| Storage/env compatibility | `MEMEX_HOME` wins, `DSH_MEMORY_HOME` legacy fallback, `~/.dsh-memory` legacy dir migrated-by-detection to `~/.memex` |

## 2. Real-archive recall after body rescue + perf pass

40 curated real-archive questions (private archive, copied to a temp root):

| Metric | v0.2.1 baseline | v0.4.0 |
|---|---|---|
| hit@1 | 73% | **70%** |
| hit@3 | 90% | 90% |
| hit@5 | 95% | **95%** |
| cold recall | 100% | **100%** |
| p50 | 0.95 ms | 1.37 ms (load ≈3) |

The hit@1 delta is the body-rescue tie-break trade-off documented in the optimization report; hit@5/cold recall are unchanged.

## 3. Profile validation (post-rename rerun)

12 comparison profiles on the seeded hot/cold/title fixture (`docs/assets/benchmarks/profile-validation.json`):

- **Cold start:** MCP `initialize` 45–50 ms p50, first `memory_search` 2–3 ms — dedicated profiles add no startup regression.
- **Retrieval parity:** hot-body/cold/title hit@5 identical at 100% / 63% / 95%; dedicated Claude 5.5 profiles keep 100% hot-body hit@1 while base `claude` loses rank-1 (0%) due to its lower body weight.
- **Long-horizon overhead:** catalog injection 340–520 tokens/turn; 50 turns = 17k–26k tokens (1.7–2.6% of a 1M window). Catalog budgets are caps, not targets.

## 4. Live integration status

`claude mcp list` (Claude Code 2.1.283) after `memex-claude init`:

```
memex: node .../memex-mcp/bin/server.mjs --root ... --model claude-sonnet-5-5 --levels l2,l3 --cwd ... - ⏸ Pending approval
```

The renamed client config is recognized; the one-time project approval is expected. **Model calls are blocked:** no provider API keys, Codex CLI absent, and the local Claude Code OAuth session expired. The [live A/B harness](live-testing.html) is ready and its dry-run plan is committed; a [help-wanted issue #1](https://github.com/QiuXu-Tech/memex/issues/1) tracks the credential-assisted live run.

## 5. Improvement points found this round

| Priority | Finding | Suggested action |
|---|---|---|
| P1 | Live endpoint A/B blocked by credentials | provide `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` or refresh `claude login`; then run `scripts/live-ab.mjs` |
| P1 | Cold-body recall stuck at **63%** for every profile | index a bounded cold-body excerpt (e.g. first/last 2 KB) or automatically suggest `memory_grep` in the recall injection |
| P2 | Catalog budgets are underused (content 340–520 vs 900–2200 caps) | scale pinned/recent card counts with the profile budget; measure catalog visibility vs tokens |
| P2 | MCP tools still use `default-session` while hooks use the client session id | allow project-level session mapping or default MCP captures to L3 (already warned by `init` for L2-only) |
| P3 | One-time MCP approval is easy to miss | print the `claude mcp list` approval hint in `init` output (partially documented) |
| P3 | Tokenizer estimates are conservative and unverified | once live keys exist, compare request token usage against `profileTokens()` and adjust `charsPerToken` |
