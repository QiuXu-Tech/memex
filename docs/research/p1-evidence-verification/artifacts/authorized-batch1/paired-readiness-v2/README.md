# Paired input readiness, metadata revision 2

This is a read-only refresh of engineering readiness after implementing and exercising the Python fixed-test capture component. It does not restage or copy source inputs and does not execute a model, provider, source test, native compaction, or method unit.

- `runtime-readiness.json` is the current final producer's actual `inspect` result.
- `backend-contract.json` records the current implemented Python component and the remaining native/arm integration operations.
- `revision.json` binds these files to the unchanged original input trees, all four original controller metadata files, all 16 prepared units, producer source hashes and the two existing Python capture receipts.

The original `../paired-inputs/` directory remains byte-for-byte untouched. Its public inputs and 16-unit preparation are valid. Its readiness language is historical: `python_execution_observer_not_implemented` was true when that preparation was made. The final source replaces that capability gap with `task_bound_python_execution_not_captured`, because the generic clean-source captures have not become an actual task diagnosis/edit/native-checkpoint trajectory. `runtime_ready=false`, `scientific_ready=false`, and accepted P1 N=0 remain unchanged.

`provenance/paired_runner-v1.py` contains the exactly recovered historical producer bytes. The known subsequent patch was reversed and the resulting SHA matched the earlier recorded `d2a79410e84ddc0e3d41e4d48ec94f91140996242210e1528fb8f77ba83fb30b`. This is an archived source snapshot; the supported CLI remains `scripts/paper1/paired_runner.py` in the repository. The revision records both producer identities without relabeling the old output as newly generated.

The existing Python fixed-test receipts report Flask 59 passed and Requests 201 passed / 11 skipped out of 212 collected, each once. This refresh links those receipts without changing them. The zero source/model/provider counts inside the new `inspect` output refer to this read-only preflight, not a claim that earlier captures never occurred.
