---
title: Extra context, not just memory
layout: default
---

# Extra context, not just memory

Most "memory" products are note stores or RAG indexes: you curate facts, embed them, and hope retrieval surfaces something useful. Memex starts from a different object — **the model's context window itself**.

An agent's context is scarce, volatile and ordered: tokens compete for attention, old turns get compacted or dropped, and the model can only reason over what is currently paged in. Memex treats conversation and tool history as a **context hierarchy**, and puts a high-performance layer between raw history and the model window.

## The context hierarchy

```
 raw session / tool history
        │
        ├─ L1  native context window          (the model's working set)
        ├─ L2  session context pool   (10M)    private to this conversation
        ├─ L3  workspace context pool (100M)   shared across sessions in a cwd
        └─ cold context tier                   verbatim, zero-LLM spillover
```

- **Eviction is context management.** DSH can move eligible older text spans out of L1 and issue a receipt; image-bearing, oversized or sensitive spans may be skipped.
- **L2/L3 are sticky context pools.** Once enabled for a session they remain enabled, subject to an adapter's explicit scope restrictions. Records can still be forgotten or removed by configured cold-tier garbage collection.
- **Paging-in can avoid re-derivation.** The model can use `memory_search` / `memory_open` to retrieve selected evidence instead of re-reading all history; finding and selecting the right evidence is not guaranteed.
- **Every pool is budgeted.** Catalog/recall/open budgets are tuned per model family; context is injected in bounded blocks, never dumped.

## Terminology: memory concepts → context concepts

| What people call it | What it actually is here |
|---|---|
| memory record | an addressable **context page** with a "when to read" hint; rendered content may be clipped |
| memory search | **context lookup** / candidate pages for paging-in |
| memory_open | **page-in** one page to the model window |
| catalog injection | **context index** for the current window |
| L1 eviction | **context spill** from the working set |
| cold tier | **context swap area** (lossless) |
| capacity compression | **context compaction** (cold spill, optional digests) |
| memory panel / context ring | **context budget UI** (what is hot/cold, what is shared) |

## Why it is a layer, not an app

1. **It is window-aware.** Operations are tied to the model's context: eviction ratios, injection budgets, per-model profiles, reasoning-mode guidance.
2. **It preserves captured source events.** DSH compaction retains captured event envelopes in SQLite alongside a rendered record; rendering can clip content and externally referenced attachment bytes are not guaranteed. The cold tier moves stored records without an LLM.
3. **It can capture automatically.** Enabled hooks capture eligible context at eviction or compaction; incomplete sources or unavailable private scope can cause a skip. Retrieval is driven by the model's tool calls or auto-recall.
4. **It is scoped.** Memex filters L2 by session and L3 by workspace; processes with direct access to stored files are outside that logical boundary. Sensitive-content detection can redirect or skip detected spans, but is not a guarantee that all secrets are detected.
5. **It is measured.** In the v0.30.0 synthetic 100M-token pool, the SQLite index was 10.7 MiB after writing and 28.3 MiB after cold spill; the measured card-field search median was 10.58 ms before and 28.33 ms after cold spill. These are shared-machine fixture results, not production guarantees (see [evaluation](evaluation.html) and [benchmark](benchmark.html)).

## What this changes in practice

- The question is not "what facts should we store?" but **"what does the model need in its window right now, and what can safely leave it?"**
- The quality metric is not only recall, but **context efficiency**: how many tokens are spent to page in the decisive evidence, and how much context stays available without bloating the prompt.
- Missing evidence is a measurable retrieval failure, but a model may still make unsupported claims. Small live runs and [pager evaluations](pager-recall-evaluation.html) do not establish a general hallucination-prevention guarantee.

## Reading guide

- [Architecture](architecture.html) — eviction seam, pools, retrieval, compression.
- [Model profiles](model-profiles.html) — context budgets per model family.
- [Evaluation](evaluation.html) / [Benchmark](benchmark.html) — retrieval, capacity and long-horizon A/B numbers.
- [Live validation](live-testing.html) — DeepSeek Flash multi-seed and tool-loop results.
