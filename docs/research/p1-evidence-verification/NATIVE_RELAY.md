# Controlled native Responses relay

`scripts/paper1/deepseek_native_relay.py` implements a loopback HTTP transport for
a separately controlled, real Codex host. It does not create native threads,
forks, compaction events or checkpoint evidence. Those identities must come from
the host integration and its retained native records.

## Interface

```python
relay = DeepSeekRelay(
    profile=profile,                    # Entire versioned public profile object.
    output=new_audit_directory,
    credential_provider=broker,         # () -> real key, never supplied to Codex.
    authorize_dispatch=controller.authorize_dispatch,
    complete_dispatch=controller.complete_dispatch,
    token_counter=reference_counter,    # (canonical_request_json: str) -> int.
)
# A canonical scope must already be reserved. The relay constructor does not
# obtain credentials or contact the provider.
relay.bind_transport(controller.register_transport(relay.registration))
activation = relay.activate(
    scope_id=scope_id,
    component="reader",                # reader/prelude/extraction/compaction.
    checkpoint_sha256=identity_sha,     # Reader: canonical identity10 digest.
    deadline=absolute_monotonic_seconds,
)
# Host provider: base_url=activation["base_url"], wire_api="responses".
# Host environment receives activation["local_token"], never the real key.
# Use a fresh short-lived host process for every activation/token epoch.
relay.deactivate()
records = relay.records                # Sanitized deep copy.
scopes = relay.scope_states             # Cumulative, including blocked old scopes.
relay.close()
```

Both callbacks are mandatory and synchronous. Each accepts its message as the
first argument and `scope_id` as a keyword. `relay.registration` is a property,
not a method. Activation is refused until its registration receipt is bound.

Native stages before a checkpoint exists may use a null checkpoint digest.
Reader activations require a digest. An existing scope cannot change checkpoint
identity. Output must be a new directory; this process does not import prior
usage or resume an old relay audit.

The fixed upstream is `https://api.deepseek.com/responses`, model
`deepseek-flash`. All profile fields, including tokenizer and host provenance,
participate in `config_sha256`. The public profile fixes reasoning effort `none`,
temperature zero, no retries, request/response byte caps and token/dispatch
ceilings. Lower positive limits are supported within the implementation's hard
ceilings; a different model or endpoint is rejected. The canonical controller's
registered native path additionally requires the complete pinned profile hash.

## Registration and completion handshake

Construction creates a private `0700` audit directory and an exclusive, fsynced
`0600` `transport.json`. The registration object binds `transport_id`,
`audit_root`, complete `config_sha256`, the actual relay source file SHA-256 and
the registration file's absolute path/hash. The canonical controller checks
ownership, regular files, single links, permissions, normalized paths and the
absence of symlinks. The audit root must be separate from public task inputs and
the original cash ledger. It must match the implementation and profile present
on the executing machine. A hash binds these bytes; it is not evidence of a
provider account balance or price by itself.

The seven-field `p1-relay-registration-receipt` contains `schema_version`,
`kind`, `transport_id`, `config_sha256`, `relay_source_sha256`,
`registration_sha256` and `admission_id`. Every provider intent binds this
transport identity. A caller cannot select an arbitrary audit path per request.

After every admitted attempt, the relay creates an exclusive, fsynced
`dispatches/<dispatch_id>.json`. This immutable record binds the scope,
transport, intent and request to observed provider dispatch state, terminal
status, response digest/bytes and actual numeric usage or explicit unknown
usage. It contains no prompt or response text. Only then does the relay call
`complete_dispatch` with the following commitments:

```json
{
  "schema_version": 1,
  "kind": "p1-provider-dispatch-completion",
  "transport_id": "registered transport identity",
  "dispatch_id": "admitted dispatch identity",
  "request_sha256": "exact forwarded request digest",
  "intent_sha256": "admitted intent digest",
  "record_sha256": "immutable dispatch record digest"
}
```

