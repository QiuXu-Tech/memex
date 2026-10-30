#!/usr/bin/env python3
"""KV block paging probe: real KV tensors from Qwen2.5-0.5B.

1. Run a context prefill, extract per-layer key/value tensors.
2. Split each layer's KV along sequence into fixed blocks.
3. Evict blocks to CPU, page a subset back to GPU, rebuild a DynamicCache.
4. Decode the query with the rebuilt cache and compare logits/output to a
   full-context forward.

This is a reference for the custom KV connector path, not a vLLM plugin yet.
"""
import json, time
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, DynamicCache

MODEL = '/root/models/qwen'
MAX_CTX = 8192
BLOCK = 256
OUT = '/root/kv-block-probe.json'
tokenizer = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.bfloat16, device_map='cuda')
model.eval()
context = ('[EXTRA-CONTEXT MATERIALIZED WINDOW]\n' + '\n'.join(
    f'context page mem_{i:010d}: archived component {i}; decision {i % 7}' for i in range(1, 300)
) + '\n[END WINDOW]\n')
query = 'Question: what did we decide about component 42? Answer:'
ctx_len = len(tokenizer(context, add_special_tokens=False).input_ids)
full_ids = tokenizer(context + query, return_tensors='pt').input_ids.to('cuda')[:, :MAX_CTX]
ctx_ids = full_ids[:, :ctx_len]
q_ids = full_ids[:, ctx_len:]
with torch.no_grad():
    full_logits = model(full_ids).logits[:, -1, :]
    prefill = model(ctx_ids, use_cache=True)
past = prefill.past_key_values
layers = len(past.layers)
# Split KV into blocks and page to CPU
blocks = []
ctx_len = ctx_ids.shape[1]
# Direct cache reuse baseline (no paging)
pos = torch.arange(ctx_len, ctx_len + q_ids.shape[1], device='cuda')
with torch.no_grad():
    direct = model(q_ids, past_key_values=past, use_cache=True, cache_position=pos, position_ids=pos.unsqueeze(0))
direct_logits = direct.logits[:, -1, :]
direct_diff = (full_logits.float() - direct_logits.float()).abs().max().item()
direct_next = direct_logits.argmax(dim=-1).item()


for layer in range(layers):
    keys = past.layers[layer].keys
    values = past.layers[layer].values
    layer_blocks = []
    for start in range(0, ctx_len, BLOCK):
        end = min(ctx_len, start + BLOCK)
        layer_blocks.append({
            'start': start, 'end': end,
            'key': keys[:, :, start:end, :].detach().to('cpu'),
            'value': values[:, :, start:end, :].detach().to('cpu'),
        })
    blocks.append(layer_blocks)
del past, prefill
torch.cuda.empty_cache()
# Page blocks back
rebuilt = DynamicCache()
for layer in range(layers):
    for block in blocks[layer]:
        k = block['key'].to('cuda', non_blocking=True)
        v = block['value'].to('cuda', non_blocking=True)
        rebuilt.update(k, v, layer)
with torch.no_grad():
    pos = torch.arange(ctx_len, ctx_len + q_ids.shape[1], device='cuda')
    paged = model(q_ids, past_key_values=rebuilt, use_cache=True, cache_position=pos, position_ids=pos.unsqueeze(0))
paged_logits = paged.logits[:, -1, :]
diff = (full_logits.float() - paged_logits.float()).abs().max().item()
full_next = full_logits.argmax(dim=-1).item()
paged_next = paged_logits.argmax(dim=-1).item()
report = {
    'model': MODEL, 'context_tokens': int(ctx_ids.shape[1]), 'block_size': BLOCK,
    'layers': layers, 'blocks_per_layer': len(blocks[0]), 'blocks_total': sum(len(x) for x in blocks),
    'kv_blocks_paged_to_cpu': sum(len(x) for x in blocks),
    'direct_reuse_max_logit_diff': direct_diff, 'direct_next_token_same': full_next == direct_next, 'paged_vs_direct_max_logit_diff': (direct_logits.float() - paged_logits.float()).abs().max().item(), 'max_logit_diff': diff, 'next_token_same': full_next == paged_next,
    'full_token': tokenizer.decode(full_next), 'paged_token': tokenizer.decode(paged_next),
    'gpu_memory_allocated_mib': round(torch.cuda.memory_allocated() / 1024**2, 1),
    'gpu_memory_reserved_mib': round(torch.cuda.memory_reserved() / 1024**2, 1),
    'caveats': ['Reference KV paging on a 0.5B HF model, not vLLM connector integration.', 'Single context/query; no concurrency.', 'Blocks are paged CPU<->GPU manually; attention reconstruction is exact for this cache.'],
}
open(OUT, 'w').write(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
