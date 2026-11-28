"""Integrity tests use fabricated fixtures, never P1 effect observations."""

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/paper1"))
import taskpack as tp


def fixture(task="d-01", family="D01"):
    return {
        "schema_version": 1,
        "task_id": task,
        "project_id": "synthetic/fixture-suite",
        "workflow_family_id": family,
        "kind": "synthetic_fixture",
        "request": "Review the local build and record a simulated review decision.",
        "budget": {
            "schema_version": 1, "frozen": False, "scope": "continuation_per_arm",
            "reader_model": None, "tokenizer": None,
            "max_initial_context_bytes": 12000,
            "max_source_open_bytes_total": 50000,
            "max_source_open_bytes_per_call": 4000,
            "max_source_open_calls": 20, "max_tool_calls": 30,
            "max_model_input_tokens": 32000, "max_model_output_tokens": 4000,
            "max_wall_seconds": 180,
        },
        "public_files": {
            "workspace/artifact.json": '{"version":"v2"}\n',
            "archive.jsonl": json.dumps({
                "event_id": "event-17", "sequence": 1, "native_role": "tool",
                "principal": "local-test-runner", "source_name": "run.log",
                "body": "Synthetic fixture: earlier build v1 passed one assertion.",
                "capture_kind": "synthetic_fixture",
            }) + "\n",
        },
        "source": None,
        "controller": {"slot": family, "variant": "changed"},
        "evaluator": {"status": "draft_unreviewed", "proposed_obligations": ["Bind tests to the final artifact."],
                      "human_reviews": [], "adjudication": None},
        "forbidden_public_literals": ["PRIVATE-ANSWER-5ae9"],
    }


class TaskPackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def build(self, spec=None, name="pack"):
        output = self.root / name
        tp.build_package(spec or fixture(), output)
        return output

    def test_identical_inputs_produce_identical_manifest_and_public_hash(self):
        a = self.build(name="a")
        b = self.build(name="b")
        self.assertEqual((a / "manifest.json").read_bytes(), (b / "manifest.json").read_bytes())
        self.assertEqual(tp.validate_package(a)["public_sha256"], tp.validate_package(b)["public_sha256"])

    def test_prepared_material_never_claims_workflow_accepted_or_human_reviewed(self):
        result = tp.validate_package(self.build())
        self.assertFalse(result["acceptance"]["accepted"])
        self.assertFalse(result["acceptance"]["frozen"])
        self.assertEqual(result["acceptance"]["independent_human_reviews"], 0)
        self.assertIn("native_compaction_receipt_missing", result["acceptance"]["blocking_gates"])
        self.assertEqual(result["model_requests"], 0)

    def test_cannot_inject_private_top_level_fields_into_public_metadata(self):
        spec = fixture()
        spec["public_files"]["task.json"] = '{"claims":["PRIVATE-ANSWER-5ae9"]}'
        with self.assertRaisesRegex(tp.ContractError, "public_file_not_allowlisted"):
            self.build(spec)

    def test_gold_needle_in_public_body_is_rejected(self):
        spec = fixture()
        spec["request"] += " PRIVATE-ANSWER-5ae9"
        with self.assertRaisesRegex(tp.ContractError, "forbidden_public_literal"):
            self.build(spec)
        self.assertFalse((self.root / "pack").exists())

    def test_public_archive_does_not_accept_evaluator_claim_fields(self):
        spec = fixture()
        event = json.loads(spec["public_files"]["archive.jsonl"])
        event["supports_claim"] = True
        spec["public_files"]["archive.jsonl"] = json.dumps(event) + "\n"
        with self.assertRaisesRegex(tp.ContractError, "invalid_archive_fields"):
            self.build(spec)

    def test_workspace_json_cannot_smuggle_an_answer_key(self):
        spec = fixture()
        spec["public_files"]["workspace/metadata.json"] = '{"nested":{"gold_claims":["use event-17"]}}'
        with self.assertRaisesRegex(tp.ContractError, "evaluator_field_in_public_json"):
            self.build(spec)

    def test_public_archive_rejects_private_nested_fields_and_structured_metadata(self):
        event = json.loads(fixture()["public_files"]["archive.jsonl"])
        for value, reason in [({"gold": "hold"}, "evaluator_field"), ({"untyped": "hold"}, "invalid_archive_metadata")]:
            with self.subTest(value=value), self.assertRaisesRegex(tp.ContractError, reason):
                tp.validate_archive(json.dumps({**event, "completion": value}))

    def test_synthetic_archive_cannot_claim_native_capture(self):
        spec = fixture()
        spec["public_files"]["archive.jsonl"] = spec["public_files"]["archive.jsonl"].replace("synthetic_fixture", "native_capture")
        with self.assertRaisesRegex(tp.ContractError, "synthetic_capture_kind_required"):
            self.build(spec)

    def test_traversal_and_secret_paths_are_rejected(self):
        for path in ("workspace/../../gold.json", "workspace/.env", "workspace/.git/config", "workspace/evaluator/key.json"):
            with self.subTest(path=path):
                spec = fixture()
                spec["public_files"][path] = "secret"
                with self.assertRaises(tp.ContractError):
                    self.build(spec)

    def test_unexpected_file_is_not_silently_left_in_public_export(self):
        pack = self.build()
        (pack / "public/extra.txt").write_text("untracked addition")
        with self.assertRaisesRegex(tp.ContractError, "public_inventory_mismatch"):
            tp.validate_package(pack)

    def test_public_byte_mutation_is_detected(self):
        pack = self.build()
        (pack / "public/request.txt").write_text("modified")
        with self.assertRaisesRegex(tp.ContractError, "public_inventory_mismatch"):
            tp.validate_package(pack)

    def test_public_symlink_and_hardlink_are_rejected(self):
        for link in ("symlink", "hardlink"):
            with self.subTest(link=link):
                pack = self.build(name=link)
                path = pack / "public/request.txt"
                path.unlink()
                secret = self.root / (link + "-secret")
                secret.write_text("private")
                if link == "symlink":
                    path.symlink_to(secret)
                else:
                    os.link(secret, path)
                with self.assertRaisesRegex(tp.ContractError, "unsafe_public_file"):
                    tp.validate_package(pack)

    def test_budget_limits_are_consistent_and_initial_context_is_bounded(self):
        spec = fixture()
        spec["budget"]["max_source_open_bytes_per_call"] = 50001
        with self.assertRaisesRegex(tp.ContractError, "source_page_exceeds_total_budget"):
            self.build(spec)
        spec = fixture()
        spec["budget"]["max_initial_context_bytes"] = 10
        with self.assertRaisesRegex(tp.ContractError, "initial_context_budget_exceeded"):
            self.build(spec)

    def test_public_export_contains_only_verified_public_material(self):
        pack = self.build()
        out = self.root / "detached-public"
        result = tp.export_public(pack, out)
        self.assertEqual(result["public_sha256"], tp.validate_package(pack)["public_sha256"])
        self.assertFalse((out / "evaluator").exists())
        self.assertFalse((out / "manifest.json").exists())
        self.assertNotIn(b"PRIVATE-ANSWER-5ae9", b"".join(p.read_bytes() for p in out.rglob("*") if p.is_file()))

    def test_draft_plan_pairs_identical_public_inputs_without_executing(self):
        pack = self.build()
        result = tp.draft_plan([pack], ["A", "B", "C", "D"], 2)
        self.assertEqual(result["planned_units"], 8)
        self.assertEqual(result["model_requests"], 0)
        self.assertFalse(result["frozen"])
        self.assertEqual(result["accepted_p1_task_count"], 0)
        tasks = result["experiment_spec_fragment"]["tasks"]
        self.assertEqual(tasks[0]["public_by_replicate"]["1"], tasks[0]["public_by_replicate"]["2"])
        self.assertEqual(len({u["public_sha256"] for u in result["units"]}), 1)

    def test_draft_plan_uses_experiment_freezer_public_hash_algorithm(self):
        import experiment
        pack = self.build()
        result = tp.draft_plan([pack], ["A", "B"], 1)
        self.assertEqual(result["units"][0]["public_sha256"], experiment.public_digest(pack / "public"))
        self.assertEqual(result["units"][0]["taskpack_public_sha256"], tp.validate_package(pack)["public_sha256"])

    def test_draft_plan_rejects_pseudo_independent_counterfactual_variants(self):
        a = self.build(name="a")
        b = self.build(fixture("d-01-unchanged", "D01"), name="b")
        with self.assertRaisesRegex(tp.ContractError, "duplicate_workflow_family"):
            tp.draft_plan([a, b], ["A", "B"], 1)

    def test_draft_plan_rejects_different_shared_budget_contracts(self):
        a = self.build(name="a")
        spec = fixture("d-02", "D02")
        spec["budget"]["max_tool_calls"] += 1
        b = self.build(spec, name="b")
        with self.assertRaisesRegex(tp.ContractError, "budget_contract_mismatch"):
            tp.draft_plan([a, b], ["A", "B"], 1)

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaisesRegex(tp.ContractError, "duplicate_json_property"):
            tp.strict_json('{"request":"ok","request":"hidden"}')

    def test_collection_cannot_relabel_another_base_as_source_qualified(self):
        path = ROOT / "docs/research/p1-evidence-verification/tasks/workflows/materialize.py"
        loader = importlib.util.spec_from_file_location("p1_materialize_for_test", path)
        materialize = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(materialize)
        acquired = tp.read_json(ROOT / "docs/research/p1-evidence-verification/tasks/acquisition/candidate-manifest.json")
        candidate = copy.deepcopy(next(x for x in acquired["candidates"] if x["candidate_id"] == "pallets__flask-5014"))
        candidate["upstream"]["base_commit"] = "0" * 40
        with self.assertRaisesRegex(tp.ContractError, "source_qualification_binding_mismatch"):
            materialize.source_spec(candidate, "w-101", "Investigate empty names.", ["src/*", "LICENSE.rst"], ["LICENSE.rst"])

    def git(self, repo, *args):
        env = {"PATH": os.environ["PATH"], "LANG": "C.UTF-8", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
        return subprocess.check_output(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *args], env=env, stderr=subprocess.DEVNULL).decode().strip()

    def repository(self):
        repo = self.root / "source-repo"
        repo.mkdir()
        self.git(repo, "init", "-q")
        (repo / "module.py").write_text("answer = 'base'\n")
        (repo / "LICENSE").write_text("Synthetic fixture license notice, not upstream evidence.\n")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-qm", "base")
        base = self.git(repo, "rev-parse", "HEAD")
        (repo / "module.py").write_text("answer = 'future-secret-fix'\n")
        (repo / "hidden-regression.py").write_text("future test")
        self.git(repo, "add", ".")
        self.git(repo, "commit", "-qm", "future")
        fix = self.git(repo, "rev-parse", "HEAD")
        return repo, base, fix

    def source_spec(self, base, fix):
        spec = fixture("w-101", "source-family-1")
        spec["kind"] = "real_source_seed"
        spec["public_files"] = {}
        spec["source"] = {"repository_url": "https://example.invalid/fixture", "base_commit": base,
                          "include": ["*.py", "LICENSE"], "required_notices": ["LICENSE"]}
        spec["evaluator"]["source_fix_commit"] = fix
        spec["forbidden_public_literals"].append(fix)
        return spec

    def test_source_export_uses_exact_base_and_never_dirty_tree_or_future_git(self):
        repo, base, fix = self.repository()
        spec = self.source_spec(base, fix)
        pack = self.root / "source-pack"
        tp.build_package(spec, pack, source_repo=repo)
        self.assertEqual((pack / "public/workspace/module.py").read_text(), "answer = 'base'\n")
        self.assertFalse((pack / "public/workspace/hidden-regression.py").exists())
        self.assertFalse((pack / "public/workspace/.git").exists())
        self.assertFalse((pack / "public/archive.jsonl").exists())
        self.assertEqual(tp.validate_package(pack)["acceptance"]["accepted"], False)

    def test_source_export_cannot_overlay_gold_test_or_patch_on_base(self):
        repo, base, fix = self.repository()
        spec = self.source_spec(base, fix)
        spec["public_files"]["workspace/hidden-regression.py"] = "gold test"
        with self.assertRaisesRegex(tp.ContractError, "source_seed_overlay_forbidden"):
            tp.build_package(spec, self.root / "pack", source_repo=repo)

    def test_future_fix_identifier_is_guarded_even_if_author_forgets_explicit_needle(self):
        repo, base, fix = self.repository()
        spec = self.source_spec(base, fix)
        spec["forbidden_public_literals"] = []
        spec["request"] += " Look at " + fix
        with self.assertRaisesRegex(tp.ContractError, "forbidden_public_literal"):
            tp.build_package(spec, self.root / "pack", source_repo=repo)

    def test_missing_required_license_notice_blocks_export(self):
        repo, base, fix = self.repository()
        spec = self.source_spec(base, fix)
        spec["source"]["include"] = ["*.py"]
        with self.assertRaisesRegex(tp.ContractError, "required_notice_not_exported"):
            tp.build_package(spec, self.root / "pack", source_repo=repo)

    def test_declared_dotenv_fixture_exclusion_is_explicit_and_recorded(self):
        repo, base, fix = self.repository()
        self.git(repo, "checkout", "--detach", base)
        (repo / ".env").write_text("SYNTHETIC_FIXTURE=1\n")
        self.git(repo, "add", ".env")
        self.git(repo, "commit", "-qm", "dotenv fixture")
        spec = self.source_spec(self.git(repo, "rev-parse", "HEAD"), fix)
        spec["source"]["include"] = ["*"]
        spec["source"]["exclude"] = [".env"]
        pack = self.root / "pack"
        tp.build_package(spec, pack, source_repo=repo)
        self.assertFalse((pack / "public/workspace/.env").exists())
        receipt = tp.read_json(pack / "controller/source-export.json")
        self.assertEqual(receipt["excluded_files"][0]["path"], ".env")
        self.assertEqual(receipt["excluded_files"][0]["reason"], "explicit_source_exclusion")

    def test_included_git_symlink_is_rejected(self):
        repo, base, fix = self.repository()
        self.git(repo, "checkout", "--detach", base)
        (repo / "unsafe.py").symlink_to("/etc/passwd")
        self.git(repo, "add", "unsafe.py")
        self.git(repo, "commit", "-qm", "symlink fixture")
        spec = self.source_spec(self.git(repo, "rev-parse", "HEAD"), fix)
        with self.assertRaisesRegex(tp.ContractError, "source_tree_not_regular"):
            tp.build_package(spec, self.root / "pack", source_repo=repo)


if __name__ == "__main__":
    unittest.main()
