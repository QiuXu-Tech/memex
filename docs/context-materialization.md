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

## Implemented today (v0.13.0)

**1. Canonical event capture**
- `context-events.js`: role/type/content/tool-call/tool-result/attachment envelope, deterministic checksum, DSH adapter, materializer-page adapter.
- `context_events` store table + `appendContextEvents`/`listContextEvents`; seam/default no-op, local backend forwarding.
- Checkpoint captures canonical events alongside rendered cards; U27 verifies round-trip/persistence.

**2. Pager + materializer + runtime injection**
- `context-materializer.js`: chronology, stable prefix/hash, budget, pinned pages, omitted ids, variants.
- `context-pager.js` + `AgentMemory.materializeContext()`.
- **DSH runtime switch**: checkpoint config `materializer: 'off' | 'timeline-exact' | 'edge-attention'` (default off for compatibility). **Enabled by default in the v0.14 bundle** (`materializer: timeline-exact`); set `materializer: off` to restore catalog+recall. The pre-step injects a materialized resident window instead of catalog+recall; capacity notices/receipts stay. U28 covers pager replay.

**3. Transformer context encoder (trained reference)**
- `training/context_encoder.py` trains a tiny real transformer encoder (token embeddings, 2-head self-attention, FFN, mean pooling, relevance head) on synthetic context-page/query data.
- Exports `docs/assets/benchmarks/context-encoder-weights.json` + metrics; `context-transformer.js` loads the weights and reproduces the Python logits exactly in pure JS (U31 parity + ranking).
- Honest scope: **tiny synthetic-data reference**, not a production per-family model; interface is replaceable.

**4. KV/prefix host (runnable reference)**
- `context-kv-host.js`: `PagedKvContextHost` with real bounded paged blocks, LRU eviction, prefix cache and page table; `context-kv.js` capability negotiation + fail-closed fallback.
- `scripts/context-kv-host.mjs`: HTTP reference host (`/health`, `/capabilities`, `/prefix`, `/page-in`, `/page-out`, `/stats`).
- U32 covers paging/prefix/eviction. **This is a host-side reference, not a model runtime**; true KV tensors require an inference engine (vLLM/SGLang/DSH host).

**5. Structural fidelity evaluation**
- `scripts/context-fidelity-eval.mjs` → `docs/assets/benchmarks/context-fidelity.json`: event round-trip, chronology, stable prefix, pager canonical coverage, KV capacity/paging. All checks pass.

**Updated default (v0.14):** the DSH bundle now enables `materializer: timeline-exact` by default. **Still external:** production training on live traces/GPUs and native vLLM/SGLang/DSH KV-cache integration; the interfaces and reference implementations are in place, but no inference runtime with real KV tensors is available in this environment.

## A-route validation: real vLLM paged-KV prefix cache (v0.15.0)

A first **A-route** milestone ran on the GPU host:

- GPU: **NVIDIA RTX PRO 6000 Blackwell Server Edition, 96GB**, driver 590.44.01
- Torch 2.8.0+cu128 / CUDA 12.8 / compute capability (12, 0)
- **vLLM 0.10.2**, Qwen2.5-0.5B-Instruct, `--enable-prefix-caching`
- Two requests sharing a **stable ~2,498-token context prefix**, differing only in the final question

Result from vLLM `/metrics`:

```text
prefix_cache_queries_total = 4997
prefix_cache_hits_total    = 2480
second-request prefix hit ratio ≈ 2480 / 2499 = 99.2%
overall hit ratio              ≈ 49.6%
```

The second request reused the materialized stable prefix through vLLM's **native paged-KV prefix cache**. This is the first real-runtime confirmation of the materializer's stable-prefix contract.

Raw: [vllm-prefix-cache.json](assets/benchmarks/vllm-prefix-cache.json); probe: `training/vllm_prefix_cache_eval.py`.

**Boundary:** this is vLLM-native prefix caching, not yet a custom external paged-KV connector that maps materializer spans to hand-managed KV blocks. Production training and the custom connector remain next steps.

## Custom KV block paging probe (v0.16.0)

On the Blackwell GPU host we ran a real **KV-tensor paging** probe with Qwen2.5-0.5B (HuggingFace, 24 layers):

- prefill 7,680 context tokens → extract per-layer key/value tensors
- split KV along sequence into **256-token blocks** → **720 blocks**
- evict all 720 blocks to CPU, page them back to GPU
- rebuild a `DynamicCache` from blocks, decode the query, compare against direct cache reuse and full-context forward

Results (`docs/assets/benchmarks/kv-block-paging.json`):

- **paged vs direct cache reuse: max logit diff = 0.0** (exact reconstruction)
- paged vs full-context: max logit diff 0.65625 (bf16 path/context truncation), **same next token** (`we`)
- 720 KV blocks paged CPU↔GPU; GPU allocated ~3.4GB during probe

This validates the **span → KV block → page-in** mechanics on real KV tensors. It is **not** vLLM connector integration yet: vLLM 0.10.2 uses its own paged-attention allocator, and the custom connector (mapping materializer spans to vLLM KV blocks) remains the next integration step.

