# Actual Codex retrieval from 10M and 100M Memex archives

Two persisted, nested synthetic engineering archives were queried separately through an actual Codex CLI 0.153.0 session using gpt-5.6-sol, the existing ChatGPT login and the local Memex MCP server. Codex received the same six questions in both cases. The answer key, source IDs and markers were withheld. An answer counted only when its value and citation matched and the native MCP trace showed that Codex opened the cited evidence. A hidden or nonexistent answer required an explicit NOT_FOUND.

| Measure | 10M archive | 100M archive |
| --- | ---: | ---: |
| Visible o200k_base body tokens | 10,005,683 | 100,005,571 |
| Visible records | 1,570 | 15,767 |
| Hot / cold visible records | 628 / 942 | 6,307 / 9,460 |
| Allocated archive size | 88.6 MiB | 893.3 MiB |
| Build wall time | 16.6 s | 336.2 s |
| Correct / answered probes | 6/6 | 6/6 |
| Correct source-backed values | 3 | 4 |
| Correct unavailable outcomes | 3 | 2 |
| Actual Memex tool calls | 18 | 16 |
| Actual Codex turn time | 37.8 s | 36.4 s |
| Median tool search duration | 62 ms | 242 ms |
| Median tool grep duration | 996 ms | 2,271 ms |
| Codex cumulative input tokens (cached part) | 98,199 (71,552) | 93,311 (68,864) |
| Last Codex request input tokens | 26,539 | 24,213 |
| Reported model context window | 258,400 | 258,400 |

The large archive's additional witness ticket was found, while cross-session and absent controls remained unavailable. A different-workspace copy of the early cold receipt did not appear in tool results. An older superseded export receipt did not replace the signed current one. Reports of accumulated input tokens represent the sum across actual model requests, including its cache usage. The archive body counts use each persisted body independently under the public o200k_base reference tokenizer. They represent the retrievable backing store.

Direct MCP preflights retained first-pass misses from distractors. Two broad searches missed top ten in the smaller store and one missed in the larger store. Targeted decision searches recovered all visible positives. Independent SQLite and stratified physical-body checks passed for 114 and 110 records. Actual Codex retrieval had one run per archive. Per-tool durations describe these calls and query choices. The observed turn times do not estimate a general speed difference.

[Graded answers, corpus identifiers and actual provider telemetry](scale-results.json)

## Reproduction

Use the [archive generator](../../../scripts/context-scale-live.mjs) with a Python environment containing tiktoken 0.12.0 and the cached o200k_base vocabulary, verified by the generator. Use an isolated output path and provision about 1 GiB for both full archives. Keep the generated key file outside the model workspace. Configure the ordinary Memex MCP binary against the selected archive using the generator's recorded workspace and session namespaces. Register only search, open and grep, then use the [single-turn Codex runner](../../../scripts/codex-retention-host.py) and [scale grader](../../../scripts/grade-codex-scale-20261126.py).
