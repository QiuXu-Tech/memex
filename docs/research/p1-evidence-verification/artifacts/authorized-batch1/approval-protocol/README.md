# P1 batch 1: pinned native approval protocol evidence

This directory records a zero-generation examination of the installed Codex
`0.153.0` app-server schema and the matching official source. It supports the
approval client's protocol implementation. It is **not** an observed live host
approval, a new human interaction, or a paper experiment result.

## Provenance

The schema was exported from the installed binary with
`codex app-server generate-json-schema --out <temporary-directory>`. The official
`rust-v0.153.0` tag resolves through tag object
`6bc50f104dcc0192e696cdeae721dfc19b507391` to commit
`41e22fee981a63b3698df7ed36bad393cda24715`.

- `schema/` contains the actual exported request/response schemas and the
  account request variants used for read-only preflight design.
- `schema/tag-provenance.json` preserves the official tag response.
- `source-excerpts.json` preserves selected source text with its original line
  numbers and the SHA-256 of each complete upstream file from which it came.
- `provenance.json` records the source URLs, scope and local validation result.
- `manifest.json` records the hashes of all evidence files in this directory,
  except the manifest itself.
- `LICENSE.upstream` contains the pinned OpenAI Codex Apache 2.0 license.

Official source references:

| File | Relevant lines in the fixed commit | Evidence |
| --- | --- | --- |
| [core/src/mcp_tool_call.rs](https://github.com/openai/codex/blob/41e22fee981a63b3698df7ed36bad393cda24715/codex-rs/core/src/mcp_tool_call.rs) | 256–285 | The native item-start notification is awaited before requesting MCP approval |
| [core/src/mcp_tool_call.rs](https://github.com/openai/codex/blob/41e22fee981a63b3698df7ed36bad393cda24715/codex-rs/core/src/mcp_tool_call.rs) | 1506–1629 | The feature-controlled elicitation path and the fallback question path |
| Same file | 1770–1966 | The native question, empty form schema, tool arguments and optional persistence advertisement |
| Same file | 1986–2022, 2052–2101 | Mapping an ordinary `accept` or `Allow` response to the one-call approval decision |
| Same file | 2113–2138 | Session and policy persistence are separate branches; an ordinary approval does not save them |
| [protocol/src/mcp_approval_meta.rs](https://github.com/openai/codex/blob/41e22fee981a63b3698df7ed36bad393cda24715/codex-rs/protocol/src/mcp_approval_meta.rs) | Full file | The reserved MCP approval metadata keys |
| [core/src/mcp_tool_approval_templates.rs](https://github.com/openai/codex/blob/41e22fee981a63b3698df7ed36bad393cda24715/codex-rs/core/src/mcp_tool_approval_templates.rs) | 21–33 | `tool_params_display` uses `name`, `value`, `display_name` |
| [app-server/README.md](https://github.com/openai/codex/blob/41e22fee981a63b3698df7ed36bad393cda24715/codex-rs/app-server/README.md) | 1987–2018 | The documented elicitation request, response actions and approval metadata |

## The two actual protocol paths

The installed protocol supports `mcpServer/elicitation/request` and
`item/tool/requestUserInput`. It does not need a fabricated
`item/mcpToolCall/requestApproval` method or custom question text.
`schema/server-request-methods.json` retains the installed method list and the
hash of the complete schema from which it was extracted. The fixed core source
awaits the MCP item-start notification before requesting approval, which
supports requiring a previously observed pending item in this client.

For the ordinary MCP elicitation path, the client accepts only the following
specific combination:

- The active native thread and turn, the server `memex`, and `mode: "form"`.
- An empty object schema and `_meta.codex_approval_kind: "mcp_tool_call"`.
- The source-defined question naming `run_current_tests` or `record_decision`.
- A unique, still-pending native `mcpToolCall` item for that tool on the same
  thread and turn. The actual native item arguments must equal `tool_params`.
- Only known metadata and argument display fields. An unknown schema, field,
  reviewer, device flow, or human-presence requirement is not approved.

The one-call affirmative response is exactly:

```json
{"action":"accept","content":{}}
```

In the fallback path, the source-defined question ID is
`mcp_tool_call_approval_` followed by the real native item ID. The header is
`Approve app tool call?`, and the prompt names the same server and tool. The
response selects only the `Allow` label for that question. Its item ID, question
identity, option text and pending native invocation must all agree.

The source can advertise session or permanent choices. An advertisement is not
a grant. Both P1 clients omit response `_meta.persist`, and neither selects the
remembered option. A request that only offers a permanent choice or asks for a
new persistence field is rejected.

## Prior authorization and human presence are different evidence

The fixed upstream functions above treat an ordinary client `accept` with no
`persist` metadata as `ReviewDecision::Approved`. They do not attach a new
human-presence or device-verification proof requirement to that particular
ordinary MCP path. The persistence function makes ordinary approval distinct
from session and stored-policy approval.

The implementation decision is therefore to permit an explicitly scoped client
to exercise the user's already-recorded approval of this concrete batch, once
for each matching pending invocation. This is an inference from the ordinary
protocol semantics **combined with the user's actual authorization**. An empty
form or the absence of a proof field does not itself confer permission.

`PriorChatApprovals` requires a controller-supplied reference with exactly:

```text
authorization_sha256
attempt_id
reservation_sha256
```

The constructor checks the shape and freezes a snapshot. These hashes are audit
references, not self-authenticating permission. Before constructing the client,
the controller must validate the authorization's content, reserve the specific
attempt in the durable budget ledger, validate that reservation, and enforce
the run, time and spending limits. The permit must remain outside model input
and the MCP tool arguments. The controller also owns the lifetime of this
client and must not reuse an attempt or reconstruct clients to reset counters.

For every invocation, the client additionally requires a real native
`item/started` notification supplied directly by the app-server transport.
Model text and tool-result text must never be reinterpreted as notifications.
Completion, request resolution, an expired deadline, ambiguous same-tool items,
request replay, item replay or changed arguments prevent acceptance.

Every prior-authorization request and response audit event records:

```json
{
  "origin": "prior_chat_authorization",
  "identityAttested": false,
  "grantReference": {
    "authorization_sha256": "<validated authorization digest>",
    "attempt_id": "<reserved attempt identifier>",
    "reservation_sha256": "<validated reservation digest>"
  }
}
```

The response event's `source` also states `prior_chat_authorization`. It does
not claim that a person pressed a terminal key or platform button. A failed
audit write prevents the handler from returning an affirmative response.

`InteractiveApprovals` remains a separate mode. It requires both input and
output to be terminals, displays the escaped real request and bound native
arguments, and reads a new human decision. It records
`origin: "interactive_terminal"` and still records `identityAttested: false`.
A Remote Desktop Commander process with piped stdin does not satisfy this
terminal condition. Creating a pseudo-terminal and feeding it canned answers
would not establish human participation and is not part of this workflow.

An explicit sensitive-action or strict-review signal, a device flow, a secret
input, or an unknown human-presence requirement is handed off by rejecting the
prior-authorization handler. No client changes host policy, approval settings,
tool annotations, credential state, or persistent permissions.

## Read-only account preflight

The installed `account/read` params schema allows an optional boolean
`refreshToken`. A non-refreshing probe uses `{"refreshToken":false}`.
`account/rateLimits/read` allows absent params or JSON `null`; its params are
not an object. The exact variants and their source schema hash are in
`schema/account-request-variants.json`.

The account response can contain identifying fields. A probe should retain only
the account mode, plan type and necessary non-identifying limit/status fields;
it should not save emails, account IDs or tokens. No account response or
credential is included in this directory. Identifying a subscription account
does not alone establish an added-spending guarantee or a monetary price.

## Validation and remaining limits

The targeted suite passed **32 tests** with:

```sh
python3 -B -m unittest discover -s test -p 'test_paper1_approvals.py'
```

It covers the actual source-defined forms and questions, exact native item and
argument binding, scope, replay, request resolution, deadlines, terminal-only
manual input, required grant references, immutable grant snapshots, mandatory
audit recording, one-call responses, and rejection of permanent-only or
unknown/device/human-presence flows. The protocol fixtures and placeholder
grant hashes are explicitly test data; they do not authorize an experiment.

`git diff --check` passed for the two implementation/test files. This evidence
collection started no model generation and no native trial. Passing local
fixtures does not demonstrate that the current host emitted this request,
accepted this client response, or completed an experiment. Actual live logs
must establish those separate facts before they are used in the paper.
