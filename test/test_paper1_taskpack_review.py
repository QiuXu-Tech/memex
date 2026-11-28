"""Development assurance tests: fixture evidence is never human or study data."""
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
import taskpack
import taskpack_review as review
from test_paper1_taskpack import fixture


class TaskpackReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def package(self):
        target = self.root / "pack"
        taskpack.build_package(fixture(), target)
        return target

    def draft(self, package):
        source = package / "public/request.txt"
        ref = review.evidence_ref(package / "public", "request.txt", 0, len(source.read_bytes()))
        return {"schema_version": "p1-assisted-task-review-2", "origin": "ai_assisted",
                "phase": "development", "status": "unfrozen_draft", "human_review_attestation": False,
                "independent_human_review_count": 0, "method_outputs_used": False,
                "ai_reviewer": "ChatGPT", "prepared_at": "2026-11-28T00:00:00+00:00",
                "exposure_disclosure": "Authoring assistant has seen prior design; not an independent blind review.",
                "tasks": [{"task_id": "d-01", "public_sha256": taskpack.validate_package(package)["public_sha256"],
                           "obligations": [{"obligation_id": "artifact", "kind": "artifact",
                               "description": "Review the current artifact.", "expected_behavior": "Bind observations to current bytes.",
                               "answerability": "requires_new_observation", "evidence": [ref],
                               "oracle_ids": ["current_artifact_test_binding"]}],
                           "remaining_gaps": ["Actual workflow is not observed."]}]}

    def test_inspection_is_read_only_and_never_accepts_a_research_task(self):
        package = self.package()
        before = taskpack.digest(taskpack.inventory(package / "public"))
        with mock.patch("subprocess.Popen", side_effect=AssertionError("no process")), \
             mock.patch("socket.socket", side_effect=AssertionError("no network")):
            result = review.inspect_package(package, repository_root=self.root)
        self.assertEqual(result["independent_human_review_count"], 0)
        self.assertEqual(result["model_requests"], 0)
        self.assertFalse(result["research_task_accepted"])
        self.assertTrue(result["material_integrity_verified"])
        self.assertEqual(result["workflow_outcome"], "NOT_MEASURED")
        self.assertEqual(before, taskpack.digest(taskpack.inventory(package / "public")))

    def test_draft_has_exact_bound_public_evidence_and_no_human_attestation(self):
        package = self.package()
        result = review.validate_drafts(self.draft(package), {"d-01": package})
        self.assertEqual(set(result), {"d-01"})
        for key, value in [("origin", "human"), ("human_review_attestation", True),
                           ("method_outputs_used", True), ("phase", "confirmatory"),
                           ("independent_human_review_count", 2)]:
            bad = self.draft(package); bad[key] = value
            with self.subTest(key=key), self.assertRaises(taskpack.ContractError):
                review.validate_drafts(bad, {"d-01": package})

    def test_ai_draft_cannot_use_missing_span_or_private_method_output_as_basis(self):
        package = self.package()
        for path in ["../evaluator/blueprint.json", "evaluator/blueprint.json", "output/final.json"]:
            bad = self.draft(package)
            bad["tasks"][0]["obligations"][0]["evidence"][0]["path"] = path
            with self.subTest(path=path), self.assertRaises(taskpack.ContractError):
                review.validate_drafts(bad, {"d-01": package})
        for field, value in [("sha256", "0" * 64), ("start_byte", -1), ("end_byte", 99999),
                             ("span_sha256", "0" * 64)]:
            bad = self.draft(package)
            bad["tasks"][0]["obligations"][0]["evidence"][0][field] = value
            with self.subTest(field=field), self.assertRaises(taskpack.ContractError):
                review.validate_drafts(bad, {"d-01": package})

    def test_complete_catalog_coverage_and_nonempty_obligations_are_required(self):
        package = self.package()
        for change in [lambda d: d.update(tasks=[]),
                       lambda d: d["tasks"][0].update(obligations=[]),
                       lambda d: d["tasks"].append(copy.deepcopy(d["tasks"][0])),
                       lambda d: d["tasks"][0]["obligations"][0].update(oracle_ids=["always_pass"])]:
            bad = self.draft(package); change(bad)
            with self.assertRaises(taskpack.ContractError):
                review.validate_drafts(bad, {"d-01": package})

    def test_junit_recounts_cases_and_does_not_trust_suite_pass_claim(self):
        path = self.root / "results.xml"
        path.write_text('<testsuite tests="2" failures="1" errors="0" skipped="0">'
                        '<testcase classname="a" name="one"/><testcase classname="a" name="two">'
                        '<failure message="fixture"/></testcase></testsuite>')
        self.assertEqual(review.junit_counts(path), {"tests": 2, "passed": 1, "failures": 1, "errors": 0, "skipped": 0})
        path.write_text(path.read_text().replace('failures="1"', 'failures="0"'))
        with self.assertRaisesRegex(taskpack.ContractError, "junit_declared_counts_mismatch"):
            review.junit_counts(path)

    def test_empty_duplicate_and_entity_xml_are_not_observed_passing_tests(self):
        path = self.root / "results.xml"
        for text in ['<testsuite tests="0"/>',
                     '<testsuite><testcase name="a"/><testcase name="a"/></testsuite>',
                     '<!DOCTYPE x [<!ENTITY a "value">]><testsuite><testcase name="&a;"/></testsuite>']:
            path.write_text(text)
            with self.subTest(text=text), self.assertRaises(taskpack.ContractError):
                review.junit_counts(path)

    def test_actual_source_seed_receipts_are_recomputed_but_not_method_scores(self):
        base = ROOT / "docs/research/p1-evidence-verification/tasks/workflows/packages"
        for task, cases, failures in [("w-101", 60, 1), ("w-102", 214, 2)]:
            with self.subTest(task=task):
                result = review.inspect_package(base / task, repository_root=ROOT)
                source = result["source_qualification"]
                self.assertEqual(source["junit_recomputed"]["base"]["tests"], cases)
                self.assertEqual(source["junit_recomputed"]["base"]["failures"], failures)
                self.assertEqual(source["junit_recomputed"]["fixed"]["failures"], 0)
                self.assertFalse(source["new_source_execution"])
                self.assertFalse(result["research_task_accepted"])

    def test_synthetic_facts_are_computed_without_promoting_archive_to_live_tests(self):
        base = ROOT / "docs/research/p1-evidence-verification/tasks/workflows/packages"
        changed = review.inspect_package(base / "d-201", repository_root=ROOT)["material_facts"]
        unchanged = review.inspect_package(base / "d-201-unchanged", repository_root=ROOT)["material_facts"]
        self.assertFalse(changed["artifact_bindings"][0]["matches_current_bytes"])
        self.assertTrue(unchanged["artifact_bindings"][0]["matches_current_bytes"])
        self.assertEqual(changed["evidence_domain"], "synthetic_fixture_content_only")
        self.assertIsNone(changed["actual_test_execution"])

    def test_revocation_scope_and_revision_conflict_rules(self):
        base = ROOT / "docs/research/p1-evidence-verification/tasks/workflows/packages"
        revoked = review.inspect_package(base / "d-204", repository_root=ROOT)["material_facts"]
        forged = review.inspect_package(base / "d-205", repository_root=ROOT)["material_facts"]
        conflict = review.inspect_package(base / "d-206", repository_root=ROOT)["material_facts"]
        self.assertEqual(revoked["authorization"]["status"], "withdrawn")
        self.assertEqual(forged["authorization"]["status"], "no_matching_native_grant")
        self.assertEqual(conflict["revision_conflict"]["status"], "conflict_at_latest_revision")
        self.assertIsNone(conflict["revision_conflict"]["resolved_value"])

    def test_long_fixture_log_and_empty_cancelled_tests_stay_content_observations(self):
        base = ROOT / "docs/research/p1-evidence-verification/tasks/workflows/packages"
        a = review.inspect_package(base / "d-202", repository_root=ROOT)["material_facts"]
        b = review.inspect_package(base / "d-207", repository_root=ROOT)["material_facts"]
        self.assertTrue(any(x["completion"] == "cancelled" for x in a["test_records"]))
        self.assertTrue(any(x["assertions_reported_in_text"] == 0 for x in a["test_records"]))
        long_record = next(x for x in b["test_records"] if x["source_name"] == "transport-long.log")
        self.assertGreater(long_record["body_bytes"], 4000)
        self.assertEqual(long_record["assertions_reported_in_text"], 330)
        self.assertIsNone(long_record["actual_test_passed"])

    def test_blank_legacy_review_audit_never_converts_a_filled_template_to_zero(self):
        import annotation
        package = self.package()
        bundle = self.root / "assignment"
        annotation.prepare(package, bundle, assignment_seed="fixture-blank-assignment")
        public_hash = taskpack.validate_package(package)["public_sha256"]
        checked = review.inspect_blank_assignment(bundle, public_hash)
        self.assertEqual(checked["blank_review_templates_verified"], 2)
        template = next((bundle / "reviewers").glob("*/review-template.json"))
        row = json.loads(template.read_text()); row["reviewer_id"] = "fixture-unverified-person"
        template.write_text(json.dumps(row))
        with self.assertRaisesRegex(taskpack.ContractError, "separate_accounting"):
            review.inspect_blank_assignment(bundle, public_hash)

    def test_delayed_old_grant_cannot_restore_a_revoked_fixture_permission(self):
        base = ROOT / "docs/research/p1-evidence-verification/tasks/workflows/packages/d-204/public"
        events = [json.loads(line) for line in (base / "archive.jsonl").read_text().splitlines()]
        delayed = copy.deepcopy(events[0]); delayed.update(sequence=4, event_id="fixture-delayed-grant")
        state = review._fixture_authorization(events + [delayed], base)
        self.assertEqual(state["status"], "unknown_nonmonotone_or_duplicate_native_revision")
        self.assertIsNone(state["real_world_authorization"])


if __name__ == "__main__":
    unittest.main()
