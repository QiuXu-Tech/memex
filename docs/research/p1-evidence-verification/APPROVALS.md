# Native approval client

Updated **2026-11-28 (Asia/Shanghai)**. This fail-closed terminal handler is a prototype based on the recorded host wire fields. The original mutable-MCP attempt remains blocked. No live host request has demonstrated either of its one-call profiles, and no human-approved execution has completed.

`scripts/paper1/approvals.py` implements a deliberately narrow interactive terminal client. `native_live.py --interactive-approval` uses the host's `on-request` policy and routes actual server requests through it. Default mode still uses `never`. The test and decision tools keep their truthful non-read-only annotations. No managed configuration, credentials or execution policy file is edited.

## Concrete supported interaction

The installed Codex 0.153.0 host generated its own four request/response schemas without a model call. Their hashes and required fields are retained in [approval-schema-receipt.json](artifacts/readonly-native/approval-schema-receipt.json). The [official App Server documentation](https://developers.openai.com/codex/app-server/) also documents thread/turn-scoped server-initiated requests and the response shapes. The captured field inventory supplies the request envelope. Actual wording, option semantics and end-to-end compatibility still require observation in the host UI.

The client recognizes two exact P1 development question profiles under `item/tool/requestUserInput` or `tool/requestUserInput`. One asks “Run the configured P1 test once?” and the other asks “Record this simulated P1 decision once?” Each has the options “Allow once” and “Decline,” in that order, with fixed invocation-specific descriptions. The client displays the bounded request as escaped JSON and forwards the selected label unchanged. Blank input, EOF or timeout supplies no positive answer.

The request must contain boolean `isBlocking: true`. Optional `autoResolutionMs` may be null or an unsigned 64-bit integer. A supplied duration shortens the terminal wait alongside the controller deadline and 120-second cap. An expired prompt cannot forward a positive answer. This allowlist applies to the entire question and option set. Generic Accept forms, persistent grants, extra options, free-form or secret questions, and unsupported fields require the host UI. The current thread and turn IDs establish request identity. They cannot establish how long the host would retain a grant. The client records the actual terminal choice without attesting identity or device verification.

Twelve offline protocol tests cover one-call choice, decline, cancellation, scope, replay and unsupported requests. These are controlled fixtures. For a different live request shape, use the actual host UI or adapt the client after inspecting that shape and its authorization semantics. The recorded read-only run retains its original source snapshot.

## Run when a human is present at the terminal

```bash
python3 scripts/paper1/native_live.py \
  --output /absolute/new/live-run \
  --run --model MODEL_RETURNED_BY_PREFLIGHT \
  --interactive-approval
```

This is a real interactive command, not an unattended example with piped answers. The person at the terminal sees each concrete request, and their decline/cancel remains a decline/cancel. Current grant scope does not turn archived evidence or a simulated release recommendation into permission to deploy anything. The development broker's byte allowlist and execution limits remain in force.

The separate [read-only native continuation](artifacts/readonly-native/README.md) exposes no action tools and does not use this approval exchange. Its successful result cannot replace the missing approved mutable-tool run.