Raw: [kv-block-paging.json](assets/benchmarks/kv-block-paging.json); probe: `training/kv_block_probe.py`.

## Custom vLLM KV connector (v0.17.0)

A prototype **MemexKVConnector** for vLLM 0.10.2 now maps a materialized prefix to externally stored KV cache:

- adapted from vLLM's `SharedStorageConnector` (Apache-2.0), keyed by a configured materialized-prefix token length instead of the full prompt;
- first request: **store 1,488 KV tokens × 24 layers** (Qwen2.5-0.5B) to `/root/memex-kv` as safetensors (~29MB);
- second request with the same materialized prefix but a different final question: **external cache hit**, then **inject 1,488 KV tokens** into vLLM's paged KV buffer;
- native prefix caching disabled, so the connector is the only external KV path.

Key logs:

```text
MEMEX store KV tokens=1488 layer=model.layers.0..23
MEMEX match prefix_len=1488 folder=/root/memex-kv/...
MEMEX EXTERNAL CACHE HIT prefix_tokens=1500
MEMEX inject KV tokens=1488
```

Raw: [vllm-memex-kv-connector.json](assets/benchmarks/vllm-memex-kv-connector.json); connector: `training/memex_kv_connector.py`.

**Boundary:** prototype uses a fixed prefix length, local-disk safetensors, and vLLM's debug connector semantics; block eviction/compression, multi-tenant isolation, and production hardening remain.

## Multi-prefix connector benchmark (v0.18.0)

Following the single-prefix validation, the same `MemexKVConnector` was exercised with **8 independent materialized prefixes** (2 requests each, different final questions):

- native prefix caching disabled; connector-only KV path
- **8/8 second requests** hit the external cache
- disk: **141MB** for 8 prefix folders (24 layer files each)
- mean latency in this run: **store 0.0617s → hit 0.0390s** (~1.6× faster; includes API overhead, not a production benchmark)

Raw: [vllm-memex-kv-connector-multiprefix.json](assets/benchmarks/vllm-memex-kv-connector-multiprefix.json).

## GPU-scaled context encoder (v0.19.0)

A larger single-layer GPU reference (DIM 128 / 4 heads / vocab 2048 / hard negatives) was trained first; then a **2-layer** version:

- data: 3,000 synthetic groups with hard negatives (15k query/page pairs), 500 held-out groups
- model: 2 encoder layers, dim 128, 4 heads, max length 128
- result: validation **accuracy 1.0 / pairwise ranking 1.0**
- weights: `docs/assets/benchmarks/context-encoder-gpu2-weights.json` (14MB); report: `context-encoder-gpu2.json`
- JS forward now supports multi-layer weights and reproduces the Python logits exactly (U34 parity)

This is a GPU-trained **reference** specialist, not a production per-family model; real traces and larger training remain.

## 3B model + custom connector (v0.20.0)

The same `MemexKVConnector` was run with **Qwen2.5-3B-Instruct** (36 layers) on the 96GB GPU:

- 8 materialized prefixes × 2 requests, native prefix caching disabled
- **8/8 second requests external-cache hits**; **420MB** external KV for 8 prefixes
- first request includes torch.compile warmup (65.9s); steady-state (excluding warmup): **store 0.1470s → hit 0.0937s**
- GPU memory during run: **88,933 / 97,887 MiB** (~91% utilized)
- KV injection: 1,488 tokens per layer per hit

Raw: [vllm-memex-kv-connector-3b.json](assets/benchmarks/vllm-memex-kv-connector-3b.json).

**Boundary:** prototype connector, fixed prefix length, disk safetensors, no eviction/compression; 3B model, single process.

## End-to-end materializer → vLLM connector (v0.21.0)

This closes the loop: a **real `context-materializer` output** (13 pages, 7,585 chars, stable hash `1498be8fc3ceb951`) was used as the prompt prefix and passed through `MemexKVConnector`:

- prompt tokens 2,037; first request stores 1,488 KV tokens (warmup 48.8s)
- second request with a different final question: **external cache hit**, injects 1,488 KV tokens, **0.018s**
- no native prefix caching; connector-only path
- generated artifact: `docs/assets/benchmarks/materialized-window-e2e.txt`; report: `vllm-materialized-window-e2e.json`

This is the first end-to-end **materializer → connector → vLLM KV load** validation. The tiny random Qwen2 model avoids network downloads; connector mechanics are model-size independent (the 3B run covers scale).

## Connector eviction (v0.22.0)

`MemexKVConnector` now supports `max_cache_mib` and LRU prefix-folder eviction. Probe with a 2MiB cap:

- 8 prefixes × 2 requests, **8/8 external hits**
- **7 evictions**; final cache **1.5MiB**, 1 folder
- mean store **0.0807s → hit 0.0179s** (tiny random model)

Raw: `docs/assets/benchmarks/vllm-memex-kv-connector-eviction.json`.
Boundary: disk safetensors, no compression yet; tiny model.

## Compression + real-trace encoder baseline (v0.23.0)

### KV compression
- Added optional gzip compression to `MemexKVConnector` (`compress: true`).
- Tiny-model probe, 8 prefixes: **6.9MiB compressed vs 12.0MiB uncompressed** (~42% disk reduction), 8/8 external hits.
- Latency of the compressed path was not captured in this run.