The controller derives the file path from the registered private root, reads
the actual file and checks its commitments. Completion messages cannot supply
replacement usage quantities. The returned seven-field
`p1-dispatch-completion-receipt` contains `schema_version`, `kind`,
`dispatch_id`, `intent_sha256`, `record_sha256`, `decision` and `admission_id`.
Only a matching `decision=continue` allows the buffered response to be replayed.
A missing or mismatched receipt withholds it and blocks the relay scope.

The controller independently enforces one unfinished provider request per scope.
Until a durable completion exists, a later dispatch or operation is rejected,
including after constructing another controller over the same canonical journal.
Completed evidence is rechecked before later work; replacement is rejected.
Unknown, excess, failed or late results permanently block further dispatches in
that scope. Late evidence can still be retained, and known usage is preserved;
it does not reopen the scope or settle actual cash.

## Request and dispatch boundary

The relay accepts `POST /responses` with JSON, an exact current bearer token,
one bounded Content-Length and no transfer encoding. It requires a complete,
stateless input and streaming mode. Previous-response chaining, server tools,
images, files, reasoning payloads and unsupported request fields are rejected.
Client tools are restricted to the five public dynamic functions `read_file`,
`write_file`, `list_files`, `run_current_tests` and `record_review`. Built-in shell,
custom/freeform tools and other functions are rejected, including their history.
The auxiliary extraction request may carry an empty tool list.

The forwarded body sets `store=false`, nonthinking reasoning, temperature zero,
and an output cap bounded by the scope's remaining output allowance. Its exact
bytes and the original host wire body receive separate SHA-256 commitments. The
reference counter measures the canonical forwarded JSON; this reproducible
reference count is not an exact prediction of provider-billed input tokens.

Every upstream HTTP request calls the canonical admission callback first. The
intent binds provider, model, endpoint, component, scope, checkpoint, complete
profile hash, exact request hash/bytes, reference input count, output/response
caps and remaining timeout. The required receipt is the shared seven-field
`p1-dispatch-admission-receipt`, with decision `allow` and matching dispatch,
request and intent hashes. The relay persists the accepted receipt and reserved
dispatch before invoking HTTPS. A callback exception, mismatched receipt or
expired deadline prevents a send. The implementation does not retry or follow
redirects.

The per-request deadline begins when the authenticated loopback request is
accepted. Reading its body, obtaining credentials, admission, HTTPS, bounded SSE
reading, completion and replay all share that deadline. A slow callback does not start a new
network timeout allowance.

## Response, usage and scope state

The complete bounded SSE response is buffered before it is delivered. The relay
checks semantic event names, increasing sequence numbers, a consistent fixed
model/response identity, permitted output items, a final terminal event and
secret reflection. Raw and escaped real/local credentials are screened. No
prompt, output or reasoning text is written to the audit. Unsupported or
incomplete responses are withheld in full.

Actual usage is taken from the terminal response's `input_tokens`,
`output_tokens`, and `input_tokens_details.cached_tokens`. Cached input is a
subset of input. Missing, inconsistent or reasoning-bearing usage is unknown;
reference counts never replace it. Complete usage from an over-budget response
is retained even though that response is rejected. A missing/unknown usage,
provider error, failed terminal or budget overrun blocks further requests in the
scope. `actual_spend` remains null: this audit is not invoice reconciliation.

Each activation rotates the local token and epoch. Switching components in the
same scope retains its cumulative quotas. Activation is refused while a request
is in flight. Deactivation/close during an in-flight operation locks that old
scope with incomplete usage and invalidates its epoch; a late response cannot be
replayed into a new operation. Old blocked scope state remains in the audit.

`relay-state.json` is replaced atomically and fsynced with its directory. It
contains only request commitments, intents/receipts, numeric usage, terminal
metadata, scope state and safe error codes. Records use the component names
`reader`, `prelude`, `extraction`, and `compaction`; the integrating runtime maps
these records into experiment usage rows and retains the audit as their source.
The immutable registration and per-dispatch files are the controller's completion
evidence; the mutable aggregate is not substituted for them.

