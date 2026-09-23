from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".agents" / "skills" / "cumcm-workflow" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from backend_selection import detect_matlab_executable, select_backend
from build_handoff import paper_payload, review_lineage, build as build_handoff
from build_independent_review_package import build as build_review_package
from init_latex_paper import commit_staged_tree
from paper_visible_text_check import inspect_text
from test_paper_pipeline import build_paper_ready_project
from workflow_fixtures import build_valid_project, write_json
from canonical_evidence import resolve_official_computation
from workflow_checks import check_project
from plan_redo import build_plan


def review_finding(finding_id: str, severity: str, status: str) -> dict:
    return {
        "finding_id": finding_id,
        "severity": severity,
        "status": status,
        "category": "implementation",
        "location": "code/solve.py",
        "evidence": "fixture evidence",
        "recommendation": "fixture recommendation",
    }


class ModesAndReviewTests(unittest.TestCase):
    def test_set_mode_refuses_blocked_finalizing_without_changing_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            state_path = root / ".cumcm/state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["mode"] = "working"
            write_json(root, ".cumcm/state.json", state)
            before = state_path.read_bytes()
            (root / "code/solve.py").write_text("print('drift')\n", encoding="utf-8")
            completed = __import__("subprocess").run(
                [sys.executable, str(SCRIPTS / "set_mode.py"), "--project", str(root), "--mode", "finalizing"],
                check=False, capture_output=True, text=True,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("blocking", completed.stderr)
            self.assertEqual(state_path.read_bytes(), before)

    def test_set_mode_commits_a_valid_finalizing_transition(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            state = json.loads((root / ".cumcm/state.json").read_text(encoding="utf-8"))
            state["mode"] = "working"
            write_json(root, ".cumcm/state.json", state)
            completed = __import__("subprocess").run(
                [sys.executable, str(SCRIPTS / "set_mode.py"), "--project", str(root), "--mode", "finalizing"],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            final = json.loads((root / ".cumcm/state.json").read_text(encoding="utf-8"))
            self.assertEqual(final["mode"], "finalizing")

    def test_enforce_cannot_bypass_stage_state_or_decisions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            state_path = root / ".cumcm" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["mode"] = "finalizing"
            state["stages"]["validation"] = "in_progress"
            write_json(root, ".cumcm/state.json", state)
            findings, summary = check_project(root, "validation", "enforce")
            rules = {item.rule_id for item in findings}
            self.assertIn("STATE-E013", rules)
            self.assertIn("DECISION-E001", rules)
            self.assertGreater(summary["blocking_error_count"], 0)

    def test_working_is_lightweight_and_finalizing_raises_formal_gates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            _, working = check_project(root, "validation", "enforce")
            self.assertEqual(working["gate_status"], "working_ready")
            self.assertEqual(working["blocking_error_count"], 0)
            state = json.loads((root / ".cumcm/state.json").read_text(encoding="utf-8"))
            state["mode"] = "finalizing"
            write_json(root, ".cumcm/state.json", state)
            findings, finalizing = check_project(root, "validation", "enforce")
            self.assertIn("PROJECT-E001", {item.rule_id for item in findings})
            self.assertGreater(finalizing["blocking_error_count"], 0)

    def test_accepted_with_concerns_and_p1_do_not_block_paper(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            path = root / "validation" / "INDEPENDENT_REVIEW_RESULT.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["verdict"] = "accepted_with_concerns"
            result["findings"] = [review_finding("REV-P1-001", "P1", "open")]
            write_json(root, "validation/INDEPENDENT_REVIEW_RESULT.json", result)
            findings, summary = check_project(root, "validation", "enforce")
            self.assertIn("IREVIEW-W001", {item.rule_id for item in findings})
            self.assertNotIn("IREVIEW-E012", {item.rule_id for item in findings})
            self.assertEqual(summary["blocking_error_count"], 0)

    def test_open_p0_is_the_only_review_severity_that_requires_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            path = root / "validation" / "INDEPENDENT_REVIEW_RESULT.json"
            result = json.loads(path.read_text(encoding="utf-8"))
            result["verdict"] = "revision_required"
            result["findings"] = [review_finding("REV-P0-001", "P0", "open")]
            write_json(root, "validation/INDEPENDENT_REVIEW_RESULT.json", result)
            findings, summary = check_project(root, "validation", "enforce")
            self.assertIn("IREVIEW-E012", {item.rule_id for item in findings})
            self.assertGreater(summary["blocking_error_count"], 0)

    def test_targeted_rereview_covers_prior_p0_without_new_full_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            current_path = root / "validation" / "INDEPENDENT_REVIEW_RESULT.json"
            prior = json.loads(current_path.read_text(encoding="utf-8"))
            prior["review_id"] = "REVIEW-FULL-001"
            prior["verdict"] = "revision_required"
            prior["findings"] = [review_finding("REV-P0-001", "P0", "open")]
            write_json(root, "validation/INDEPENDENT_REVIEW_RESULT.json", prior)
            (root / "model/VALIDATION_PLAN.md").write_text("# Validation plan\n", encoding="utf-8")
            shutil.rmtree(root / "validation" / "independent-review-package")
            package_path = build_review_package(root)
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["reviewer_selection"] = {
                "status": "recorded",
                "reviewer": "fixture-reviewer",
                "model": "fixture-model",
                "originating_task_ref": "fixture-origin-task",
                "task_ref": "fixture-targeted-task",
            }
            write_json(root, "validation/independent-review-package/REVIEW_PACKAGE_MANIFEST.json", package)

            targeted = json.loads((root / "validation/independent-review-package/TARGETED_FINDINGS.json").read_text(encoding="utf-8"))
            self.assertEqual(targeted["source_review_id"], "REVIEW-FULL-001")
            self.assertEqual(
                set(targeted["findings"][0]),
                {"finding_id", "category", "location", "evidence", "recommendation"},
            )
            self.assertFalse(any(item.get("source_path", "").startswith("validation/review-history/") for item in package["files"]))

            result = json.loads(current_path.read_text(encoding="utf-8"))
            result.update({
                "review_id": "REVIEW-TARGETED-002",
                "package_digest": package["package_digest"],
                "review_mode": "targeted",
                "previous_review_path": package["previous_review_path"],
                "target_finding_ids": ["REV-P0-001"],
                "verdict": "accepted",
                "findings": [review_finding("REV-P0-001", "P0", "resolved")],
            })
            result["reviewer_context"]["task_ref"] = "fixture-targeted-task"
            write_json(root, "validation/INDEPENDENT_REVIEW_RESULT.json", result)
            findings, summary = check_project(root, "validation", "enforce")
            rules = {item.rule_id for item in findings}
            self.assertNotIn("IREVIEW-E024", rules)
            self.assertNotIn("IREVIEW-E012", rules)
            self.assertEqual(summary["blocking_error_count"], 0)

    def test_editing_code_after_the_official_run_blocks_even_though_the_decision_still_binds(self):
        """The decision bound frozen evidence, which did not change; the working tree did.

        Reporting it once, at the run, is more precise than also staling the
        decision -- and it still blocks.
        """
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            _, before = check_project(root, "delivery")
            self.assertIn("computation", before["stages_with_current_decision"])
            (root / "code" / "solve.py").write_text("print('changed after official run')\n", encoding="utf-8")
            findings, after = check_project(root, "delivery")
            self.assertIn("computation", after["stages_with_current_decision"])
            self.assertIn("RUN-E020", {item.rule_id for item in findings})
            self.assertGreater(after["blocking_error_count"], 0)

    def supersede(self, root, *, official=True, exit_code=0):
        """Append a child of RUN-Q1-001 by hand, so the fixture stays declarative."""
        source = json.loads((root / "runs/RUN-Q1-001/RUN_MANIFEST.json").read_text(encoding="utf-8"))
        child = dict(source)
        child.update({
            "run_id": "RUN-Q1-002", "parent_run_id": "RUN-Q1-001",
            "official_run": official, "exit_code": exit_code,
            "status": "completed" if exit_code == 0 else "failed",
            "stdout_path": "runs/RUN-Q1-002/stdout.log", "stderr_path": "runs/RUN-Q1-002/stderr.log",
        })
        (root / "runs/RUN-Q1-002").mkdir(parents=True, exist_ok=True)
        (root / "runs/RUN-Q1-002/stdout.log").write_text("child\n", encoding="utf-8")
        (root / "runs/RUN-Q1-002/stderr.log").write_text("", encoding="utf-8")
        write_json(root, "runs/RUN-Q1-002/RUN_MANIFEST.json", child)

    def test_every_formal_consumer_agrees_on_what_a_superseded_run_means(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            self.supersede(root)
            findings, summary = check_project(root, "validation")
            rules = {item.rule_id for item in findings}
            self.assertEqual(summary["superseded_run_ids"], ["RUN-Q1-001"])
            self.assertIn("RESULT-E017", rules)   # the checker blocks
            self.assertIn("CLAIM-W020", rules)    # the claim points at retired evidence
            # the resolver every builder shares must refuse it too, not quietly package it
            with self.assertRaises(ValueError) as raised:
                resolve_official_computation(root)
            self.assertIn("--follow-lineage", str(raised.exception))

    def test_a_failed_child_leaves_every_consumer_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            self.supersede(root, official=False, exit_code=3)
            findings, summary = check_project(root, "validation")
            self.assertEqual(summary["superseded_run_ids"], [])
            self.assertNotIn("RESULT-E017", {item.rule_id for item in findings})
            self.assertEqual([item["run_id"] for item in resolve_official_computation(root)], ["RUN-Q1-001"])

    def test_one_capability_may_not_have_official_runs_in_two_backends(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            rival = json.loads((root / "runs/RUN-Q1-001/RUN_MANIFEST.json").read_text(encoding="utf-8"))
            rival = dict(rival)
            rival["run_id"] = "RUN-Q1-MATLAB"
            rival["argv"] = ["matlab", "-batch", "solve"]
            rival["implementation"] = dict(rival["implementation"], selected_language="matlab")
            rival["stdout_path"] = "runs/RUN-Q1-MATLAB/stdout.log"
            rival["stderr_path"] = "runs/RUN-Q1-MATLAB/stderr.log"
            (root / "runs/RUN-Q1-MATLAB").mkdir(parents=True, exist_ok=True)
            (root / "runs/RUN-Q1-MATLAB/stdout.log").write_text("done\n", encoding="utf-8")
            (root / "runs/RUN-Q1-MATLAB/stderr.log").write_text("", encoding="utf-8")
            write_json(root, "runs/RUN-Q1-MATLAB/RUN_MANIFEST.json", rival)

            findings, _ = check_project(root, "computation")
            clash = [item for item in findings if item.rule_id == "RUN-E024"]
            self.assertTrue(clash, "two backends for one capability must be reported")
            self.assertIn("CAP-Q1-001", clash[0].message)
            self.assertEqual(clash[0].severity, "warning")  # working mode keeps exploring cheap

    def test_revision_requested_invalidates_stage_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            completed = __import__("subprocess").run(
                [sys.executable, str(SCRIPTS / "record_decision.py"), "--project", str(root),
                 "--stage", "computation", "--decision", "revision_requested",
                 "--decision-id", "DEC-COMP-REVISION", "--reviewer", "fixture-reviewer",
                 "--task-turn-ref", "revision-test", "--summary", "Computation needs revision."],
                check=False, capture_output=True, text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse((root / ".cumcm/snapshots/computation.json").exists())
            _, summary = check_project(root, "delivery")
            self.assertNotIn("computation", summary["stages_with_current_decision"])

    def test_finalizing_requires_derived_stage_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            (root / ".cumcm/snapshots/validation.json").unlink()
            findings, summary = check_project(root, "delivery")
            self.assertIn("DECISION-E014", {item.rule_id for item in findings})
            self.assertGreater(summary["blocking_error_count"], 0)

    def test_redo_plan_names_the_actual_work_a_change_invalidates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            plan = build_plan(root, ["code/solve.py"])
            self.assertEqual(plan["stale_official_runs"], ["RUN-Q1-001"])
            self.assertEqual(plan["stale_results"], ["RES-Q1-001"])
            self.assertEqual(plan["stale_claims"], ["CLM-Q1-001"])
            self.assertIn("computation", plan["actions"])
            self.assertIn("validation", plan["actions"])
            self.assertIn("delivery", plan["actions"])

    def test_official_source_change_propagates_through_every_downstream_layer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            run_path = root / "runs/RUN-Q1-001/RUN_MANIFEST.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["inputs"][0]["evidence_role"] = "auxiliary_input"
            write_json(root, "runs/RUN-Q1-001/RUN_MANIFEST.json", run)

            plans = [
                build_plan(root, ["problem/official/problem.txt"]),
                build_plan(root, ["./problem/official/problem.txt"]),
                build_plan(root, [str(root / "problem/official/problem.txt")]),
            ]
            for plan in plans:
                self.assertEqual(plan["changed_paths"], ["problem/official/problem.txt"])
                self.assertEqual(plan["stale_facts"], ["FACT-Q1-001"])
                self.assertEqual(plan["stale_capabilities"], ["CAP-Q1-001"])
                self.assertEqual(plan["stale_models"], ["MODEL-Q1-001"])
                self.assertEqual(plan["stale_official_runs"], ["RUN-Q1-001"])
                self.assertEqual(plan["stale_results"], ["RES-Q1-001"])
                self.assertEqual(plan["stale_claims"], ["CLM-Q1-001"])
                self.assertTrue(set(("intake", "problem-analysis", "model-design", "computation", "validation", "paper", "delivery")).issubset(plan["actions"]))

    def test_redo_plan_rejects_project_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            with self.assertRaisesRegex(ValueError, "outside project"):
                build_plan(root, ["../outside.txt"])

    def test_redo_plan_leaves_unrelated_work_alone(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            plan = build_plan(root, ["notes/scratch.md"])
            self.assertEqual(plan["stale_official_runs"], [])
            self.assertEqual(plan["stale_claims"], [])
            self.assertEqual(plan["actions"], {})
            self.assertIn("RUN-Q1-001", plan["unaffected"]["computation"])

    def test_matlab_is_selected_for_matlab_fit_on_a_tie_break(self):
        result = select_backend(
            {"features": ["numerical_linear_algebra", "optimization"]},
            {"preferred": "matlab", "fallback": "python", "selection": "auto"},
            {"matlab": True, "python": True},
        )
        self.assertEqual(result["selected_language"], "matlab")
        self.assertTrue(result["single_backend_policy"])

    def test_python_is_selected_when_task_fit_is_clear(self):
        result = select_backend(
            {"features": ["data_cleaning", "csv_excel"]},
            {"preferred": "matlab", "fallback": "python", "selection": "auto"},
            {"matlab": True, "python": True},
        )
        self.assertEqual(result["selected_language"], "python")

    def test_matlab_preferred_falls_back_to_python_when_unavailable(self):
        result = select_backend(
            {"features": ["optimization"]},
            {"preferred": "matlab", "fallback": "python", "selection": "auto"},
            {"matlab": False, "python": True},
        )
        self.assertEqual(result["selected_language"], "python")
        self.assertEqual(result["fallback_from"], "matlab")

    def test_configured_matlab_executable_has_detection_priority(self):
        with tempfile.TemporaryDirectory() as temp:
            executable = Path(temp) / "custom-matlab"
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            executable.chmod(0o755)
            detected = detect_matlab_executable({"matlab_executable": str(executable)})
            self.assertEqual(detected, {"path": str(executable.resolve()), "source": "configured"})

    def test_matlab_detection_uses_path_before_macos_applications(self):
        with tempfile.TemporaryDirectory() as temp:
            executable = str(Path(temp) / "matlab")
            with mock.patch("backend_selection.shutil.which", return_value=executable), mock.patch(
                "backend_selection.glob.glob", return_value=["/Applications/MATLAB_R2026b.app/bin/matlab"]
            ) as app_glob:
                detected = detect_matlab_executable({})
            self.assertEqual(detected, {"path": str(Path(executable).resolve()), "source": "path"})
            app_glob.assert_not_called()

    def test_matlab_detection_uses_newest_macos_application(self):
        candidates = [
            "/Applications/MATLAB_R2025b.app/bin/matlab",
            "/Applications/MATLAB_R2026a.app/bin/matlab",
        ]
        with mock.patch("backend_selection.shutil.which", return_value=None), mock.patch(
            "backend_selection.glob.glob", return_value=candidates
        ), mock.patch("backend_selection.executable_path", side_effect=lambda value: value):
            detected = detect_matlab_executable({})
        self.assertEqual(detected, {"path": candidates[1], "source": "macos_application"})

    def test_required_matlab_does_not_silently_fallback(self):
        with self.assertRaisesRegex(ValueError, "required backend is unavailable: matlab"):
            select_backend(
                {"features": ["data_cleaning"], "required_backend": "matlab"},
                {"preferred": "matlab", "fallback": "python", "selection": "auto"},
                {"matlab": False, "python": True},
            )

    def test_paper_handoff_stale_detection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            path = root / "validation" / "CLAIM_LEDGER.json"
            claims = json.loads(path.read_text(encoding="utf-8"))
            claims["claims"][0]["text"] += " Changed upstream."
            write_json(root, "validation/CLAIM_LEDGER.json", claims)
            findings, _ = check_project(root, "paper")
            self.assertIn("HANDOFF-E003", {item.rule_id for item in findings})

    def test_paper_handoff_excludes_full_run_history(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            handoff = json.loads((root / "handoffs" / "validation-paper" / "HANDOFF.json").read_text(encoding="utf-8"))
            self.assertFalse(any(item["path"].startswith("runs/") for item in handoff["canonical_artifacts"]))
            self.assertEqual(
                set(handoff["payload"]),
                {"problem_summary", "model_summary", "verified_results", "claims", "limitations", "representation_candidates", "official_format_files", "official_materials"},
            )
            self.assertIn("debug transcripts", handoff["excluded_history"])

    def test_paper_handoff_uses_real_limitations_and_proactive_representation_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            claims_path = root / "validation" / "CLAIM_LEDGER.json"
            claims = json.loads(claims_path.read_text(encoding="utf-8"))
            claims["claims"][0]["text"] = "The cost trend compares multiple policies over time."
            claims["claims"][0]["limitations"] = "Only the observed time window is supported."
            claims["claims"][0]["evidence"].pop("figure_ids", None)
            write_json(root, "validation/CLAIM_LEDGER.json", claims)

            model_path = root / "model" / "MODEL_CONTRACT.json"
            model = json.loads(model_path.read_text(encoding="utf-8"))
            model_scope = model["components"][0]["scope"]
            model["components"][0]["assumptions"] = ["Demand remains stationary."]
            model["components"][0]["known_limitations"] = ["Not calibrated for regime shifts."]
            write_json(root, "model/MODEL_CONTRACT.json", model)

            review_path = root / "validation" / "INDEPENDENT_REVIEW_RESULT.json"
            review = json.loads(review_path.read_text(encoding="utf-8"))
            review["verdict"] = "accepted_with_concerns"
            review["findings"] = [review_finding("REV-P1-001", "P1", "accepted_concern")]
            write_json(root, "validation/INDEPENDENT_REVIEW_RESULT.json", review)

            payload = paper_payload(root)
            limitation_text = json.dumps(payload["limitations"], ensure_ascii=False)
            self.assertNotIn(model_scope, limitation_text)
            self.assertIn("Only the observed time window is supported.", limitation_text)
            self.assertIn("Demand remains stationary.", limitation_text)
            self.assertIn("Not calibrated for regime shifts.", limitation_text)
            self.assertIn("REV-P1-001", limitation_text)
            kinds = {item["kind"] for item in payload["representation_candidates"]}
            self.assertTrue({"trend", "multi_group_comparison"}.issubset(kinds))

    def test_targeted_review_preserves_open_p1_lineage_and_filters_unsupported_claim_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            current_path = root / "validation/INDEPENDENT_REVIEW_RESULT.json"
            full = json.loads(current_path.read_text(encoding="utf-8"))
            full.update({
                "review_id": "REVIEW-FULL-P1",
                "review_mode": "full",
                "previous_review_path": None,
                "target_finding_ids": [],
                "verdict": "revision_required",
                "findings": [
                    review_finding("REV-P0-001", "P0", "open"),
                    review_finding("REV-P1-KEEP", "P1", "accepted_concern"),
                    review_finding("REV-P1-DROP", "P1", "open"),
                ],
            })
            history = root / "validation/review-history/REVIEW-FULL-P1.json"
            write_json(root, history.relative_to(root).as_posix(), full)

            targeted = json.loads(current_path.read_text(encoding="utf-8"))
            targeted.update({
                "review_id": "REVIEW-TARGETED-P1",
                "review_mode": "targeted",
                "previous_review_path": history.relative_to(root).as_posix(),
                "target_finding_ids": ["REV-P0-001"],
                "verdict": "accepted",
                "findings": [
                    review_finding("REV-P0-001", "P0", "resolved"),
                    review_finding("REV-P1-DROP", "P1", "resolved"),
                ],
            })
            write_json(root, "validation/INDEPENDENT_REVIEW_RESULT.json", targeted)

            claims_path = root / "validation/CLAIM_LEDGER.json"
            claims = json.loads(claims_path.read_text(encoding="utf-8"))
            contradicted = dict(claims["claims"][0])
            contradicted.update({
                "claim_id": "CLM-CONTRADICTED",
                "text": "Unsupported alternative claim.",
                "evidence_state": "contradicted",
                "limitations": "This must not enter the paper brief.",
            })
            claims["claims"].append(contradicted)
            write_json(root, "validation/CLAIM_LEDGER.json", claims)

            payload = paper_payload(root)
            limitation_text = json.dumps(payload["limitations"], ensure_ascii=False)
            self.assertIn("REV-P1-KEEP", limitation_text)
            self.assertNotIn("REV-P1-DROP", limitation_text)
            self.assertNotIn("This must not enter the paper brief.", limitation_text)
            self.assertIn(history.relative_to(root).as_posix(), review_lineage(root, targeted)[1])

    def test_paper_delivery_handoff_is_self_contained_for_fresh_delivery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            handoff = json.loads((root / "handoffs/paper-delivery/HANDOFF.json").read_text(encoding="utf-8"))
            payload = handoff["payload"]
            self.assertEqual(payload["approved_pdf"]["path"], "paper/paper.pdf")
            self.assertEqual(payload["editable_latex"]["entrypoint"], "paper/main.tex")
            self.assertEqual(payload["editable_latex"]["source_snapshot"]["entrypoint"], "paper/main.tex")
            self.assertEqual(payload["computation_evidence"][0]["run_id"], "RUN-Q1-001")
            self.assertIn("runs/RUN-Q1-001/source/code/solve.py", payload["computation_evidence"][0]["source_files"])
            roles = {item["role"] for item in handoff["canonical_artifacts"]}
            self.assertTrue({"results", "official_run", "computation_source", "compile_receipt", "editable_source", "approved_pdf"}.issubset(roles))

    def test_paper_delivery_handoff_rejects_stale_editable_source_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            (root / "paper/main.tex").write_text("% changed after compile\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "compile-bound editable LaTeX"):
                build_handoff(root, "paper-delivery")

    def test_paper_delivery_handoff_carries_classified_official_rules(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            rules_path = root / "problem/official/submission-rules.pdf"
            rules_path.write_bytes(b"official submission rules")
            manifest_path = root / "problem/SOURCE_MANIFEST.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["sources"].append(
                {
                    "source_id": "SRC-SUBMISSION-RULES",
                    "path": rules_path.relative_to(root).as_posix(),
                    "origin": "official",
                    "authoritative_for": ["submission_rules"],
                }
            )
            write_json(root, "problem/SOURCE_MANIFEST.json", manifest)
            handoff_path = build_handoff(root, "paper-delivery")
            handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
            self.assertIn(
                {
                    "source_id": "SRC-SUBMISSION-RULES",
                    "path": "problem/official/submission-rules.pdf",
                    "role": "format_or_submission_rule",
                    "authoritative_for": ["submission_rules"],
                },
                handoff["payload"]["official_materials"],
            )
            self.assertIn("format_or_submission_rule", {item["role"] for item in handoff["canonical_artifacts"]})

    def test_all_canonical_consumers_reject_a_nonofficial_referenced_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            run_path = root / "runs/RUN-Q1-001/RUN_MANIFEST.json"
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["official_run"] = False
            write_json(root, "runs/RUN-Q1-001/RUN_MANIFEST.json", run)
            shutil.rmtree(root / "validation/independent-review-package")
            (root / "model/VALIDATION_PLAN.md").write_text("# Validation plan\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not a successful official run"):
                build_handoff(root, "computation-validation")
            with self.assertRaisesRegex(ValueError, "not a successful official run"):
                build_review_package(root)
            with self.assertRaisesRegex(ValueError, "not a successful official run"):
                build_handoff(root, "paper-delivery")

    def test_review_package_contains_only_canonical_official_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            shutil.rmtree(root / "validation" / "independent-review-package")
            (root / "model/VALIDATION_PLAN.md").write_text("# Validation plan\n", encoding="utf-8")

            unused_code = root / "code" / "unused_experiment.py"
            unused_code.write_text("print('unused')\n", encoding="utf-8")
            official_run_path = root / "runs/RUN-Q1-001/RUN_MANIFEST.json"
            official_run = json.loads(official_run_path.read_text(encoding="utf-8"))
            for name, role in (("diagnostic.json", "diagnostic_output"), ("intermediate.json", "intermediate_output")):
                output_path = root / "runs/RUN-Q1-001/outputs" / name
                output_path.write_text("{}\n", encoding="utf-8")
                official_run["outputs"].append(
                    {"path": output_path.relative_to(root).as_posix(), "evidence_role": role, "size": 3, "media_type": "application/json"}
                )
            write_json(root, "runs/RUN-Q1-001/RUN_MANIFEST.json", official_run)

            failed_dir = root / "runs/RUN-FAILED-001"
            failed_dir.mkdir(parents=True)
            failed = dict(official_run)
            failed.update({"run_id": "RUN-FAILED-001", "official_run": False, "status": "failed", "exit_code": 1})
            write_json(root, "runs/RUN-FAILED-001/RUN_MANIFEST.json", failed)
            (failed_dir / "stdout.log").write_text("debug history\n", encoding="utf-8")

            manifest_path = build_review_package(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            source_paths = {item.get("source_path") for item in manifest["files"] if item.get("source_path")}
            self.assertIn("problem/official/problem.txt", source_paths)
            self.assertIn("results/RESULTS_INDEX.json", source_paths)
            self.assertIn("runs/RUN-Q1-001/RUN_MANIFEST.json", source_paths)
            self.assertIn("runs/RUN-Q1-001/source/code/solve.py", source_paths)
            self.assertIn("runs/RUN-Q1-001/outputs/result.json", source_paths)
            self.assertNotIn("runs/RUN-Q1-001/stdout.log", source_paths)
            self.assertNotIn("runs/RUN-Q1-001/stderr.log", source_paths)
            self.assertNotIn("runs/RUN-Q1-001/outputs/diagnostic.json", source_paths)
            self.assertNotIn("runs/RUN-Q1-001/outputs/intermediate.json", source_paths)
            self.assertNotIn("runs/RUN-FAILED-001/RUN_MANIFEST.json", source_paths)
            self.assertNotIn("code/unused_experiment.py", source_paths)

    def test_handoffs_bind_only_canonical_downstream_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            modeling = json.loads((root / "handoffs" / "modeling-computation" / "HANDOFF.json").read_text(encoding="utf-8"))
            computation = json.loads((root / "handoffs" / "computation-validation" / "HANDOFF.json").read_text(encoding="utf-8"))
            modeling_paths = {item["path"] for item in modeling["canonical_artifacts"]}
            computation_roles = {item["role"] for item in computation["canonical_artifacts"]}
            self.assertIn("problem/SOURCE_MANIFEST.json", modeling_paths)
            self.assertIn("problem/official/problem.txt", modeling_paths)
            self.assertTrue({"official_run", "computation_source", "claim_bearing_output"}.issubset(computation_roles))
            self.assertNotIn("run_log", computation_roles)

    def test_working_tree_drifting_from_the_official_run_is_caught(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            (root / "code" / "solve.py").write_text("print('stale')\n", encoding="utf-8")
            findings, _ = check_project(root, "computation")
            drift = [item for item in findings if item.rule_id == "RUN-E020"]
            self.assertTrue(drift)
            self.assertIn("code/solve.py", drift[0].message)
            self.assertIn("--rerun", drift[0].remediation)

    def test_tampering_with_the_frozen_evidence_is_a_different_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            (root / "runs/RUN-Q1-001/source/code/solve.py").write_text("print('forged')\n", encoding="utf-8")
            findings, _ = check_project(root, "computation")
            rules = {item.rule_id for item in findings}
            self.assertIn("RUN-E021", rules)
            self.assertNotIn("RUN-E020", rules)

    def test_review_package_detects_upstream_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            shutil.rmtree(root / "validation" / "independent-review-package")
            (root / "validation" / "INDEPENDENT_REVIEW_RESULT.json").unlink()
            (root / "validation" / "INDEPENDENT_REVIEW_RAW.md").unlink()
            (root / "model" / "VALIDATION_PLAN.md").write_text("# Validation plan\n", encoding="utf-8")
            build_review_package(root)
            (root / "runs/RUN-Q1-001/source/code/solve.py").write_text("print('changed upstream')\n", encoding="utf-8")
            findings, _ = check_project(root, "validation")
            self.assertIn("IREVIEW-E025", {item.rule_id for item in findings})

    def test_visible_local_paths_cover_unix_and_windows_home_directories(self):
        blocking, _ = inspect_text(r"/home/alice/project/output.json C:\Users\alice\project\result.json")
        self.assertTrue(any(item["rule_id"] == "PAPER-TEXT-E004" for item in blocking))

    def test_latex_commit_rolls_back_partial_publish(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            staging = root / "staging"
            paper = root / "paper"
            staging.mkdir()
            (staging / "a.tex").write_text("a", encoding="utf-8")
            (staging / "b.tex").write_text("b", encoding="utf-8")
            real_replace = __import__("os").replace
            calls = 0

            def flaky(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("fixture commit failure")
                return real_replace(source, destination)

            with mock.patch("init_latex_paper.os.replace", side_effect=flaky):
                with self.assertRaises(OSError):
                    commit_staged_tree(staging, paper)
            self.assertEqual(list(paper.iterdir()), [])
