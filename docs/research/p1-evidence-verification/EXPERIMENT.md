# P1 execution, measurement and evaluator join

`scripts/paper1/experiment.py` connects a frozen paired schedule to first-attempt
execution records, raw usage, evaluator quality and the existing `analyze.py`.
It uses the Python standard library on Linux/macOS. It does not implement an
agent, verifier, model client, evaluator or filesystem sandbox.

**Status:** the controller contracts are tested with synthetic temporary fixtures
and mocked runner boundaries. Those fixtures are not research observations.
This implementation does not establish that a live A/C/D demonstration, a
credentialed Raw-RAG run, an independent pilot or a confirmatory study has run.
Use the actual execution receipts to determine which of those stages occurred.

## Decisions relative to the existing protocol

The [analysis manifest schema](schemas/study-manifest.schema.json) and
[run schema](schemas/run.schema.json) forbid additional properties. Therefore the
controller writes separate `schedule.json` and `measurement.json` files instead
of placing runner paths, resource limits or raw meter definitions in the analysis
manifest. `freeze.json` binds the four files by canonical SHA256. The numerical
`cost_model.rates` in the manifest retain the prices; their units and denominators
are recorded in `measurement.json`. An entirely unpriced development plan omits
the optional manifest cost model and keeps the unknown prices in the sidecar.

The [protocol](PROTOCOL.md) specifies first attempts. A durable `run_started`
reservation is written **before launching** the executable. An interrupted
reservation is never made pending again: recovery appends `capture_incomplete`.
This conservative choice can count a pre-launch crash as an unobserved attempt;
it prevents choosing a later successful retry. Diagnostic retries need a
different study/analysis and must retain the original costs and failures.

The protocol's analyzer still audits submitted totals rather than reconstructing
usage. This controller provides the missing reconstruction step and emits a
separate audit. Its presence does not prove that the source telemetry is truthful,
all deployments have been inventoried, rates are externally registered, task
families are independent or labels were independently adjudicated.

## Execution and scoring commands

```bash
# 1. Local freeze only: no model, host or runner invocation.
python -B scripts/paper1/experiment.py freeze \
  --spec /absolute/controller/study-spec.json \
  --output /absolute/controller/new-plan

# 2. Default dry run: reads the plan/state; creates no execution state.
python -B scripts/paper1/experiment.py dispatch \
  --plan /absolute/controller/new-plan \
  --state /absolute/controller/first-attempt-state

# Explicit execution, only after the frozen task, host and resource gates are met.
python -B scripts/paper1/experiment.py dispatch \
  --plan /absolute/controller/new-plan \
  --state /absolute/controller/first-attempt-state --run

# 3. Export exact sealed-run bindings for the evaluator; no model invocation.
python -B scripts/paper1/experiment.py score-inputs \
  --plan /absolute/controller/new-plan \
  --state /absolute/controller/first-attempt-state \
  --output /absolute/evaluator/new-score-inputs.json

# 4. Evaluator-only phase, after scoring those specific sealed outputs.
python -B scripts/paper1/experiment.py join \
  --plan /absolute/controller/new-plan \
  --state /absolute/controller/first-attempt-state \
  --quality /absolute/evaluator/quality.jsonl \
  --output /absolute/controller/new-scored-export

# 5. Existing analysis entry point; no model calls.
python -B scripts/paper1/analyze.py \
  --manifest /absolute/controller/new-plan/manifest.json \
  --runs /absolute/controller/new-scored-export/runs.jsonl \
  > /absolute/controller/analysis.json
```

The commands above are interface examples, not a record of executed model work.
`freeze` and `join` require new output directories; `score-inputs` requires a new
output file outside the sealed run directories. `dispatch` is resumable and
uses a nonblocking single-controller lock. Exit 2 means a contract/input problem.
Exit 0 reports what happened; it does not imply task success or H1/H2 support.

## Authoring and freezing a study

The spec has exactly these top-level fields; `analysis_plan` is optional for a
nonconfirmatory study and must follow the existing analysis schema when present:

