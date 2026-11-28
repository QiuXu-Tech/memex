# Live host integration: implementation and observed boundary

Updated **2026-11-28 (Asia/Shanghai)**. **The full online method has not passed an end-to-end native-host run.** The current development controller reaches a real MCP read, but the installed host rejects its test-execution call because approval is required and the unattended client uses `approvalPolicy=never`. The failed attempt is retained. No annotation, managed policy, credential or access boundary was changed to route around this rejection.

## Implemented path

`native_live.py` owns a fresh two-file benign Node workspace and a persistent `live-broker.mjs` process. `live_mcp.py` exposes only `workspace_inspect`, `run_current_tests` and `record_decision`. Private preparation, extraction installation, verification and metrics operations are not MCP tools. The test executor checks exact file-byte allowlists and uses fixed Node argv, a bounded runtime and a minimal child environment. Its execution producer is `p1_live_process_broker`, delivered as an MCP result; it is **not** a Codex native shell `commandExecution` receipt.

The broker binds real before/after observations, normalizes complete TAP output and writes original receipts to real Memex L2. It can verify current-workspace test claims and cache receipts only within one fresh process/session. State/output directories must be outside the observed workspace, and used state is rejected rather than resetting sequence numbers over old history. This small allowlisted executor is not an OS sandbox for arbitrary repository code.

The proposed native flow has a prelude, real auxiliary-model extraction, source verification, a supported native compaction, evidence delivery and a recorded simulated release/hold attempt. A second checkpoint changes file bytes and checks whether the earlier passing receipt is rejected. No external deployment occurs. The simulator records attempts without deciding whether they are correct; the controller's evaluator runs afterward. Historical questions and arbitrary request templates are rejected by this current-workspace-only development interface.

`--run` is explicit; default mode performs capability discovery with zero model turns. The controller records generation-turn reservations before dispatch, retains raw token-usage notifications, caps protocol waits by a shared wall deadline and measures the exact serialized evidence bytes delivered. Five generation-turn starts, two compactions, six test executions and twenty public tool calls are per-session maximums, not observed usage. Cleanup may extend beyond the active-work deadline. Byte budgets are development guards, not a matched cross-arm token budget.

## Actual runs

| Run | Observed outcome | Scope |
|---|---|---|
| `preflight-01` | Host/model discovery completed; zero generation turns | Runtime capability only |
| `attempt-01` | One generation-turn start; actual `workspace_inspect` succeeded; `run_current_tests` was rejected before broker dispatch | Zero test executions, extractions, compactions and decisions; full integration blocked |
| `extraction-only-01` | One independent, read-only auxiliary generation; valid schema, three proposals, zero `test_result` proposals | Required prerequisite was placed only in `unresolved`; component qualification failed |
| `extraction-only-02` | One auxiliary generation after generic prompt clarification; valid schema, three proposals including one properly targeted `test_result` | Component qualification passed on the same development input family; coverage remains unestablished |

The complete records are in [artifacts/live-native/](artifacts/live-native/README.md). Across this new batch there were **three generation-turn starts**, zero native compactions, zero broker test executions and zero recorded decisions. One turn can contain multiple model requests; turn counts are not a billable-request or token total. Actual spend and full standardized cost remain null. Previous native-smoke compactions belong to a separate older experiment and are not added to these outcomes.

The `elapsedMs` inside an installed extraction measures the shared validator's consumption of an already returned output. The actual auxiliary generation happened in a separate host before installation; its turn time and raw usage are recorded by that host. Treating this validation time as total extraction latency would omit the model call and is not a supported cost calculation.

## Extractor revision

The first real auxiliary output was syntactically valid. It nevertheless missed the test prerequisite and incorrectly used a command string as a `current_version` proposal's version. This distinguishes schema validity from obligation coverage.

The shared prompt now records policy `observable-obligations-v2`: explicit decision prerequisites require proposals even without an observed result; the command identifies the test entity, while version identifies the artifact. This is a generic clarification to `claims.mjs`, not a prefilled claim or a gold-source hint. Both full prompts, raw outputs, proposal grounding and usage traces are retained. This single-family development revision supplies no extraction-accuracy estimate and must remain outside an independent pilot. A formal run must freeze the chosen prompt digest anew.

## Reproduction entry points

On an already authorized compatible host:

```bash
python3 scripts/paper1/native_live.py --output /absolute/new/preflight
python3 scripts/paper1/native_live.py \
  --output /absolute/new/extraction-only \
  --run --extraction-only --model MODEL_RETURNED_BY_PREFLIGHT
```

The second command is an independent read-only model/schema check. It creates no MCP server for the model and performs no test execution, L2 ingestion, compaction or decision action. It does not substitute for the blocked full integration or grant permission for the rejected write-like tools.

The full integration requires a supported approval-capable client and genuine authorization for its exact test/decision tool calls. The current unattended client does not implement that interactive exchange. The [official App Server documentation](https://developers.openai.com/codex/app-server/) describes server-initiated approvals; no synthetic `accept` response or false read-only annotation is implemented here. Further work must preserve the actual user's decision and the host's permitted policy.

The current live binder supports selected Node test artifacts. General Python workflows, natural-language lifecycle projection, complete obligation labels, all comparison arms, measured full costs and independent real-task validation remain separate work.
