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

- **Eviction is context management, not deletion.** When L1 fills, the oldest balanced span is moved out *verbatim*; a receipt keeps the model oriented.
- **L2/L3 are sticky context pools.** Once a pool is enabled it stays enabled, so context that was moved out never silently disappears.
- **Paging-in replaces re-derivation.** The model uses `memory_search` / `memory_open` to page the right evidence back into its window, paying for what it needs instead of re-reading history.
- **Every pool is budgeted.** Catalog/recall/open budgets are tuned per model family; context is injected in bounded blocks, never dumped.

## Terminology: memory concepts → context concepts

| What people call it | What it actually is here |
|---|---|
| memory record | a **context page** (verbatim, addressable, with a "when to read" hint) |
| memory search | **context lookup** / candidate pages for paging-in |
| memory_open | **page-in** one page to the model window |
| catalog injection | **context index** for the current window |
| L1 eviction | **context spill** from the working set |
| cold tier | **context swap area** (lossless) |
| capacity compression | **context compaction** (cold spill, optional digests) |
| memory panel / context ring | **context budget UI** (what is hot/cold, what is shared) |

## Why it is a layer, not an app

1. **It is window-aware.** Operations are tied to the model's context: eviction ratios, injection budgets, per-model profiles, reasoning-mode guidance.
2. **It is lossless before it is clever.** Raw context is archived verbatim; summaries are optional and never the source of truth.
3. **It is automatic.** No curation step: capture happens at eviction/compaction, and retrieval is driven by the model's own tool calls or auto-recall.
4. **It is scoped.** L2 private to a session, L3 shared by workspace; sensitive content policy keeps secrets private.
5. **It is measured.** In the v0.8.1 + tail-fix synthetic 100M-token pool, the SQLite index was 10.5 MiB after writing and 28.0 MiB after cold spill; the measured card-field search median was 10.36 ms before and 28.08 ms after cold spill. These are shared-machine fixture results, not production guarantees (see [evaluation](evaluation.html) and [benchmark](benchmark.html)).

## What this changes in practice

- The question is not "what facts should we store?" but **"what does the model need in its window right now, and what can safely leave it?"**
- The quality metric is not only recall, but **context efficiency**: how many tokens are spent to page in the decisive evidence, and how much context stays available without bloating the prompt.
- The failure mode is explicit: if evidence is missing, the model reports it (as DeepSeek Flash did in our live runs) rather than hallucinating; the gap becomes a measurable retrieval target (see [live validation](live-testing.html)).

## Reading guide

- [Architecture](architecture.html) — eviction seam, pools, retrieval, compression.
- [Model profiles](model-profiles.html) — context budgets per model family.
- [Evaluation](evaluation.html) / [Benchmark](benchmark.html) — retrieval, capacity and long-horizon A/B numbers.
- [Live validation](live-testing.html) — DeepSeek Flash multi-seed and tool-loop results.
