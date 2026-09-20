from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path


from test_paper_pipeline import build_paper_ready_project
from workflow_fixtures import build_valid_project, write_json

from build_independent_review_package import build as build_review_package
from paper_visible_text_check import inspect_text
from workflow_checks import check_project


class ReviewAndVisibleTextTests(unittest.TestCase):
    def test_same_context_review_cannot_pass_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            path = root / "validation" / "INDEPENDENT_REVIEW_RESULT.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["reviewer_context"].update(
                {
                    "reviewer_kind": "same_context_model",
                    "different_conversation": False,
                    "independence_grade": "correlated_self_review",
                }
            )
            write_json(root, "validation/INDEPENDENT_REVIEW_RESULT.json", data)
            findings, _ = check_project(root, "validation")
            self.assertIn("IREVIEW-E009", {item.rule_id for item in findings})

    def test_missing_delivery_role_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            path = root / "delivery" / "DELIVERY_MANIFEST.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            del data["deliverables"]["computation_source"]
            write_json(root, "delivery/DELIVERY_MANIFEST.json", data)
            findings, _ = check_project(root, "delivery")
            self.assertIn("DELIVERY-E015", {item.rule_id for item in findings})

    def test_missing_user_material_blocks_without_network_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            path = root / "delivery" / "DELIVERY_MANIFEST.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["source_policy"]["missing_user_materials"] = ["current official format rules"]
            write_json(root, "delivery/DELIVERY_MANIFEST.json", data)
            findings, _ = check_project(root, "delivery")
            self.assertIn("DELIVERY-E014", {item.rule_id for item in findings})

    def test_internal_ids_and_workflow_states_are_visible_text_errors(self):
        blocking, flags = inspect_text("validation 门禁将 CLM-Q1-001 标记为 supported_not_reproduced。")
        self.assertGreaterEqual(len(blocking), 3)
        self.assertEqual(flags, [])

    def test_number_dense_sentence_and_excess_precision_require_review(self):
        blocking, flags = inspect_text("结果依次为 1.123456789、2.1、3.2、4.3、5.4、6.5。")
        self.assertEqual(blocking, [])
        self.assertEqual({item["rule_id"] for item in flags}, {"PAPER-TEXT-W001", "PAPER-TEXT-W002"})

    def test_template_has_no_default_table_of_contents(self):
        template = Path(__file__).resolve().parents[1] / ".agents" / "skills" / "cumcm-workflow" / "assets" / "latex-template" / "generic-ctex" / "main.tex.tmpl"
        self.assertNotIn(r"\tableofcontents", template.read_text(encoding="utf-8"))

    def test_review_package_contains_user_routable_skill(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            package = root / "validation" / "independent-review-package"
            shutil.rmtree(package)
            (root / "validation" / "INDEPENDENT_REVIEW_RESULT.json").unlink()
            (root / "validation" / "INDEPENDENT_REVIEW_RAW.md").unlink()
            (root / "model" / "VALIDATION_PLAN.md").write_text("# Validation plan\n", encoding="utf-8")
            manifest_path = build_review_package(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertTrue((root / manifest["review_skill_path"]).is_file())
            self.assertEqual(sorted(manifest["context_excluded"]), ["debug_history", "failed_runs", "originating_task_transcript", "prior_review_prose"])
            self.assertEqual(manifest["reviewer_selection"]["status"], "unreviewed")

    def test_refresh_archives_existing_review_package_under_its_own_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            old_manifest_path = root / "validation/independent-review-package/REVIEW_PACKAGE_MANIFEST.json"
            old_digest = json.loads(old_manifest_path.read_text(encoding="utf-8"))["package_digest"]
            new_manifest_path = build_review_package(root, refresh=True)
            new_digest = json.loads(new_manifest_path.read_text(encoding="utf-8"))["package_digest"]
            self.assertNotEqual(old_digest, new_digest)
            self.assertTrue((root / "validation/review-archive" / f"package-{old_digest[:12]}").is_dir())
            self.assertFalse((root / "validation/review-archive" / f"package-{new_digest[:12]}").exists())


if __name__ == "__main__":
    unittest.main()
