# Quality A/B evaluation protocol

This protocol separates **selection quality** from **answer quality** and avoids treating one query/model/order as multiple independent results.

## Dataset requirements

- Record- or session-disjoint split; document the split key.
- Realistic questions with explicit `recordIds` and `humanRelevance` labels.
- Labels must be human-verified (`verified: true`); LLM-only labels run in exploratory mode and are never used to change defaults.
- Store rule and hybrid contexts separately with their materializer config and budget.

## Metrics (report separately)

- Record recall / key-fact coverage in the selected window.
- Answer correctness, unsupported claims, and citation quality.
- Condition mapping for both answer orders (A/B ↔ rule/hybrid).
- Per-question raw answers and judge rationale, saved verbatim.
- Input/output tokens, latency, and cost under a stated cost model.

## Protocol

Use `training/quality_ab_protocol.py`:

```bash
python3 training/quality_ab_protocol.py dataset.json --out quality-ab.json \
  --answer-models deepseek-flash,claude-haiku-4-5 --judge gpt-6-astra
```

The script randomizes condition order, saves the mapping, raw answers, judge rationale, usage and cost per question. It does not alter defaults.

## Privacy

- Do not send real memory content to a third party without recorded authorization.
- Synthetic or sanitized fixtures are preferred; otherwise keep evaluation local.
- Trace and raw answers are local artifacts; do not publish them.