### Real-trace encoder baseline (negative result)
- Built a dataset from the **real local memex archive** (36 records, 108 query groups, 540 samples).
- Trained the 2-layer encoder; held-out: **sample accuracy 0.518**, **pairwise ranking 0.518** — near chance.
- Cause: 36 records + templated queries are too small; this is an honest negative baseline, not a production model.
- Only aggregate metrics are committed; data/weights stay local.

## 7B architecture scale test (v0.24.0)

Real 7B weight downloads kept failing at the CDN, so the connector was exercised with the **Qwen2.5-7B architecture and dummy random weights** (`--load-format dummy`):

- 28 layers, no weight download; 14.2GiB model allocation
- 8 prefixes × 2 requests: **8/8 external hits**
- external KV **652MiB / 8 prefixes**
- GPU **88,939 / 97,887 MiB (~91%)**
- mean store **0.2673s → hit 0.1348s**

This validates **7B-scale architecture/memory/KV connector mechanics**, not model quality. Real AWQ weights remained in download.

Raw: `docs/assets/benchmarks/vllm-memex-kv-connector-7b-dummy.json`.

## 7B concurrency + real materialized window (v0.25.0)

On the 7B dummy-weight server (28 layers, ~91% GPU):

- **8 concurrent requests** sharing the same materialized prefix: **8/8 OK**, max 0.756s, **7 external hits** (one request stored, the rest loaded), no errors.
- Real `context-materializer` output (2,037 prompt tokens) through the connector: store **0.204s**, second request external hit **0.088s**.
- This exercises concurrent load/store races at 7B architecture scale; dummy weights mean quality is out of scope.

Raw: `vllm-memex-kv-connector-7b-concurrency.json`.

## 7B connector hardening (v0.26.0)

On the 7B dummy-weight server:

- **gzip compression:** 8 prefixes → **222MiB vs 652MiB (~66% disk reduction)**, 8/8 hits; however gzip CPU cost raised latency (mean store 3.63s / hit 0.43s vs uncompressed 0.27s / 0.14s).
- **Eviction:** 100MiB cap → 5 evictions, final 84MiB/3 folders, 8/8 hits.
- **Corruption fallback:** corrupted one `.gz` layer file → manifest validation detected it, evicted the invalid prefix, request returned **HTTP 200** (recomputed) instead of HTTP 500.

Raw: `vllm-memex-kv-connector-7b-hardening.json`.
Boundary: dummy weights; gzip level not tuned; single process.

## Tenant isolation + concurrency + gzip tuning (v0.27.0)

- **gzip level tuning:** level1 vs level9 both yield **222MiB** for 8 prefixes and nearly identical latency (store ~3.61s / hit ~0.43s); gzip CPU/serialization dominates, so compression level is not the lever.
- **Tenant isolation:** connector now keys the cache hash with `tenant_id` and validates the tenant in each `manifest.json`. Switching from tenantA to tenantB did not reuse tenantA folders; tenantB stored then hit its own prefix (first store 5.99s, second request 0.565s).
- **32-way concurrency:** 32/32 requests succeeded, max 15.147s, 32 external-hit log entries, **0 invalid caches** (single process, compressed path).

Raw: `vllm-memex-kv-connector-hardening2.json`.
Boundary: dummy weights; gzip latency not production-tuned; single process.

## Real Qwen2.5-7B-AWQ connector result (v0.28.0)

The real 7B-AWQ weights finally downloaded and passed safetensors validation. vLLM 0.10.2 + `MemexKVConnector`:

- 8 materialized prefixes × 2 requests, native prefix caching disabled
- **8/8 external cache hits**
- external KV **652MiB / 8 prefixes**
- GPU **89,023 / 97,887 MiB (~91%)**
- first request warmup **70.5s**; steady-state **store 0.2263s → hit 0.1184s**
- real Qwen2.5-7B-AWQ weights (not dummy)

Raw: `vllm-memex-kv-connector-real-7b.json`.
Boundary: synthetic prefix workload, single process, prototype connector; model quality of generated answers not evaluated here.

## KV strategy comparison (v0.29.0)

Same real Qwen2.5-7B-AWQ, 8 prefixes ×2 requests, 1,856-token prefix:

| strategy | first | second |
|---|---:|---:|
| no cache | 0.0907s | 0.0924s |
| native vLLM prefix cache | 0.0922s | **0.0187s** |
| Memex external KV | 0.1468s | 0.0583s |

- Native hot cache wins clearly.
- External KV beats recompute but is ~3× slower than native on hit; first store overhead is high.
- Recommended: hybrid native-hot / external-cold routing; async/pinned loads; measure prefix-length crossover; reserve less GPU KV when external cache is used.

Raw: `kv-strategy-comparison.json`.

## Production benchmark + DSH runtime integration (v0.30.0)

### Production throughput (real 7B-AWQ + external connector)
64 requests / 8 prefixes / 1,856-token prefix:

