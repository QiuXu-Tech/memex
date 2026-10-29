---
title: Model profiles
layout: default
---

# Model profiles

Every integration resolves a **profile** from the running model id, then tunes memory behavior per family. Profiles are data in `packages/dsh-memory-core/lib/model-profiles.js`; no host dependency is involved.

| Profile | Match examples | Window | Est. chars/token | Injection | Catalog / recall budget | Digest style |
|---|---|---|---|---|---|---|
| `claude` | `claude-sonnet-4`, `claude-opus-4` | 200K (1M beta) | 3.6 | XML tags | 1400 / 600 | bullets + `ids:` |
| `openai` | `gpt-5`, `gpt-5-codex`, `o3` | 400K (1M variants) | 4.0 | Markdown | 1200 / 500 | numbered + `ids:` |
| `gemini` | `gemini-2.5-pro`, `gemini-2.0-flash` | 1M (2M variants) | 4.0 | Markdown | 1600 / 600 | table + `ids:` |
| `deepseek` | `deepseek-chat`, `deepseek-reasoner` | 160K | 3.4 | Markdown | 900 / 400 | bilingual + `ids:` |
| `qwen` | `qwen-max`, `qwen3-coder` | 128K–1M | 3.5 | Markdown | 900 / 400 | bilingual + `ids:` |
| `kimi` | `kimi-k2`, `moonshot-v1` | 128K–256K | 3.5 | Markdown | 900 / 400 | bilingual + `ids:` |
| `glm` | `glm-4.6`, `chatglm` | 128K–200K | 3.6 | Markdown | 900 / 400 | bilingual + `ids:` |
| `llama` | `llama-3.1`, `mistral`, `mixtral` | 128K–1M | 4.1 | Plain text | 800 / 350 | numbered + `ids:` |
| `xai` | `grok-4`, `grok-3` | 256K–2M | 3.8 | Markdown | 1000 / 450 | numbered + `ids:` |
| `cohere` | `command-r-plus`, `command-a` | 128K | 4.0 | Markdown | 900 / 400 | numbered + `ids:` |
| `gemma` | `gemma-3-27b` | 128K | 4.0 | Markdown | 800 / 350 | numbered + `ids:` |
| `phi` | `phi-4`, `phi-4-mini` | 128K | 4.0 | Markdown | 800 / 350 | numbered + `ids:` |
| `generic` | anything else | 128K | 4.0 | Markdown | 900 / 400 | numbered + `ids:` |

## What a profile changes

- **Budgets** — how many tokens of catalog and auto-recall are injected, and how much body `memory_open` returns by default.
- **Injection format** — XML tags for Claude (`<memory-catalog>`), Markdown headings for GPT/Gemini/Qwen, plain bracketed blocks for smaller open models (less instruction drift).
- **Manual style** — explicit tool choreography for Claude, terse numbered steps for GPT, table-first reading for Gemini, **bilingual (English + Chinese)** guidance for DeepSeek/Qwen/Kimi/GLM where CJK prompts are common.
- **Digest prompt** — the compaction-summary prompt used by digest flows, tailored per family, always requiring an `ids:` line so evicted facts stay retrievable.
- **Defaults** — e.g. Claude/DSH keep both L2+L3, Codex/Gemini default to L3 project memory.

## Retrieval reranking

Each profile also carries **rerank weights** for the hybrid search: the store merges them over `DEFAULT_RERANK_WEIGHTS` (`title 3.0, tags 1.6, summary 1.4, useWhen 1.2, abstract 0.9, body 5.0, recency 0.4, coldPenalty 0.1, bm25 0.8`). The `body` weight applies to body-rescue hits (identifier-like terms found only in a record body). This is the ranking half of model-specific adaptation; the fields above tune injection and prompting.

| Profile | Rerank override | Why |
|---|---|---|
| `claude` | title 3.2 · useWhen 1.6 · recency 0.3 | tool-oriented; "when to read" matters more than freshness |
| `openai` | tags 1.8 · summary 1.5 · recency 0.55 | codex-style agents surface fresh labels and concise summaries |
| `gemini` | tags 2.0 · summary 1.6 · title 2.8 | large-context models tolerate broader recall; tag/summary anchors help |
| `deepseek` | abstract 1.3 · summary 1.5 · recency 0.35 | CJK sessions rely on bounded cold abstracts |
| `qwen` / `kimi` / `glm` | abstract 1.2 · summary 1.4 · recency 0.3 | CJK + long-context; damp recency |
| `llama` | title 3.4 · abstract 0.7 · recency 0.25 | lean ranking, less field noise |
| `generic` | defaults | fallback |

Integrations pass `profile.rerank` into `store.search` automatically (MCP, Claude Code hooks, Codex), and `profile.queryTerms.maxTerms` bounds query extraction (16–24 terms). Override per integration:

```js
new AgentMemory({ model: 'claude-sonnet-4', profileOverrides: { rerank: { tags: 2.2 }, windowTokens: 128_000 } })
```

## Override

```bash
# MCP or adapters
node packages/dsh-memory-mcp/bin/server.mjs --model my-custom-model --levels l2,l3

# programmatically
import { resolveModelProfile } from '@qiuxu/dsh-memory-core/model-profiles'
const profile = resolveModelProfile('my-model', { windowTokens: 64_000, catalogTokens: 500 })
```

## Limits (be honest)

- Window sizes and chars/token are **conservative estimates**, not vendor-tokenizer claims; exact token counts vary per provider and version.
- Reranking weights in the store are shared; profiles tune the *injection/prompting surface*, which is where models differ most in practice.
- A profile does not compensate for retrieval misses — combine it with `memory_grep`/`memory_index` when search ranks late.
- New families are cheap to add: one data entry + a test case; do not fork the core.
