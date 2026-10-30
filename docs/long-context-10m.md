# 10M-token long-context controlled experiment

**Status:** historical synthetic pilot, one stochastic run, 40 probes. Reported with Wilson 95% CIs. Not a human-labelled production benchmark. The generator uses `Math.random()` and does not accept or record a seed, so the original fixture cannot be exactly reproduced from a seed.

**Reproduction limitation:** the historical generator falls back to the ground-truth target record if search misses (`scripts/long-context-10m.mjs`); its answer condition is therefore not a valid end-to-end retrieval measurement on a miss. The published aggregate reports 40/40 hit@1, under which the fallback would not be exercised, but per-probe evidence for that run was not published. The later [pager retest](pager-retest.md) keeps retrieval and pager selection separate and does not inject target records.

## Abstract

We built a 10,000,000-token archive (2,000 records ×5,000 tokens), evicted half to cold storage, and asked 40 questions whose unique FACT ids exist only in the archive. Three conditions used the same answer models and output constraint:

1. **baseline** — recent conversation tail only (~536/548 prompt tokens), no evicted fact;
2. **memex** — top-1 retrieved archived evidence (~216/234 prompt tokens);
3. **distractor** — same-size unrelated archived evidence (~216/234 prompt tokens).

Both answer models answered **40/40** correct with memex; baseline and distractor answered **0/40**. Retrieval was **40/40 hit@1** at a median 4.94 ms.

## Setup

- Environment: Apple M4, 16 GiB, macOS arm64, Node v24.21.0.
- Archive: 2,000 records ×5,000 tokens = **10M tokens**; 1,000 hot / 1,000 cold (5M each).
- Store write: **1.65 s**; cold archive: **1.32 s**; DB **6.0 MB**; records directory **10.7 MB**.
- Probes: 40; 25 target facts were cold, 15 hot.
- Retrieval: `memory_search` by a card cue (`cardcue<turn>`); top-5 returned; target fact located by exact FACT id.
- Answerers: APIMaster `deepseek-flash` and `claude-haiku-4-5`; `gpt-6-astra` was not used as a judge because the metric is exact FACT-id match.
- Output constraint: answer only the FACT id or `UNKNOWN`; temperature 0; max_tokens 200 (DeepSeek needs reasoning tokens).
- The original report described shuffled jobs, but the checked-in reproduction script constructs them in fixed order; the original ordering cannot be independently verified from the aggregate. The script retries failures; the report says only emitted evidence contexts, not the full archive, were sent to the models.

## Results

### Retrieval

| metric | value |
|---|---:|
| hit@1 | **40/40 = 100%** |
| hit@3 | 40/40 = 100% |
| hit@5 | 40/40 = 100% |
| median latency | **4.94 ms** |
| p95 latency | 5.31 ms |

### Answer accuracy

| model | condition | correct | accuracy | Wilson 95% CI | avg prompt tokens | avg latency | avg cost* |
|---|---|---|---:|---:|---|---:|---:|---:|
| DeepSeek Flash | baseline | 0/40 | 0% | 0–8.8% | 536.4 | 3.53 s | $0.000045 |
| DeepSeek Flash | **memex** | **40/40** | **100%** | **91.2–100%** | **234.3** | 3.27 s | $0.000032 |
| DeepSeek Flash | distractor | 0/40 | 0% | 0–8.8% | 234.3 | 3.91 s | $0.000047 |
| Claude Haiku | baseline | 0/40 | 0% | 0–8.8% | 548.4 | 5.09 s | $0.000573 |
| Claude Haiku | **memex** | **40/40** | **100%** | **91.2–100%** | **216.2** | 5.30 s | $0.000299 |
| Claude Haiku | distractor | 0/40 | 0% | 0–8.8% | 216.3 | 5.58 s | $0.000275 |

\* Reference public rates: DeepSeek Flash $0.06/M input and $0.24/M output; Claude Haiku 4.5 official $1/M input and $5/M output. Actual APIMaster channel/routing may differ. Costs exclude retrieval/store cost.

Paired outcomes: for each model, memex-only correct = **40**, baseline-only correct = **0** (exact McNemar/binomial discordance p < 1e-12). Distractor was never correct.

### Token/task observation

The memex condition used **fewer prompt tokens** than the tail-only baseline while answering correctly: ~234 vs ~536 (DeepSeek), ~216 vs ~548 (Claude). The tail context is larger but lacks the evicted fact.

## Threats to validity

- Synthetic filler records and unique FACT ids: this measures long-horizon **availability/retrieval**, not natural-language ambiguity or semantic recall.
- One stochastic run and 40 probes; CIs are wide. This is a controlled experiment, not a leaderboard.
- APIMaster routing and pricing vary; latency includes provider/network variance.
- The metric is exact FACT-id containment, not human-judged answer quality.
- The report says no 10M-token prompt was sent; the published aggregate does not contain request-level evidence for independent verification.
- Cost figures are reference-rate estimates, not invoices.

## Reproduction

```bash
# 1. Build 10M archive and retrieval probes
node --import ./test/register.mjs scripts/long-context-10m.mjs \
  --records 2000 --tokens 5000 --probes 40 --out /tmp/tenm-data.json

# 2. Answer A/B (baseline / memex / distractor)
python3 training/long_context_10m_ab.py \
  --data /tmp/tenm-data.json --out /tmp/tenm-quality.json \
  --models deepseek-flash,claude-haiku-4-5

# 3. Aggregate JSON
docs/assets/benchmarks/long-context-10m.json
```

## Conclusion

At 10M archive tokens, direct retrieval exposed the target fact for every probe; both answer models then answered correctly, while a tail-only baseline and a same-size distractor were at 0%. The result supports the claim that the value is **availability of evicted content**, not merely a larger prompt. It does not establish production superiority of any hybrid materializer policy; that still requires human-labelled, record/session-isolated evaluation.
