# P1 task-bound paired runtime

`scripts/paper1/paired_runtime.py` implements controller orchestration with an
injected host/backend and one authoritative admission controller. It performs
real calls to those injected operations; it does not supply a provider, sandbox,
credential loader, native host, human review, or experimental result.

The module adds an explicit public-path relocation receipt, native checkpoint
admission, forward-only operation journals, separate arm workspaces, and the
existing `experiment.py` result/usage output contract. The original source plan,
authorization, public packages, and historical ledgers are not rewritten.

## Entry points

| Function | Result and boundary |
| --- | --- |
| `create_relocation_receipt(plan_path, packages, authorization)` | Revalidates both authorized packages and returns a derived path receipt. No reservation or model request. |
| `admit_relocation(receipt, plan_path, packages, authorization)` | Recomputes that receipt and rejects any changed field. |
| `prepare_block(task, replicate, backend, controller, output, ...)` | Reserves a **native** scope through the controller, then captures the actual parent, primes D, and compacts that parent. Publishes a checkpoint only after successful finalization. |
| `load_checkpoint(checkpoint_path, ...)` | Revalidates the published checkpoint, completed preparation, original request in the native prelude, completed native compaction, retained prelude prefix, and all bound artifact bytes. |
| `import_checkpoint(checkpoint_path, task, replicate, output)` | Copies an already task-bound checkpoint and its first-attempt registry. A historical summary for another scenario is not an importable checkpoint. No new native permit is created. |
| `run_unit(checkpoint_path, arm, run_id, output, backend, controller, ...)` | Executes exactly one method unit, suitable for an executable wrapper implementing the `experiment.py` ABI. |
| `run_paired_block(task, replicate, backend, controller, output, order=...)` | Convenience composition of one preparation and all four separately admitted method units. Never invoke this once per arm from `experiment.py`. |

`task` has exactly `task_id`, `project_id`, `public_path`, `public_sha256`,
`taskpack_public_sha256`, `original_request_sha256`, and
`shared_reader_config_sha256`. The first five can be obtained from an admitted
relocation row, excluding `original_public_path`. The request hash is the SHA-256
of the unchanged request file. The reader hash must identify the separately
frozen common configuration, not an unrecorded runtime choice.

Relocation compares the entire regenerated original plan after substituting
only the two recorded `public_by_replicate` locations. Both replicates of each
task remain bound to one identical public tree. All other plan fields, the
authorization's original plan-file hash, both tree digest algorithms, permission
modes, budget bytes, arms, and the sixteen units must agree. Original absolute
paths are treated as recorded identities and never followed. Save the returned
receipt as a new controller artifact with `write_json`; it is not a replacement
for the original plan or new permission.

## Backend protocol

Every operation has this synchronous signature:

```python
def operation(context: dict, *, output: pathlib.Path, deadline: float) -> dict:
    return {"value": value, "usage_rows": observed_usage, "trace_refs": references}
```

The deadline uses `time.monotonic()`. Backends must enforce cancellation and
per-request/tool admission inside long operations. The runtime checks the
deadline before and after each operation; it cannot preempt arbitrary synchronous
Python or cancel an already dispatched remote request by itself.

Contexts are controller-only. Forwarding a complete context to a model would
expose controller paths and method metadata. The backend constructs the common
model-visible input from the public descriptor/request/budget, actual compacted
parent, permitted tool results, and the delivered method packet.

Each `trace_refs` item is exactly `{path, sha256}`. Paths in operation values,
trace references, and usage `source_ref`/`evidence_ref` are relative to that
operation's output directory. Symlinks, traversal, and external references are
rejected. The runtime preserves the original response and rebases usage evidence
paths into the final per-unit output tree.

