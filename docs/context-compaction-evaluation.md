# Evidence retention across repeated compactions

Run from a bootstrapped repository with Node 24 or newer. Each run uses disposable local SQLite stores and the offline host stub. The output directory should be new or empty.

```sh
node --import ./test/register.mjs ./scripts/context-compaction-eval.mjs \
  --out /tmp/memex-context-compaction-results
```

The fixture contains two synthetic software-work trajectories, a release queue and a schema migration. Each has three successive DSH compaction boundaries and six questions per boundary. Each trajectory shadows about 33,300 estimated tokens. The source includes an early user constraint, two later readback corrections, `NOT RUN` and then an actual failed check, an explicit `UNKNOWN`, an unsupported assistant handoff, and a tool receipt beyond the 4,000-character rendered tool-line cap. The current user instruction in the retained tail serves as a positive control. Every question uses only evidence available at its boundary.

## Conditions

- **Rolling summary.** The compaction stand-in rolls forward the four most recent message lines of at most 280 characters, preserving their roles. The same summary and retained tail are present in all four conditions. The handoffs and filler are scripted.
- **Search and open.** The real DSH `memory_search` returns at most two ranked records. A deterministic reader opens their rendered bodies in rank order with the remaining budget, without a source locator or follow-up query supplied by the fixture.
- **Canonical pager.** The real store pager uses `timeline-exact`, the natural-language question, and a 145-token page cap. It selects search-hit record pages and fills the remaining budget in chronology.
- **Query-ranked pager.** The same pager and page cap use the repository's existing opt-in local lexical reranker, selecting up to four ranked pages before filling the balance. No model, generated query expansion, or expected source ID is supplied to retrieval.

The 1,200- and 2,400-token ceilings include the shared handoff and retained tail along with whatever search or pager evidence reaches the answerer. Cost is the repository's estimate of UTF-16 code units divided by four and rounded up. The prompt instructions and question sit outside this evidence ceiling and are identical across conditions for a question. The script checks every delivered window against the ceiling. The source round-trip audit separately opens every original event by known index with DSH `memory_open`, follows every pagination cursor, and compares the reconstructed JSON exactly. This index-assisted audit contributes zero evidence to the answer conditions.

## Local results

The run produced six complete checkpoints and reconstructed all 118 original shadowed events across the six checkpoints. Each budget column covers the same 36 probes. The two budget columns and the three observations of each long-lived fact are repeated measurements.

| Condition | Grounded at 1,200 | Grounded at 2,400 | Misleading only at 1,200 | Misleading only at 2,400 | Mean evidence at 1,200 / 2,400 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rolling summary | 20/36 | 20/36 | 4/36 | 4/36 | 168 / 168 |
| Search and open | 29/36 | 30/36 | 1/36 | 0/36 | 951 / 2,017 |
| Canonical pager | 27/36 | 27/36 | 3/36 | 3/36 | 1,170 / 2,369 |
| Query-ranked pager | 36/36 | 36/36 | 0/36 | 0/36 | 1,161 / 2,359 |

A **grounded** window contains the full expected source reference and receipt or user instruction. **Misleading only** means the window exposes a stale selection or unsupported claim without the expected source. The query-ranked pager recovered all six clipped-receipt probes at both budgets. Each other condition missed all six. Even the query-ranked pager included a conflicting claim alongside the supporting source in 16/36 cases at each budget. An answerer still needs to distinguish current readback, earlier readbacks, and assistant claims.

The oldest receipt was intact in the archive. The rendered search and chronology pager paths could miss it because of rendering clips, record-level hit discovery, and spending the remaining evidence budget on earlier pages. Page-level lexical ranking reached the receipt through the canonical event body on these fixtures. A more direct search result that points to the raw source event and opening offset would make the ordinary search-and-open workflow able to recover the same evidence without selecting a whole context window. That path would need scoped visibility, bounded results, and verification against realistic queries and archives.

## Separate answer evaluation

`results.json` records archive counts and per-question outcomes. `answer-packets.json` contains 12 paired questions from the summary and query-ranked pager, 24 independently presentable cases with opaque IDs. Give an answerer only the common instructions and the evidence for one case at a time. Keep `answer-key.json` separate until answers are fixed. It identifies the pairing, condition, expected source, misleading statements, and whether the source was visible.

Grade answer correctness, actual citation support, unsupported assertions, and appropriate abstention separately. On absent evidence, abstention is appropriate even if it cannot recover the target answer. On explicit `UNKNOWN` or `NOT RUN`, cite the receipt and retain the distinction. Treat the retained-tail positive controls separately from claims that rely on archival recovery. The pager's context formatting and length can reveal which condition supplied evidence even with opaque packet IDs. Two Codex respondents requested with the same model and reasoning level each received one context per question, under opaque IDs and with no answer key. Each handled six summary and six query-ranked cases. They recovered and cited **6/12** target answers from the summary and **12/12** from the query-ranked pager. Both arms produced **zero unsupported assertions**. The six missing summary answers were appropriate abstentions. The recovered evidence covered two clipped receipts, two old constraints, and two failed checks for which a later assistant handoff claimed success. This small run used a scripted compaction stand-in. The prompts' formatting and length could cue the condition, the sample is small, and no live-host long-workflow gain or hallucination-rate reduction has been measured. [Answer scoring and receipts](research/2026-11-25/followup/answer-grades.json)

## Trying query-ranked evidence in DSH

The evaluated paging settings correspond to the existing checkpoint options below. The fixture uses a stricter shared evidence ceiling and includes a scripted host tail and handoff in both arms. Keep enough headroom in the host prompt for those messages when evaluating live.

```json
{
  "materializer": "timeline-exact",
  "materializerMaxTokens": 1200,
  "materializerPageTokenCap": 145,
  "materializerHybridRerank": true,
  "materializerLearnedTopK": 4,
  "materializerQueryExpansion": false
}
```

The query-ranked arm uses the existing local reranker. The source-available and abstention checks follow evaluation dimensions used in [LongMemEval](https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html). The repeated-boundary design also draws on [LoCoMo's multi-session evaluation](https://aclanthology.org/2024.acl-long.747/).
