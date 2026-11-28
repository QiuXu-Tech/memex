"""Offline behavioral tests for the P1 intent-to-treat analysis entry point.

All datasets below are synthetic test inputs, never study observations.
Run: PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s test -p test_paper1_analysis.py -v
"""

import copy
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "paper1" / "analyze.py"


def plan(tasks=1, replicates=2, projects=None, phase="development"):
    rows = []
    for task in range(tasks):
        project = projects[task] if projects is not None else f"project-{task}"
        for arm in ("B", "C", "D"):
            for replicate in range(1, replicates + 1):
                rows.append(dict(task_id=f"task-{task}", project_id=project,
                                 arm=arm, replicate=replicate))
    return {"schema_version": 1, "study_phase": phase, "frozen": True, "runs": rows}


def observation(planned, success=True, cost=1.0, **extra):
    return {**planned, "status": "completed", "decision_success": success,
            "standardized_cost": cost, **extra}


def frozen_analysis():
    return {
        "frozen": True, "primary_contrast": "D-B", "secondary_contrast": "D-C",
        "confidence_level": 0.95, "noninferiority_margin": 0.03,
        "bootstrap_method": "project_then_task_percentile", "task_weighting": "equal",
        "replicate_aggregation": "mean", "seed": 17, "bootstrap_samples": 1000,
        "min_tasks": 20, "min_projects": 8,
    }


def frozen_cost_model():
    return {"frozen": True, "currency": "USD", "rate_card_id": "test-rates-v1",
            "rates": {"input_token": 0.000001, "output_token": 0.000005, "cpu_second": 0.0001},
            "cost_scope": "full_pipeline_per_scheduled_task",
            "allocation_rule": "shared prelude once per deployed arm; index over frozen task count"}


def confirmatory_fixture(*, all_success=False):
    manifest = plan(tasks=24, replicates=1, phase="confirmatory",
                    projects=[f"project-{i // 3}" for i in range(24)])
    manifest["analysis_plan"] = frozen_analysis()
    manifest["cost_model"] = frozen_cost_model()
    records = [observation(row, all_success or row["arm"] == "D"
                           or int(row["task_id"].split("-")[-1]) % 4 == 0)
               for row in manifest["runs"]]
    return manifest, records