| Operation | Exact `value` fields |
| --- | --- |
| `capture_parent` | `task_binding`, `native_parent_thread_id`, `workspace_path`, `source_archive_path`, `native_capture_path` |
| `prime_D` | `extraction_path`, `receipts_path` |
| `compact_parent` | `native_parent_thread_id`, `turn_id`, `item_id`, `native_capture_path` |
| `verify_checkpoint` | `binding` |
| `fork_parent` | `native_parent_thread_id`, `thread_id`, `workspace_path`, `fork_response_path` |
| `build_packet` | `packet`, `checkpoint_sha256`, `source_archive_sha256`, `original_request_sha256`, `extraction_sha256`, `d_prime_sha256`, `shared_reader_config_sha256` |
| `continue_reader` | `result`, `budget_usage` |

`capture_parent.task_binding` has exactly `task_id`, `replicate`, `public_sha256`,
`original_request_sha256`, and `shared_reader_config_sha256`. The capture must
contain a completed native user-message event holding the actual original
request, in a completed turn on the claimed parent. The completed compaction
capture must retain the admitted prelude bytes as an exact prefix. A summary
with an item ID is insufficient: the runtime requires the actual ordered
`turn/started`, completed `contextCompaction` item, and successful
`turn/completed` events for the same thread and turn.

`prime_D` supplies the actual checked extractor result and a separate receipt
object. The extraction requires `ok=true`, nonempty `claims`, `rawOutput`, and
`coverageEstablished=false`. Priming requires `extraction_sha256`,
`source_archive_sha256`, and nonempty `receipts`. The backend is responsible for
using the shared extractor/verifier and retaining their source provenance. The
runtime verifies bindings; it cannot turn untrusted backend assertions into
authenticated provider observations.

`verify_checkpoint.binding` contains exactly the following ten fields:

```text
task_id, replicate, public_sha256, workspace_snapshot_sha256,
native_parent_thread_id, native_capture_sha256, native_compaction_item_id,
source_archive_sha256, shared_reader_config_sha256, original_request_sha256
```

The runtime calls this operation before the fork and again after the
continuation. The backend must inspect the actual retained parent and return
its current identity, rather than echoing the expected value without checking.
All four arms must use the same unchanged parent. Each fork must have a distinct
thread ID and separate, non-hardlinked workspace whose initial digest equals
the checkpoint workspace. The `fork_response_path` file retains the native
`thread/fork` request and response as `{method, request, response}`.

Two hashes have deliberately distinct meanings:

- `checkpoint_sha256` is the canonical digest of the ten identity fields. It is
  also the checkpoint identity accepted by the strict Raw-RAG controller.
- `sealed_checkpoint_sha256` binds the complete checkpoint object, excluding
  only this seal field. It additionally binds task paths, priming, extraction,
  compaction turn, artifact references, and evidence origin. Paired admission
  intents carry both hashes.

A receives no supplemental packet and does not call `build_packet`. B binds its
retrieval output to the original request and exact source archive; its
`extraction_sha256` and `d_prime_sha256` are null. C and D both bind the actual
same extraction. C has null `d_prime_sha256`; D binds the primed receipt bytes.
The common reader configuration hash must match in every packet.

`continue_reader.result` uses the existing `experiment.py` result schema and
must point to a captured local trace. It never supplies `decision_success`.
`budget_usage` has exactly `model_input_tokens`, `model_output_tokens`,
`tool_calls`, `source_open_calls`, and `source_open_bytes`, with observed integer
counts. Missing counters remain a capture failure. Exceeding an original public
limit produces `budget_exhausted`, retaining observed usage. The backend must
also prevent excess dispatch in advance; the outer postcheck does not itself
enforce limits during a provider's execution.

## Admission and failure handling

The controller implements `admit_scope(intent)`, `before_operation(intent)`, and
`finish_scope(intent, result)`. Both admission calls return the seven-field
`p1-dispatch-admission-receipt` envelope used by the provider transports. The
runtime checks dispatch, request, and intent hashes before calling the backend.

Method `scope_id` is the supplied `run_id`. Native scope IDs come from
`native_scope_id(task, replicate)`. Intents contain the kind (`native` or
`method`), operation, task/project, replicate, arm, run ID, both checkpoint
hashes, unique dispatch ID, request digest, and intent digest. The intent digest
is computed over the whole intent excluding its own field.

