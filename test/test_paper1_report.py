"""Reporting contracts on synthetic fixtures only; never study observations."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_paper1_analysis import plan, observation

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/paper1/report.py"


class ReportTests(unittest.TestCase):
    def invoke(self, manifest, records=(), *, raw_lines=None, code=0):
        self.assertTrue(SCRIPT.is_file(), "The reproducible report entry point is missing")
        with tempfile.TemporaryDirectory(prefix="p1-report-fixture-") as directory:
            root = Path(directory)
            (root / "manifest.json").write_text(json.dumps(manifest))
            lines = raw_lines if raw_lines is not None else [json.dumps(r) for r in records]
            (root / "runs.jsonl").write_text("\n".join(lines))
            args = [sys.executable, "-B", str(SCRIPT), "--manifest", str(root / "manifest.json"),
                    "--runs", str(root / "runs.jsonl"), "--output", str(root / "report"),
                    "--data-kind", "fixture"]
            result = subprocess.run(args, text=True, capture_output=True)
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
            if code:
                return json.loads(result.stdout)
            summary = json.loads((root / "report/summary.json").read_text())
            summary["markdown"] = (root / "report/report.md").read_text()
            summary["raw_analysis"] = json.loads((root / "report/analysis.json").read_text())
            summary["provenance"] = json.loads((root / "report/provenance.json").read_text())
            summary["csv"] = (root / "report/arms.csv").read_text()
            again = subprocess.run(args, text=True, capture_output=True)
            self.assertEqual(again.returncode, 2, "Reports must not silently overwrite an earlier artifact")
            return summary

    def test_unrun_schedule_is_unmeasured_not_observed_zero(self):
        result = self.invoke(plan())
        self.assertEqual(result["measurement_status"], "unmeasured")
        self.assertEqual(result["counts"]["planned_runs"], 6)
        self.assertEqual(result["counts"]["measured_quality_runs"], 0)
        for arm in result["arms"]:
            self.assertIsNone(arm["decision_success_task_mean"])
            self.assertIsNone(arm["standardized_cost_task_mean"])
        self.assertIsNone(result["comparisons"]["D-B"]["quality"]["estimate"])
        self.assertIn("NOT MEASURED", result["markdown"])
        self.assertEqual(result["raw_analysis"]["counts"]["successful_runs"], 0)
        self.assertFalse(result["scientific_effect_claims_allowed"])

    def test_task_means_preserve_failed_and_missing_replicates(self):
        manifest = plan(tasks=2, replicates=2)
        records = [observation(r, success=(r["task_id"] == "task-0"), cost=2,
                               elapsed_seconds=10 if r["replicate"] == 1 else 20)
                   for r in manifest["runs"]]
        result = self.invoke(manifest, records)
        for arm in result["arms"]:
            self.assertEqual(arm["decision_success_task_mean"], 0.5)
            self.assertEqual(arm["standardized_cost_task_mean"], 2)
            self.assertEqual(arm["latency"]["p95_seconds"], 20)
            self.assertEqual(arm["latency"]["observed_runs"], 4)
        self.assertEqual(result["measurement_status"], "measured")
        self.assertEqual(result["data_kind"], "fixture")
        self.assertIn("FIXTURE", result["markdown"])
        self.assertEqual(len(result["provenance"]["inputs"]["manifest"]["sha256"]), 64)

    def test_partial_noncollection_suppresses_empirical_effect_but_preserves_itt_audit(self):
        manifest = plan()
        result = self.invoke(manifest, [observation(manifest["runs"][0])])
        self.assertEqual(result["measurement_status"], "incomplete")
        self.assertIsNone(result["comparisons"]["D-B"]["quality"]["estimate"])
        self.assertEqual(result["raw_analysis"]["counts"]["planned_runs"], 6)
        self.assertEqual(result["raw_analysis"]["counts"]["missing_runs"], 5)

    def test_known_method_failure_is_measured_itt_failure_and_timeout_duration_is_retained(self):
        manifest = plan(replicates=1)
        rows = [observation(r, success=False, status="host_timeout", elapsed_seconds=30)
                for r in manifest["runs"]]
        result = self.invoke(manifest, rows)
        self.assertEqual(result["measurement_status"], "measured")
        for arm in result["arms"]:
            self.assertEqual(arm["decision_success_task_mean"], 0)
            self.assertEqual(arm["latency"]["timeout_or_budget_stop_runs"], 1)
            self.assertEqual(arm["latency"]["p95_seconds"], 30)

    def test_invalid_cost_never_changes_quality_and_absent_components_are_not_false(self):
        manifest = plan(replicates=1)
        rows = [observation(r, cost="unknown", elapsed_seconds=-1) for r in manifest["runs"]]
        result = self.invoke(manifest, rows)
        for arm in result["arms"]:
            self.assertEqual(arm["decision_success_task_mean"], 1)
            self.assertIsNone(arm["standardized_cost_task_mean"])
            self.assertIsNone(arm["components"]["behavior_success"]["observed_rate"])
            self.assertIsNone(arm["latency"]["p95_seconds"])

    def test_malformed_json_is_reported_without_removing_planned_runs(self):
        result = self.invoke(plan(), raw_lines=['{"task_id":'])
        self.assertEqual(len(result["raw_analysis"]["input_issues"]), 1)
        self.assertEqual(result["counts"]["planned_runs"], 6)
        self.assertIsNone(result["comparisons"]["D-C"]["quality"]["estimate"])

    def test_duplicate_run_is_rejected_by_existing_analyzer(self):
        manifest = plan()
        row = observation(manifest["runs"][0])
        result = self.invoke(manifest, [row, row], code=2)
        self.assertEqual(result["error"]["code"], "duplicate_run")


if __name__ == "__main__":
    unittest.main()