| concurrency | throughput | p50 | p95 |
|---:|---:|---:|---:|
| 1 | 13.1 rps | 75.6ms | 82.3ms |
| 8 | 18.9 rps | 419.9ms | 444.0ms |
| 16 | 19.1 rps | 826.7ms | 842.6ms |
| 32 | 18.9 rps | 1637.4ms | 1779.4ms |

Throughput saturates around **19 rps**; latency scales linearly with concurrency, indicating a single-process/CPU/disk bottleneck. Raw: `production-throughput-benchmark.json`.

### DSH runtime integration
- Added provider **`local-memex`** to the desktop profile, baseURL `http://127.0.0.1:18000/v1`, served by a tunnel to the remote vLLM connector.
- Set the profile default model to **`local-memex/qwen-7b-awq`** (backup profile YAML exists).
- Verified through the tunnel: long prompt requests return 200 and increase external-hit count.
- **Restart DSH** for the provider/default model to take effect.
- Caveats: local 7B quality differs from DeepSeek Flash; tunnel is a prototype without auto-reconnect.

### Real-trace encoder with pretrained BGE
- Real archive (36 records, 108 groups): scratch 2-layer **0.518**, TF-IDF **0.444**, **BGE-small pretrained + linear head 0.5926**.
- Pretrained embeddings help, but the corpus/queries are still too small for production.

## Six optimizations (v0.31.0)

1. **Hybrid native-first routing** — connector now returns 0 external tokens when `num_computed_tokens > 0`; native prefix cache serves hot prefixes. Cold unique 2,933-token prefix: first external hit **0.363s**, second native **0.024s**; short prefixes stay native **0.013–0.020s**.
2. **Parallel batch KV load** — per-request layer files are loaded via `ThreadPoolExecutor(8)` before injection.
3. **Prefix threshold** — `min_prefix_tokens` (tested 2000) keeps short prompts on native cache; long/cold prompts can use external KV.
4. **Low GPU reservation** — hybrid at `--gpu-memory-utilization 0.5`: GPU used **50,103/97,887 MiB**, cold external 0.385s, subsequent native 0.028s.
5. **Cold-only compression** — external KV is the cold tier; gzip applies only there (222MiB vs 652MiB at 7B) and is not used on the hot native path.
6. **Grouped external loads** — files are grouped per request and loaded in parallel, with manifest validation before use.

Raw: `six-optimizations.json`.
Boundary: single process/GPU; batch load has no isolated A/B benchmark yet.

## Prefix-length crossover (v0.32.0)

Real Qwen2.5-7B-AWQ, unique random prefixes, 2 requests per length, 50% GPU KV reservation:

| prefix tokens | baseline 2nd | native 2nd | external connector 2nd | hybrid 2nd |
|---:|---:|---:|---:|---:|
| 545 | 0.0385s | **0.0175s** | 0.0339s | 0.0169s |
| 1,057 | 0.0618s | **0.0197s** | 0.0380s | 0.0187s |
| 1,889 | 0.0981s | **0.0228s** | 0.0623s | 0.0220s |
| 2,833 | 0.1392s | **0.0249s** | 0.1020s | 0.0238s |

- Native prefix cache wins at every tested length.
- External connector still beats recompute (~27% faster at 2,833 tokens) but pays a first-store cost.
- Hybrid native-first keeps short prefixes on native; long prefixes pay external store on first request then native on repeat.
- Cold external fallback was not reliably observed in the native+connector hybrid; it needs a forced-cold test.
- Raw: `kv-length-crossover.json`.

## Forced-cold fallback + batch load (v0.33.0)

- **Forced-cold hybrid**: with native cache empty and external KV present, first request took the external path (**1 external hit, 1,488 KV tokens injected, 0.431s**); second request used native cache (**0.025s**). This closes the earlier cold-fallback gap.
- **Batch load A/B**: cold external first request **0.414s sequential vs 0.384s parallel** (~7% in one run; variance-limited).
- **gzip store overhead**: compressed store measured **3.334s**; a clean compressed cold-load comparison was not completed because overlapping test servers interfered, so no compressed hit claim.

Raw: `kv-cold-fallback-batch-load.json`.
Boundary: single-run timings, API overhead included; gzip cold-load comparison incomplete.

## Learned real-trace cross-encoder (v0.34.0)

To move beyond the scratch encoder, BGE-small was fine-tuned as a **cross-encoder** on the real archive dataset (36 records, 108 query groups, templated queries):

| model | sample accuracy | pairwise ranking |
|---|---:|---:|
| BGE bi-encoder + linear | 0.5926 | 0.5926 |
| **BGE cross-encoder fine-tuned** | **0.963** | **0.963** |

The jump is real **on this split**, but the split shares records and query templates; it is evidence of learnability, not production generalization. Next: real user queries, record-disjoint splits, and a query-aware materializer policy.

Raw: `real-trace-cross-encoder.json`; code: `training/real_trace_cross_encoder.py`.
Boundary: 36-record corpus, templated queries, no JS/DSH integration yet.

## Learned materializer prototype (v0.35.0)

A query-aware selector was evaluated against the current rule/budget materializer on the real archive dataset (27 held-out query groups, 500-token budget):