The local operation journal records and fsyncs `operation_started` before the
controller admission, then `operation_admitted` before the actual backend call.
An interrupted operation keeps its start record and partial files. No resume
path repeats it. Each arm is durably reserved locally before its first method
call; retries, renamed output directories, and checkpoint imports cannot erase
that local reservation. Global cash and attempt enforcement still belongs to
the one controller and canonical ledger. The local registry does not claim
distributed locking across manually copied repositories or devices.

The two historical native attempt slots remain consumed. `prepare_block` needs
a real native-scope admission and cannot obtain one from a method reservation.
Importing unrelated archived compaction evidence cannot fill that requirement.
No ordinary DeepSeek completion can replace a host's native compacted state or
its actual same-parent forks.

Checkpoint admission also checks the entire containing directory for regular
files, symlinks, environment files, and the existing size bound before import or
per-unit copying. Ancillary evidence cannot hide a link to external controller
data merely because it is absent from the six primary artifact references.

## Output and accounting

Every method output contains `result.json`, `usage.jsonl`, a hash-chained
`operations.jsonl`, per-operation admission/response/artifacts, the actual method
packet, and a full copy of checkpoint evidence. This keeps the bytes needed for
scoring inside the output sealed by `experiment.py`.

Observed usage is appended before subsequent operations. Component seals are
retained and combined only after all local stages finish; no missing component
is invented. Shared preparation usage is copied with its evidence and must be
allocated according to the separate frozen measurement declaration. Actual
cash, standardized full cost, and full-pipeline capture completeness remain
unknown until the external controller/measurement audit establishes them.
Provider token counts alone do not settle the cash reservation.

Controller finalization failure changes the terminal outcome to
`capture_incomplete`. Preparation candidates are not importable published
checkpoints. `scientific_ready` remains false: native runtime completion does not
create accepted workflows, independent human reviews, hidden behavior scores,
or evidence for a method effect.

## Offline verification

```bash
python -B -m unittest discover -s test -p test_paper1_paired_runtime.py -v
```

Tests use temporary contract fixtures with
`backend.evidence_origin='contract_fixture'` and explicit
`execution_mode='contract_test'`. Such a backend is rejected by the live entry
point. A separate test reads the existing `readonly-native/attempt-01` host log
to validate the real recorded compaction event structure, then verifies that
the other scenario's summary cannot be imported as an authorized source task.
These checks perform no provider requests, native execution, source tests,
credential access, or method-budget reservation.

## Public workspace broker

`scripts/paper1/public_workspace.py` supplies the model-visible workspace tools
used by the separate native backend. It accepts only a validated source-task
public package and copies its workspace into a new independent directory. It
does not expose evaluator files or an arbitrary command tool.

```python
broker = PublicWorkspace(
    public_path, new_workdir, new_controller_root,
    authorize_operation=admit_tool,
    limits=optional_stricter_limits,
    sandbox=actually_probed_runner,
    python=pinned_task_python,
    source_snapshot=optional_bound_checkpoint_workspace,
    expected_snapshot_sha256=optional_checkpoint_workspace_digest,
)
broker.constrain_deadline(controller_monotonic_deadline)
response = broker.call("read_file", {
    "path": "src/flask/blueprints.py", "offset": 0, "limit": 4000,
})
```

Every `.call(name, arguments)` returns exactly `{ok, result, receipt}`.
`.tool_descriptions` returns the JSON schemas for `read_file`, `write_file`,
`list_files`, `run_current_tests`, and `record_review`. `.workdir` is the current
public tree, `.counters` is a copy of observed counts, and `.snapshot()` reports
both the observer's original digest and `version`, the
`experiment.public_digest` used by checkpoint binding. The constructor rejects
an existing session directory; restarting a broker cannot reset its counters.

`constrain_deadline` takes a finite monotonic time and can only shorten the
session. A deadline already in the past makes later tool calls fail before a
side effect. The host must call it with the enclosing operation's deadline so
a late test call cannot acquire a new wall-clock allowance.

The admission callback is synchronous and receives exactly:

```text
schema_version, operation_id, tool, arguments_sha256,
workspace_sha256, kinds, observable_kind
```

