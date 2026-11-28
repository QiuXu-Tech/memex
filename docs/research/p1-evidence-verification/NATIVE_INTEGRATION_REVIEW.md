# Native P1 integration review

Reviewed on 2026-11-28. This is a source/interface review and offline test record,
not a native experiment result or provider compatibility claim. The original
authorization, cash ledger, Raw-RAG configuration and frozen experiment records
were not modified by these tests.

## Reviewed boundaries

The review covered `native_backend.py`, `reader_profile.py`, `paired_runtime.py`,
`runtime_controller.py`, `deepseek_native_relay.py`, `rawrag_controller.py` and
the persistent `paired_evidence.mjs` helper. The native backend uses one canonical
controller and relay across the paired work. Each host operation starts a fresh
restricted Codex process with that activation's random local token, then resumes
or forks the actual persisted native thread. The real credential callback is
passed only to the relay; neither host environment nor model input receives the
real provider credential.

The final `_ensure_relay` wiring passes both mandatory controller callbacks,
registers the relay's immutable private audit identity and binds its receipt
before activation. Every actual forwarded provider request therefore requires
durable admission. Every admitted request must also complete the immutable-file
usage handshake before a later request or operation. Native thread metadata and
zero-call reads do not create provider usage observations.

## Concrete findings and fixes inspected

| Finding | Corrected path inspected | Focused regression coverage |
|---|---|---|
| A successful RPC response could identify the wrong resumed thread or claim a fork without proving its parent and inherited history. | `PublicNativeHost.select_thread` checks the returned resume ID and actual `forkedFromId`; `fork_parent` performs `thread/read` with turns and checks retained compaction, original request, parent content hash and turn IDs. | `test_actual_fork_lineage_and_inherited_content_are_independently_checked`; actual-history and partial-history tests in `test_paper1_native_backend.py`. |
| A host failure retained a local provider audit but could omit already observed usage from the experiment's usage stream. | `_Scope.operation` invokes the non-dispatching `capture_failure_usage` hook on failure. The native backend preserves measured provider usage and valid Raw-RAG usage prefixes while marking coverage incomplete. | `test_failed_backend_known_usage_is_retained_before_terminal_failure`; failed-provider and interrupted-baseline-tail tests. |
| Evidence-open admission checked the archive/task but did not reject a different original request, helper epoch or verification unit before canonical ledger writes. | `_source_admission` verifies original-request digest, retained prime digest/epoch, same live helper epoch, expected prime or run identity and the 4,000-byte source bound before `record_action`. | `test_source_admission_binds_request_epoch_and_unit_before_ledger_write`. |
| Charging every possible DeepSeek request the full single-request bound made the five-scope block exceed the unchanged original cash cap even with small actual cumulative usage. | The optional, current-source/current-profile serial envelope independently checks actual completed provider totals and permits at most one pending request. A final unknown, excess or late result blocks the scope permanently. The registered immutable transport proof and same-UTC-day official price basis support the CNY 3.20 reservation. | Controller and relay handshake tests, including pending work after restart, expiry, tampering, limits and mixed-provider B bounds. |

The last row is a conditional reservation proof, not observed spending. The
legacy per-request mode remains. B still needs independently checked real
embedding/reranker billing evidence; the new proof does not invent that price or
relax the original retrieval limits.

## Evidence and retrieval interfaces

C and D use a single persistent helper process and one actual archive epoch
across preparation, prime and later verification. Each verification unit clones
the immutable prime cache; a C run's new receipts cannot prime a later D unit.
The backend checks archive, original-request and epoch identities in helper
results. Helper state is outside the sealed checkpoint, whose extraction copy is
byte-identical to the retained extraction artifact.

Every original archive open is preceded by a controller admission request. The
helper rejects a source whose ingested metadata bound exceeds 4,000 bytes before
opening it, rather than silently truncating it. Counts describe actual calls,
pages and bytes. An abstention keeps its null receipt. Public-tool continuation
and method verification share the canonical action limits. The helper does not
label UTF-8 byte counts as tokenizer usage.

B passes the unchanged fixed configuration as an object and its explicit
`faithful` or `budget-matched` display policy as a string. Its checkpoint digest
is the canonical digest of the ten identity fields; the complete sealed
checkpoint has a separate digest. Usage and trace references use the shared
`{path, sha256}` convention with consistent component prefixes. Each embedding or
rerank attempt has a distinct durable admission and meter record.

## Verification performed and limits

The following targeted suites passed during this work:

| Suite | Result | What was actually exercised |
|---|---:|---|
| `test_paper1_rawrag*.py` | 57 passed, 0 skipped | Installed SDK/HTTP clients with in-memory transports, retries, immutable input binding and direct `experiment.standardized_cost` integration. |
| `test_paper1_runtime_controller.py` | 40 passed | Canonical controller over temporary authorization/ledger fixtures, actual registered audit files, sequential completion and cash proof failure boundaries. |
| `test_paper1_deepseek_native_relay.py` | 16 passed | Real loopback HTTP server, in-memory upstream, sanitized SSE/usage handling, epoch invalidation and real controller registration/completion integration. |
| `paper1-paired-evidence.mjs` | 11 passed | Real archive/helper behavior, immutable prime cloning, admission before opens, truthful limits and retained receipts. |
| Helper plus relevant archive/claim/replay/verification suites | 47 passed | Combined Node contracts; includes the helper's 11 tests rather than adding 47 new helper tests. |

The parent integration also retains a real Python-to-Node protocol test covering
prime/C/D with one helper epoch; the review inspected this test and the corrected
source paths. The final whole-repository suite belongs to the parent integration
handoff and is not claimed here as rerun after every later edit.

There were zero external model or paid endpoint calls in this review. Real
provider credentials were not read. A native paid run still needs valid
credentials, a working pinned host/provider wire combination, real native
compaction and inherited-thread observations, and verified fixed-model B billing.
Offline passing tests do not substitute for those observations or create any
scientific sample. Missing or partial usage remains incomplete, and actual cash
is not settled from reference tokens or public list prices.
