---
title: Context materialization
layout: default
---

# Context materialization: from retrieval to virtual context

**Direction (locked):** stop treating the extra-context layer as a search index that returns evidence. Make it a **context virtualizer** that materializes an exact, ordered, budgeted window from archived context, with a seam for transformer context-specialist variants.

## Why materialization is the next step

Retrieval answers "which page is relevant?". A real context answers a different question: **"what exact ordered content should occupy the model's window right now?"**

The difference is measurable. In our tests:

- evidence-in-prompt restored evicted facts to 60/60 on the synthetic fixture, but the model saw a **reordered evidence block**, not the original event stream;
- the real tool loop (Claude Sonnet 5.5, 3/3) proved the model can page records itself, but it still received `tool` results rather than resident context;
- the remaining gap to "true context" is **structural/attention fidelity**, not fact recall.

## Three-layer target architecture

```
 canonical context event log
   (exact role, payload, tool schema, token offsets, attachments, sequence)
                │
   context pager / resident-set manager
   (L1 budget, pinning, eviction, page-in policy, KV hints)
                │
   materializer  ─────────────────────────────────────────────┐
   (deterministic text layout, stable prefix, chronological)   │
                │                                              │
   host prompt / KV-cache pager  ← transformer context specialist
```

1. **Canonical event log** — preserve what actually happened, not only a markdown body: role, tool name/arguments/result, content type, exact text, attachment references, sequence, checksum. This is the source of truth for exact materialization.
2. **Context pager** — owns the resident set: what stays in the window, what is pinned as orientation, what is paged out, and the model-specific budget.
3. **Materializer** — turns the resident set into a deterministic window: stable index prefix (prompt-cache friendly), chronological page bodies, explicit positions, omission report. The current heuristic implementation is `packages/memex-core/lib/context-materializer.js`.
4. **Transformer context specialist** — the learned/KV-aware layer that can replace or guide the materializer.

## Transformer context-specialist variants

These are **separate specialist components around the model**, not a replacement of the base model. All three share the same materializer interface, so the heuristic can be swapped for a learned variant.

### 1. Context encoder (salience specialist)

- Input: current task/query state + candidate pages (title/summary/body tokens).
- Output: per-page salience / expected recovery value.
- Architecture: small transformer encoder (or cross-encoder) with a per-family adapter.
- Trains on: evicted-fact recovery traces, tool-loop traces, reranker labels; the live A/B harness already produces the labels.
- Replaces: lexical rerank weights (`title/summary/body/coldAnchor/...`).
- Runtime: CPU/GPU sidecar or host-provided embedding service; must stay below the retrieval latency budget.

### 2. Context assembler (window-packing specialist)

- Input: candidate pages + token budget + model profile (window, format, attention quirks).
- Output: ordered selection, positions, section boundaries, maybe a compact "orientation receipt".
- Architecture: sequence-to-sequence/pointer transformer, or a lightweight policy network trained with task-success reward.
- Trains on: end-to-end task outcomes (answers, continuation quality), not just recall.
- Replaces: `materializeContext` selection/ordering heuristics.
- Key constraint: output must be deterministic and prompt-cache stable for repeated prefixes.

### 3. KV / paged-attention specialist (native-context path)

- Requires a host seam: paged KV blocks, attention sinks, prefix-cache keys, exact token spans.
- Architecture: attention variant with paged KV/prefix cache, optional block-level retrieval; position handling (RoPE scaling, sink tokens) chosen per model.
- The materializer supplies exact span boundaries and block descriptors; the specialist maps them to KV blocks.
- Fallback: text-only materializer when the host exposes no KV seam.
- This is the only path that can recover the **attention/positional** part of true context; API-only agents cannot reach it.

## Implemented today (offline)

`packages/memex-core/lib/context-materializer.js`:

- `CONTEXT_VARIANTS`:
  - `timeline-exact` — chronological verbatim pages + stable index prefix
  - `edge-attention` — chronology with pinned attention edges
  - `context-specialist-v1` — interface slot; `requiresKV: true`; heuristic fallback
- `materializeContext({ pages, budgetTokens, variant, pinnedIds, reserveTokens })`
  - deterministic ordering by `sequence`/`createdAt`
  - stable prefix hash (prompt-cache key)
  - budgeted inclusion, pinned-page forcing, explicit `omittedIds`
  - returned metadata: `tokens`, `includedIds`, `order`, `requiresKV`
- U26 covers chronology, determinism, budget, pinning, and the specialist variant contract.

**Not implemented yet:** training the encoder/assembler, wiring the pager into the host runtime, KV-block paging. This is deliberate: the interface and deterministic baseline come first.

## How it gets wired next

1. **Event capture**: extend the checkpoint/compaction seam to store canonical events alongside records (`role`, `tool`, payload, offsets, attachments).
2. **Pager integration**: checkpoint/compaction asks the materializer for a resident window instead of emitting a fixed catalog + recall block; the tail is materialized last, query-specific content stays after the stable prefix.
3. **Model profiles**: add context-window capabilities (`kvPaging`, `attentionSinks`, `prefixCache`, `materializerVersion`) to family profiles; model-specific variants can select different assemblers.
4. **Specialist training**: use the live traces (DeepSeek/GPT/Claude) and eviction/recovery labels to train the encoder first (cheap, measurable), then the assembler with task-success reward.
5. **Native path**: when the host exposes KV paging, route exact spans through the KV specialist; otherwise keep text materialization.

## Evaluation targets

- **Structural fidelity**: exact event round-trip, role/tool schema preservation, chronology and position checks.
- **Attention/position probes**: same fact at different positions/formats; does materialization preserve use?
- **Oracle gap**: full context (when it fits) vs materialized window on the same questions.
- **Task-level**: long-horizon continuation and recovery, not only fact recall.
- **Cost**: prompt tokens, stable-prefix cache hit rate, retrieval/paging latency.

The honest goal is not to claim "true context" for API-only agents. It is to make the extra-context layer **structurally exact and functionally indistinguishable where the host permits**, and explicitly mark the KV/attention gap where it does not.
