#!/usr/bin/env python3
"""Train a tiny transformer context encoder (relevance specialist baseline).

This is a real transformer encoder, but intentionally tiny and trained on
synthetic context-page/query pairs derived from the same fixture vocabulary as
the live A/B runs. It is a reproducible reference, not a production model.

Outputs:
  docs/assets/benchmarks/context-encoder-weights.json
  docs/assets/benchmarks/context-encoder.json
"""
import json
import math
import random
from pathlib import Path

import torch
from torch import nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'docs/assets/benchmarks'
VOCAB = 1024
DIM = 32
HEADS = 2
MAX_LEN = 64
SEED = 42
random.seed(SEED)
torch.manual_seed(SEED)
torch.set_num_threads(2)

TOPICS = [
    'billing retry policy', 'auth token rotation', 'cache eviction policy',
    'database migration window', 'gateway timeout budget', 'deployment rollback rule',
    'scheduler lease duration', 'ledger reconciliation cadence', 'worker pool sizing',
    'index rebuild strategy', 'bridge reconnect backoff', 'harbor release checklist',
    'parser error budget', 'router weighted routing', 'telemetry sampling rate',
    'secrets rotation window', 'feature flag cleanup', 'queue backpressure policy',
    'cold start latency target', 'snapshot retention window',
]
QUESTIONS = [
    'what did we decide about {topic}?',
    'which option did we choose for {topic}?',
    'what was the {topic} decision?',
    'remind me of the {topic} decision',
    'what did we settle on for {topic}?',
]
TOKEN_RE = __import__('re').compile(r'[a-z0-9]+')
FNV_OFFSET = 0x811c9dc5
FNV_PRIME = 0x01000193

def fnv1a(text):
    h = FNV_OFFSET
    for byte in text.encode('utf-8'):
        h ^= byte
        h = (h * FNV_PRIME) & 0xFFFFFFFF
    return h

def tokenize(text):
    return [fnv1a(token) % VOCAB for token in TOKEN_RE.findall(text.lower())]

def encode(query, page):
    tokens = tokenize(query) + tokenize(page['title']) + tokenize(page['summary']) + tokenize(page['body'])
    tokens = tokens[:MAX_LEN]
    mask = [1] * len(tokens)
    while len(tokens) < MAX_LEN:
        tokens.append(0)
        mask.append(0)
    return tokens, mask

