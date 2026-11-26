"""Delegated decisions require scoped authority and current review evidence."""
import json
import tempfile
import unittest
from pathlib import Path

from paper_fixtures import build_paper_ready_project
from recorder_fixtures import make_project, model_with_candidates, run_script
from workflow_checks import require_human_checkpoint


class DelegatedCheckpoints(unittest.TestCase):
    def grant(self, root, stage, ref="user-turn"):
        return run_script("record_delegation.py", "--project", str(root), "--stage", stage,
                          "--user-turn-ref", ref)

    def decide(self, root, stage, ref="user-turn", *extra):
        return run_script("record_decision.py", "--project", str(root), "--stage", stage,
                          "--decision", "accepted", "--delegated", "--reviewer", "lead-agent",
                          "--task-turn-ref", ref, "--summary", "Reviewed current material", *extra)

    def paper_project(self, root):
        build_paper_ready_project(root)
        pages = root / ".cumcm/tmp/pages"
        pages.mkdir(parents=True, exist_ok=True)
        # Synthetic fixture for the recorded page raster; the production recorder uses pdftoppm.
        (pages / "page-1.png").write_bytes(b"\x89PNG\r\n\x1a\nsynthetic")

    def test_model_delegation_is_stage_scoped_and_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_project(Path(temp))
            model_with_candidates(root, ["selected"])
            self.assertNotEqual(self.decide(root, "model-design").returncode, 0)
            self.assertEqual(self.grant(root, "model-design").returncode, 0)
            done = self.decide(root, "model-design")
            self.assertEqual(done.returncode, 0, done.stderr)
            require_human_checkpoint(root, "model-design")
            check = json.loads((root / "model/MODEL_CONTRACT.json").read_text())["selection_check"]
            self.assertEqual((check["reviewer_kind"], check["reviewer"]), ("lead_agent", "lead-agent"))
            with self.assertRaises(ValueError):
                require_human_checkpoint(root, "validation")
            (root / ".cumcm/delegations/model-design.json").unlink()
            with self.assertRaises(ValueError):
                require_human_checkpoint(root, "model-design")

    def test_revoke_changes_future_owner_and_preserves_accepted_decision(self):
        from project_status import inspect_project
        with tempfile.TemporaryDirectory() as temp:
            root = make_project(Path(temp))
            model_with_candidates(root, ["selected"])
            for stage in ("model-design", "validation", "delivery"):
                self.assertEqual(self.grant(root, stage).returncode, 0)
            self.assertEqual(self.decide(root, "model-design").returncode, 0)
            action = ("--project", str(root), "--stage", "model-design", "--revoke",
                      "--user-turn-ref", "take-it-back")
            for _ in range(2):
                result = run_script("record_delegation.py", *action)
                self.assertEqual(result.returncode, 0, result.stderr)
            owners = inspect_project(root)["decision_owners"]
            self.assertEqual(owners, {"model-design": "human_user", "validation": "delegated_lead_agent",
                                      "delivery": "delegated_lead_agent"})
            require_human_checkpoint(root, "model-design")
            self.assertNotEqual(self.decide(root, "model-design").returncode, 0)
            self.assertNotEqual(self.grant(root, "model-design").returncode, 0)
            self.assertEqual(self.grant(root, "model-design", "fresh-grant").returncode, 0)
            require_human_checkpoint(root, "model-design")
            self.assertEqual(self.decide(root, "model-design", "fresh-grant").returncode, 0)
            require_human_checkpoint(root, "model-design")

    def test_validation_requires_current_independent_review_and_retains_default_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.paper_project(root)
            self.assertEqual(self.grant(root, "validation").returncode, 0)
            review = root / "validation/INDEPENDENT_REVIEW_RESULT.json"
            original = review.read_bytes()
            review.unlink()
            self.assertNotEqual(self.decide(root, "validation", "user-turn", "--scope", "validation/CLAIM_LEDGER.json").returncode, 0)
            review.write_bytes(original)
            data = json.loads(original)
            data["reviewer_context"]["different_conversation"] = False
            review.write_text(json.dumps(data))
            self.assertNotEqual(self.decide(root, "validation").returncode, 0)
            review.write_bytes(original)
            request = root / "validation/independent-review-package/REVIEW_REQUEST.md"
            request_original = request.read_bytes()
            request.write_bytes(request_original + b"stale")
            self.assertNotEqual(self.decide(root, "validation").returncode, 0)
            request.write_bytes(request_original)
            done = self.decide(root, "validation", "user-turn", "--scope", "validation/CLAIM_LEDGER.json")
            self.assertEqual(done.returncode, 0, done.stderr)
            require_human_checkpoint(root, "validation")
            snapshot = json.loads((root / ".cumcm/snapshots/validation.json").read_text())
            paths = {entry["path"] for entry in snapshot["artifacts"]}
            self.assertIn("validation/INDEPENDENT_REVIEW_RESULT.json", paths)
            self.assertIn("validation/independent-review-package/REVIEW_PACKAGE_MANIFEST.json", paths)
            review.write_bytes(original + b" ")
            with self.assertRaises(ValueError):
                require_human_checkpoint(root, "validation")

    def test_delivery_requires_separate_authority_pages_and_current_quality(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.paper_project(root)
            self.assertEqual(self.grant(root, "validation").returncode, 0)
            self.assertNotEqual(self.decide(root, "delivery").returncode, 0)
            self.assertEqual(self.grant(root, "delivery", "delivery-turn").returncode, 0)
            handoff = root / "handoffs/paper-delivery/HANDOFF.json"
            original = handoff.read_bytes()
            handoff.unlink()
            self.assertNotEqual(self.decide(root, "delivery", "delivery-turn").returncode, 0)
            handoff.write_bytes(original)
            page = root / ".cumcm/tmp/pages/page-1.png"
            image = page.read_bytes()
            page.unlink()
            self.assertNotEqual(self.decide(root, "delivery", "delivery-turn").returncode, 0)
            page.write_bytes(image)
            quality = root / "paper/PAPER_QUALITY_REPORT.json"
            old = quality.read_bytes()
            data = json.loads(old)
            data["paper_status"] = "draft"
            quality.write_text(json.dumps(data))
            self.assertNotEqual(self.decide(root, "delivery", "delivery-turn").returncode, 0)
            quality.write_bytes(old)
            done = self.decide(root, "delivery", "delivery-turn")
            self.assertEqual(done.returncode, 0, done.stderr)
            require_human_checkpoint(root, "delivery")
            page.write_bytes(image + b"changed")
            with self.assertRaises(ValueError):
                require_human_checkpoint(root, "delivery")

    def test_malformed_delegation_and_pending_status(self):
        with tempfile.TemporaryDirectory() as temp:
            root = make_project(Path(temp))
            model_with_candidates(root, ["selected"])
            self.assertEqual(self.grant(root, "model-design").returncode, 0)
            path = root / ".cumcm/delegations/model-design.json"
            path.write_text("[]")
            done = self.decide(root, "model-design")
            self.assertNotEqual(done.returncode, 0)
            self.assertNotIn("Traceback", done.stderr)
            self.assertEqual(self.grant(root, "model-design").returncode, 0)
            state_path = root / ".cumcm/state.json"
            state = json.loads(state_path.read_text())
            state["current_stage"] = "model-design"
            state_path.write_text(json.dumps(state))
            status = run_script("project_status.py", "--project", str(root), "--json", encoding="utf-8")
            report = json.loads(status.stdout)
            checkpoint = next(c for c in report["checkpoints"] if c["stage"] == "model-design")
            self.assertEqual(checkpoint["authority"], "delegated_lead_agent")
            self.assertIn("delegated decision pending", checkpoint["reason"])
