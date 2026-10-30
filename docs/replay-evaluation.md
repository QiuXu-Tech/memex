# Local replay-evaluation extraction

`training/extract_replay_episodes.py` builds local replay episodes from a DSH session + memex records. It makes **no network calls**.

## Outputs

Run against the current workspace session:

```bash
python3 training/extract_replay_episodes.py /path/to/output
```

- `replay-episodes.json` — local episode data: source, seq/time, query, relevant record IDs/titles, reference facts, available records, provisional label state.
- `replay-review.md` — human-readable review sheet with blank labels.
- `replay-labels.csv` — spreadsheet-friendly review sheet.

## Sources

- `l1-eviction`: L1 → L2/L3 archive records and the query before the eviction.
- `memory-write`: exact `memory_write` tool calls matched by title to the created record, with the nearest preceding real user query.

## Limits

- Labels are provisional (`verified: false`); a human must confirm relevant records/facts.
- One continuous session/trajectory is not an independent benchmark.
- Raw session/memory content stays local; do not send it to a third party without explicit authorization.
- Later turns are not included in the replay context; keep record/session isolation when scoring.

## Local selection test

28 provisional episodes, active 1,800 budget. Without excerpts, relevant-record hit rates were rule 3.6%, rule+core 7.1%, hybrid 28.6%, hybrid+core 32.1%. Adding `pageTokenCap=400` source-marked excerpts raised hybrid+core to **42.9%**, with no over-budget windows. L1 archive records are raw and huge; they must be excerpted/carded before materialization. This is a selection test, not answer quality; labels remain provisional.