class TinyContextTransformer(nn.Module):
    def __init__(self):
        super().__init__()
        self.token_emb = nn.Embedding(VOCAB, DIM)
        self.pos_emb = nn.Embedding(MAX_LEN, DIM)
        self.qkv = nn.Linear(DIM, DIM * 3)
        self.out = nn.Linear(DIM, DIM)
        self.ff1 = nn.Linear(DIM, DIM * 4)
        self.ff2 = nn.Linear(DIM * 4, DIM)
        self.ln1 = nn.LayerNorm(DIM)
        self.ln2 = nn.LayerNorm(DIM)
        self.head = nn.Linear(DIM, 1)

    def forward(self, tokens, mask):
        positions = torch.arange(tokens.shape[1], device=tokens.device).unsqueeze(0)
        h = self.token_emb(tokens) + self.pos_emb(positions)
        qkv = self.qkv(h).reshape(tokens.shape[0], tokens.shape[1], 3, HEADS, DIM // HEADS).permute(2, 0, 3, 1, 4)
        q, k, v = qkv[0], qkv[1], qkv[2]
        scores = (q @ k.transpose(-2, -1)) / math.sqrt(DIM // HEADS)
        scores = scores.masked_fill(mask[:, None, None, :] == 0, -1e9)
        attn = torch.softmax(scores, dim=-1)
        context = (attn @ v).transpose(1, 2).reshape(tokens.shape[0], tokens.shape[1], DIM)
        h = self.ln1(h + self.out(context))
        h = self.ln2(h + self.ff2(F.gelu(self.ff1(h))))
        pooled = (h * mask.unsqueeze(-1)).sum(dim=1) / mask.sum(dim=1, keepdim=True).clamp(min=1)
        return self.head(pooled).squeeze(-1)

def make_group(rng):
    topic = rng.choice(TOPICS)
    other = rng.choice([t for t in TOPICS if t != topic])
    fact = f"FACT-{rng.randrange(100000):05d}"
    question = rng.choice(QUESTIONS).format(topic=topic)
    relevant = {
        'title': 'decision record',
        'summary': f'{topic} decision',
        'body': f'The {topic} decision is {fact}; keep it for the {topic} question.',
        'fact': fact,
    }
    distractors = []
    for _ in range(4):
        d_topic = rng.choice([other, rng.choice(TOPICS)])
        distractors.append({
            'title': f'{d_topic} note',
            'summary': f'weekly {d_topic}',
            'body': f'General {d_topic} notes. Nothing decided.',
        })
    pages = [relevant] + distractors
    rng.shuffle(pages)
    return question, pages

def make_dataset(groups, rng):
    samples = []
    for _ in range(groups):
        question, pages = make_group(rng)
        for page in pages:
            tokens, mask = encode(question, page)
            samples.append((tokens, mask, 1.0 if 'fact' in page else 0.0, question, page))
    return samples

def batch(samples, index):
    rows = [samples[i] for i in index]
    tokens = torch.tensor([row[0] for row in rows], dtype=torch.long)
    mask = torch.tensor([row[1] for row in rows], dtype=torch.float32)
    labels = torch.tensor([row[2] for row in rows], dtype=torch.float32)
    return tokens, mask, labels

train_rng = random.Random(SEED)
val_rng = random.Random(SEED + 1)
train = make_dataset(400, train_rng)
val = make_dataset(100, val_rng)
model = TinyContextTransformer()
optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=0.01)
for epoch in range(16):
    model.train()
    order = list(range(len(train)))
    random.shuffle(order)
    total = 0.0
    for start in range(0, len(order), 32):
        indices = order[start:start + 32]
        tokens, mask, labels = batch(train, indices)
        optimizer.zero_grad()
        logits = model(tokens, mask)
        loss = F.binary_cross_entropy_with_logits(logits, labels)
        loss.backward()
        optimizer.step()
        total += float(loss) * len(indices)
    if (epoch + 1) % 4 == 0:
        print(f'epoch {epoch+1}: train loss {total/len(train):.4f}')

model.eval()
with torch.no_grad():
    val_tokens, val_mask, val_labels = batch(val, list(range(len(val))))
    val_logits = model(val_tokens, val_mask)
    accuracy = float(((val_logits > 0).float() == val_labels).float().mean())
    # ranking: relevant page must beat its four distractors
    correct_pairs = 0
    total_pairs = 0
    for start in range(0, len(val), 5):
        group_logits = val_logits[start:start + 5]
        group_labels = val_labels[start:start + 5]
        positive = group_logits[group_labels == 1]
        negative = group_logits[group_labels == 0]
        if len(positive) == 1 and len(negative) > 0:
            total_pairs += 1
            correct_pairs += int((positive > negative).all().item())
    ranking = correct_pairs / max(1, total_pairs)

state = model.state_dict()
def to_list(tensor):
    return tensor.detach().cpu().numpy().tolist()
weights = {
    'format': 1,
    'model': 'memex-context-encoder-transformer-v0',
    'config': {'vocab': VOCAB, 'dim': DIM, 'heads': HEADS, 'max_len': MAX_LEN, 'layers': 1, 'activation': 'gelu', 'tokenizer': 'fnv1a32-word'},
    'token_emb': to_list(state['token_emb.weight']),
    'pos_emb': to_list(state['pos_emb.weight']),
    'qkv_w': to_list(state['qkv.weight']), 'qkv_b': to_list(state['qkv.bias']),
    'out_w': to_list(state['out.weight']), 'out_b': to_list(state['out.bias']),
    'ff1_w': to_list(state['ff1.weight']), 'ff1_b': to_list(state['ff1.bias']),
    'ff2_w': to_list(state['ff2.weight']), 'ff2_b': to_list(state['ff2.bias']),
    'ln1_w': to_list(state['ln1.weight']), 'ln1_b': to_list(state['ln1.bias']),
    'ln2_w': to_list(state['ln2.weight']), 'ln2_b': to_list(state['ln2.bias']),
    'head_w': to_list(state['head.weight']), 'head_b': to_list(state['head.bias']),
}
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'context-encoder-weights.json').write_text(json.dumps(weights))
# Reference outputs for JS parity / tests
refs = []
with torch.no_grad():
    for index in [0, 1, 2]:
        tokens, mask = val[index][0], val[index][1]
        logit = float(model(torch.tensor([tokens]), torch.tensor([mask], dtype=torch.float32))[0])
        refs.append({'query': val[index][3], 'page': val[index][4], 'label': val[index][2], 'logit': logit})
report = {
    'format': 1,
    'kind': 'context-encoder-training',
    'model': weights['model'],
    'architecture': weights['config'],
    'train': {'groups': 400, 'samples': len(train), 'epochs': 16, 'seed': SEED},
    'validation': {'groups': 100, 'samples': len(val), 'accuracy': accuracy, 'pairwiseRanking': ranking},
    'references': refs,
    'caveats': [
        'Tiny transformer trained on synthetic fixtures, not production traces.',
        'Reference/JS-parity model; not trained on live provider token distributions.',
        'The interface is deliberately replaceable by a larger per-family context encoder.',
    ],
}
(OUT / 'context-encoder.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'accuracy': accuracy, 'ranking': ranking, 'samples': len(val)}, indent=2))
