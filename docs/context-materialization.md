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
