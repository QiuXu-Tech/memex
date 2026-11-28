# Selected development execution

`scripts/paper1/development_driver.py` prepares one real native parent and runs
the fixed A, C, D first attempts with one backend and one evidence-helper
lifetime. B remains a planned unit with
`not_dispatched_dependency_blocked`; this entry never calls `run_unit` for B.
The existing `native_driver.py` CLI still requires all four arms and B's fixed
dependencies. The frozen study and launcher interfaces are unchanged.

## Entry and eligibility

The Python interface is:

```python
run_selected(
    run=False,
    settings_path=None,
    scope_specs_path=None,
    state_root=None,
    output=None,
    task_id='w-101',
    replicate=1,
    profile_path=reader.PROFILE,
)
```

The CLI accepts `--settings`, `--scope-specs`, `--profile`, `--state-root`,
`--output`, `--task`, `--replicate`, and explicit `--run`. It has no arbitrary
arm-selection or retry option. Without `--run`, it performs the same local
read-only checks as the native driver and creates no output, backend, scope
reservation, or attempt. A check can complete with dispatch blockers; callers
must inspect `dispatch_ready` and `blockers`.

The internal `_inspect(development_selection=('A', 'C', 'D'))` seam excludes
only B's embedding/reranker environment requirements and Raw-RAG runtime/source
checks. All shared requirements remain: the canonical authorization and ledger,
native grant, source-plan/public identities, reader profile, tokenizer, task
Python pins, sandbox configuration, credential-file metadata, fresh private
state/output paths, selected scope/provider price evidence and whole-selection
cash capacity. The scope validator still validates every supplied scope spec;
malformed or unknown errors are not filtered out. No credential contents are
read during inspection. Actual authentication, host behavior, sandbox probes,
provider usage, and request admission remain runtime checks.

## Execution and retained state

An explicit eligible run constructs one canonical controller and one backend,
calls `prepare_block` once, and then calls `run_unit` for A, C, D in that order.
It uses the existing `p1-method-` plus task/replicate/arm digest run IDs. The
checkpoint remains at `output/block/checkpoint.json` with its original
`unit-state` registry; the driver neither imports nor recreates that registry.
Each actual unit inherits the existing parent revalidation, actual native
fork, independent workspace, per-operation admission, provider admission and
failure/usage retention behavior. The backend is closed in `finally`.

The persistent helper supplies the same archive epoch and immutable prime
cache for C and D. Each unit clones that prime cache, so receipts acquired by
C do not become D's prime. A failed preparation dispatches no method units. A
unit failure returned by the runtime is retained once; the driver does not
retry it. An unexpected exception aborts the remaining selected calls and
preserves uncertainty about the active unit's attempt and usage state.

`development-selection-result.json` records the wrapper result after cleanup.
`selected_execution_complete` means that preparation and A/C/D returned
`completed`. `execution_complete` remains false because B was not dispatched.
The report retains all four block units and all sixteen planned development
units, with `score_status='not_scored'`, `quality_scored=false`, and
`scientific_ready=false`. It does not supply quality measurements, provider
usage, or actual cash from wrapper success. Use the retained runtime and
provider artifacts for those measurements.

## Deferred B and acceptance boundaries

B must not be invoked merely to probe unavailable dependencies: `run_unit`
records an arm's first attempt before scope admission. Its metadata-only
deferral leaves that first-attempt slot untouched and does not reserve a B
scope. This entry does not substitute the fixed embedding, reranker, upstream
commit, pricing evidence, or source checkout requirements.

After the original backend closes, a fresh backend can run B directly from
the original checkpoint through the existing `run_unit` interface if B's
prerequisites are ready, the actual persisted native parent still exists
unchanged, and the sealed reader configuration matches. B does not require
the C/D helper. Reconstructing a helper cannot honestly restore C/D's previous
archive epoch. No B-resumption CLI or automatic replay is added here.

The serial DeepSeek cash envelope additionally requires pricing/profile
freshness on the execution UTC date. The complete reader profile hash is
sealed into the checkpoint; silently refreshing that profile on another day
would change the binding. Deferred cross-day B therefore remains a separate
compatibility and budget decision, not a promised continuation.

Development execution does not require fabricated human review or formal
acceptance. The task packages retain their existing prepared/unaccepted,
unfrozen state. This component entry does not change those gates or claim
formal study readiness.

## Offline verification

The new driver has fourteen boundary tests, covering selected-only dependency
gates, retained common errors, one backend/controller lifetime, unchanged run
IDs and checkpoint registry, B non-dispatch, all planned denominators,
preparation and unit failures, input drift, explicit run selection, and cleanup.
The existing native driver has eighteen regression tests. All thirty-two
passed; an independent read-only review repeated both suites successfully.
These tests use temporary fixture ledgers and mocked execution boundaries,
not a provider, device execution, or research outcome.
