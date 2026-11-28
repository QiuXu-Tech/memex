# Two public Python source captures

These are two **controller-only development captures of the clean public source bases**, executed once each on 2026-11-28. They do not complete the natural-language repair tasks, construct a native prelude/compaction checkpoint, run the 16 paired method units, or increase the number of accepted P1 workflows.

| Source | Fixed public test module | Collected | Passed | Skipped | Failed / errors | Process exit |
|---|---|---:|---:|---:|---:|---:|
| w-101 / Flask | `tests/test_blueprints.py` | 59 | 59 | 0 | 0 / 0 | 0 |
| w-102 / Requests | `tests/test_utils.py` | 212 | 201 | 11 | 0 / 0 | 0 |

The original public trees contain no official fix or official test patch. Accordingly, these 59/212 collected counts differ from the previous evaluator-only patched-source qualification counts. Passing these public tests does not establish that the requested blueprint/proxy behavior has been fixed.

## What was actually observed

Both captures use existing CPython 3.10.16 and exact previously pinned dependencies. Flask uses pytest 7.2.2. Requests uses pytest 6.2.5 with explicit pytest_mock 2.0.0. No installer, model, provider, API, upstream service, or external connection was used. The controller did not reserve or consume a paired method unit.

The child interpreter starts with `-I -S -B`; it does not execute `.pth` or `.egg-link` files. This matters because the existing environments contain editable references to evaluator reproduction repositories. Only explicitly selected dependency directories and the fresh clean public source copy are placed on the import path. Actual project-module origins and source hashes are recorded; Requests' known dependency aliases are separately bound to the pinned dependency objects/files. The old evaluator source repository is never imported or supplied to the test subprocess.

Each run records actual stdout/stderr bytes, return code, signal/timeout/output-limit state, collected nodeids, setup/call/teardown outcomes, pytest's own exit status, module bindings, and before/after source/dependency identities. Both the original public copy and the executed copy retained their original content/mode hashes; dependency hashes also remained unchanged. The tests completed with no collection error or blocked network operation.

`os_isolation=false` is explicit. This is reviewed controller-side source execution with a cleared inherited environment, fixed test selection, disabled plugin autoload, separate temporary directories, and a Python network audit hook; it is not an OS security boundary. Requests' urllib3 import made one local loopback port-zero bind capability probe. It did not listen, connect, send, or contact an external host. This execution mode accepts only the exact two clean public source hashes, not arbitrary model-edited code.

## Evidence files

`summary.json` indexes the two current `capture.json` files. Each task's `attempt-001/` directory contains:

- `capture.json`: current public receipt, including process outcome, source/runtime bindings and raw/published stream hashes.
- `stdout.txt` and `stderr.txt`: transparently redacted public stream copies. Original-byte hashes are retained separately.
- `pytest-observation.json`: structured actual pytest observations; no keyword-based pass inference.
- `pytest.junit.xml`: valid public JUnit XML.
- `workspace-before.json` and `workspace-after.json`: complete source path/mode/content manifests.
- `capture.export-v1.json`, `pytest.junit.export-v1.txt`, and `export-repair.json`: preserved export revision history.

The initial generic path substitution produced invalid XML for a Requests parameterized test name containing a runtime path. The exporter was corrected to parse XML, redact values, and escape them through serialization. Both public XML exports were regenerated from the unchanged private raw JUnit. The original raw SHA values, first exports and repair records are preserved. **This export repair added zero source executions and did not alter any test observation or outcome.**

`provenance/` contains the exact controller and observer bytes used for the two source runs and their hashes. The current repository controller additionally contains the XML export repair. `validation/` contains the passing focused test logs: 19 paired-runner tests and 19 Python-capture tests. Those unit tests execute only owned tiny fixtures, not these upstream test modules.

The original unredacted controller receipts and streams are retained separately as owner-private records; they are not model inputs. The public files replace known controller/runtime paths and the hostname, with both raw and published hashes available to distinguish the transformation.

## Remaining research gates

`model_requests=0`, `provider_requests=0`, `native_compactions=0`, `method_attempts_reserved=0`, `accepted_p1_task_count=0`, `scientific_ready=false`, `method_runtime_ready=false`, `archive_created=false`, and `native_event_claimed=false` remain deliberate scope labels. The next engineering connection is actual task diagnosis/edit/state-change capture followed by a real shared native checkpoint and arm-specific continuation. These fixed-test observations supply a working Python execution component, not fabricated archive or method results.