## Conditional scope cash bound

The old per-request cash envelope remains available. The pinned native Responses
provider may instead declare this exact optional provider field:

```json
{
  "scope_usage_envelope": {
    "kind": "deepseek-native-serial-envelope-v1",
    "relay_source_sha256": "SHA-256 of the executing relay source file",
    "max_input_tokens": 65536,
    "max_output_tokens": 8192,
    "max_http_dispatches": 8,
    "scope_upper_bound_cny": "3.20"
  }
}
```

This mode requires `checked_upper_bound_cny` to equal `3.00`, the current complete
reader profile hash, actual transport registration and the completion handshake.
Its `checked_upper_bound_evidence` must hash a checked public price-basis file
with the fixed model, CNY currency, official URL, peak prices, conservative
context cap and the profile's `checked_date`. That date must equal the executing
machine's UTC date at validation, registration and each new admission. An expired
proof blocks new work; finishing an interrupted scope with unknown actual cash
remains possible. Refreshing the development profile and factual pricing evidence
requires rebinding their hashes and does not change the original authorization.

The [official DeepSeek price page](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/),
checked on 2026-11-28, lists peak uncached input at CNY 2 per million tokens and
output at CNY 8 per million for the fixed Flash model. Pricing all input as
uncached bounds any cache discount. Before a last uncertain request, known
cumulative usage is at most 65,536 input and 8,192 output tokens, costing at most
CNY `0.196608` under that price basis. The controller holds an additional CNY
`3.00` for the last unknown or over-limit request. Its conservative 1,048,576
context-token cap plus 8,192 output tokens costs at most CNY `2.162688` at those
prices. Rounding `0.196608 + 3.00` upward to whole fen gives CNY `3.20` per scope.
Sequential admission and permanent blocking after the first unknown/over-limit
result are essential to this proof. Reference tokenizer counts do not establish
the known prefix; completed provider usage does.

For a B scope this bound covers only the DeepSeek reader. The unchanged 16-call
retrieval envelope additionally requires `16 × max(checked non-DeepSeek
per-request bound)`. It needs genuine fixed-model embedding/reranking billing
evidence. This code does not assign a guessed Cohere price. All values here are
reservation bounds: actual cash stays unknown until supported reconciliation,
and no reservation is released by treating token estimates as an invoice.

The checked fact artifact is
[`artifacts/remaining-completion-01/deepseek-price-basis.json`](artifacts/remaining-completion-01/deepseek-price-basis.json).
It is explicitly neither an authorization nor a cash observation.

## Verification and external prerequisites

Tests in `test/test_paper1_deepseek_native_relay.py` exercise the real loopback
HTTP server with an in-memory upstream. They cover profile hashing, fixed wire
settings, callback proof, deadline expiry, allowed tools, credential reflection,
SSE validity, byte limits, missing/over-budget usage, epoch rotation, cumulative
quotas and deactivation of an in-flight request. On 2026-11-28, the relay's 16
tests and the controller's 40 tests passed. One integration test connects the
real loopback server to an actual canonical controller over a temporary fixture
ledger, checks immutable usage completion, and makes a second admitted request.
Controller tests cover restart with pending work, immutable evidence replacement,
late/unknown/excess completion, remaining output allowance, same-day pricing and
mixed B cash bounds. These tests do not contact a provider, touch the original
cash ledger or read a real credential.

An authorized live run still requires the canonical budget controller, a real
credential broker, the pinned public tokenizer, a correctly restricted Codex
custom-provider profile, real native thread/resume/fork/compaction evidence and
the host's public tool broker. Loopback protocol tests do not establish live
provider or native-host compatibility.

Primary protocol references:

- [DeepSeek Responses API guide](https://api-docs.deepseek.com/guides/responses_api/)
- [DeepSeek create-response API](https://api-docs.deepseek.com/api/create-response/)
