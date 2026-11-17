# Research choices for the 2026-11-16 weekly cycle

Reviewed on 2026-11-16. This is a bounded literature and implementation survey, not a reproduction of the cited systems. The selected experiment changes deterministic context assembly only. The immutable protocol is in [PROTOCOL.md](PROTOCOL.md).

| Primary source / version | Relevant idea | Decision for Memex |
| --- | --- | --- |
| [FlexA-Mem v1, 2026-10-23](https://arxiv.org/abs/2610.33274v1); [official repository at 37ba0ce](https://github.com/WujiangXu/Flex-Amem/tree/37ba0ce2b4d14f6746e819b6a2d728ad74c364f2) | Immutable history units and a budget-dependent timeline plus raw detail/excerpts, rendered without an additional LLM call. | Closest architectural comparison for deterministic rendering. First reduce repeated ordering and rendering work while holding every output byte constant. The paper's task gains are not Memex measurements. |
| [SimpleMem v3, revised 2026-01-29](https://arxiv.org/abs/2601.02553v3); [official repository at db80b6a](https://github.com/aiming-lab/SimpleMem/tree/db80b6a7c591e0ea730a058e9f5fc4eb06572299) | Structured semantic compression, online synthesis and intent-aware retrieval planning. | Potential later quality/cost study. Semantic rewriting would change the current exact-output contract and requires a separate task-quality evaluation. Current repository documentation has evolved beyond paper v3; they are not interchangeable snapshots. |
| [A-MEM v11, revised 2025-10-08](https://arxiv.org/abs/2502.12110v11) | Dynamically linked notes and updates to related memories. | Useful alternative to static retrieval, but introduces write-time reasoning and semantic change. Not implemented in this deterministic performance cycle. |
| [LLMLingua official documentation at 01b9e94](https://github.com/microsoft/LLMLingua/blob/01b9e9481d7395e1e83a48df4a062b11f6304325/DOCUMENT.md) | Model-based prompt compression. | Requires model resources and separate quality evaluation. No model downloads, extra paid endpoints or GPU rental in this cycle. Compression ratios reported elsewhere are not evidence here. |
| [SQLite FTS5 official documentation](https://www.sqlite.org/fts5.html) | FTS5 offers ranking and an optimized rank ordering route; query/index work can be studied separately. | Defer Store/search changes: scope filters, expiration, ordering and recovery must be held independently. Mixing them with rendering would obscure causality. |
| [Python 3.14 heapq](https://docs.python.org/3.14/library/heapq.html) | Multiway merging maintains stream heads rather than repeatedly sorting the full queue. | A generic heap is not a drop-in replacement: Memex preserves stream sequence under clock skew, and the previous first head wins equal-key ties. Use stable lower-bound reinsertion with a guarded domain instead. |
| [tiktoken educational BPE, 79dc2c0](https://github.com/openai/tiktoken/blob/79dc2c0533685b893616c78160b5d9e40876e724/tiktoken/_educational.py) | Tokenization operates on text boundaries; arbitrary token counters need not be additive. | Keep custom counters on complete text with the original invocation sequence. Exact length accounting applies only to the existing default UTF-16 chars/4 heuristic. |

The paper abstracts, official project READMEs and the linked LLMLingua documentation were read. Repository heads were recorded on the review date; this is not an audit of those complete codebases. No external implementation or benchmark dataset was copied into Memex. The reviewer's early alternatives and challenges are retained separately; the final frozen protocol supersedes those exploratory targets.

## Selected aggressive experiment

The baseline rebuilds and counts the growing rendered window for each attempted addition, repeatedly sorts stream heads, and scans selected/dependency/retrieved membership. A wide accepted window compounds these costs. Three cumulative rounds address those independent sources of repeated work:

1. Maintain ordered stream heads and sort singleton streams once, preserving the legacy merge semantics.
2. Add request-local membership/dependency/retrieval indexes for stable values and preserve a legacy route for dynamic inputs.
3. Cache exact default rendered lengths rather than rebuilding large strings during budget probes; still render the final output and preserve selected-subset ordering.

Reject any candidate with a full-output, object-identity, mutation or callback-trace mismatch. A fast global sort, per-page token ceilings and an initial-stream tie ordinal were rejected before implementation because they change behavior. Safe-domain checks and fallbacks are part of the implementation cost, not excluded from timing.

## Follow-up research boundary

Once this assembly optimization is merged and client acceptance is established, a separately frozen task-quality study could compare exact history, excerpts, semantic units and learned selection under equal budgets. [EvalMem v2](https://arxiv.org/abs/2609.22231v2) and [LongMemEval-V2 v1](https://arxiv.org/abs/2605.12493v1) were considered by the reviewer as evaluation references; neither was run here. The LongMemEval repository was only identified by its head, not audited. Real task outcomes and actual model billing remain unmeasured.
