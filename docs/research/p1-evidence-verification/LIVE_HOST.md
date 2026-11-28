# Live host integration: implementation and observed boundary

Updated **2026-11-28 (Asia/Shanghai)**. **The full online method has not passed an end-to-end native-host run in the evidence reported here.** The original development attempt reached a real MCP read, then the installed host rejected its test-execution call because approval was required and that client used `approvalPolicy=never`. The failed attempt is retained. The user later approved the concrete [batch 1 scope](artifacts/authorized-batch1/authorization.json). Its second attempt observed two successful one-call prior-authorization exchanges, a real passing test, two native compactions and one simulated stable release; the changed-state final decision timed out. No annotation, managed policy, credential or access boundary was changed to route around the historical rejection.

## Implemented path

`native_live.py` owns a fresh two-file benign Node workspace and a persistent `live-broker.mjs` process. `live_mcp.py` exposes only `workspace_inspect`, `run_current_tests` and `record_decision`. Private preparation, extraction installation, verification and metrics operations are not MCP tools. The test executor checks exact file-byte allowlists and uses fixed Node argv, a bounded runtime and a minimal child environment. Its execution producer is `p1_live_process_broker`, delivered as an MCP result; it is **not** a Codex native shell `commandExecution` receipt.

The broker binds real before/after observations, normalizes complete TAP output and writes original receipts to real Memex L2. It can verify current-workspace test claims and cache receipts only within one fresh process/session. State/output directories must be outside the observed workspace, and used state is rejected rather than resetting sequence numbers over old history. This small allowlisted executor is not an OS sandbox for arbitrary repository code.

The proposed native flow has a prelude, real auxiliary-model extraction, source verification, a supported native compaction, evidence delivery and a recorded simulated release/hold attempt. A second checkpoint changes file bytes and checks whether the earlier passing receipt is rejected. No external deployment occurs. The simulator records attempts without deciding whether they are correct; the controller's evaluator runs afterward. Historical questions and arbitrary request templates are rejected by this current-workspace-only development interface.

`--run` is explicit; default mode performs capability discovery with zero model turns. The controller records generation-turn reservations before dispatch, retains raw token-usage notifications, caps protocol waits by a shared wall deadline and measures the exact serialized evidence bytes delivered. Five generation-turn starts, two compactions, six test executions and twenty public tool calls are per-session maximums, not observed usage. Cleanup may extend beyond the active-work deadline. Byte budgets are development guards, not a matched cross-arm token budget.

## Historical observed runs

For the newer authorized attempts, see [the batch report](artifacts/authorized-batch1/README.md). Native-01 used one generation start and timed out in prelude; native-02 used five starts, completed four generation turns and two compactions, then timed out at 480 seconds during the changed-state decision. The actual verifier reused the unchanged test receipt and rejected it after a version change. There is no observed later failing test or hold decision, and the integration check remains incomplete. Both central attempt slots are consumed; these counts do not replace or combine with the historical table below as one experiment.

| Run | Observed outcome | Scope |
|---|---|---|
| `preflight-01` | Host/model discovery completed; zero generation turns | Runtime capability only |
| `attempt-01` | One generation-turn start; actual `workspace_inspect` succeeded; `run_current_tests` was rejected before broker dispatch | Zero test executions, extractions, compactions and decisions; full integration blocked |
| `extraction-only-01` | One independent, read-only auxiliary generation; valid schema, three proposals, zero `test_result` proposals | Required prerequisite was placed only in `unresolved`; component qualification failed |
| `extraction-only-02` | One auxiliary generation after generic prompt clarification; valid schema, three proposals including one properly targeted `test_result` | Component qualification passed on the same development input family; coverage remains unestablished |

The complete records are in [artifacts/live-native/](artifacts/live-native/README.md). Across these historical full-integration and extractor checks there were **three generation-turn starts**, zero native compactions, zero broker test executions and zero recorded decisions. These are not the outcomes or attempt count of the newly authorized batch 1. One turn can contain multiple model requests; turn counts are not a billable-request or token total. Actual spend and full standardized cost remain null for these records. Previous native-smoke compactions belong to a separate older experiment and are not added to these outcomes.

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

The full integration now has two explicit approval modes. A validated one-use `--batch-permit` selects `PriorChatApprovals` under `on-request`, binding each ordinary native MCP approval to a real pending `memex` test/decision invocation and its exact arguments. Its audit records `origin=prior_chat_authorization` and `identityAttested=false`; it does not claim a fresh human or device confirmation. The response grants only that invocation, never session or persistent authority. The separate `--interactive-approval` mode requires a human-operated terminal. Without either mode, the default remains `approvalPolicy=never`. Unknown forms, explicit human/device requirements, sensitive/strict-review signals, foreign or replayed scopes, and expired requests stop the prior-authorization path. [APPROVALS.md](APPROVALS.md) and the [fixed-version protocol evidence](artifacts/authorized-batch1/approval-protocol/README.md) document the source-defined form/question paths and the 32 offline boundary tests; neither fixture success nor the user's permission establishes a successful live execution.

For batch 1, a single trusted central issuer owns the authoritative ledger and reserves at most **two full native attempts**, each capped at five generation starts, two compactions and 600 seconds. It issues the runtime-bound, expiring one-use permit only for a validated reservation. Remote runtime copies, restarts or manual mode changes do not create extra authorized attempts. The shared CNY 100 added-spending cap also covers the sixteen approved development method units, diagnostics, failures and retries. The reproduction commands above describe component entry points; they do not allocate additional budget. New batch outcomes must be recorded separately from the historical table before any claim that the missing mutable-tool stages are complete.

## Separate read-only native continuation

The later [read-only component check](artifacts/readonly-native/README.md) completed actual extraction, L2 verification, native compaction and three native forks over previously recorded receipts. It exposes no action tools, runs no test, and makes no live-state claim. It therefore supplies an independently executable interface check without filling the missing approved mutable-tool stages above. All three recommendations were correct in that one archived scenario; C reopened sources and D reused a verified source, but their delivered packets and native input-token totals were equal. No formal method effect or full cost result follows.

The current live binder supports selected Node test artifacts. General Python workflows, natural-language lifecycle projection, complete obligation labels, all comparison arms, measured full costs and independent real-task validation remain separate work.
