"""Design summaries use fixture data and explicit assumptions, never real pilots."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_paper1_analysis import plan, observation

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/paper1/design_analysis.py"


class DesignAnalysisTests(unittest.TestCase):
    def invoke(self, manifest, records=(), scenarios=None, *, code=0):
        self.assertTrue(SCRIPT.is_file(), "The pilot design-analysis entry point is missing")
        with tempfile.TemporaryDirectory(prefix="p1-design-fixture-") as directory:
            root = Path(directory)
            (root / "manifest.json").write_text(json.dumps(manifest))
            (root / "runs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
            args = [sys.executable, "-B", str(SCRIPT), "--manifest", str(root / "manifest.json"),
                    "--runs", str(root / "runs.jsonl"), "--output", str(root / "output"),
                    "--data-kind", "fixture"]
            if scenarios is not None:
                (root / "scenarios.json").write_text(json.dumps(scenarios))
                args.extend(["--scenarios", str(root / "scenarios.json")])
            result = subprocess.run(args, text=True, capture_output=True)
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
            if code:
                return json.loads(result.stdout)
            return json.loads((root / "output/design-analysis.json").read_text())

    def scenarios(self):
        return {"schema_version": 1, "kind": "assumption_only", "scenarios": [{
            "name": "fixture-only", "n_tasks": 16, "n_projects": 8, "replicates": 2,
            "arms": ["A", "B", "C", "D", "T"], "shared_prelude": True,
            "assumed_cost_per_continuation": 0.5, "assumed_cost_per_prelude": 2,
            "currency": "CNY", "assumption_source": "Synthetic resource arithmetic example, not measured rates."}]}

    def test_empty_pilot_has_no_estimated_variance_or_formal_sample_size(self):
        result = self.invoke(plan(phase="pilot"))
        self.assertEqual(result["measurement_status"], "unmeasured")
        self.assertFalse(result["real_pilot_estimates_available"])
        self.assertIsNone(result["formal_sample_size"])
        self.assertFalse(result["power_simulation_performed"])
        self.assertIsNone(result["paired_diagnostics"]["D-B"]["paired_task_variance"])

    def test_explicit_assumptions_produce_run_counts_not_power_or_observed_cost(self):
        result = self.invoke(plan(phase="pilot"), scenarios=self.scenarios())
        scenario = result["resource_scenarios"][0]
        self.assertEqual(scenario["continuations"], 160)
        self.assertEqual(scenario["preludes"], 32)
        self.assertEqual(scenario["assumed_total_cost"], 144)
        self.assertEqual(scenario["kind"], "assumption_only")
        self.assertIsNone(scenario["power"])
        self.assertIsNone(result["formal_sample_size"])

    def test_unknown_cost_assumptions_remain_unknown(self):
        scenarios = self.scenarios()
        scenarios["scenarios"][0]["assumed_cost_per_continuation"] = None
        result = self.invoke(plan(), scenarios=scenarios)
        self.assertIsNone(result["resource_scenarios"][0]["assumed_total_cost"])

    def test_fixture_paired_diagnostics_are_descriptive_and_replicates_do_not_increase_n(self):
        manifest = plan(tasks=2, replicates=2, phase="pilot")
        rows = [observation(r, success=(r["arm"] == "D" or r["task_id"] == "task-1"))
                for r in manifest["runs"]]
        result = self.invoke(manifest, rows)
        diagnostic = result["paired_diagnostics"]["D-B"]
        self.assertEqual(diagnostic["planned_tasks"], 2)
        self.assertEqual(diagnostic["complete_tasks"], 2)
        self.assertEqual(diagnostic["paired_task_variance"], 0.5)
        self.assertEqual(diagnostic["task_discordance"], {"left_better": 1, "equal": 1, "right_better": 0})
        self.assertFalse(result["real_pilot_estimates_available"])

    def test_incomplete_pairs_are_not_silently_treated_as_measured_pilot_effects(self):
        manifest = plan(tasks=2, replicates=1, phase="pilot")
        rows = [observation(r) for r in manifest["runs"] if r["task_id"] == "task-0"]
        result = self.invoke(manifest, rows)
        diagnostic = result["paired_diagnostics"]["D-B"]
        self.assertEqual(diagnostic["complete_tasks"], 1)
        self.assertEqual(diagnostic["planned_tasks"], 2)
        self.assertIsNone(diagnostic["paired_task_variance"])
        self.assertEqual(diagnostic["status"], "incomplete_pairs")

    def test_non_assumption_scenarios_and_impossible_project_counts_are_rejected(self):
        scenarios = self.scenarios()
        scenarios["kind"] = "pilot_estimate"
        self.assertEqual(self.invoke(plan(), scenarios=scenarios, code=2)["error"]["code"], "assumption_only_scenarios_required")
        scenarios = self.scenarios()
        scenarios["scenarios"][0]["n_projects"] = 17
        self.assertEqual(self.invoke(plan(), scenarios=scenarios, code=2)["error"]["code"], "invalid_resource_scenario")


if __name__ == "__main__":
    unittest.main()
