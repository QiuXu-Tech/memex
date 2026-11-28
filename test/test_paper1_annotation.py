"""Synthetic structural reviews test workflow integrity; none are human labels."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/paper1"))
import taskpack as tp
import annotation as an
from test_paper1_taskpack import fixture


class AnnotationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pack = self.root / "package"
        tp.build_package(fixture(), self.pack)
        self.bundle = self.root / "annotation"
        an.prepare(self.pack, self.bundle, assignment_seed="unit-test-only")
        self.mapping = tp.read_json(self.bundle / "controller/mapping.json")
        self.packets = [self.bundle / "reviewers" / r["packet_id"] for r in self.mapping["reviews"]]

    def tearDown(self):
        self.temp.cleanup()

    def complete_review(self, index, reviewer=None, decision="accept_design"):
        packet = self.packets[index]
        value = tp.read_json(packet / "review-template.json")
        ref = "request.txt"
        value.update({
            "reviewer_id": reviewer or f"human-{index + 1}",
            "reviewed_at": "2026-11-28T02:00:00+00:00",
            "human_review_attestation": True,
            "independence_attestation": True,
            "method_outputs_seen": False,
            "decision": decision,
            "material_completeness": "incomplete_workflow",
            "critical_obligations": [{
                "obligation_id": "r1", "kind": "test", "description": "Bind testing to the current artifact.",
                "expected_behavior": "Recheck current state before a simulated action.",
                "answerability": "requires_new_observation",
                "evidence": [{"path": ref, "sha256": hashlib.sha256((packet / "material" / ref).read_bytes()).hexdigest(),
                              "locator": "whole file"}],
            }],
            "gaps": ["No real native-compaction trajectory yet."],
        })
        return value

    def adjudication(self, reviews):
        value = tp.read_json(self.bundle / "controller/adjudication-template.json")
        value.update({
            "adjudicator_id": "human-3", "adjudicated_at": "2026-11-28T03:00:00+00:00",
            "human_review_attestation": True, "method_outputs_seen": False,
            "review_sha256": [tp.digest(r) for r in reviews],
            "resolution": "resolved_disagreement" if reviews[0]["decision"] != reviews[1]["decision"] else "confirmed_agreement",
            "rationale": "Structural test fixture only; real workflow capture is still required.",
            "decision": "revise_design", "resolved_obligations": reviews[0]["critical_obligations"],
            "remaining_gaps": ["Native trajectory missing."],
        })
        return value

    def test_preparation_is_blank_and_contains_no_private_answers_or_arm_outputs(self):
        self.assertEqual(len(self.packets), 2)
        self.assertNotEqual(self.packets[0].name, self.packets[1].name)
        for packet in self.packets:
            review = tp.read_json(packet / "review-template.json")
            self.assertIsNone(review["reviewer_id"])
            self.assertIsNone(review["critical_obligations"])
            content = b"".join(p.read_bytes() for p in packet.rglob("*") if p.is_file())
            self.assertNotIn(b"PRIVATE-ANSWER-5ae9", content)
            self.assertNotIn(b"source_fix_commit", content)
            self.assertNotIn(b'"arm":', content)

    def test_unfilled_templates_are_not_independent_human_reviews(self):
        blank = tp.read_json(self.packets[0] / "review-template.json")
        with self.assertRaisesRegex(tp.ContractError, "review_incomplete"):
            an.validate_review(blank, self.packets[0])

    def test_completed_review_is_bound_to_blinded_packet(self):
        result = an.validate_review(self.complete_review(0), self.packets[0])
        self.assertTrue(result["structurally_complete"])
        self.assertFalse(result["human_identity_verified"])
        value = self.complete_review(0)
        value["packet_id"] = "different-packet"
        with self.assertRaisesRegex(tp.ContractError, "review_packet_mismatch"):
            an.validate_review(value, self.packets[0])

    def test_review_requires_positive_human_and_independence_attestations(self):
        for field, value in (("human_review_attestation", False), ("independence_attestation", False), ("method_outputs_seen", True)):
            review = self.complete_review(0)
            review[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(tp.ContractError, "review_attestation_required"):
                an.validate_review(review, self.packets[0])

    def test_evidence_reference_cannot_escape_public_material(self):
        review = self.complete_review(0)
        review["critical_obligations"][0]["evidence"][0]["path"] = "../../controller/mapping.json"
        with self.assertRaisesRegex(tp.ContractError, "unsafe_relative_path"):
            an.validate_review(review, self.packets[0])

    def test_evidence_hash_mismatch_is_rejected(self):
        review = self.complete_review(0)
        review["critical_obligations"][0]["evidence"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(tp.ContractError, "annotation_evidence_hash_mismatch"):
            an.validate_review(review, self.packets[0])

    def test_post_assignment_material_mutation_is_rejected(self):
        review = self.complete_review(0)
        (self.packets[0] / "material/request.txt").write_text("changed after assignment")
        with self.assertRaisesRegex(tp.ContractError, "annotation_material_mismatch"):
            an.validate_review(review, self.packets[0])

    def test_two_reviews_from_same_identity_cannot_satisfy_double_review(self):
        reviews = [self.complete_review(0, "same-human"), self.complete_review(1, "same-human")]
        with self.assertRaisesRegex(tp.ContractError, "distinct_reviewers_required"):
            an.validate_pair(self.bundle, reviews, self.adjudication(reviews))

    def test_all_pairs_require_an_explicit_adjudication(self):
        reviews = [self.complete_review(0), self.complete_review(1)]
        with self.assertRaisesRegex(tp.ContractError, "adjudication_required"):
            an.validate_pair(self.bundle, reviews, None)

    def test_changed_review_requires_a_new_adjudication_binding(self):
        reviews = [self.complete_review(0), self.complete_review(1)]
        adj = self.adjudication(reviews)
        reviews[0]["gaps"].append("new gap")
        with self.assertRaisesRegex(tp.ContractError, "adjudication_review_hash_mismatch"):
            an.validate_pair(self.bundle, reviews, adj)

    def test_adjudicator_is_a_third_identity(self):
        reviews = [self.complete_review(0), self.complete_review(1)]
        adj = self.adjudication(reviews)
        adj["adjudicator_id"] = reviews[0]["reviewer_id"]
        with self.assertRaisesRegex(tp.ContractError, "independent_adjudicator_required"):
            an.validate_pair(self.bundle, reviews, adj)

    def test_disagreement_cannot_be_silently_marked_agreement(self):
        reviews = [self.complete_review(0), self.complete_review(1, decision="insufficient_material")]
        adj = self.adjudication(reviews)
        adj["resolution"] = "confirmed_agreement"
        with self.assertRaisesRegex(tp.ContractError, "disagreement_requires_resolution"):
            an.validate_pair(self.bundle, reviews, adj)

    def test_structurally_complete_reviews_never_self_certify_p1_acceptance(self):
        reviews = [self.complete_review(0), self.complete_review(1)]
        result = an.validate_pair(self.bundle, reviews, self.adjudication(reviews))
        self.assertTrue(result["structurally_complete"])
        self.assertEqual(result["independent_review_records"], 2)
        self.assertFalse(result["human_identity_verified"])
        self.assertFalse(result["research_task_accepted"])
        self.assertFalse(result["frozen"])

    def test_arm_score_fields_cannot_be_smuggled_into_a_blinded_review(self):
        review = self.complete_review(0)
        review["arm"] = "D"
        with self.assertRaisesRegex(tp.ContractError, "unexpected_fields"):
            an.validate_review(review, self.packets[0])


if __name__ == "__main__":
    unittest.main()
