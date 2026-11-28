# Bounded offline replay of native-smoke-02

Status: **development integration replay; no model calls; no performance estimate**. Recorded on the user's local date 28 November 2026; original event UTC timestamps remain 27 November 2026.

## Actual inputs and scope

The replay reads the two saved host event logs and the resumed controller summary. It selects terminal `item/completed` command events, including the command whose terminal status is `failed`. The two supported Node/TAP executions are preserved completely. Other command events remain listed in `command-inventory.json`; original failed infrastructure attempts remain in the native-smoke directories and are not rewritten.

| Recorded phase | Original observation UTC | Exit code | Parsed test state | Saved stdout bytes |
|---|---|---:|---|---:|
| prelude | 2026-11-27T17:09:12.422944+00:00 | 0 | passed | 182 |
| continuation | 2026-11-27T17:26:15.480693+00:00 | 1 | failed | 822 |

Artifact mapping is **offline and known**: the controller summary maps prelude to the original `sum.mjs` digest and continuation to the changed digest. Actual `cat sum.mjs` and `shasum -a 256 sum.mjs` receipts independently agree with those values. The equal before/after hashes supplied to normalization are assigned from that mapping; they are not two independently observed live measurements around each execution. The digest covers `sum.mjs`, not a complete workspace or environment. Claim objects are manually constructed development inputs. No automatic model extraction or live object-state polling is established.

Every normalized source uses the actual log row's `utc`, not a fixed test-helper timestamp. The supplied logs already contain path redactions such as `<RUN_ROOT>`; this replay makes no further edits to their saved stdout. Source sequence 1/2 is the explicitly constructed order of these two completed test-state snapshots, not a claim that the host emitted those sequence numbers.

## Actual verifier outcomes

| Replay check | API outcome | API status | Reason | Reused | Original opens |
|---|---|---|---|---|---:|
| original_pass | supported | passed | verified_current_ingested_view | false | 1 |
| unchanged_original_reuse | supported | passed | verified_current_ingested_view | true | 0 |
| changed_version_before_rerun | abstain | unknown | version_mismatch | false | 1 |
| later_actual_failure | supported | failed | verified_current_ingested_view | false | 2 |
| old_version_after_later_failure | abstain | unknown | version_mismatch | false | 2 |

**API interpretation:** `supported` means that the returned state has evidence. Therefore `supported / failed` supports the fact that the later test failed; it never means the tests passed or release was authorized. All packets have `authorizesExecution=false`.

The changed-version check before rerun uses the same one-event archive as the original check and a manually supplied changed digest. Its refusal is a version mismatch, not evidence of automatic workspace-change detection. After ingestion of the real later failure, the archive head changes and the old passing receipt cannot revive the earlier result. Historical queries are outside this API's current-snapshot replay.

## Storage and shared sources

Normalization feeds the real `EvidenceArchive`, which writes Memex L2 originals, searches them, and opens paginated records. `memex-l2/` retains this local store. `archive-roundtrip.json` records exact source and stdout equality after reopening. No mocked archive or retrieval callback is used.

The public exports are `source-archive-prefix.json` (one original test event) and `source-archive.json` (both actual test events). Both pass the repository's `rawrag_adapter.validate_archive` using its frozen limits. `comparison-inputs.json` gives B and D the **same source path and hash at each snapshot**, with the original logged phase request. Raw-RAG itself is **not run**; this is input compatibility, not a B-versus-D result. The public archives contain source metadata and original output, not development claims or scoring labels.

Completeness is asserted only for the two-file, supported Node/TAP execution stream admitted in this replay. It is not a complete natural-language lifecycle reconstruction, a claim about unobserved external changes, or a complete host-history corpus. Unsupported non-test commands are inventoried rather than treated as proof of test execution.

## Bounds and reproduction

The replay is limited to 1048576 bytes per input, 2000 rows per log, 32 completed commands, two supported test events, and 5 verifier calls. Each call permits 8 hits and 16384 evidence bytes. The token guard is the verifier's conservative UTF-8-byte upper bound (16384); reported referenceTokens are not tokenizer measurements. There are no model, embedding, reranker, or network calls.

From the repository root, run into a **new** output directory:

```bash
node scripts/paper1/replay_native.mjs --output docs/research/p1-evidence-verification/artifacts/replay/native-smoke-02-rerun
node --test test/paper1-replay.mjs
```

The script refuses to overwrite an existing output directory. Source archive content, UTC, output hashes, and decision states are reproducible; archive epochs and local storage metadata are run identities and may differ. Full decisions and traces are in `replay-results.json`. Input file hashes, manual artifact mapping, and captures are in `input-manifest.json`. Original user requests are copied without rewriting into `requests/`.

These checks exercise an offline development interface. They do not establish live native-host evidence delivery, automatic claim extraction, host decision improvement, Raw-RAG superiority, a paired trial, or a paper result.
