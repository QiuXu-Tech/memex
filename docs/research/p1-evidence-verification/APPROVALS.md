# Native approval client

Updated **2026-11-28 (Asia/Shanghai)**. The user has approved the concrete [batch 1 scope](artifacts/authorized-batch1/authorization.json). The client supports exercising that prior authorization for a strictly bound ordinary MCP call, alongside a separate manual terminal mode. The original mutable-MCP rejection remains historical evidence. The later [native-02 event capture](artifacts/authorized-batch1/native-02/main-host/events.jsonl) now records actual successful one-call approvals and subsequent test/decision tool execution; its full workflow still ended in a final-decision timeout.

`scripts/paper1/approvals.py` implements `PriorChatApprovals` and `InteractiveApprovals`. `native_live.py` selects the first only after admitting a controller-issued batch permit; `--interactive-approval` selects the second. Both use the host's `on-request` policy. Without either mode, the default remains `never`. The test and decision tools keep their truthful non-read-only annotations. No managed configuration, credentials or execution policy file is edited.

## Concrete supported interaction

The installed Codex 0.153.0 binary exported its own request/response schemas without a model call. The [pinned protocol evidence](artifacts/authorized-batch1/approval-protocol/README.md) preserves those schemas, the official `rust-v0.153.0` source at commit `41e22fee981a63b3698df7ed36bad393cda24715`, hashes and source excerpts. That source emits the native MCP item-start notification before requesting approval. It defines the actual question text and maps an ordinary one-call response separately from a remembered grant. Actual form-path compatibility was then observed in native-02; the fallback question path remains covered by offline/schema checks rather than a new live exchange.

The client recognizes two source-defined protocol paths: `mcpServer/elicitation/request` with the ordinary empty approval form and `_meta.codex_approval_kind: "mcp_tool_call"`, or `item/tool/requestUserInput` with the native MCP approval question. Both must name the `memex` server and either `run_current_tests` or `record_decision`. Every response requires a unique, still-pending native item on the active thread and turn, with exact tool-argument binding; the question path also binds its question ID to that item's ID. The former custom P1 question profiles and legacy `tool/requestUserInput` alias are not accepted.

An affirmative form response is only `{"action":"accept","content":{}}`; the question response selects only `Allow`. The client never returns `_meta.persist` or a session/permanent option. Advertised remembered choices do not widen the response. Generic forms, unknown fields, secret/free-form questions, explicit human/device verification, and sensitive-action or strict-review signals stop the prior-authorization path for handoff through the supported human flow. Replayed/resolved requests, completed items, changed arguments and expired deadlines cannot receive an affirmative response. The question path requires `isBlocking: true`; optional nullable uint64 `autoResolutionMs` can only shorten the wait alongside the controller deadline and 120-second cap.

The two modes record different sources. `PriorChatApprovals` records `origin` and `source` as `prior_chat_authorization`, with `identityAttested: false` and the authorization, attempt and reservation references. It does not represent prior chat consent as a fresh terminal click. `InteractiveApprovals` requires human-operated TTY input/output, displays the escaped request and native arguments, and records the actual choice as `interactive_terminal`, also with `identityAttested: false`. Blank input, EOF or timeout cannot approve. Thirty-two offline tests cover both modes and their binding, replay, deadline, grant-reference and audit-write boundaries. These fixtures are not live execution results.

## Batch 1 execution authority

One trusted central issuer reserves attempts in the single authoritative batch ledger and supplies one-use permits to fresh runtimes. The approved maximum is **two new full native development attempts**, each with at most five generation starts, two compactions and 600 seconds. The batch's CNY 100 added-spending limit is shared with its sixteen authorized development method units and includes failures, diagnostics and retries. A copied or reset remote ledger does not authorize another attempt. Permit admission checks the expected digest, reservation, runtime/output binding, expiry and one-use consumption; a digest is not a human signature or a replacement for the trusted issuer.

Only after the central issuer has validated and reserved that exact attempt may its controller invoke:

```bash
python3 scripts/paper1/native_live.py \
  --output /absolute/new/live-run \
  --run --model MODEL_RETURNED_BY_PREFLIGHT \
  --batch-permit /absolute/controller-issued-permit.json \
  --expected-permit-sha256 DIGEST_RETURNED_BY_ISSUER
```

The permit remains outside model input and MCP arguments. Unknown or explicitly human/device-only requests still stop; changing client modes or restarting does not replenish the central budget. The separate manual `--interactive-approval` mode remains available for genuinely human-operated sessions, without piped answers. Its presence supplies no additional batch attempt. Current grant scope does not turn archived evidence or a simulated release recommendation into permission to deploy anything. The development broker's byte allowlist and execution limits remain in force.

The separate [read-only native continuation](artifacts/readonly-native/README.md) exposes no action tools and does not use this approval exchange. Its successful result is distinct from the later partially completed mutable-tool run. Batch 1 has consumed both native attempts; additional native trials need a new explicit attempt allocation, while the already authorized sixteen development units retain their original scope.