class AnalysisCliTests(unittest.TestCase):
    def invoke(self, manifest, records=(), *, raw_lines=None, expected_code=0,
               bootstrap_samples=200, seed=17):
        with tempfile.TemporaryDirectory(prefix="paper1-analysis-test-") as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            results_path = root / "runs.jsonl"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            lines = raw_lines if raw_lines is not None else [json.dumps(row) for row in records]
            results_path.write_text("\n".join(lines), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), "--manifest", str(manifest_path),
                 "--runs", str(results_path), "--bootstrap-samples", str(bootstrap_samples),
                 "--seed", str(seed)], text=True, capture_output=True, check=False,
            )
        self.assertEqual(result.returncode, expected_code, result.stderr or result.stdout)
        self.assertTrue(result.stdout.lstrip().startswith("{"),
                        "The CLI must emit a JSON report or JSON input error: " + result.stderr)
        return json.loads(result.stdout)

    def test_missing_and_host_failed_runs_remain_in_planned_denominator(self):
        manifest = plan()
        rows = manifest["runs"]
        records = [observation(rows[0]), observation(rows[1]),
                   observation(rows[2], status="host_error"),
                   observation(rows[4], success=False, cost=2),
                   observation(rows[5], cost=2)]
        report = self.invoke(manifest, records)
        self.assertEqual(report["counts"]["planned_runs"], 6)
        self.assertEqual(report["counts"]["missing_runs"], 1)
        self.assertEqual(report["counts"]["successful_runs"], 3)
        task = report["tasks"][0]
        self.assertEqual(task["arms"]["B"]["decision_success_mean"], 1.0)
        self.assertEqual(task["arms"]["C"]["decision_success_mean"], 0.0)
        self.assertEqual(task["arms"]["D"]["decision_success_mean"], 0.5)
        self.assertEqual(report["comparisons"]["D-B"]["quality"]["estimate"], -0.5)
        self.assertEqual(report["comparisons"]["D-C"]["quality"]["estimate"], 0.5)

    def test_malformed_success_is_failure_and_replicates_do_not_inflate_n(self):
        manifest = plan(replicates=4)
        records = [observation(row, claims=[True] * 100, seed=i)
                   for i, row in enumerate(manifest["runs"])]
        records[-1]["decision_success"] = "true"
        report = self.invoke(manifest, records)
        self.assertEqual(report["counts"]["malformed_runs"], 1)
        self.assertEqual(report["comparisons"]["D-B"]["n_tasks"], 1)
        self.assertEqual(report["comparisons"]["D-B"]["n_projects"], 1)
        self.assertEqual(report["comparisons"]["D-B"]["quality"]["estimate"], -0.25)
        self.assertIsNone(report["comparisons"]["D-B"]["quality"]["hierarchical_ci"])

    def test_duplicate_observations_are_rejected_even_with_distinct_seed_or_attempt(self):
        manifest = plan()
        first = observation(manifest["runs"][0], success=False, seed=1, attempt=1)
        second = observation(manifest["runs"][0], success=True, seed=2, attempt=2)
        report = self.invoke(manifest, [first, second], expected_code=2)
        self.assertEqual(report["error"]["code"], "duplicate_run")

    def test_duplicate_plan_and_inconsistent_project_are_rejected(self):
        manifest = plan()
        manifest["runs"].append(copy.deepcopy(manifest["runs"][0]))
        report = self.invoke(manifest, expected_code=2)
        self.assertEqual(report["error"]["code"], "duplicate_plan")
        manifest = plan()
        manifest["runs"][-1]["project_id"] = "different-project"
        report = self.invoke(manifest, expected_code=2)
        self.assertEqual(report["error"]["code"], "inconsistent_project")

    def test_unparseable_jsonl_is_reported_without_dropping_planned_runs(self):
        report = self.invoke(plan(), raw_lines=['{"task_id":'])
        self.assertEqual(report["counts"]["planned_runs"], 6)
        self.assertEqual(report["counts"]["missing_runs"], 6)
        self.assertEqual(report["counts"]["successful_runs"], 0)
        self.assertEqual(len(report["input_issues"]), 1)
        self.assertFalse(report["hypotheses"]["H1"]["supported"])

    def test_missing_standardized_cost_is_not_filled_from_actual_spend(self):
        manifest = plan(replicates=1)
        records = [observation(row, cost=None, actual_spend=9.0,
                               actual_spend_currency="USD") for row in manifest["runs"]]
        report = self.invoke(manifest, records)
        self.assertIsNone(report["tasks"][0]["arms"]["D"]["standardized_cost_mean"])
        self.assertIsNone(report["comparisons"]["D-C"]["cost"]["estimate"])
        self.assertEqual(report["actual_spend"]["by_currency"]["USD"]["observed_total"], 27.0)
        self.assertFalse(report["hypotheses"]["H2"]["supported"])

    def test_unplanned_run_is_rejected_instead_of_silently_selected(self):
        manifest = plan()
        record = observation(manifest["runs"][0])
        record["task_id"] = "not-in-plan"
        report = self.invoke(manifest, [record], expected_code=2)
        self.assertEqual(report["error"]["code"], "unplanned_run")

    def test_project_bootstrap_keeps_cluster_dependence_and_task_weighting(self):
        manifest = plan(tasks=40, replicates=1,
                        projects=[f"project-{i // 5}" for i in range(40)])
        records = []
        for row in manifest["runs"]:
            group = int(row["project_id"].split("-")[-1])
            success = (group < 4) if row["arm"] == "D" else (group >= 4)
            records.append(observation(row, success))
        report = self.invoke(manifest, records, bootstrap_samples=1000)
        comparison = report["comparisons"]["D-B"]
        quality = comparison["quality"]
        self.assertEqual(comparison["n_tasks"], 40)
        self.assertEqual(comparison["n_projects"], 8)
        self.assertEqual(quality["estimate"], 0.0)
        self.assertEqual(quality["status"], "ok")
        hierarchical = quality["hierarchical_ci"]
        sensitivity = quality["task_ci"]
        self.assertIsNotNone(hierarchical)
        self.assertIsNotNone(sensitivity)
        self.assertGreater(hierarchical["upper"] - hierarchical["lower"],
                           sensitivity["upper"] - sensitivity["lower"])

    def test_too_few_projects_blocks_primary_inference_despite_many_tasks(self):
        manifest = plan(tasks=20, replicates=1, projects=["large"] * 19 + ["small"])
        records = [observation(row, (row["project_id"] == "large") == (row["arm"] == "D"))
                   for row in manifest["runs"]]
        report = self.invoke(manifest, records, bootstrap_samples=1000)
        quality = report["comparisons"]["D-B"]["quality"]
        self.assertAlmostEqual(quality["estimate"], 0.9)
        self.assertEqual(quality["status"], "insufficient_projects")
        self.assertIsNone(quality["hierarchical_ci"])
        self.assertIsNotNone(quality["task_ci"])
        self.assertFalse(report["hypotheses"]["H1"]["supported"])

    def test_seed_and_input_order_reproduce_intervals(self):
        manifest = plan(tasks=24, replicates=1,
                        projects=[f"project-{i // 3}" for i in range(24)])
        records = [observation(row, int(row["task_id"].split("-")[-1]) % 3 == (row["arm"] == "D"),
                               cost=1 + int(row["task_id"].split("-")[-1]) % 4)
                   for row in manifest["runs"]]
        original = self.invoke(manifest, records, bootstrap_samples=1000)
        manifest["runs"].reverse()
        repeated = self.invoke(manifest, list(reversed(records)), bootstrap_samples=1000)
        self.assertEqual(original["comparisons"], repeated["comparisons"])
        self.assertIn("analysis", original, "The report must identify its resampling settings")
        self.assertEqual(original["analysis"]["seed"], 17)

    def test_degenerate_bootstrap_does_not_report_certain_effect(self):
        manifest = plan(tasks=24, replicates=1,
                        projects=[f"project-{i // 3}" for i in range(24)])
        records = [observation(row, row["arm"] == "D") for row in manifest["runs"]]
        report = self.invoke(manifest, records, bootstrap_samples=1000)
        quality = report["comparisons"]["D-B"]["quality"]
        self.assertEqual(quality["estimate"], 1.0)
        self.assertEqual(quality["status"], "degenerate_bootstrap")
        self.assertIsNone(quality["hierarchical_ci"])
        self.assertFalse(report["hypotheses"]["H1"]["supported"])

    def test_missing_failure_cost_blocks_cost_interval_not_just_one_task(self):
        manifest = plan(tasks=24, replicates=1,
                        projects=[f"project-{i // 3}" for i in range(24)])
        records = [observation(row, cost=1 if row["arm"] == "D" else 2)
                   for row in manifest["runs"]]
        records[-1].update(status="host_error", decision_success=False, standardized_cost=None)
        report = self.invoke(manifest, records, bootstrap_samples=1000)
        cost = report["comparisons"]["D-C"]["cost"]
        self.assertIsNone(cost["estimate"])
        self.assertIsNone(cost["hierarchical_ci"])
        self.assertEqual(cost["status"], "missing_cost")
        self.assertFalse(report["hypotheses"]["H2"]["supported"])

    def test_nonpositive_bootstrap_count_is_rejected(self):
        report = self.invoke(plan(), bootstrap_samples=0, expected_code=2)
        self.assertEqual(report["error"]["code"], "invalid_analysis_config")

    def test_pilot_is_descriptive_even_when_interval_is_strictly_positive(self):
        manifest = plan(tasks=40, replicates=1, phase="pilot",
                        projects=[f"project-{i // 5}" for i in range(40)])
        manifest["analysis_plan"] = frozen_analysis()
        manifest["cost_model"] = frozen_cost_model()
        records = [observation(row, row["arm"] == "D" or int(row["task_id"].split("-")[-1]) % 4 == 0)
                   for row in manifest["runs"]]
        report = self.invoke(manifest, records, bootstrap_samples=1000)
        self.assertGreater(report["comparisons"]["D-B"]["quality"]["hierarchical_ci"]["lower"], 0)
        self.assertEqual(report["hypotheses"].get("mode"), "descriptive")
        self.assertFalse(report["hypotheses"]["H1"]["supported"])
        self.assertFalse(report["hypotheses"]["H2"]["supported"])

    def test_operational_sample_guards_are_configurable_and_not_power_claims(self):
        manifest = plan(tasks=24, replicates=1,
                        projects=[f"project-{i // 3}" for i in range(24)])
        manifest["analysis_plan"] = frozen_analysis()
        manifest["analysis_plan"]["min_tasks"] = 30
        records = [observation(row, row["arm"] == "D" or int(row["task_id"].split("-")[-1]) % 4 == 0)
                   for row in manifest["runs"]]
        report = self.invoke(manifest, records, bootstrap_samples=1000)
        self.assertEqual(report["comparisons"]["D-B"]["quality"]["status"], "insufficient_tasks")
        self.assertEqual(report["analysis"]["min_tasks"], 30)
        self.assertTrue(report["analysis"].get("guard_not_power_analysis"))

    def test_structurally_bad_status_is_scored_failure_without_crashing(self):
        manifest = plan(replicates=1)
        records = [observation(row) for row in manifest["runs"]]
        records[-1]["status"] = {"completed": True}
        report = self.invoke(manifest, records)
        self.assertEqual(report["counts"]["malformed_runs"], 1)
        self.assertEqual(report["tasks"][0]["arms"]["D"]["decision_success_mean"], 0)

    def test_single_retry_record_is_not_accepted_as_first_attempt(self):
        manifest = plan()
        record = observation(manifest["runs"][0], attempt=2)
        report = self.invoke(manifest, [record], expected_code=2)
        self.assertEqual(report["error"]["code"], "unsupported_attempt")

    def test_missing_planned_arm_does_not_become_a_complete_case_comparison(self):
        manifest = plan(tasks=2, replicates=1)
        manifest["runs"] = [row for row in manifest["runs"]
                            if not (row["task_id"] == "task-1" and row["arm"] == "B")]
        report = self.invoke(manifest, [observation(row) for row in manifest["runs"]])
        comparison = report["comparisons"]["D-B"]
        self.assertEqual(comparison["unpaired_tasks"], ["task-1"])
        self.assertIsNone(comparison["quality"]["estimate"])
        self.assertEqual(comparison["quality"]["status"], "unpaired_design")

    def test_collection_gap_blocks_confirmation_while_retaining_failure(self):
        manifest = plan(tasks=24, replicates=1, phase="confirmatory",
                        projects=[f"project-{i // 3}" for i in range(24)])
        manifest["analysis_plan"] = frozen_analysis()
        records = [observation(row, row["arm"] == "D" or int(row["task_id"].split("-")[-1]) % 4 == 0)
                   for row in manifest["runs"]][1:]
        report = self.invoke(manifest, records, bootstrap_samples=1000)
        self.assertEqual(report["counts"]["missing_runs"], 1)
        self.assertFalse(report["hypotheses"]["H1"]["supported"])
        self.assertIn("unresolved_input_or_collection_issue", report["hypotheses"]["blocking_reasons"])

    def test_invalid_manifest_types_return_structured_errors(self):
        for field, value in (("schema_version", True), ("study_phase", {})):
            with self.subTest(field=field):
                manifest = plan()
                manifest[field] = value
                report = self.invoke(manifest, expected_code=2)
                self.assertEqual(report["error"]["code"], "invalid_manifest")

    def test_invalid_cost_is_unknown_without_overriding_valid_quality(self):
        for cost in (True, -1, 10 ** 400):
            with self.subTest(cost_type=type(cost).__name__):
                manifest = plan(replicates=1)
                records = [observation(row) for row in manifest["runs"]]
                records[-1]["standardized_cost"] = cost
                report = self.invoke(manifest, records)
                self.assertEqual(report["counts"]["malformed_runs"], 0)
                self.assertEqual(report["counts"]["successful_runs"], 3)
                self.assertEqual(report["counts"].get("invalid_cost_runs"), 1)
                self.assertIsNone(report["tasks"][0]["arms"]["D"]["standardized_cost_mean"])

    def test_damaged_b_costs_cannot_create_false_h1_from_72_successful_runs(self):
        # Reviewer reproduction: all 72 outcomes are true; only 18 B costs are
        # damaged. The old normalizer created a false D-B quality gain of 0.75.
        manifest, records = confirmatory_fixture(all_success=True)
        for row in records:
            if row["arm"] == "B" and int(row["task_id"].split("-")[-1]) < 18:
                row["standardized_cost"] = "damaged"
        report = self.invoke(manifest, records, bootstrap_samples=1000)
        self.assertFalse(report["hypotheses"]["H1"]["supported"])
        self.assertEqual(report["comparisons"]["D-B"]["quality"]["estimate"], 0.0)
        self.assertEqual(report["counts"]["successful_runs"], 72)
        self.assertEqual(report["counts"]["malformed_runs"], 0)
        self.assertEqual(report["counts"].get("invalid_cost_runs"), 18)
        self.assertEqual(len(report.get("data_issues", [])), 18)
        for issue in report["data_issues"]:
            self.assertEqual(issue["field"], "standardized_cost")
            self.assertFalse(issue["blocks_quality_confirmation"])

    def test_cost_corruption_preserves_a_valid_quality_comparison(self):
        manifest, records = confirmatory_fixture()
        expected = self.invoke(manifest, records, bootstrap_samples=1000)
        self.assertTrue(expected["hypotheses"]["H1"]["supported"])
        for row in records:
            if row["arm"] == "B":
                row["standardized_cost"] = "damaged"
        actual = self.invoke(manifest, records, bootstrap_samples=1000)
        self.assertEqual(actual["comparisons"]["D-B"]["quality"],
                         expected["comparisons"]["D-B"]["quality"])
        self.assertEqual(actual["hypotheses"]["H1"], expected["hypotheses"]["H1"])
        self.assertIsNone(actual["comparisons"]["D-B"]["cost"]["estimate"])

    def test_unknown_status_blocks_confirmation_without_removing_runs(self):
        manifest, records = confirmatory_fixture(all_success=True)
        for row in records:
            if row["arm"] == "B" and int(row["task_id"].split("-")[-1]) < 18:
                row["status"] = "damaged_status"
        report = self.invoke(manifest, records, bootstrap_samples=1000)
        self.assertFalse(report["hypotheses"]["H1"]["supported"])
        self.assertEqual(report["counts"]["planned_runs"], 72)
        self.assertEqual(len(report["runs"]), 72)
        self.assertEqual(report["counts"]["malformed_runs"], 18)
        self.assertIn("unresolved_input_or_collection_issue", report["hypotheses"]["blocking_reasons"])
        self.assertTrue(all(issue["blocks_quality_confirmation"] for issue in report["data_issues"]))

    def test_unreadable_completed_outcome_blocks_confirmation(self):
        manifest, records = confirmatory_fixture(all_success=True)
        for row in records:
            if row["arm"] == "B" and int(row["task_id"].split("-")[-1]) < 18:
                row["decision_success"] = "unreadable"
        report = self.invoke(manifest, records, bootstrap_samples=1000)
        self.assertFalse(report["hypotheses"]["H1"]["supported"])
        self.assertEqual(report["counts"]["planned_runs"], 72)
        self.assertEqual(report["counts"]["malformed_runs"], 18)
        self.assertTrue(all(issue["field"] == "decision_success" for issue in report["data_issues"]))

    def test_predefined_method_invalid_output_is_an_itt_failure_not_a_data_gap(self):
        manifest, records = confirmatory_fixture(all_success=True)
        for row in records:
            if row["arm"] == "B" and int(row["task_id"].split("-")[-1]) < 18:
                row.update(status="model_invalid_output", decision_success=False)
        report = self.invoke(manifest, records, bootstrap_samples=1000)
        self.assertTrue(report["hypotheses"]["H1"]["supported"])
        self.assertEqual(report["comparisons"]["D-B"]["quality"]["estimate"], 0.75)
        self.assertEqual(report["counts"]["planned_runs"], 72)
        self.assertEqual(report["counts"]["malformed_runs"], 0)
        self.assertEqual(report["hypotheses"]["blocking_reasons"], [])

    def test_bad_ratecard_fields_do_not_change_quality(self):
        manifest, records = confirmatory_fixture()
        expected = self.invoke(manifest, records, bootstrap_samples=1000)
        for field, value in (("rates", {"input_token": "damaged"}), ("currency", {}),
                             ("rate_card_id", None)):
            with self.subTest(field=field):
                damaged = copy.deepcopy(manifest)
                damaged["cost_model"][field] = value
                actual = self.invoke(damaged, records, bootstrap_samples=1000)
                self.assertEqual(actual["comparisons"]["D-B"]["quality"],
                                 expected["comparisons"]["D-B"]["quality"])
                self.assertEqual(actual["hypotheses"]["H1"], expected["hypotheses"]["H1"])
                self.assertFalse(actual["hypotheses"]["H2"]["frozen_full_cost_model_available"])
                self.assertFalse(actual["hypotheses"]["H2"]["supported"])

    def test_bad_jsonl_line_cannot_selectively_remove_a_planned_run(self):
        manifest, records = confirmatory_fixture()
        lines = [json.dumps(row) for row in records]
        lines[0] = '{"task_id":"task-0", "project_id":'
        report = self.invoke(manifest, raw_lines=lines, bootstrap_samples=1000)
        self.assertEqual(report["counts"]["planned_runs"], 72)
        self.assertEqual(len(report["runs"]), 72)
        self.assertEqual(report["counts"]["missing_runs"], 1)
        self.assertEqual(report["counts"]["received_runs"], 71)
        self.assertEqual(len(report["input_issues"]), 1)
        self.assertFalse(report["hypotheses"]["H1"]["supported"])


class HypothesisGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = runpy.run_path(str(SCRIPT))

    def gate(self, *, phase="confirmatory", quality_lower=-0.02, cost_upper=-0.5,
             primary_lower=0.08, cost_complete=True, edit_manifest=None,
             integrity_ok=True, settings=None):
        self.assertTrue("hypothesis_decisions" in self.module,
                        "The analysis must implement its explicit hierarchical decision rule")
        manifest = plan(tasks=24, replicates=1, phase=phase,
                        projects=[f"project-{i // 3}" for i in range(24)])
        manifest["analysis_plan"] = frozen_analysis()
        manifest["cost_model"] = frozen_cost_model()
        if edit_manifest:
            edit_manifest(manifest)

        def metric(lower, upper):
            return {"status": "ok", "estimate": (lower + upper) / 2,
                    "hierarchical_ci": {"lower": lower, "upper": upper, "confidence_level": 0.95}}

        comparisons = {"D-B": {"quality": metric(primary_lower, 0.2)},
                       "D-C": {"quality": metric(quality_lower, 0.04), "cost": metric(-2.0, cost_upper)}}
        return self.module["hypothesis_decisions"](
            manifest, comparisons, cost_complete=cost_complete, integrity_ok=integrity_ok,
            settings=settings if settings is not None else frozen_analysis())

    def test_h2_requires_all_three_strict_conditions(self):
        self.assertTrue(self.gate()["H2"]["supported"])
        self.assertFalse(self.gate(primary_lower=0.0)["H2"]["supported"])
        self.assertFalse(self.gate(quality_lower=-0.03)["H2"]["supported"])
        self.assertTrue(self.gate(quality_lower=-0.029)["H2"]["supported"])
        self.assertFalse(self.gate(cost_upper=0.0)["H2"]["supported"])

    def test_missing_cost_or_rate_information_cannot_establish_h2(self):
        self.assertFalse(self.gate(cost_complete=False)["H2"]["supported"])
        self.assertFalse(self.gate(edit_manifest=lambda m: m.pop("cost_model"))["H2"]["supported"])
        self.assertFalse(self.gate(edit_manifest=lambda m: m["cost_model"].update(rates={}))
                         ["H2"]["supported"])
        self.assertFalse(self.gate(edit_manifest=lambda m: m["cost_model"].update(cost_scope="reader_only"))
                         ["H2"]["supported"])

    def test_nonconfirmatory_or_unfrozen_protocol_never_supports_hypotheses(self):
        for phase in ("development", "pilot", "external"):
            with self.subTest(phase=phase):
                result = self.gate(phase=phase)
                self.assertFalse(result["H1"]["supported"])
                self.assertFalse(result["H2"]["supported"])
        edits = [lambda m: m.pop("analysis_plan"),
                 lambda m: m["analysis_plan"].update(noninferiority_margin=0.04),
                 lambda m: m["analysis_plan"].update(frozen=False)]
        for edit in edits:
            result = self.gate(edit_manifest=edit)
            self.assertFalse(result["H1"]["supported"])
            self.assertFalse(result["H2"]["supported"])

    def test_settings_override_or_unassigned_bad_record_blocks_confirmation(self):
        settings = frozen_analysis()
        settings["seed"] = 18
        self.assertFalse(self.gate(settings=settings)["H1"]["supported"])
        self.assertFalse(self.gate(integrity_ok=False)["H1"]["supported"])


if __name__ == "__main__":
    unittest.main()
