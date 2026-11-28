# Persistent paired evidence helper

`scripts/paper1/paired_evidence.mjs` replaces the fixture-specific read-only
replay interface for real public task archives. It uses the existing
`extractClaims`, `verifyEvidence`, and real Memex `EvidenceArchive` without
substituting expected answers or model-supplied receipt locations.

## Bound inputs and lifecycle

Start one process for the entire prime/C/D family of one checkpoint:

```text
node scripts/paper1/paired_evidence.mjs CONFIG_JSON_PATH
```

The configuration has exactly these fields:

```json
{
  "schema_version": 1,
  "archivePath": "/absolute/public-source-archive.json",
  "archiveSha256": "64 lowercase hex characters",
  "requestPath": "/absolute/original-request.txt",
  "requestSha256": "64 lowercase hex characters",
  "taskId": "bound-public-task-id",
  "output": "/absolute/new-helper-directory",
  "publicInput": {
    "draft": "actual prelude final text",
    "context": "public workspace summary",
    "toolDescriptions": ["public tool descriptions"]
  }
}
```

Archive and request hashes commit raw file bytes. The archive's task ID must
match. The archive uses the common public schema
`{schema:1,taskId,snapshot:{cutoff,watermark,complete:true},sources:[...]}`.
It must contain a complete, bounded snapshot without supervision metadata.
The helper rechecks both input commitments before operations and around source
admission/verification. Input/output symlinks and reused output directories are
rejected.

The integrating controller constructs `publicInput` only from observable task,
prelude and public tool material. The helper does not derive extraction hints
from the archive. `prepare` exposes only request, draft, context and tool
descriptions to the auxiliary model. It retains the exact prompt and input
commitment. `install` accepts the model's actual text and applies the existing
grounding contract; it never accepts manually supplied claims. Invalid and empty
extractions are retained without filling in missing obligations or receipts.

Prime performs one real selective verification. Its valid receipts form a
private cache. Every later unit receives a new clone of that original cache;
results produced by a prior C or D unit never update it. C uses `always` and
reopens actual originals. D uses `selective` and reuses receipts only when the
existing verifier confirms the same real archive view and epoch. Receipt reuse
still delivers the complete original and has nonzero evidence bytes.

The helper creates one actual archive epoch and keeps it for its lifetime.
Restarting creates a new epoch and requires a new prime. The protocol has no
operation for importing prime receipts. Each unit ID is consumed once, so C and
D need different unit IDs. The helper supports one prime and up to 128 later
units; the outer runtime remains responsible for its registered experiment plan.

## JSON-lines protocol

Commands have a unique caller ID. Successful responses have
`{ok:true,id,result}`; errors have `{ok:false,id,error}` with a safe code.

```json
{"id":"prepare","op":"prepare"}
{"id":"install","op":"install","rawOutput":"{\"claims\":[],\"unresolved\":[]}"}
{"id":"prime","op":"prime","limits":{"maxSourceOpens":6,"maxSourceBytes":24000,"maxSourceBytesPerOpen":4000}}
{"id":"C","op":"verify","unitId":"task-replicate-C","mode":"always","limits":{"maxSourceOpens":32,"maxSourceBytes":96000,"maxSourceBytesPerOpen":4000}}
{"id":"D","op":"verify","unitId":"task-replicate-D","mode":"selective","limits":{"maxSourceOpens":32,"maxSourceBytes":96000,"maxSourceBytesPerOpen":4000}}
```

Prime/verify optionally accept `maxPacketBytes`, `maxEvidenceBytes` and
`maxReferenceBytes`. These are byte limits, not tokenizer measurements.
Per-original evidence/reference limits cannot exceed 4000 bytes. Combined
delivery defaults to 20000 bytes; an oversized complete packet is withheld with
an explicit notice, while full verification records remain retained.

## Source-open admission

Search selects real Memex locators. Before each original is opened, the helper
looks up its byte bound from the same ingested archive metadata. A source whose
complete serialized original exceeds the per-open limit is rejected before any
original open. The implementation deliberately abstains on those sources; it
does not pretend that a large read cost one 4000-byte open.

For an eligible original, the helper emits an intermediate line and waits:

```json
{
  "kind": "operation_admission_required",
  "id": "generated-admission-id",
  "intent": {
    "schema_version": 1,
    "kind": "source_open",
    "operation_id": "generated-source-open-id",
    "task_id": "bound-public-task-id",
    "archive_sha256": "bound archive hash",
    "original_request_sha256": "bound request hash",
    "archive_epoch": "actual live archive epoch",
    "unit_id": "task-replicate-C",
    "event_id": "real discovered source event",
    "source_bytes_upper_bound": 1000,
    "bound_from_ingested_archive_metadata": true
  }
}
```

The outer controller must persist the corresponding `source_open` and public
tool-call accounting before replying. The reply must match both IDs:

```json
{
  "kind": "operation_admission_response",
  "id": "generated-admission-id",
  "allowed": true,
  "operation_id": "generated-source-open-id",
  "receipt": {"operation_id":"generated-source-open-id","persisted":true}
}
```

`receipt` is optional when the operation ID already identifies a persisted outer
controller record; the helper retains any supplied receipt. These example
receipt fields do not themselves create canonical authorization. The real
parent must call its canonical ledger, not copy the example proof.

Only a matching positive response permits the real `archive.open`. That open
must consume one actual `engine.openEvent` page, and the observed serialized
bytes and digest must match the predeclared bound. Denial, missing proof,
timeout, unknown locator, input mutation or an exhausted limit yields a real
verifier abstention or operation failure. There is no hidden source read to
replace the denied operation. The admission wait is at most 30 seconds; EOF
rejects pending admissions.

Prime permits at most six source opens; later units permit at most 32, with
96000 total bytes and 4000 bytes per open as hard ceilings. The caller may pass
smaller remaining limits, including zero available opens/bytes. Parent scopes
combine these operations with public prelude or continuation tools. The helper
does not reset or replace those outer cumulative quotas.

## Results and retained evidence

Every successful result includes task/request/archive identity and the actual
archive epoch. Verification adds full `results`, the delivered `packet`, and a
parallel `receipts` array in which null abstentions remain null. It returns
`counts.source_open_calls`, `source_open_bytes`, `source_open_pages`,
`public_tool_calls`, admission counts and verifier view/search/open-attempt
counts. An attempted verifier open that was blocked before original I/O does
not count as an actual source open. Reserved byte bounds are reported separately.
If an actual page fails before returning observable byte data,
`source_open_bytes_complete` is false; the canonical reservation is still kept.

The existing verifier's `metrics.referenceTokens` fallback is explicitly marked
`utf8_bytes_upper_bound`. The helper also reports
`tokenizerMeasurement:false`, `referenceTokenCount:null`, and
`providerTokenCount:null`. The native backend must measure the complete final
packet with its pinned public tokenizer and obtain provider usage independently.

The new output directory retains the bound raw inputs, binding, preparation,
extraction, prime, every verification, each source admission/result and the real
Memex L2 store. Immutable `trace_refs` use `{path,sha256}` relative to this
directory. The outer runtime prefixes their paths when assembling a unit's
records. The helper's `extraction_sha256` is the actual `extraction.json` file
hash, so the outer prime/checkpoint binding must reference that exact artifact.

Tests in `test/paper1-paired-evidence.mjs` exercise real archives, actual page
opens, exact prime receipt reuse, cross-unit isolation, failed/empty extraction
outcomes, byte/call caps, changed bindings, process restarts and the persistent
bidirectional CLI. No provider or credential is involved.