| selector | positive recall | avg selected tokens | latency |
|---|---:|---:|---:|
| current rule materializer | 0.5185 | 326.9 | — |
| **learned BGE cross-encoder** | **0.963** | 387.8 | **8.64ms/query** |

- The learned selector ranks candidate pages by a fine-tuned BGE cross-encoder and greedily fills the budget.
- This is the first evidence that a **query-aware learned policy** materially beats the rule materializer on the real archive split.
- Caveats: templated queries, record-shared split, small corpus, GPU scoring; not yet integrated into JS/DSH.

Raw: `learned-materializer-eval.json`; code: `training/learned_materializer_eval.py`.

## Real-query generalization test (v0.36.0)

Extracted **real user queries from DSH session logs**, manually labeled to 36 real archive records, with positive records disjoint from train for validation:

- 29 query groups: 25 train / 4 validation
- rule materializer val positive recall: **0.50**
- learned BGE cross-encoder on real train: **0.25 accuracy / 0.25 ranking**
- zero-shot BGE alignment: **0.25**

This is a **negative generalization result**: the earlier 0.963 result came from a templated, record-shared split and does not survive real-query, record-disjoint validation. The rule materializer currently beats the learned selector on this tiny real set.

Raw: `real-query-materializer-eval.json`.
Boundary: only 4 val groups; labels noisy; this is a warning, not a final verdict.

## Hybrid rule + learned selection (v0.37.0)

Learned ranking alone is not reliable on real queries, so we evaluated a **hybrid policy**: keep rule-selected pages and add the learned top-1 candidate.

| dataset | val groups | rule recall | learned top-1 | **rule ∪ learned** |
|---|---:|---:|---:|---:|
| real session queries (nearest-message labels) | 18 | 0.222 | 0.500 | **0.667** |
| manual real-query labels | 4 | 0.500 | 0.250 | **0.750** |

Takeaway: **rule-only is a weak baseline; learned alone is unstable; hybrid union improves recall** while keeping the rule path as a safety net. Next: integrate the learned reranker as an additive candidate and validate at larger real-query scale.

Raw: `hybrid-materializer-eval.json`.
Boundary: small/noisy labels; union measured offline; not yet integrated in JS.

## JS hybrid materializer hook (v0.38.0)

`materializeContext` now accepts optional `query` + `learnedRerank`; when present it adds the learned top candidate before chronological fill. On 18 held-out real session-query groups:

| budget | rule recall | hybrid recall |
|---:|---:|---:|
| 500 | 0.222 | **0.333** |
| 1,000 | 0.722 | **0.833** |
| 1,500 | 0.778 | **0.889** |
| 2,400 | 0.778 | **0.889** |

The learned reranker is a lexical-feature logistic model (exported `lexical-reranker.json`); the default rule path is unchanged. U36 verifies the hook. Raw: `js-hybrid-materializer.json`.
Boundary: noisy nearest-query labels; lexical model; optional path only.

## Production API wiring for hybrid rerank (v0.39.0)

The learned rerank hook is now wired through the production materializer API path:

- `context-pager.materializeStoreContext({ query, learnedRerank })`
- `engine.materializeContext({ query, learnedRerank })`
- local backend forwards the same request
- default behavior remains unchanged when query/weights are absent
- **U37** validates pager forwarding; **U36** validates the hook
- 133/133 tests pass

This makes the hybrid path callable by DSH/adapters without changing the default rule path.
Boundary: DSH's active checkpoint call does not yet pass a live query; enabling it there is the next deployment step.

## DSH live-query integration (v0.40.0)

The active DSH memory bundle was wired for **optional query-aware hybrid rerank**:

- checkpoint `agent/pre-step` extracts the newest direct user message
- passes it as `query` into `memory.materializeContext`
- when `materializerHybridRerank: true`, passes the learned reranker weights
- default code path remains rule-only unless the flag is enabled
- active bundle config now sets `materializerHybridRerank: true`
- active memory subsystem tests: **98/98**
- repo harness: **133/133**

Rollback:

- bundle code: `backups/dsh-memory-next-prehybrid-*`
- bundle config: `dsh-memory-next/cordis.patch.yml.bak-prehybrid-*`
- disable flag: set `materializerHybridRerank: false` and restart DSH

## LLM-labeled real-query evaluation (v0.41.0)

Extracted 99 real DSH session queries; labeled 52 to real archive records with an LLM judge (top-3 relevance). Record-disjoint validation: 29 train / 23 val groups (6 val records).

| budget | rule recall | hybrid recall |
|---:|---:|---:|
| 500 | 0.217 | 0.087 |
| 1,000 | 0.478 | 0.435 |
| 1,500 | 0.478 | 0.478 |
| 1,800 | 0.522 | 0.522 |
| 2,400 | 0.348 | **0.783** |

Conclusion: **budget-sensitive**. Hybrid is not safe as default at the current 1,800-token budget; it becomes clearly better only at 2,400. Needs more labels and budget-aware reranking before enabling by default.

Raw: `llm-labeled-real-query-eval.json`.
Boundary: LLM labels not human-verified; small val; lexical reranker; active DSH config unchanged.

## Production config: LLM-labeled hybrid at 2,400 tokens (v0.42.0)

