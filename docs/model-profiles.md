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
| `generic` | anything else | 128K | 4.0 | Markdown | 900 / 400 | numbered + `ids:` |

## What a profile changes

- **Budgets** — how many tokens of catalog and auto-recall are injected, and how much body `memory_open` returns by default.
- **Injection format** — XML tags for Claude (`<memory-catalog>`), Markdown headings for GPT/Gemini/Qwen, plain bracketed blocks for smaller open models (less instruction drift).
- **Manual style** — explicit tool choreography for Claude, terse numbered steps for GPT, table-first reading for Gemini, **bilingual (English + Chinese)** guidance for DeepSeek/Qwen/Kimi/GLM where CJK prompts are common.
- **Digest prompt** — the compaction-summary prompt used by digest flows, tailored per family, always requiring an `ids:` line so evicted facts stay retrievable.
- **Defaults** — e.g. Claude/DSH keep both L2+L3, Codex/Gemini default to L3 project memory.

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