It must persist its admission before returning
`{operation_id: intent.operation_id, admitted_kinds: intent.kinds}`. `kinds`
contains `public_tool_call`, plus `source_open` for `read_file`.
`observable_kind` identifies `test_execution` for the fixed test tool. The
native canonical ledger supports tool and test counters; its original schema
does not have a separate source-open event. The enclosing native controller
therefore counts those reads as public tools while retaining actual broker
source-open counters. Method scopes count their original tool/source-open
events. This adaptation must not expand the original ledger's event schema or
return an incompatible callback envelope.

Reads expose at most 4,000 UTF-8 bytes per call, 96,000 bytes and 32 opens in one
session. All calls share the 64-tool cap, and an attempted call is consumed even
when its arguments fail. Byte offsets cannot split a UTF-8 character. Writes
require the exact current file hash, or null for a new file, and may replace an
explicit byte range. They operate on the detached public copy only. Absolute
paths, traversal, symbolic links, private directory names and environment files
are rejected. Reviews bind actual prior tool receipt IDs and the current
workspace version; they are local observations with no independent quality
judgment or publication.

### Edited-source tests and OS isolation

`run_current_tests` executes the fixed task profile against a copy of the
**currently edited** source. It retains the original Python workflow observer,
fixed test selection, dependency identity, nonce, stdout/stderr, and before and
after snapshots. It does not widen `python_workflow.py`'s pristine-source entry
point. Added cases in the fixed test modules run; a newly created unrelated
test module is not silently added to the selected suite.

The returned result includes `status`, `completed`, `executed`, `testCount`,
`exitCode`, `command`, workspace digests, dependency/observer/observation
digests, and bounded stream previews. A zero exit with no valid observer report
is `unknown`, not a passing test. The private controller retains the full
capture; the model receives the public typed result. A selected-suite pass
does not establish hidden acceptance or independently validate a local review.

`SandboxRunner` takes exactly `kind`, `executable`, `python`, `dependencies`, and
`runtime_roots`. `kind` is `bwrap` on Linux or `sandbox-exec` on macOS. Paths must
be explicit; broad runtime roots such as `/`, `/Users`, `/home`, `/tmp`, `/etc`
and `/workspace`, the current home, and the whole `.config` directory are
rejected. An explicit interpreter installation below a `.config` dependency
directory can be granted as its exact read-only subtree; no ancestor or sibling
configuration is granted by that rule. A configured runner is not yet verified. Its
`probe(new_output)` executes only the module's own small canary and checks an
allowed read/write, denied private reads/writes, and a denied connection to a
known-live controller loopback listener. It binds the configuration, sandbox
binary, interpreter, dependencies, and current platform. A saved receipt or a
boolean cannot activate another runner instance; changes invalidate the live
proof, which also expires after one hour.

Linux construction uses separate namespaces, no shared network, no capabilities,
read-only interpreter/dependency mounts, and isolated writable workspace/output
mounts. It does not mount the host filesystem root. The macOS profile denies by
default, denies network and process forking, allows only explicit system/runtime
reads and workspace/output writes, and reads the literal root directory only
for platform startup. That literal rule does not grant reads below `/`.
Neither path falls back to an unsandboxed interpreter. Missing or failed OS
verification stops test execution. Task execution additionally requires the
original Python 3.10.16 and pinned dependency profile.

### Actual macOS engineering canary, 2026-11-28

Two actual own-code canaries were run on the authorized Mac with Python 3.14.3.
Both receipts are retained under `artifacts/checks/public-workspace/`:

| Receipt | Observed result | Scope |
| --- | --- | --- |
| `macos-canary-01.json` | Sandbox process SIGABRT, return code -6, no stdout/stderr, runner unverified. | Failed engineering probe; retained unchanged probe observation. |
| `macos-canary-02.json` | Return code 0; all five isolation checks true; private sentinel unchanged; runner verified in that process. | Successful own-code probe after the literal root-directory read rule. |