Deployed the LLM-labeled real-query setup to the active DSH bundle:

- active `lexical-reranker.json` replaced with the LLM-labeled-trained weights
- active `materializerMaxTokens` raised **1,800 → 2,400**
- `materializerHybridRerank: true` remains enabled
- active memory tests **98/98**; repo harness **133/133**
- validation on 23 LLM-labeled real-query groups: rule recall **0.348** → hybrid **0.783** at 2,400 tokens

Rollback:
- config backups: `dsh-memory-next/cordis.patch.yml.bak-pre2400-*`
- weights backup: `modules/memory-core/lib/lexical-reranker.json.bak-*`
- disable with `materializerHybridRerank: false`

## Online A/B trace (v0.43.0)

The active checkpoint now records both selections for every hybrid materialization:

- `form: materializer-ab`
- `query`, `budgetTokens`
- `ruleIds`, `hybridIds`
- `ruleTokens`, `hybridTokens`
- `addedIds`, `removedIds`

This double materialization is best-effort and does not change the injected window. Analyze with:

```bash
python3 scripts/materializer-ab-report.py
```

Next: restart DSH once, accumulate real turns, then compare rule vs hybrid page/token deltas online.
## Long-horizon memex vs no-memex A/B (v0.44.0)

Controlled synthetic long-horizon benchmark (60 archived decisions, recent tail only; 10 probes for facts only present in the archive) with two real API models:

| model | condition | correct | accuracy | avg prompt tokens |
|---|---|---:|---:|---:|
| claude-haiku-4-5 | baseline: recent tail only | 0/10 | **0.0** | 3,222 |
| claude-haiku-4-5 | memex materialized archive | 10/10 | **1.0** | 5,532 |
| claude-haiku-4-5 | decoy archive (same size, facts replaced) | 0/10 | **0.0** | 5,566 |
| gpt-6-astra | baseline: recent tail only | 0/10 | **0.0** | 4,317 |
| gpt-6-astra | memex materialized archive | 10/10 | **1.0** | 7,905 |
| gpt-6-astra | decoy archive (same size, facts replaced) | 0/10 | **0.0** | 7,649 |

- memex archive recovers **10/10** long-horizon facts in both models; recent-tail baseline gets **0/10**.
- The **same-size decoy archive** also scores 0/10, so the gain is not merely extra prompt tokens.
- Cost: +2.3k (Claude) and +3.6k (GPT) prompt tokens on this synthetic run.

Raw: `long-horizon-memex-ab.json`; script: `training/long_horizon_memex_ab.py`.
Boundary: synthetic facts, all-fact archive, API models, not a real DSH session; tests 133/133.

## Answer-quality A/B for hybrid materializer (v0.45.0)

Real memory pages, multi-topic query, rule vs hybrid contexts, two answer models, blind judge with two answer orders:

| answerer | order | judge winner |
|---|---|---|
| deepseek-flash | forward | **hybrid** |
| deepseek-flash | reverse | **hybrid** |
| claude-haiku-4-5 | forward | **hybrid** |
| claude-haiku-4-5 | reverse | **hybrid** |

- Rule context: 3 records / 2,903 chars; hybrid: 16 records / 4,542 chars.
- Hybrid answers were longer (DeepSeek 1,134 vs 536 chars) and more complete on memex architecture and priorities.
- However both missed the real KV 7B results and the DSH default-model facts; judge scores are low for both. **Hybrid improves breadth, not yet sufficient coverage.**
- Raw: `quality-ab-materializer.json`; aggregate only; real memory content was not committed.

## Updated-memory quality A/B (v0.46.0)

The previous quality A/B showed both contexts missing KV/DSH facts. Three real memory records were written (KV 7B results, DSH default model, next priorities), then the hybrid context was rebuilt with those records pinned.

- Old hybrid: 16 records, no KV/DSH/priority facts.
- Updated hybrid: 9 records including the three new records.
- APIMaster answerers: `deepseek-flash`, `claude-haiku-4-5`; blind `gpt-6-astra` judge; both answer orders.

Result: **updated context won both orders for both models.**

- Claude Haiku updated answer: judge coverage up to **10/10**, correctness 8, focus 9.
- DeepSeek Flash updated answer: coverage 4/6, correctness 6, focus 6 (improved but still missed some architecture/priority detail).
- Conclusion: missing key facts were primarily a **memory-content gap**, not only a selection problem.

Raw: `quality-ab-updated-memory.json`.
Boundary: one query; pinned updated context is not a production selector; aggregates only.
## Normal-selection quality A/B + learnedTopK (v0.47.0)

Added optional `learnedTopK` to materializer (multiple learned candidates before chronology); U38 covers it.

Normal selection (41 real records, budget 1,800, no pinning), rule vs hybrid with `learnedTopK=8`, APIMaster answerers and blind judge:

| answerer | forward | reverse |
|---|---|---|
| deepseek-flash | **hybrid** (coverage 7 vs 0) | **hybrid** (coverage 6 vs 0) |
| claude-haiku-4-5 | **hybrid** (coverage 6 vs 0) | **hybrid** (coverage 6 vs 0) |

