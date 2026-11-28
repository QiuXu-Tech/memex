"""Synthetic evaluator contracts. No fixture identity represents a human review."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/paper1"))
import annotation as an
import experiment as ex
import taskpack as tp
import report as reporting
from test_paper1_taskpack import fixture
import test_paper1_experiment as experiment_fixtures

SCRIPT = ROOT / "scripts/paper1/score.py"


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "The sealed evaluator scoring entry point is missing")
        self.temp = tempfile.TemporaryDirectory(prefix="p1-score-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.pack = self.root / "package"
        tp.build_package(fixture(), self.pack)
        self.bundle = self.root / "annotation"
        an.prepare(self.pack, self.bundle, assignment_seed="score-fixture-only")
        mapping = tp.read_json(self.bundle / "controller/mapping.json")
        self.reviews = []
        reviewed_at = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        for i, slot in enumerate(mapping["reviews"]):
            packet = self.bundle / "reviewers" / slot["packet_id"]
            record = tp.read_json(packet / "review-template.json")
            obligation = {"obligation_id": "test-current", "kind": "test",
                          "description": "Synthetic current-test requirement.",
                          "expected_behavior": "Execute the fixture check before deciding.",
                          "answerability": "requires_new_observation",
                          "evidence": [{"path": "request.txt", "sha256": file_hash(packet / "material/request.txt"),
                                        "locator": "whole file"}]}
            record.update(reviewer_id=f"fixture-person-{i}", reviewed_at=reviewed_at,
                          human_review_attestation=True, independence_attestation=True,
                          method_outputs_seen=False, decision="accept_design", material_completeness="complete_workflow",
                          critical_obligations=[obligation], gaps=[])
            self.reviews.append(record)
            (self.root / f"review-{i}.json").write_text(json.dumps(record))
        adjudication = tp.read_json(self.bundle / "controller/adjudication-template.json")
        adjudication.update(adjudicator_id="fixture-person-adjudicator", adjudicated_at=reviewed_at,
                            human_review_attestation=True, method_outputs_seen=False,
                            review_sha256=[tp.digest(r) for r in self.reviews], resolution="confirmed_agreement",
                            rationale="Synthetic schema exercise only, not a real human judgment.",
                            decision="accept_design", resolved_obligations=[obligation], remaining_gaps=[])
        (self.root / "adjudication.json").write_text(json.dumps(adjudication))
        runner = self.root / "fixture-runner"
        runner.write_text(f"#!{sys.executable}\nimport json\nfrom pathlib import Path\n"
                          "Path('trace.json').write_text(json.dumps({'fixture_only': True, 'check': 'passed'}))\n"
                          "Path('result.json').write_text(json.dumps({'status':'completed','trace_ref':'trace.json'}))\n")
        runner.chmod(0o700)
        spec = {"schema_version": 1, "study_phase": "development", "tasks": [{
            "task_id": "fixture", "project_id": "fixture-project",
            "public_by_replicate": {"1": str(self.pack / "public")}}], "arms": ["A", "C", "D"],
            "replicates": 1, "seed": 7, "runner": str(runner), "env_allowlist": ["PATH"],
            "budgets": {"max_runs": 3, "max_wall_seconds": 60, "per_run_seconds": 10},
            "measurement": experiment_fixtures.ExperimentTests().measurement()}
        (self.root / "spec.json").write_text(json.dumps(spec))
        self.plan = self.root / "plan"
        self.state = self.root / "state"
        ex.freeze_study(self.root / "spec.json", self.plan)
        frozen = ex.load_frozen(self.plan)
        self.labels = {"schema_version": 1, "data_kind": "fixture", "frozen": True,
                       "frozen_at": datetime.now(timezone.utc).isoformat(),
                       "study_freeze_sha256": ex.digest(frozen["freeze"]), "tasks": [{
            "task_id": "fixture", "project_id": "fixture-project",
            "public_sha256_by_replicate": {"1": ex.public_digest(self.pack / "public")},
            "annotation": {"origin": "fixture", "bundle": "annotation", "reviews": [
                {"path": f"review-{i}.json", "sha256": file_hash(self.root / f"review-{i}.json")} for i in (0, 1)],
                "adjudication": {"path": "adjudication.json", "sha256": file_hash(self.root / "adjudication.json")}},
            "obligations": [{"obligation_id": "test-current", "requires_evidence": True,
                             "behavior_check_ids": ["test-before-decision"]}]}]}
        self.labels_path = self.root / "labels.json"
        self.save_labels()
        ex.dispatch(self.plan, self.state, run=True)
        ex.export_score_inputs(self.plan, self.state, self.root / "sealed.json")
        self.sealed = ex.read_json(self.root / "sealed.json")["runs"]
        self.assessments = []
        for run in self.sealed:
            ref = {"path": "trace.json", "sha256": file_hash(Path(run["output_directory"]) / "trace.json"),
                   "locator": "whole file"}
            self.assessments.append({"schema_version": 1, "data_kind": "fixture",
                **{k: run[k] for k in (*ex.KEY_FIELDS, "run_id", "freeze_sha256", "sealed_run_sha256", "output_sha256")},
                "labels_sha256": file_hash(self.labels_path), "judgment_origin": "fixture",
                "reviewer_id": "fixture-outcome-reviewer", "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "human_review_attestation": False,
                "obligations": [{"obligation_id": "test-current", "decision": "satisfied", "evidence": "supported",
                                 "incorrect_high_impact_affirmative": False, "unnecessary_abstention": False,
                                 "evidence_refs": [ref]}],
                "behavior_checks": [{"check_id": "test-before-decision", "status": "passed", "evidence_refs": [ref]}]})

    def save_labels(self):
        self.labels_path.write_text(json.dumps(self.labels))

    def invoke(self, *, code=0):
        path = self.root / "assessments.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in self.assessments))
        output = self.root / "score-output"
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--plan", str(self.plan),
                                 "--state", str(self.state), "--labels", str(self.labels_path),
                                 "--assessments", str(path), "--output", str(output)], text=True, capture_output=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        if code:
            return json.loads(result.stdout)
        return {"audit": json.loads((output / "score-audit.json").read_text()),
                "quality": [json.loads(s) for s in (output / "quality.jsonl").read_text().splitlines()],
                "components": [json.loads(s) for s in (output / "quality-components.jsonl").read_text().splitlines()]}

    def test_explicit_complete_fixture_scores_join_without_claiming_human_reviews(self):
        result = self.invoke()
        self.assertTrue(all(r["decision_success"] is True for r in result["quality"]))
        self.assertEqual(result["audit"]["completed_human_reviews"], 0)
        self.assertFalse(result["audit"]["human_identity_verified"])
        self.assertFalse(result["audit"]["research_task_accepted"])
        joined = ex.join_results(self.plan, self.state, self.root / "score-output/quality.jsonl", self.root / "joined")
        self.assertEqual(joined["planned_runs"], 3)
        self.assertEqual(joined["complete_cost_runs"], 0)
        reporting.create_report(self.plan / "manifest.json", joined["runs_path"], self.root / "report",
                                data_kind="fixture", score_dir=self.root / "score-output")
        summary = ex.read_json(self.root / "report/summary.json")
        self.assertTrue(all(row["components"]["behavior_success"]["observed_rate"] == 1 for row in summary["arms"]))
        self.assertFalse(summary["scientific_effect_claims_allowed"])

    def test_annotation_of_a_different_public_material_is_rejected(self):
        frozen = ex.load_frozen(self.plan)
        public = self.pack / "public/request.txt"
        public.write_text(public.read_text() + "\nChanged public request after annotation.\n")
        altered = ex.public_digest(self.pack / "public")
        for unit in frozen["schedule"]["units"]:
            unit["public_sha256"] = altered
        self.labels["tasks"][0]["public_sha256_by_replicate"]["1"] = altered
        self.save_labels()
        import score as scoring
        with self.assertRaisesRegex(ex.ContractError, "annotation_material_does_not_match_scheduled_public"):
            scoring.validate_labels(self.labels_path, frozen, {})

    def test_behavior_failure_and_unnecessary_abstention_make_success_false(self):
        self.assessments[0]["behavior_checks"][0]["status"] = "failed"
        self.assessments[1]["obligations"][0]["unnecessary_abstention"] = True
        result = self.invoke()
        self.assertEqual(sum(r["decision_success"] is False for r in result["quality"]), 2)

    def test_missing_assessment_or_unmeasured_behavior_is_unscored_not_failure(self):
        self.assessments.pop()
        self.assessments[0]["behavior_checks"][0]["status"] = "unmeasured"
        self.assessments[0]["behavior_checks"][0]["evidence_refs"] = []
        result = self.invoke()
        self.assertEqual(sum(r["decision_success"] is None for r in result["quality"]), 2)
        joined = ex.join_results(self.plan, self.state, self.root / "score-output/quality.jsonl", self.root / "joined")
        rows = [json.loads(s) for s in Path(joined["runs_path"]).read_text().splitlines()]
        self.assertEqual(sum(r["status"] == "evaluator_error" for r in rows), 2)

    def test_ai_origin_cannot_be_declared_completed_human_judgment(self):
        self.assessments[0]["judgment_origin"] = "ai"
        self.assessments[0]["human_review_attestation"] = True
        self.assertEqual(self.invoke(code=2)["error"]["code"], "judgment_origin_mismatch")

    def test_fixture_annotation_cannot_be_promoted_to_research(self):
        self.labels["data_kind"] = "research"
        self.save_labels()
        self.assertEqual(self.invoke(code=2)["error"]["code"], "annotation_origin_mismatch")

    def test_false_label_freeze_is_rejected(self):
        self.labels["frozen"] = False
        self.save_labels()
        self.assertEqual(self.invoke(code=2)["error"]["code"], "frozen_labels_required")

    def test_post_run_label_freeze_is_rejected(self):
        self.labels["frozen_at"] = datetime.now(timezone.utc).isoformat()
        self.save_labels()
        self.assertEqual(self.invoke(code=2)["error"]["code"], "labels_not_frozen_before_execution")

    def test_duplicate_assessment_is_rejected(self):
        self.assessments.append(copy.deepcopy(self.assessments[0]))
        self.assertEqual(self.invoke(code=2)["error"]["code"], "duplicate_or_unsealed_assessment")

    def test_missing_frozen_behavior_check_is_rejected(self):
        self.assessments[0]["behavior_checks"] = []
        self.assertEqual(self.invoke(code=2)["error"]["code"], "assessment_behavior_set_mismatch")

    def test_score_component_file_tampering_is_rejected_by_report(self):
        self.invoke()
        joined = ex.join_results(self.plan, self.state, self.root / "score-output/quality.jsonl", self.root / "joined")
        target = self.root / "score-output/quality-components.jsonl"
        target.write_text(target.read_text() + "\n")
        with self.assertRaisesRegex(ex.ContractError, "score_artifact_binding_mismatch"):
            reporting.create_report(self.plan / "manifest.json", joined["runs_path"], self.root / "report",
                                    data_kind="fixture", score_dir=self.root / "score-output")

    def test_changed_sealed_output_is_rejected_before_scoring(self):
        (Path(self.sealed[0]["output_directory"]) / "trace.json").write_text("changed")
        self.assertEqual(self.invoke(code=2)["error"]["code"], "sealed_execution_or_output_changed")

    def test_foreign_seal_and_omitted_frozen_obligation_are_rejected(self):
        self.assessments[0]["sealed_run_sha256"] = "0" * 64
        self.assertEqual(self.invoke(code=2)["error"]["code"], "assessment_execution_binding_mismatch")

    def test_omitted_frozen_obligation_cannot_create_success(self):
        self.assessments[0]["obligations"] = []
        self.assertEqual(self.invoke(code=2)["error"]["code"], "assessment_obligation_set_mismatch")

    def test_evidence_must_reference_unchanged_sealed_output(self):
        self.assessments[0]["obligations"][0]["evidence_refs"][0]["path"] = "../result.json"
        self.assertEqual(self.invoke(code=2)["error"]["code"], "unsafe_evaluator_path")


if __name__ == "__main__":
    unittest.main()
