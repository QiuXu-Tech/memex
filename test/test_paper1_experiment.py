"""Synthetic controller-contract tests; never research/model observations."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/paper1/experiment.py"


def module():
    name = "paper1_experiment_under_test"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, SCRIPT)
        value = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(value)
        sys.modules[name] = value
    return sys.modules[name]


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.public = self.root / "agent-public"
        self.public.mkdir()
        (self.public / "request.txt").write_text("A synthetic controller test only.\n")
        self.runner = self.root / "explicit-runner"
        self.runner.write_text("#!/bin/sh\nexit 99\n")
        self.runner.chmod(0o700)

    def measurement(self):
        m = module()
        rates = {
            "input": {"price": 2, "per": 1000, "unit": "token", "source": "test-fixture", "as_of": "2026-11-28"},
            "cached": {"price": 1, "per": 1000, "unit": "token", "source": "test-fixture", "as_of": "2026-11-28"},
            "output": {"price": 4, "per": 1000, "unit": "token", "source": "test-fixture", "as_of": "2026-11-28"},
            "unit": {"price": 1, "per": 1, "unit": "operation", "source": "test-fixture", "as_of": "2026-11-28"},
        }
        components = {name: {"kind": "quantity", "unit": "operation", "rate": "unit"}
                      for name in m.PIPELINE_COMPONENTS}
        components["model"] = {"kind": "tokens", "rates": {
            "input_uncached": "input", "input_cached": "cached", "output": "output"}}
        return {"schema_version": 1, "frozen": True, "currency": "USD",
                "rate_card_id": "synthetic-unit-test-only", "rates": rates,
                "cost_scope": "full_pipeline_per_scheduled_task",
                "allocation_rule": "component_factors_per_scheduled_task_v1",
                "components": components,
                "required_components": {arm: list(m.PIPELINE_COMPONENTS) for arm in ("A", "C", "D")},
                "mandatory_measured_components": {"A": ["model"], "C": ["model", "extraction"],
                                                  "D": ["model", "extraction"]},
                "not_applicable": {arm: [] for arm in ("A", "C", "D")},
                "allocation_factors": {name: 1 for name in m.PIPELINE_COMPONENTS}}

    def spec(self, **overrides):
        value = {"schema_version": 1, "study_phase": "development",
                 "tasks": [{"task_id": "fixture", "project_id": "fixture-project",
                            "public_by_replicate": {"1": str(self.public)}}],
                 "arms": ["A", "C", "D"], "replicates": 1, "seed": 7,
                 "runner": str(self.runner), "env_allowlist": ["PATH"],
                 "budgets": {"max_runs": 3, "max_wall_seconds": 60, "per_run_seconds": 10},
                 "measurement": self.measurement()}
        value.update(overrides)
        return value

    def freeze(self, spec=None):
        path = self.root / "spec.json"
        path.write_text(json.dumps(spec or self.spec()))
        plan = self.root / "plan"
        module().freeze_study(path, plan)
        return plan

    def usage(self, arm="A"):
        rows = []
        for component in module().PIPELINE_COMPONENTS:
            values = ({"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 10}
                      if component == "model" else {"quantity": 1 if component == "extraction" and arm in {"C", "D"} else 0})
            identifier = "fixture-" + component
            rows.extend([
                {"event": "usage", "usage_id": identifier, "measurement_id": identifier,
                 "operation_id": identifier, "component": component, "counter_kind": "delta",
                 "values": values, "source_ref": "synthetic-fixture-only"},
                {"event": "component_end", "component": component, "coverage": "measured",
                 "usage_ids": [identifier], "reason": None, "evidence_ref": "synthetic-fixture-only"},
            ])
        return rows

    def fake_launch(self, argv, *, cwd, env, timeout, stdout, stderr):
        output = Path(argv[argv.index("--output") + 1])
        (output / "result.json").write_text(json.dumps({"status": "completed", "trace_ref": "fixture"}))
        arm = argv[argv.index("--arm") + 1]
        (output / "usage.jsonl").write_text("".join(json.dumps(row) + "\n" for row in self.usage(arm)))
        return 0

    def quality_rows(self, plan, state, success=True):
        frozen = module().load_frozen(plan)
        terminal = {r["run_id"]: r for r in module().read_ledger(state / "run-ledger.jsonl")
                    if r["event"] == "run_finished"}
        return [{**u["key"], "run_id": u["run_id"],
                 "freeze_sha256": module().digest(frozen["freeze"]),
                 "sealed_run_sha256": terminal[u["run_id"]].get("sealed_run_sha256", "old-unbound-run"),
                 "decision_success": success, "quality_review_ref": "synthetic-test-only"}
                for u in frozen["schedule"]["units"]]

    def test_frozen_manifest_is_paired_and_analyzer_schema_compatible(self):
        plan = self.freeze()
        frozen = module().load_frozen(plan)
        manifest = frozen["manifest"]
        self.assertEqual(set(manifest), {"schema_version", "study_phase", "frozen", "runs", "cost_model"})
        self.assertTrue(manifest["frozen"])
        self.assertEqual({r["arm"] for r in manifest["runs"]}, {"A", "C", "D"})
        self.assertTrue(all(set(r) == {"task_id", "project_id", "arm", "replicate"} for r in manifest["runs"]))
        self.assertEqual(len({u["public_sha256"] for u in frozen["schedule"]["units"]}), 1)
        self.assertEqual(len({u["run_id"] for u in frozen["schedule"]["units"]}), 3)

    def test_gold_paths_cannot_be_added_to_controller_runner_spec(self):
        spec = self.spec()
        spec["tasks"][0]["gold_path"] = "/private/evaluator/gold.json"
        with self.assertRaises(module().ContractError):
            self.freeze(spec)

    def test_default_dry_run_does_not_start_subprocess_or_create_state(self):
        plan = self.freeze()
        state = self.root / "state"
        with mock.patch.object(module(), "launch_runner", side_effect=AssertionError("unexpected dispatch")):
            result = module().dispatch(plan, state)
        self.assertEqual(result["mode"], "dry-run")
        self.assertEqual(result["model_requests"], 0)
        self.assertFalse(state.exists())

    def test_dispatch_only_passes_public_and_output_data_paths(self):
        plan = self.freeze()
        with mock.patch.object(module(), "launch_runner", side_effect=self.fake_launch) as launch:
            module().dispatch(plan, self.root / "state", run=True)
        self.assertEqual(launch.call_count, 3)
        for call in launch.call_args_list:
            argv = call.args[0]
            self.assertEqual(argv[0], str(self.runner))
            self.assertEqual(argv[argv.index("--public") + 1], str(self.public))
            self.assertNotIn(str(plan), argv)
            self.assertFalse(any("gold" in arg or "evaluator" in arg for arg in argv))
            self.assertLessEqual(call.kwargs["timeout"], 10)
            self.assertEqual(set(call.kwargs["env"]) - {"PATH"}, set())

    def test_first_attempt_resume_never_repeats_finished_units(self):
        plan = self.freeze()
        state = self.root / "state"
        with mock.patch.object(module(), "launch_runner", side_effect=self.fake_launch) as launch:
            module().dispatch(plan, state, run=True)
            before = (state / "run-ledger.jsonl").read_bytes()
            module().dispatch(plan, state, run=True)
        self.assertEqual(launch.call_count, 3)
        self.assertTrue((state / "run-ledger.jsonl").read_bytes().startswith(before))

    def test_interrupted_reserved_unit_is_not_dispatched_again(self):
        spec = self.spec(arms=["A"])
        spec["measurement"]["required_components"] = {"A": list(module().PIPELINE_COMPONENTS)}
        spec["measurement"]["not_applicable"] = {"A": []}
        spec["measurement"]["mandatory_measured_components"] = {"A": ["model"]}
        plan = self.freeze(spec)
        state = self.root / "state"
        with mock.patch.object(module(), "launch_runner", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                module().dispatch(plan, state, run=True)
        with mock.patch.object(module(), "launch_runner", side_effect=AssertionError("retry forbidden")):
            module().dispatch(plan, state, run=True)
        events = module().read_ledger(state / "run-ledger.jsonl")
        final = [e for e in events if e["event"] == "run_finished"]
        self.assertEqual(len(final), 1)
        self.assertEqual(final[0]["status"], "capture_incomplete")

    def test_run_budget_is_global_across_resumes(self):
        spec = self.spec()
        spec["budgets"]["max_runs"] = 1
        plan = self.freeze(spec)
        with mock.patch.object(module(), "launch_runner", side_effect=self.fake_launch) as launch:
            module().dispatch(plan, self.root / "state", run=True)
            module().dispatch(plan, self.root / "state", run=True)
        self.assertEqual(launch.call_count, 1)

    def test_wall_budget_stops_later_units(self):
        plan = self.freeze()
        now = [1000.0]

        def slow_runner(*args, **kwargs):
            result = self.fake_launch(*args, **kwargs)
            now[0] += 61
            return result

        with mock.patch.object(module().time, "time", side_effect=lambda: now[0]), \
                mock.patch.object(module(), "launch_runner", side_effect=slow_runner) as launch:
            module().dispatch(plan, self.root / "state", run=True)
        self.assertEqual(launch.call_count, 1)

    def test_mutated_public_input_and_tampered_ledger_fail_closed(self):
        plan = self.freeze()
        (self.public / "request.txt").write_text("modified input")
        with self.assertRaises(module().ContractError):
            module().dispatch(plan, self.root / "state", run=True)
        ledger = self.root / "ledger.jsonl"
        module().append_ledger(ledger, {"event": "first"})
        ledger.write_text(ledger.read_text().replace('"first"', '"altered"'))
        with self.assertRaises(module().ContractError):
            module().read_ledger(ledger)

    def test_cached_tokens_are_a_partition_not_double_priced(self):
        cost = module().standardized_cost(self.measurement(), "A", self.usage())
        self.assertTrue(cost["complete"])
        self.assertAlmostEqual(cost["standardized_cost"], 0.2)

    def test_missing_unknown_and_cumulative_measurements_do_not_yield_full_cost(self):
        for change in ("missing", "unknown", "cumulative", "unsealed", "duplicate", "duplicate-operation"):
            rows = self.usage()
            model = next(r for r in rows if r.get("component") == "model" and r["event"] == "usage")
            if change == "missing":
                rows = [r for r in rows if r.get("component") != "compaction"]
            elif change == "unknown":
                model["values"]["cached_input_tokens"] = None
            elif change == "cumulative":
                model["counter_kind"] = "cumulative"
            elif change == "unsealed":
                rows = [r for r in rows if not (r.get("component") == "model" and r["event"] == "component_end")]
            elif change == "duplicate":
                rows.append(copy.deepcopy(model))
            else:
                duplicate = copy.deepcopy(model)
                duplicate.update(usage_id="another-id", measurement_id="another-measurement")
                rows.append(duplicate)
            with self.subTest(change=change):
                cost = module().standardized_cost(self.measurement(), "A", rows)
                self.assertFalse(cost["complete"])
                self.assertIsNone(cost["standardized_cost"])

    def test_unit_mismatch_and_unknown_rate_fail_cost_without_crashing(self):
        for changed in ("unit", "price"):
            measurement = self.measurement()
            measurement["rates"]["input"][changed] = "request" if changed == "unit" else None
            cost = module().standardized_cost(measurement, "A", self.usage())
            self.assertIsNone(cost["standardized_cost"])

    def test_quality_join_is_separate_and_bad_cost_does_not_flip_success(self):
        plan = self.freeze()
        state = self.root / "state"

        def partial(*args, **kwargs):
            result = self.fake_launch(*args, **kwargs)
            argv = args[0]
            output = Path(argv[argv.index("--output") + 1])
            (output / "usage.jsonl").write_text('{"event":"usage","component":"model"}\n')
            return result

        with mock.patch.object(module(), "launch_runner", side_effect=partial):
            module().dispatch(plan, state, run=True)
        quality = self.root / "evaluator-only-quality.jsonl"
        quality.write_text("".join(json.dumps(r) + "\n" for r in self.quality_rows(plan, state)))
        result = module().join_results(plan, state, quality, self.root / "joined")
        rows = [json.loads(line) for line in Path(result["runs_path"]).read_text().splitlines()]
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r["decision_success"] is True and r["status"] == "completed" for r in rows))
        self.assertTrue(all(r["standardized_cost"] is None for r in rows))
        spec = importlib.util.spec_from_file_location("p1_analyzer_compatibility", ROOT / "scripts/paper1/analyze.py")
        analyzer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(analyzer)
        report = analyzer.analyze(module().load_frozen(plan)["manifest"], rows)
        self.assertEqual(report["counts"]["successful_runs"], 3)
        self.assertEqual(report["comparisons"]["D-C"]["cost"]["status"], "missing_cost")

    def test_absent_quality_does_not_erase_a_complete_measured_cost(self):
        plan = self.freeze()
        with mock.patch.object(module(), "launch_runner", side_effect=self.fake_launch):
            module().dispatch(plan, self.root / "state", run=True)
        quality = self.root / "empty-quality.jsonl"
        quality.write_text("")
        result = module().join_results(plan, self.root / "state", quality, self.root / "joined")
        rows = [json.loads(line) for line in Path(result["runs_path"]).read_text().splitlines()]
        self.assertTrue(all(r["status"] == "evaluator_error" and r["decision_success"] is None for r in rows))
        self.assertTrue(all(r["standardized_cost"] == (0.2 if r["arm"] == "A" else 1.2) for r in rows))

    def test_duplicate_evaluator_rows_are_not_selected_for_best_quality(self):
        plan = self.freeze()
        with mock.patch.object(module(), "launch_runner", side_effect=self.fake_launch):
            module().dispatch(plan, self.root / "state", run=True)
        quality = self.root / "quality.jsonl"
        row = self.quality_rows(plan, self.root / "state")[0]
        quality.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n")
        with self.assertRaises(module().ContractError):
            module().join_results(plan, self.root / "state", quality, self.root / "joined")

    def test_runner_change_between_arms_stops_before_next_attempt(self):
        plan = self.freeze()

        def changed_runner(*args, **kwargs):
            value = self.fake_launch(*args, **kwargs)
            self.runner.write_text("#!/bin/sh\nexit 98\n")
            return value

        with mock.patch.object(module(), "launch_runner", side_effect=changed_runner) as launch:
            with self.assertRaises(module().ContractError):
                module().dispatch(plan, self.root / "state", run=True)
        self.assertEqual(launch.call_count, 1)

    def test_timeout_cannot_certify_full_cost_from_an_earlier_seal(self):
        plan = self.freeze()

        def timeout_runner(*args, **kwargs):
            self.fake_launch(*args, **kwargs)
            raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

        with mock.patch.object(module(), "launch_runner", side_effect=timeout_runner):
            module().dispatch(plan, self.root / "state", run=True)
        terminal = [r for r in module().read_ledger(self.root / "state/run-ledger.jsonl") if r["event"] == "run_finished"]
        self.assertTrue(all(r["status"] == "host_timeout" for r in terminal))
        self.assertTrue(all(r["usage_capture_complete"] is False for r in terminal))

    def test_total_cost_overflow_is_unknown_instead_of_nonfinite(self):
        rows = self.usage()
        for row in rows:
            if row["event"] == "usage" and row["component"] != "model":
                row["values"]["quantity"] = 1e308
        result = module().standardized_cost(self.measurement(), "A", rows)
        self.assertFalse(result["complete"])
        self.assertIsNone(result["standardized_cost"])
        self.assertIsNone(result["partial_observed_cost"])

    def test_component_seal_cannot_precede_its_measurements(self):
        rows = self.usage()
        rows[0], rows[1] = rows[1], rows[0]
        result = module().standardized_cost(self.measurement(), "A", rows)
        self.assertIsNone(result["standardized_cost"])

    def test_invalid_analysis_plan_cannot_be_frozen_as_analyzer_compatible(self):
        spec = self.spec(analysis_plan={
            "frozen": True, "primary_contrast": "D-B", "secondary_contrast": "D-C",
            "confidence_level": 0.95, "noninferiority_margin": 0.03,
            "bootstrap_method": "project_then_task_percentile", "task_weighting": "equal",
            "replicate_aggregation": "mean", "seed": 1, "bootstrap_samples": 1000,
            "min_tasks": True, "min_projects": 2})
        with self.assertRaises(module().ContractError):
            self.freeze(spec)

    def test_usage_digest_mismatch_keeps_quality_but_makes_cost_unknown(self):
        plan = self.freeze()
        state = self.root / "state"
        with mock.patch.object(module(), "launch_runner", side_effect=self.fake_launch):
            module().dispatch(plan, state, run=True)
        usage_path = state / "usage-ledger.jsonl"
        records = module().read_ledger(usage_path)
        usage_path.unlink()
        for event in records:
            event["source_sha256"] = "0" * 64
            module().append_ledger(usage_path, event)
        quality = self.root / "quality.jsonl"
        quality.write_text("".join(json.dumps(r) + "\n" for r in self.quality_rows(plan, state)))
        result = module().join_results(plan, state, quality, self.root / "joined")
        rows = [json.loads(line) for line in Path(result["runs_path"]).read_text().splitlines()]
        self.assertTrue(all(r["decision_success"] is True for r in rows))
        self.assertTrue(all(r["standardized_cost"] is None for r in rows))

    def test_wall_budget_is_rechecked_after_input_verification_before_launch(self):
        plan = self.freeze()
        now, calls = [1000.0], [0]
        original = module().public_digest

        def expensive_check(path):
            calls[0] += 1
            if calls[0] == 4:
                now[0] += 61
            return original(path)

        with mock.patch.object(module().time, "time", side_effect=lambda: now[0]), \
                mock.patch.object(module(), "public_digest", side_effect=expensive_check), \
                mock.patch.object(module(), "launch_runner", side_effect=self.fake_launch) as launch:
            module().dispatch(plan, self.root / "state", run=True)
        self.assertEqual(launch.call_count, 0)

    def test_score_from_different_public_freeze_cannot_join(self):
        plan = self.freeze()
        old_state = self.root / "first-state"
        with mock.patch.object(module(), "launch_runner", side_effect=self.fake_launch):
            module().dispatch(plan, old_state, run=True)
        quality = self.root / "old-quality.jsonl"
        quality.write_text("".join(json.dumps(r) + "\n" for r in self.quality_rows(plan, old_state)))
        (self.public / "request.txt").write_text("A different public input with the same task label.\n")
        second_spec = self.root / "second-spec.json"
        second_spec.write_text(json.dumps(self.spec()))
        second_plan = self.root / "second-plan"
        module().freeze_study(second_spec, second_plan)
        with mock.patch.object(module(), "launch_runner", side_effect=self.fake_launch):
            module().dispatch(second_plan, self.root / "second-state", run=True)
        with self.assertRaises(module().ContractError):
            module().join_results(second_plan, self.root / "second-state", quality, self.root / "joined")

    def test_score_from_another_execution_of_same_plan_cannot_join(self):
        plan = self.freeze()
        with mock.patch.object(module(), "launch_runner", side_effect=self.fake_launch):
            module().dispatch(plan, self.root / "first-state", run=True)
            module().dispatch(plan, self.root / "second-state", run=True)
        quality = self.root / "old-quality.jsonl"
        quality.write_text("".join(json.dumps(r) + "\n" for r in
                                   self.quality_rows(plan, self.root / "first-state")))
        with self.assertRaises(module().ContractError):
            module().join_results(plan, self.root / "second-state", quality, self.root / "joined")

    def test_quality_binding_is_mandatory_not_only_a_run_key(self):
        plan = self.freeze()
        with mock.patch.object(module(), "launch_runner", side_effect=self.fake_launch):
            module().dispatch(plan, self.root / "state", run=True)
        quality = self.root / "unbound-quality.jsonl"
        quality.write_text("".join(json.dumps({**r, "decision_success": True}) + "\n"
                                   for r in module().load_frozen(plan)["manifest"]["runs"]))
        with self.assertRaises(module().ContractError):
            module().join_results(plan, self.root / "state", quality, self.root / "joined")

    def test_output_mutation_after_sealing_invalidates_the_score(self):
        plan = self.freeze()
        state = self.root / "state"
        with mock.patch.object(module(), "launch_runner", side_effect=self.fake_launch):
            module().dispatch(plan, state, run=True)
        quality = self.root / "quality.jsonl"
        quality.write_text("".join(json.dumps(r) + "\n" for r in self.quality_rows(plan, state)))
        unit = module().load_frozen(plan)["schedule"]["units"][0]
        (state / "runs" / unit["run_id"] / "additional-trace.txt").write_text("changed after scoring")
        with self.assertRaises(module().ContractError):
            module().join_results(plan, state, quality, self.root / "joined")

    def test_all_components_cannot_be_declared_not_applicable(self):
        spec = self.spec()
        spec["measurement"]["not_applicable"] = {arm: list(module().PIPELINE_COMPONENTS)
                                                   for arm in spec["arms"]}
        with self.assertRaises(module().ContractError):
            self.freeze(spec)

    def test_known_zero_prices_cannot_create_complete_reference_cost(self):
        measurement = self.measurement()
        for rate in measurement["rates"].values():
            rate["price"] = 0
        self.assertIsNone(module().standardized_cost(measurement, "A", self.usage())["standardized_cost"])

    def test_completed_model_stage_cannot_have_only_zero_usage(self):
        rows = self.usage()
        for row in rows:
            if row["event"] == "usage" and row["component"] == "model":
                row["values"] = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
        self.assertIsNone(module().standardized_cost(self.measurement(), "A", rows)["standardized_cost"])

    def test_public_digest_covers_file_permissions_and_empty_directories(self):
        source = self.public / "request.txt"
        source.chmod(0o600)
        before = module().public_digest(self.public)
        source.chmod(0o700)
        self.assertNotEqual(module().public_digest(self.public), before)
        before = module().public_digest(self.public)
        (self.public / "empty-workspace").mkdir()
        self.assertNotEqual(module().public_digest(self.public), before)

    def test_public_digest_covers_directory_permissions(self):
        self.public.chmod(0o700)
        before = module().public_digest(self.public)
        self.public.chmod(0o755)
        self.assertNotEqual(module().public_digest(self.public), before)

    def test_completed_selective_arm_requires_extraction_activity(self):
        self.assertIsNone(module().standardized_cost(self.measurement(), "D", self.usage())["standardized_cost"])

    def test_failure_before_model_work_does_not_invent_positive_usage(self):
        rows = self.usage()
        for row in rows:
            if row["event"] == "usage" and row["component"] == "model":
                row["values"] = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
        cost = module().standardized_cost(self.measurement(), "D", rows, terminal_status="host_error")
        self.assertTrue(cost["complete"])
        self.assertEqual(cost["standardized_cost"], 0)

    def test_score_input_export_supplies_the_required_sealed_binding(self):
        plan = self.freeze()
        state = self.root / "state"
        with mock.patch.object(module(), "launch_runner", side_effect=self.fake_launch):
            module().dispatch(plan, state, run=True)
        path = self.root / "score-inputs.json"
        module().export_score_inputs(plan, state, path)
        score_inputs = json.loads(path.read_text())
        self.assertEqual(score_inputs["sealed_runs"], 3)
        for row in score_inputs["runs"]:
            self.assertEqual(len(row["sealed_run_sha256"]), 64)
            self.assertEqual(row["freeze_sha256"], score_inputs["freeze_sha256"])
        quality = self.root / "quality.jsonl"
        quality.write_text("".join(json.dumps({**row, "decision_success": True}) + "\n"
                                   for row in score_inputs["runs"]))
        result = module().join_results(plan, state, quality, self.root / "joined")
        self.assertEqual(result["complete_cost_runs"], 3)

    def test_documented_zero_reference_rate_still_requires_measured_work(self):
        measurement = self.measurement()
        for rate in measurement["rates"].values():
            rate["price"] = 0
            rate["zero_price_evidence"] = {
                "ref": "synthetic-test-contract-only",
                "sha256": hashlib.sha256(b"synthetic zero-price contract").hexdigest()}
        complete = module().standardized_cost(measurement, "D", self.usage("D"))
        self.assertTrue(complete["complete"])
        self.assertEqual(complete["standardized_cost"], 0)
        self.assertIsNone(module().standardized_cost(measurement, "D", self.usage())["standardized_cost"])

    def test_not_performed_is_only_allowed_for_noncompleted_execution(self):
        rows = [{"event": "component_end", "component": component, "coverage": "not_performed",
                 "usage_ids": [], "reason": "runner launch failed before any work", "evidence_ref": "launch-error"}
                for component in module().PIPELINE_COMPONENTS]
        self.assertIsNone(module().standardized_cost(self.measurement(), "D", rows)["standardized_cost"])
        failed = module().standardized_cost(self.measurement(), "D", rows, terminal_status="host_error")
        self.assertTrue(failed["complete"])
        self.assertEqual(failed["standardized_cost"], 0)

    def test_omitted_extraction_mandatory_rule_cannot_be_frozen_for_d(self):
        spec = self.spec()
        spec["measurement"]["mandatory_measured_components"]["D"] = ["model"]
        with self.assertRaises(module().ContractError):
            self.freeze(spec)


if __name__ == "__main__":
    unittest.main()