The successful probe ran at 10:44:35 UTC. Its exported record contains source
hashes, interpreter/sandbox hashes, dependency/configuration binding, process
times, and stream hashes. It is evidence about the observed canary policy, not
a reusable permission token. The subsequent controller deadline API does not
change that policy; every real task runner must still probe its current
configuration in its own process.

No provider request, model request, third-party task test, native attempt, or
method unit was used. At this initial probe stage, `python3.10` and `pyenv` were
not found on the inspected PATH; `uv` was present. The 3.14.3 canary cannot
satisfy the 3.10.16 task-runtime requirement. No four-arm result, new accepted
workflow, or paper outcome is claimed.

### Isolated pinned Python preparation

Later the same day, explicit environment-preparation authorization was used to
install Python **3.10.16** and two independent virtual environments below the
private P1 dependency directory. No global executable, PATH, user config,
credential, ledger or original taskpack was modified. The public receipts use
`<SETUP_ROOT>` and `<HOME>` placeholders; deployment paths remain private.

The installer was the already available `uv 0.11.6`. Its actual CLI help was
checked before use. Python installation used `--install-dir`, `--no-bin`,
`--no-config` and a local cache. Package installation used the unchanged
requirements files, `--only-binary :all:`, `--no-deps`, `--link-mode copy`, an
explicit public PyPI index, disabled keyring authentication, and isolated
configuration/cache directories. Source distributions and native builds were
not permitted; pins were not lowered or replaced.

| Preserved setup receipt | Result |
| --- | --- |
| `macos-python-setup-01.json` | Python download/install succeeded. The orchestration then stopped because `uv` exposed both a precise version and its minor-version alias, which the initial uniqueness check treated as two candidates. |
| `macos-python-setup-02.json` | The exact installed interpreter reported `[3, 10, 16]`; both virtual environments were created. Package commands were rejected before installation because this `uv` version treats `--no-build` and `--only-binary` as mutually exclusive. |
| `macos-python-setup-03.json` | With the redundant flag removed and `--only-binary :all:` retained, both fixed dependency installations completed, all pins matched, and both actual OS canaries passed. |

The first two receipts and their logs were retained rather than rewritten as
successful preparation. The final receipt binds both earlier receipts by hash
and records the flag correction explicitly. Python was not downloaded again,
and no native or method attempt was retried.

The final preparation completed at **10:56:16 UTC on 2026-11-28**:

| Task | Matched pinned distributions | Requirements SHA-256 | Dependency snapshot SHA-256 |
| --- | ---: | --- | --- |
| w-101 | 17 | `5817943cece5ddfb25e91eb00ca3c608502f9c029b970fd570a92b7aef96801a` | `2c1851f900d622538952ea3df56262886df007182b865d553484d6d74a819d16` |
| w-102 | 15 | `652d5312533e0ef8ab830f85811c20391d520b55624ae516de28d325d4578313` | `0e60a828ccb8ff8f659ee3c17f176c8ae859e7e20c5279336070e3d6d244eae7` |

The actual interpreter hash is
`f96bcd63e75ec9780fc29047a9be24911abaf5b3ce260650b1a030cde50252cc`.
Each canary used its own task dependency mount and the exact 3.10.16 runtime
root. Both observed allowed public reads/writes, denied private reads/writes,
denied loopback connection, and an unchanged private sentinel. The module
source hashes used by these successful canaries are included in the final
receipt and match the prepared broker implementation.

This completes runtime preparation only. Flask/Requests task source and their
selected tests have not been executed during setup. No model/provider request,
experiment quality score, native checkpoint or method result was produced.
The actual backend must still validate the runtime and run a fresh canary in
its own live `SandboxRunner` instance before executing edited source.

The broker's focused offline suite is:

```bash
python -B -m unittest discover -s test -p test_paper1_public_workspace.py -v
```

It covers copy and disclosure boundaries, exact admission receipts, bounded
reads, hash-bound edits, deadline contraction, local review references,
unverified-execution refusal, namespace/policy construction, live-proof
invalidation, missing canary witnesses, and the distinction between process
exit and an observed test outcome. Its fake process transport exists only in
temporary tests and is not exported as platform or scientific evidence.
