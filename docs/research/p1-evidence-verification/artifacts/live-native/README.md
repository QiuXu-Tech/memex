# Native live development records

Date: **2026-11-28 (Asia/Shanghai)**. Host: Codex 0.153.0, Node 25.9.0, Python 3.14.3; actual requested/resolved model `gpt-5.6-sol`.

**No full online-method success is reported.** [manifest.json](manifest.json) lists the four attempts/components, raw and published SHA-256 digests, and the exact redactions. The public files replace only the controlled temporary root with `<ROOT>` and the device home path with `<USER_HOME>`. Reasoning content was not captured; native event traces retain only reasoning item IDs/types. No API-key values or account configuration are included.

| Artifact | Meaning |
|---|---|
| [preflight](preflight-01/summary.json) | Successful capability discovery, no model turn |
| [full attempt](attempt-01/summary.json), [native events](attempt-01/main-host/events.jsonl) | Real MCP read succeeded; execution rejected: `MCP tool call requires approval, but approval policy is never` |
| [first extraction](extraction-only-01/read-only-extraction.json), [input/prompt](extraction-only-01/read-only-extract-input.json) | Schema-valid first output omitted the test prerequisite; component failed |
| [revised extraction](extraction-only-02/read-only-extraction.json), [input/prompt](extraction-only-02/read-only-extract-input.json) | Generic prompt v2 produced one test claim; component passed on the same synthetic family |

There are three generation-turn starts in this batch. Every auxiliary host has its own trace and usage notifications; the main preflight hosts generated no answer. Do not add duplicated usage arrays from `summary.json`, `host_traces` and raw events. Notification totals/last values and compaction billing have not been reconciled; **actual spend and standardized full cost are unknown**. None of these records is a formal run row for `analyze.py`.

An extraction result's `elapsedMs` covers validation/installation of an already returned model output. It excludes the separately recorded auxiliary host turn, and must not be reported as total extraction latency or used to price the model call.

Per-run `independent_workflows` and `checkpoints` fields describe the controller's configured development scenario, not accepted or completed research tasks. The batch manifest sets formal task count to zero. No test executed through the native broker in this batch, no native compaction occurred and no simulated decision was recorded. Successful local broker tests are different artifacts.

The initial remote `git clone` exited 69 because Xcode's license was not accepted; no license was accepted automatically. A public archive download exceeded a deliberately imposed 12 MB cap and was not extracted. A minimal 28-file runtime transfer was then verified by SHA-256 before preflight. [initial-runtime-manifest.json](initial-runtime-manifest.json) records that initial source bundle. Subsequent source versions and complete extraction prompts are preserved in the run records/source snapshots; a later source check is not evidence that earlier failed attempts used an updated file.

See [LIVE_HOST.md](../../LIVE_HOST.md) for the control boundary, prompt revision and remaining native-approval dependency.