```json
{
  "schema_version": 1,
  "study_phase": "development",
  "tasks": [
    {
      "task_id": "registered-task-identifier",
      "project_id": "registered-cluster-identifier",
      "public_by_replicate": {
        "1": "/absolute/path/to/agent-public-bundle"
      }
    }
  ],
  "arms": ["A", "C", "D"],
  "replicates": 1,
  "seed": 20261128,
  "runner": "/absolute/path/to/explicit-executable-runner",
  "env_allowlist": ["PATH"],
  "budgets": {
    "max_runs": 3,
    "max_wall_seconds": 600,
    "per_run_seconds": 180
  },
  "measurement": "REPLACE WITH THE MEASUREMENT OBJECT BELOW"
}
```

The placeholder string is deliberately not runnable. Populate it with the
measurement object described below and use real, independently registered task
identities and public paths. `public_by_replicate` must contain every planned
replicate. Every arm in a task×replicate block receives the identical public path
and content digest. Blocks are shuffled with the frozen seed, then arm order is
shuffled within each block. The exact realized order is saved; repetitions do
not increase independent N.

Public inputs may be a file or directory. The freezer hashes every relative
entry name, entry type, permission mode and file content. The root directory and
empty directories are included, so chmod and empty-directory changes are
detected. It rejects symbolic links and `.env` files, and bounds bundles to
20,000 entries/256 MiB. It never opens an evaluator/gold path. Task fields such as
`gold_path` are rejected instead of being filtered from an already loaded case.
The public bundle must already have been built by an audited public-only export.
These checks cannot recognize secret information hidden inside otherwise ordinary
public text. The bundle must remain immutable; each arm reconstructs a separate
workspace. Both the bundle and runner file are checked again before dispatch.

All four run-key fields are copied unchanged to `manifest.json`:
`(task_id, project_id, arm, replicate)`. Duplicate task identities are rejected.
The run ID additionally binds the spec, public snapshot and runner digest; it is
not derived from the four labels alone. The full planned denominator is retained even if the execution budget permits
fewer runs, an arm fails, a provider is unavailable or no score is available.
The freeze operation is a local content freeze, not proof of pre-registration.

## Runner contract and public/evaluator isolation

The frozen runner is one explicitly supplied absolute executable file. Use an
executable wrapper if an interpreter or remote transport is needed. The exact
subprocess arguments are:

```text
RUNNER --public PUBLIC_PATH --arm ARM --replicate N --run-id ID
       --output OUTPUT_DIRECTORY --timeout-seconds SECONDS
```

The controller does not pass the spec, analysis manifest, rate card, evaluator
file, gold directory or hidden checks. It runs without a shell, with stdin closed,
in the per-run output directory. Only the frozen `env_allowlist` is inherited;
names containing `GOLD`, `EVALUATOR` or `PRIVATE` are rejected. No environment
values are written to the plan or normal CLI output. Explicitly include whatever
normal PATH/proxy/certificate/credential variables the approved runner needs;
the scheduler neither discovers credentials nor changes proxies.

For a remote native host, send only the public bundle and the public execution
instructions to that host. Keep gold and evaluator code on the controller-side
evaluation machine. The explicit runner must provide this separation using
permissions, mounts or a separate machine. Passing only public arguments does
not create OS isolation in a shared filesystem.

The output directory already exists. The runner writes:

| File | Contract |
| --- | --- |
| `result.json` | Required `status`; optional `schema_version`, `host_version`, `model_version`, `trace_ref`, `failure_reason`. |
| `usage.jsonl` | Raw delta measurements and component-end records described below; an absent/invalid file leaves cost incomplete. |
| Other local receipts | Immutable traces/provider usage/simulator outputs inside this output tree; no evaluator answer inserted into method input. |

`result.json` must not contain `decision_success`. The evaluator supplies that
field later. Recognized runner terminal statuses are `completed`, `failed`,
`host_error`, `host_failed`, `host_failure`, `host_timeout`, `provider_error`,
`model_invalid_output`, `budget_exhausted`, `capture_incomplete`, `prelude_failed`.
An unrecognized/missing result is a capture failure, not an invented model error.
A nonzero process exit remains `host_failed` even if a file claims completion.
All material used to score the run must be captured inside this output tree;
an opaque/external `trace_ref` alone does not preserve an external trace's bytes.

## Bounds, recovery and the append-only journals