- Rule context coverage score 0; hybrid 6–7.
- Hybrid now includes KV/DSH/priority facts via top-K retrieval, but still misses some architecture detail and adds unsupported specifics.
- `learnedTopK` is prototype; not yet synced to the active DSH bundle.

Raw: `quality-ab-normal-selection.json`; harness **134/134**.
## Active DSH config: hybrid + learnedTopK (v0.48.0)

Active memory bundle is now wired with:

- `materializer: timeline-exact`
- `materializerMaxTokens: 2400`
- `materializerHybridRerank: true`
- `materializerLearnedTopK: 8`
- checkpoint passes live query + learned weights into the materializer

Active memory tests: **98/98**; repo harness **134/134**.
Requires DSH restart to load the new materializer/checkpoint code and config.

Definition: **hybrid** is not a model. It is the materializer selection policy: rule/budget/pinned selection as the safety net, plus query-aware learned top-K candidates under the same token budget.
## Selection matrix: budget/topK optimization directions (v0.49.0)

Tested 41 real records, 5 query types, budgets 1,200/1,800/2,400 and learnedTopK 1/4/8/16. Key-record coverage is **non-monotonic**:

- Multi query: 3/4 key records at 1,200–1,800/topK8; **0/4 at 2,400/topK8**.
- KV: hit at all tested budgets for hybrid.
- DSH: hit at 1,200 and 1,800/topK4–8, missed at 2,400.
- Architecture: only specific 1,800/2,400 configurations.
- Returned tokens exceed budget by ~1–8% because the stable prefix is outside the page budget.
- Large learned top candidates can consume budget and reduce page count; topK alone is not budget-aware.

Active config was therefore set to **1,800 + topK8**, not 2,400 + topK8.

Optimization directions: budget-aware reranking with per-page caps; core-fact always-include tier; diversity/coverage constraints; semantic/BGE reranker or query routing; multi-query human-verified benchmark; validate with real DSH trace.

Raw: `selection-matrix.json`, `selection-matrix-optimization.json`.
## All materializer optimizations + multi-query matrix (v0.50.0)

Implemented:

1. **Core-fact tier** — `alwaysIncludeIds` guarantees architecture, KV 7B, DSH default model, next-priorities summaries before ordinary selection.
2. **Budget-aware rerank** — learned candidates ranked by score/token; oversized pages skipped via `learnedPageMaxTokens`.
3. **Total budget enforcement** — removable non-core pages dropped until returned tokens <= budget.
4. **Diversity** — near-duplicate learned candidates skipped (title/summary Jaccard >= 0.8).

Multi-query matrix on 41 real records, optimized config (1,800 budget, topK8, page cap 700, core tier): all core facts hit; tokens 1,428–1,753.

Optimized answer quality (multi query, 1,496-token context): DeepSeek Flash coverage 7 / correctness 6 / focus 7; Claude Haiku 7 / 6 / 9.

Not yet done: BGE/semantic reranker (current lexical + core tier), full answer-quality A/B on all five query types, human-verified labels.

Active bundle config is synced; **DSH restart required**. Tests: repo **137/137**, active **98/98**.

Raw: `all-optimizations-materializer.json`.
## Budget semantics + CJK + observability (v0.51.0)

### Budget accounting
Budget now covers **page content + index prefix** (plus `reserveTokens` headroom) and is checked on every candidate addition. Results expose:

- `budgetStatus`: `ok | empty | empty-budget | exceeded`
- `overBudgetBy`, `overBudgetReason`: `core | pinned | forced`
- `forcedIds`, `omittedIds`
- `budgetBreakdown`: page tokens, prefix tokens, reserved tokens, total, tokenizer, chars, estimate error note
- optional `tokenCounter` / `tokenizerName` for exact model tokenizer; default is chars/4 heuristic

Tests U42/U43 cover empty budget, forced-over-budget status, and estimator metadata. A 60-combination regression (5 queries x 3 budgets x 4 topK) now reports **0 silent over-budget results**.

### Selection optimizations
- Core-fact tier (`alwaysIncludeIds`, experimental/configurable — not a universal hardcode).
- Budget-aware learned rerank by score/token; `learnedPageMaxTokens` skips oversized candidates.
- Diversity guard for near-duplicate pages.
- The non-monotonic matrix is kept in `selection-matrix.json` as a regression case.

### CJK / mixed-language input
Lexical reranker now uses one tokenizer for ASCII words plus CJK unigrams/bigrams/trigrams (U44). Weights have not yet been retrained on CJK-specific data; that remains a validation item.

### Observability
Active checkpoint A/B trace now includes `budgetStatus`, `overBudgetBy`, `overBudgetReason`, `omittedIds`, `tokenizer`, and `configVersion`. Materialized-context trace includes the same budget metadata. Privacy: traces contain query/memory IDs and local content; retain locally, do not ship to third parties.

Active config remains 1,800 / topK8 / core IDs / page cap 700 / total enforcement; **DSH restart required**.
## Multi-query answer quality: hybrid is not universally better (v0.52.0)

After adding the core-fact tier, five query types were tested with optimized selection (1,800, topK8), APIMaster DeepSeek/Claude, blind GPT-6 judge, both orders:

