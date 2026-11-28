"""Typed trace oracle fixtures; none are observations of an actual method."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/paper1"))
import development_oracle as oracle
import experiment


def call(identifier, tool, result, before="a" * 64, after=None, *, ok=True):
    after = before if after is None else after
    kinds = ["public_tool_call"]
    intent = {"schema_version": 1, "operation_id": identifier, "tool": tool,
              "arguments_sha256": "b" * 64, "workspace_sha256": before, "kinds": kinds,
              "observable_kind": "test_execution" if tool == "run_current_tests" else tool}
    receipt = {"schema_version": 1, "kind": "public_workspace_operation", "event_id": identifier,
               "tool": tool, "ok": ok, "workspace_before_sha256": before,
               "workspace_after_sha256": after, "result_sha256": experiment.digest(result), "authorizesExecution": False}
    return [{"event": "tool_started", "intent": intent},
            {"event": "tool_admitted", "operation_id": identifier,
             "admission": {"operation_id": identifier, "admitted_kinds": kinds}},
            {"event": "tool_finished", "receipt": receipt, "result": result, "counters": {}}]


def passed_result(version="a" * 64):
    return {"status": "passed", "completed": True, "executed": True, "testCount": 2,
            "workspace_before_sha256": version, "workspace_after_sha256": version,
            "executed_snapshot_after_sha256": version, "observation_sha256": "d" * 64}


class DevelopmentOracleTests(unittest.TestCase):
    def result(self, rows, *, final="a" * 64, test_states=None):
        return oracle.trace_components(rows, initial_workspace="a" * 64, final_workspace=final,
                                       observed_test_states=test_states or {})

    def test_no_execution_is_unmeasured_and_cannot_be_success(self):
        result = self.result([])
        self.assertIsNone(result["current_public_tests_passed"])
        self.assertIsNone(result["decision_success"])
        self.assertFalse(result["independent_human_review_performed"])

    def test_valid_test_and_local_review_close_only_typed_components(self):
        rows = call("test1", "run_current_tests", passed_result())
        rows += call("review1", "record_review", {"review_id": "review1", "text": "Fixture review.",
            "evidence_event_ids": ["test1"], "workspace_sha256": "a" * 64,
            "published": False, "correctness_judged": False})
        result = self.result(rows, test_states={"test1": True})
        self.assertTrue(result["current_public_tests_passed"])
        self.assertTrue(result["local_review_bound_to_current_tests"])
        self.assertIsNone(result["requested_hidden_behavior_passed"])
        self.assertIsNone(result["decision_success"])

    def test_self_reported_pass_without_rechecked_observer_is_unmeasured(self):
        result = self.result(call("test1", "run_current_tests", passed_result()))
        self.assertIsNone(result["current_public_tests_passed"])
        self.assertIn("test_observer_not_revalidated:test1", result["issues"])

    def test_missing_second_observer_cannot_disappear_from_the_test_denominator(self):
        rows = call("test1", "run_current_tests", passed_result())
        rows += call("test2", "run_current_tests", passed_result())
        rows += call("review1", "record_review", {"review_id": "review1", "text": "Fixture review.",
            "evidence_event_ids": ["test1"], "workspace_sha256": "a" * 64,
            "published": False, "correctness_judged": False})
        result = self.result(rows, test_states={"test1": True})
        self.assertFalse(result["typed_trace_complete"])
        self.assertIsNone(result["current_public_tests_passed"])
        self.assertIsNone(result["local_review_bound_to_current_tests"])
        self.assertEqual(result["recorded_test_receipts"], 2)
        self.assertEqual(result["observed_test_receipts"], 1)
        self.assertEqual(result["unrevalidated_test_receipts"], 1)

    def test_zero_test_count_cannot_pass_despite_claimed_observer_state(self):
        result = passed_result(); result["testCount"] = 0
        checked = self.result(call("test1", "run_current_tests", result), test_states={"test1": True})
        self.assertIsNone(checked["current_public_tests_passed"])

    def test_edit_after_test_invalidates_reuse_for_final_artifact(self):
        rows = call("test1", "run_current_tests", passed_result())
        rows += call("edit1", "write_file", {"executed": False}, after="e" * 64)
        result = self.result(rows, final="e" * 64, test_states={"test1": True})
        self.assertFalse(result["current_public_tests_passed"])
        self.assertTrue(result["workspace_change_observed"])

    def test_forged_receipt_or_missing_admission_is_rejected(self):
        rows = call("test1", "run_current_tests", passed_result())
        for changed in [rows[:1] + rows[2:], copy.deepcopy(rows)]:
            if len(changed) == 3:
                changed[-1]["result"]["testCount"] = 3
            with self.subTest(rows=changed), self.assertRaises(experiment.ContractError):
                self.result(changed, test_states={"test1": True})

    def test_review_cannot_reference_future_or_unrelated_event(self):
        result = {"review_id": "review1", "text": "Fixture review.", "evidence_event_ids": ["future"],
                  "workspace_sha256": "a" * 64, "published": False, "correctness_judged": False}
        with self.assertRaisesRegex(experiment.ContractError, "review_reference_not_observed"):
            self.result(call("review1", "record_review", result))

    def test_unfinished_or_discontinuous_trace_never_closes_components(self):
        rows = call("test1", "run_current_tests", passed_result())[:2]
        result = self.result(rows, test_states={"test1": True})
        self.assertFalse(result["typed_trace_complete"])
        self.assertIsNone(result["current_public_tests_passed"])
        result = self.result(call("read1", "read_file", {"text": "fixture"}), final="f" * 64)
        self.assertFalse(result["typed_trace_complete"])
        self.assertIsNone(result["decision_success"])

    def test_unstarted_frozen_plan_produces_nulls_without_creating_state(self):
        import test_paper1_experiment as fixtures
        owner = fixtures.ExperimentTests(); owner.setUp()
        self.addCleanup(owner.doCleanups)
        plan, state, output = owner.freeze(), owner.root / "state", owner.root / "oracle"
        with mock.patch("subprocess.Popen", side_effect=AssertionError("no process")), \
             mock.patch("socket.socket", side_effect=AssertionError("no network")):
            result = oracle.inspect_sealed_runs(plan, state, output)
        self.assertEqual(result["planned_runs"], 3)
        self.assertEqual(result["sealed_runs"], 0)
        self.assertFalse(state.exists())
        rows = json.loads((output / "trace-oracle.json").read_text())["runs"]
        self.assertTrue(all(r["decision_success"] is None and r["measurement_status"] == "NOT_MEASURED" for r in rows))

    def test_existing_experiment_seal_is_rechecked_not_trusted_from_a_file(self):
        import test_paper1_experiment as fixtures
        owner = fixtures.ExperimentTests(); owner.setUp()
        self.addCleanup(owner.doCleanups)
        plan, state = owner.freeze(), owner.root / "state"
        with mock.patch.object(experiment, "launch_runner", side_effect=owner.fake_launch):
            experiment.dispatch(plan, state, run=True)
        result = oracle.inspect_sealed_runs(plan, state, owner.root / "oracle")
        self.assertEqual(result["sealed_runs"], 3)
        self.assertEqual(result["method_composite_scores"], 0)
        run = next((state / "runs").iterdir())
        (run / "result.json").write_text('{"status":"completed","trace_ref":"changed"}')
        with self.assertRaisesRegex(experiment.ContractError, "sealed_execution_or_output_changed"):
            oracle.inspect_sealed_runs(plan, state, owner.root / "oracle-changed")

    def test_formal_plan_is_rejected_even_with_programmatic_route(self):
        with mock.patch.object(experiment, "load_frozen", return_value={"manifest": {"study_phase": "confirmatory"}}):
            with self.assertRaisesRegex(experiment.ContractError, "cannot_score_formal_study"):
                oracle.inspect_sealed_runs("fixture-plan", "fixture-state", "fixture-output")

    def observer_fixture(self, root):
        identifier = "tool-" + "1" * 32
        folder = root / "tests" / identifier
        workspace = folder / "workspace"
        (workspace / "fixture").mkdir(parents=True)
        (workspace / "fixture/__init__.py").write_text("VALUE=1\n")
        (workspace / "tests").mkdir()
        (workspace / "tests/test_fixture.py").write_text("def test_x(): assert True\n")
        snapshot = oracle.workflow.snapshot(workspace)
        node = "tests/test_fixture.py::test_x"
        origin = {"fixture": {"scope": "workspace", "path": "fixture/__init__.py",
                             "sha256": hashlib.sha256((workspace / "fixture/__init__.py").read_bytes()).hexdigest()}}
        observation = {"schema_version": "p1-python-child-1", "nonce": "fixture-nonce", "error": None,
            "pytest_started": True, "pytest_finished": True, "pth_processing_disabled": True,
            "isolated_python_mode": True, "network_attempts_blocked": 0, "pytest_exit_code": 0,
            "process_exit_requested": 0, "collection_errors": [], "collected": [node],
            "reports": [{"nodeid": node, "when": phase, "outcome": "passed"} for phase in ("setup", "call", "teardown")],
            "project_origins_before": origin, "project_origins_after": origin}
        process = {"spawned": True, "error": None, "timed_out": False, "output_limit_exceeded": False, "returncode": 0}
        config = {"nonce": "fixture-nonce", "tests": ["tests/test_fixture.py"], "module": "fixture"}
        summary = oracle.workflow.summarize(process, observation, snapshot, snapshot,
            nonce=config["nonce"], tests=config["tests"], module="fixture", dependencies=[])
        def write(name, value):
            path = folder / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value))
        for name, value in [("workspace-before.json", snapshot), ("workspace-after.json", snapshot),
            ("executed-after.json", snapshot), ("observer-config.json", config),
            ("execution/sandbox-output/pytest-observation.json", observation), ("execution/process.json", process),
            ("dependency-snapshot.json", {"files": []}), ("summary.json", summary)]:
            write(name, value)
        (folder / "observer.py").write_text("# Fixture bytes only; no interpreter executed.\n")
        result = {**passed_result(experiment.public_digest(workspace)), "testCount": 1,
                  "selected_tests": config["tests"], "nonce": config["nonce"], "test_counts": summary["test_counts"],
                  "summary_status": summary["status"],
                  "observation_sha256": hashlib.sha256((folder / "execution/sandbox-output/pytest-observation.json").read_bytes()).hexdigest(),
                  "observer_sha256": hashlib.sha256((folder / "observer.py").read_bytes()).hexdigest()}
        write("public-result.json", result)
        return identifier, folder, result

    def test_observer_recomputation_uses_actual_stored_cases_and_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identifier, folder, result = self.observer_fixture(root)
            self.assertTrue(oracle.recheck_test_observer(root, identifier, result))
            (folder / "workspace/fixture/__init__.py").write_text("VALUE=2\n")
            self.assertIsNone(oracle.recheck_test_observer(root, identifier, result))

    def test_observer_nonce_change_cannot_be_hidden_by_updating_only_result_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            identifier, folder, result = self.observer_fixture(root)
            path = folder / "execution/sandbox-output/pytest-observation.json"
            data = json.loads(path.read_text()); data["nonce"] = "wrong"; path.write_text(json.dumps(data))
            result["observation_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            (folder / "public-result.json").write_text(json.dumps(result))
            with self.assertRaisesRegex(experiment.ContractError, "recomputed_test_summary_mismatch"):
                oracle.recheck_test_observer(root, identifier, result)


if __name__ == "__main__":
    unittest.main()