`max_runs` applies across resumes, including failed or interrupted reserved
attempts. `max_wall_seconds` establishes a fixed deadline at the first execution;
recovery downtime consumes that wall-clock allowance. Each launched subprocess
gets the smaller of the remaining study time and `per_run_seconds`. The deadline
is rechecked after input verification. The wrapper process and its process group
are terminated on exit/timeout/interruption so ordinary descendants do not
continue after a finished controller invocation. External services and remote
workers require the runner's own timeout/cancellation enforcement.

The state contains:

| Artifact | Purpose |
| --- | --- |
| `run-ledger.jsonl` | Study binding/deadline, first-attempt reservations, terminal records, budget stops. |
| `usage-ledger.jsonl` | Each original usage line, parsed value/error, source-file digest, line number and bound run identity. |
| `runs/RUN_ID/` | Original runner output, stdout/stderr and raw receipts; no later attempt replaces it. |

Journals use `O_APPEND`, a SHA256 chain and `fsync` for each record. A changed
record, incomplete trailing line or inconsistent run identity stops processing;
the controller never truncates a bad tail or silently selects a later record.
Keep damaged originals and audit them separately. A hash chain is an integrity
check, not external attestation against an operator replacing the entire study.

After an interrupted reservation, recovery appends `capture_incomplete`, preserves
available raw usage, marks coverage incomplete, and skips that unit permanently.
Timeouts also cannot certify full cost from an earlier component seal: an in-flight
provider operation may still have unobserved usage. Unattempted units remain in
the denominator as `not_dispatched`. A hardware/controller crash requires an
external process supervisor for orphan cleanup; the journal alone is not such a
supervisor and never retries an uncertain attempt.

Each reserved attempt gets a fresh `execution_id`, even when the same frozen
plan is intentionally executed in another state directory. The terminal record
is sealed with `freeze_sha256`, that execution identity, the full reservation and
terminal metadata, and `output_sha256` for the complete output tree (including
permissions and empty directories). `score-inputs` and `join` recompute the seal
and current output digest. They reject changed output or a score belonging to a
different public freeze or execution. Exported scoring files must not be written
inside a sealed run directory, because that would change the scored evidence.

## Frozen rate and coverage declarations

`measurement.json` requires these fields:

```text
schema_version: 1
frozen: true
currency: three-letter currency code
rate_card_id: immutable identity for this dated rate declaration
cost_scope: full_pipeline_per_scheduled_task
allocation_rule: component_factors_per_scheduled_task_v1
rates: map of rate ID → {price, per, unit, source, as_of}
components: map of component → token or quantity meter declaration
required_components: map of arm → complete required component list
mandatory_measured_components: map of arm → components that must have observed activity on completion
not_applicable: map of arm → predeclared inapplicable component list
allocation_factors: map of every declared component → number in (0, 1]
```

`price` is the amount of `currency` per `per` units; `per` must be positive.
`price:null` explicitly means unpriced. An unexplained zero price is invalid.
A documented contractual zero reference rate may use `price:0` only with a
separately frozen `zero_price_evidence:{ref,sha256}` identifying the supporting
document. This still requires actual measured work and all coverage checks; the
controller does not certify the document's truth. Actual credits/free trials
must not silently replace the study's standardized reference rates.
`source` identifies the actual rate source
and `as_of` is an ISO date. The same currency applies to the entire card. Rate
units must exactly match meter units; the controller does not guess conversions.
Prices are supplied by the study author, not fetched or fabricated by this tool.

Every arm must explicitly inventory at least these components:

```text
setup, prelude, compaction, extraction, query_generation, embedding, rerank,
source_open, parsing, freshness, certificate_validation, cache_read, cache_write,
evidence_delivery, model, cpu, gpu, storage
```

Additional components are allowed and can be required per arm. `model` must use
the token meter so cached input cannot disappear from accounting. A token meter
may also be used for compaction, extraction or query generation. A quantity meter
can use `token`, `pair`, `cpu_second`, `gpu_second`, `byte_second`, `operation`, or
another explicitly defined unit. Choose a physically justified unit for every
component; naming a meter does not itself measure the work.

The frozen mandatory component declaration cannot be weakened below these
method-specific minimums or overlap `not_applicable`:

| Arm | Minimum mandatory measured components on `completed` |
| --- | --- |
| A | `model` |
| B | `model`, `embedding`, `rerank` |
| C, D | `model`, `extraction` |
| T and other registered continuation arms | `model` |

For example, an A/C/D plan declares
`{"A":["model"],"C":["model","extraction"],"D":["model","extraction"]}`.
The list may be enlarged. A completed run requires a measured seal and positive
observed usage for each listed stage. All-zero tokens, an empty inventory or
declaring every required component N/A cannot make a completed D cost zero.
Unknown tokens remain unknown even if a declared rate is zero.

Example declarations (not real provider prices):

```json
{
  "rates": {
    "reader_uncached": {"price": null, "per": 1000000, "unit": "token", "source": "pending-rate-source", "as_of": "2026-11-28"},
    "reader_cached": {"price": null, "per": 1000000, "unit": "token", "source": "pending-rate-source", "as_of": "2026-11-28"},
    "reader_output": {"price": null, "per": 1000000, "unit": "token", "source": "pending-rate-source", "as_of": "2026-11-28"},
    "cpu": {"price": null, "per": 1, "unit": "cpu_second", "source": "pending-rate-source", "as_of": "2026-11-28"}
  },
  "components": {
    "model": {"kind": "tokens", "rates": {"input_uncached": "reader_uncached", "input_cached": "reader_cached", "output": "reader_output"}},
    "cpu": {"kind": "quantity", "unit": "cpu_second", "rate": "cpu"}
  }
}
```

This fragment needs the remaining required component declarations and other
fields before freezing. Keep unknown rates unknown. The frozen allocation factor
is applied once to each component charge. A factor of 1 counts the work once per
scheduled arm/task; a justified setup amortization uses a predeclared fractional
factor. Shared prelude/extraction replicated into deployment estimates must use
the protocol's once-per-arm/task rule. Do not count an identical physical charge
again under another component. Shared source receipts may support separate arm
deployment estimates; they are not separate actual payments.

## Raw usage and completion records

A token measurement explicitly means **one non-overlapping increment**, with
total input including its cached subset:

```json
{"event":"usage","usage_id":"turn-17-tokens","measurement_id":"provider/request-17/tokens","operation_id":"provider/request-17","component":"model","counter_kind":"delta","values":{"input_tokens":100,"cached_input_tokens":40,"output_tokens":10},"source_ref":"receipts/turn-17.json"}
```

Those numbers are illustrative. Optional provenance fields are `provider`,
`model`, `request_id`, `source_sha256`. A quantity measurement has the same
identity/provenance fields but `values:{"quantity":NUMBER_OR_NULL}`. The meter's
unit comes from the frozen component declaration. Every value must represent
observed raw usage; unknown values are `null`, never inferred zero.

Only a clearly defined single-turn terminal delta may be converted to that form.
Native notifications can contain both cumulative `total` and `last` counters;
neither summing all notifications nor assuming every `last` is new is permitted.
Keep ambiguous notifications unchanged in a raw receipt, reference it, and mark
the component unmeasured. `counter_kind:"cumulative"` is retained in the raw
journal but cannot produce a complete standardized cost. Counter differencing
across thread/fork/reset boundaries is not implemented here.

After **all** measurements for a component, append exactly one end record:

```json
{"event":"component_end","component":"model","coverage":"measured","usage_ids":["turn-17-tokens"],"reason":null,"evidence_ref":"receipts/turn-17.json"}
```

Its usage-ID inventory must match exactly, without duplicates. No measurement
may follow that component's end record. `coverage:"measured"` needs at least one
measurement, including an explicitly observed zero when justified. A predeclared
`not_applicable` component may have an empty inventory, but must have a reason
and an evidence reference. Other cases use `unmeasured` or `incomplete`, a reason
and the available inventory. Missing component end records always leave cost
incomplete. A provider-log line count is not an HTTP request count or a bill.

The terminal status matters. A failure before model work is not assigned invented
positive tokens. An explicitly observed zero delta is valid for such a failed
attempt. A never-performed stage may also seal with `coverage:"not_performed"`,
an empty inventory, a reason and evidence, but only for a noncompleted execution.
That is distinct from a method-level N/A declaration. Captured work in other
stages still costs what was measured; incomplete capture/timeouts remain unknown.