- Multi: DeepSeek preferred rule 2/2; Claude split.
- KV: mostly rule/tie; hybrid only on one order.
- Architecture: rule/tie.
- DSH: DeepSeek preferred hybrid 2/2; Claude split.
- Next priorities: DeepSeek rule 2/2; Claude split.
- TopK comparison: DeepSeek preferred topK8; Claude preferred topK1.

Conclusion: **core-fact tier is the main coverage win; hybrid topK8 adds noise in several queries and is not consistently preferred.** Rule + core tier is the safer default; hybrid should be opt-in until a selective/query-aware gate is validated. This also shows why selection metrics alone are insufficient.

Raw: `multiquery-answer-quality.json`.
Boundary: one context per query, no human labels, judge variance; real memory content sent to APIMaster (aggregate only retained).
## Final-order budget, negative sorting, pressure tests, protocol (v0.54.0)

### Budget ordering
Budget is now evaluated on the **final chronological rendered text**, not the order in which pages were selected. A custom order-sensitive tokenizer regression (U47) confirms no silent over-budget result. Non-forced overflow reason is `budget`, not `forced`; forced core/pinned reasons remain explicit.

### Sorting objective
The learned candidate order is now: **highest relevance score first; ties prefer the cheaper page**. Equal negative scores therefore do not favor larger pages. U48 asserts the cheaper equal-negative page is selected under a tight budget; U46 covers negative/tied scores and partial budgets.

### Chinese pressure test
U44 now uses a budget that fits only one page. The Chinese query selects the KV page; the no-query control selects a different chronology page. This demonstrates query-driven selection, not just "function executes".

### Quality A/B protocol
`training/quality_ab_protocol.py` now checks:

- human-verified labels unless `--exploratory`
- disjoint train/test keys
- explicit `--authorize-real-memory` for real memory
- non-zero cost model required unless exploratory
- both answer orders, with condition mapping
- per-question raw answers, judge rationale, latency, selected-window recall, answer/judge cost

### Runtime state
Process started 22:20:49; active config loaded; final sorting/budget materializer has mtime 23:06:34 and is **not loaded** until DSH restart. No default strategy change.

Repo **144/144 offline**, **36/36 SQLite**, active **98/98**.
## Runtime verification after v0.54 restart (v0.55.0)

- DSH process started **23:19:07**; active materializer mtime **23:06:34**, so the final sorting/budget materializer was loaded.
- Active checkpoint trace was still labeled `0.51` and lacked `formatTokens`/`renderedChars` because the checkpoint trace fields were updated after that process start.
- Patched active checkpoint trace to `configVersion: 0.54` and to include `formatTokens`, `renderedChars` from the materializer breakdown.
- One more DSH restart is required to observe those fields; the materializer itself is already loaded.
- Active memory tests **98/98**.

=== Remaining evaluation requirements ===
- Human-verified, record/session-isolated labels.
- Both answer orders saved per question with condition mapping.
- Selected-window recall, answer correctness, unsupported claims, latency, answer+judge cost.
- Explicit real-memory authorization before third-party API use.
## Format-field fix + protocol dry-run (v0.56.0)

- `formatTokens` is now computed from the final rendered text minus body and prefix tokens; the previous loaded version could clamp it to 0. Code + active file updated.
- Runtime: process 89051 started 23:22; config 0.54 trace fields are visible; `formatTokens=0` in the latest trace came from the pre-fix breakdown. One restart is required to observe the fixed field.
- Quality protocol dry-run against a mock API: 2 synthetic queries, both answer orders, condition mapping, selection recall, answer and judge cost all captured; total mock cost 0.00416. No real memory sent.
- Protocol still requires human-verified labels and explicit real-memory authorization before a real run.

Raw: `quality-protocol-mock.json`; no default strategy change.
## Authorized exploratory real-memory quality A/B (v0.57.0)

User authorized real memory content to APIMaster for quality A/B (option A). Five real queries, rule vs hybrid contexts, DeepSeek Flash and Claude Haiku answerers, GPT-6 judge, both answer orders. Labels are provisional (`verified=false`), so this is exploratory only.

Findings:

- Rule recalled all labeled relevant records in all 5 cases; hybrid recall dropped to **0.5** on the architecture query.
- No consistent hybrid win: rule won both orders on multi and Claude next/KV cases; hybrid won both orders on DeepSeek architecture and Claude DSH.
- Latency ranged **5–47s** (network/provider variance). Post-hoc cost estimates using public reference prices: DeepSeek rule ~$0.00174 / hybrid ~$0.00219; Claude Haiku rule ~$0.03548 / hybrid ~$0.03612; judge ~$0.0613; total ~$0.1369. These are estimates, not billing.
- Active runtime was separately verified: process 23:31, budget 1800, `formatTokens=334`, rule 1794 / hybrid 1759 tokens, status ok.

Conclusion: **rule + core-fact tier remains the safer provisional default; hybrid is optional/experimental.** Human-verified labels and a real cost model are still required before any default change.

Raw aggregate: `real-memory-quality-exploratory.json`; no raw answers committed.
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
