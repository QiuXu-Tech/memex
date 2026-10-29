---
title: Live endpoint A/B
layout: default
---

# Live endpoint A/B: status and how to run

The live model-in-the-loop experiment is prepared but **blocked by credentials on this machine**. The harness is committed and its dry-run plan is reproducible; once a provider key (or a logged-in agent CLI) is available, it runs end-to-end.

## Harness

`scripts/live-ab.mjs` builds a deterministic 120-turn project history with 8 deep facts, keeps the newest 20 turns as "recent tail" and archives the rest (simulating L1 eviction). For each question it asks the same model in two conditions:

- **control** — only the recent tail is in the prompt; old facts are gone;
- **treatment** — the tail plus the memex `memory_search` + `memory_open` evidence for that turn.

Answers are graded by exact `FACT-###` token; latency and provider usage are recorded.

```bash
# dry run (no network): prompts + sizes only
node --import ./test/register.mjs scripts/live-ab.mjs --dry-run --probes 4 --out /tmp/live-ab-dry.json

# live run per provider (keys from env; missing providers are skipped, not fatal)
ANTHROPIC_API_KEY=... node --import ./test/register.mjs scripts/live-ab.mjs --provider anthropic --probes 6 --out docs/assets/benchmarks/live-ab.json
OPENAI_API_KEY=...    node --import ./test/register.mjs scripts/live-ab.mjs --provider openai    --probes 6 --out docs/assets/benchmarks/live-ab.json
DEEPSEEK_API_KEY=...  node --import ./test/register.mjs scripts/live-ab.mjs --provider deepseek  --probes 6 --out docs/assets/benchmarks/live-ab.json
```

Default models: `claude-sonnet-5-5`, `gpt-6.1-sol`, `deepseek-flash` (override with `--model` or `ANTHROPIC_MODEL` / `OPENAI_MODEL` / `DEEPSEEK_MODEL`).

## Current status (2026-10-29)

| Check | Result |
|---|---|
| Dry run (4 probes) | ✅ prompts built: control ≈1,081 chars, treatment ≈3,586 chars per question; plan committed as `docs/assets/benchmarks/live-ab.json` |
| `ANTHROPIC_API_KEY` | ❌ not set in the environment |
| `OPENAI_API_KEY` | ❌ not set in the environment |
| `DEEPSEEK_API_KEY` | ❌ not set in the environment |
| Codex CLI | ❌ not installed on this machine |
| Claude Code CLI (2.1.283) | ✅ installed; **OAuth session expired** (`Failed to authenticate: OAuth session expired`) → live model calls blocked |
| Claude Code MCP config (renamed `memex`) | ✅ `claude mcp list` recognizes `memex` with the generated `--model claude-sonnet-5-5`, project approval pending as expected |

So the integration surface is verified live (client parses the generated config and starts the server), but **no model endpoint answered a prompt**. We deliberately did not fake or proxy live results.

## What to do next

1. Set one of the API keys above (or `claude login` to refresh the CLI session) and re-run the matching command.
2. The script appends provider results to the output JSON: per-probe `correct`, `ms`, `usage`, and aggregate `accuracy.control` vs `accuracy.treatment`.
3. Success criterion: treatment accuracy meaningfully above control (the offline evidence fixtures put control at 0% for evicted facts), with a bounded token/latency overhead.
4. Repeat with the 8 dedicated profiles (`--model claude-opus-5-5`, `gpt-6-astra`, `deepseek-flash`, …) to tune per-model budgets against real answers.