## Cost reconstruction and independent quality parsing

For a token measurement, let total input be `I`, cached input `K` and output `O`:

`charge = (I − K) × uncached_rate + K × cached_rate + O × output_rate`.

Each rate is normalized by its frozen `per` denominator; the component allocation
factor is then applied once. `0 ≤ K ≤ I` is required. The total-input charge is
never added on top of its cached subset. Quantity meters use
`quantity × price / per × allocation_factor`. Decimal arithmetic precedes the
finite JSON-number conversion.

Duplicate usage IDs, duplicate measurement IDs, or repeated `(operation_id,
unit)` charges are invalid even if their component labels differ. Distinct
requests need distinct operation identities. Missing/null counters, a cumulative
counter, an unknown rate, a unit mismatch, an unmeasured required component,
duplicate pricing, incomplete capture, mismatched terminal usage hash/count or
numeric overflow makes **the complete `standardized_cost` null**. The audit can
retain a partial observed sum, clearly labelled as partial; that value is never
sent to `analyze.py` as full cost. Full real-world scope still requires human
coverage and allocation review.

After sealing execution, `score-inputs` exports the specific run bindings,
terminal statuses and output locations. The independent evaluator inspects those
captured outputs and writes one JSONL row per scored planned key, copying all
three mandatory binding fields from that export:

```json
{"task_id":"registered-task-identifier","project_id":"registered-cluster-identifier","arm":"D","replicate":1,"run_id":"ACTUAL_RUN_ID","freeze_sha256":"ACTUAL_FREEZE_SHA256","sealed_run_sha256":"ACTUAL_SEALED_RUN_SHA256","decision_success":true,"quality_review_ref":"adjudication/task-review.json"}
```

`run_id`, `freeze_sha256` and `sealed_run_sha256` are all mandatory and must match
the current sealed execution. Matching task labels or terminal statuses alone
is insufficient. No score can be joined to an unsealed or unattempted unit.
`attempt`, if supplied, must be integer 1 and `retry_of` must be null. Duplicate or unplanned evaluator keys are
rejected; the join does not select the most favorable score. Unassignable JSON
requires correction/audit before export, with the original evaluator file retained.

The join emits exactly one run-schema-compatible row for every planned unit.
Valid completed quality remains valid when cost is damaged or unknown. Missing
or unreadable quality becomes `evaluator_error` while a separately measured cost
can remain available. A real method/host failure retains its failure status and
ITT zero even if an evaluator row claims success. A runner-provided success field
is not accepted as an evaluator score.

`runs.jsonl` contains quality and complete standardized totals. `join-audit.json`
records independent quality issues, meter/coverage issues, line-item charges,
partial sums and source-ledger hashes. Actual payment reconciliation is not
performed: `actual_spend` and its currency remain null. In particular, shared
deployment estimates must not be summed and relabelled as actual research spend.

## Verification performed for this implementation

```bash
python -B -m unittest discover -s test -p 'test_paper1_experiment.py' -v
```

The initial 15 contract tests failed before implementation and then passed.
Review added seven meaningful regressions that failed against the initial
implementation: early component seals, invalid frozen analysis settings,
between-arm runner drift, timeout cost completeness, total-cost overflow,
usage/terminal hash mismatch, and budget exhaustion during input validation.
Those 22 passed after those defects were fixed. A further independent review
added score/trace binding, method-specific mandatory activity and permission/
empty-directory digest regressions. Nine new cases reproduced the unsafe
behavior before its fix; a separate legitimate-zero-rate case failed before
explicit zero-price evidence was supported. The final **37 tests passed**.
They also verify the score-input export, keep failed pre-model work at its
observed zero instead of inventing usage, and require extraction activity for a
completed selective arm. The tests include direct ingestion
of the exported records by the existing `analyze.analyze` function: broken cost
does not flip valid task quality, and a missing score does not erase measured cost.

The saved review red/green test logs are controller development evidence. Mocked
runner calls and illustrative accounting figures must not be published as live
native-host, Raw-RAG, pilot or confirmatory outcomes.
