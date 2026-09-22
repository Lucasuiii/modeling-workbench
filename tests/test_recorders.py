"""End-to-end tests for the v0.6 recorders and Deferred Model Selection.

Unlike the contract tests, these do not hand-write a single hash: every run,
result and compile receipt here is produced by the tooling the workflow ships.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from recorder_fixtures import (ROOT, SCRIPTS, PROJECT_ID, envelope, write_json, run_script,
    SOLVER, make_project, ctex_available, MINIMAL_TEX, GREEDY, NO_OP, SELF_EDITING, record_official)

from init_project import initialize  # noqa: E402
from plan_redo import build_plan  # noqa: E402
from workflow_fixtures import write_accepted_snapshot
from workflow_checks import check_project  # noqa: E402


class RecorderTests(unittest.TestCase):
    def test_command_keeps_internal_cli_separator_and_records_exact_argv(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            script = project / "code" / "show_argv.py"
            script.write_text("import json, sys\nprint(json.dumps(sys.argv[1:]))\n", encoding="utf-8")
            completed = run_script(
                "record_run.py", "--project", str(project), "--",
                sys.executable, "code/show_argv.py", "before", "--", "after",
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            manifest = json.loads((project / "runs/RUN-001/RUN_MANIFEST.json").read_text(encoding="utf-8"))
            expected = [sys.executable, "code/show_argv.py", "before", "--", "after"]
            self.assertEqual(manifest["argv"], expected)
            self.assertEqual(
                json.loads((project / manifest["stdout_path"]).read_text(encoding="utf-8")),
                ["before", "--", "after"],
            )

    def test_rerun_rejects_a_replacement_command(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            first = run_script("record_run.py", "--project", str(project), "--", sys.executable, "code/solve.py")
            self.assertEqual(first.returncode, 0, first.stderr)
            refused = run_script(
                "record_run.py", "--project", str(project), "--rerun", "RUN-001", "--",
                sys.executable, "-c", "print('different')",
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("cannot provide a command with --rerun", refused.stderr)
            self.assertEqual({path.name for path in (project / "runs").iterdir()}, {"RUN-001"})

    def test_exploratory_run_needs_no_declarations_and_never_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            completed = run_script("record_run.py", "--project", str(project), "--", sys.executable, "code/solve.py")
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            manifest = json.loads((project / "runs" / "RUN-001" / "RUN_MANIFEST.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["official_run"])
            self.assertEqual(manifest["exit_code"], 0)
            self.assertEqual(manifest["implementation"]["selected_language"], "python")
            # nothing was typed by hand: the snapshot and the log paths were observed
            self.assertEqual(manifest["implementation"]["source_snapshot"]["files"], ["runs/RUN-001/source/code/solve.py"])
            self.assertTrue((project / "runs/RUN-001/source/code/solve.py").is_file())
            self.assertTrue((project / manifest["stdout_path"]).is_file())

    def test_failing_exploratory_run_is_recorded_without_blocking_the_formal_chain(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            (project / "code" / "broken.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
            run_script("record_run.py", "--project", str(project), "--run-id", "RUN-BROKEN",
                       "--", sys.executable, "code/broken.py")
            record_official(project)
            findings, summary = check_project(project, "computation")
            self.assertEqual([item for item in findings if item.severity == "error"], [])
            self.assertEqual(summary["run_count"], 2)
            self.assertEqual(summary["official_run_count"], 1)


    def test_official_run_and_indexed_result_pass_the_checker_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            record_official(project)
            index = json.loads((project / "results" / "RESULTS_INDEX.json").read_text(encoding="utf-8"))
            self.assertEqual(index["results"][0]["value"], 1.5)
            findings, summary = check_project(project, "computation")
            self.assertEqual([item for item in findings if item.severity == "error"], [])
            self.assertEqual(summary["gate_status"], "working_ready")

    def test_index_result_refuses_a_non_official_or_non_claim_output(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            run_script("record_run.py", "--project", str(project), "--run-id", "RUN-EXP",
                       "--", sys.executable, "code/solve.py")
            rejected = run_script("index_result.py", "--project", str(project), "--result-id", "RES-X",
                                  "--run", "RUN-EXP", "--locator", "results/q1_output.json#/minimum_cost",
                                  "--name", "n", "--scope", "s")
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("not a successful official run", rejected.stderr)

    def test_a_rerun_appends_and_leaves_the_superseded_run_intact(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            record_official(project)
            first = project / "runs" / "RUN-Q1-001" / "RUN_MANIFEST.json"
            before_bytes = first.read_bytes()
            before_stdout = (project / "runs" / "RUN-Q1-001" / "stdout.log").read_bytes()

            (project / "code" / "solve.py").write_text(SOLVER.replace("4.25", "0.5"), encoding="utf-8")
            drift, _ = check_project(project, "computation")
            self.assertIn("RUN-E020", {item.rule_id for item in drift})
            self.assertEqual(build_plan(project, ["code/solve.py"])["stale_official_runs"], ["RUN-Q1-001"])

            completed = run_script("record_run.py", "--project", str(project), "--rerun", "RUN-Q1-001", "--official")
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

            # the superseded run is byte-for-byte what it was, evidence included
            self.assertEqual(first.read_bytes(), before_bytes)
            self.assertEqual((project / "runs" / "RUN-Q1-001" / "stdout.log").read_bytes(), before_stdout)
            self.assertIn("4.25", (project / "runs/RUN-Q1-001/source/code/solve.py").read_text(encoding="utf-8"))

            second = json.loads((project / "runs" / "RUN-Q1-002" / "RUN_MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual(second["run_id"], "RUN-Q1-002")
            self.assertEqual(second["parent_run_id"], "RUN-Q1-001")
            self.assertEqual(second["argv"], json.loads(first.read_text(encoding="utf-8"))["argv"])
            self.assertEqual(second["capability_ids"], ["CAP-Q1-001"])
            self.assertIn("0.5", (project / "runs/RUN-Q1-002/source/code/solve.py").read_text(encoding="utf-8"))

            # the index still cites the superseded run, and that now blocks
            stale, summary = check_project(project, "computation")
            self.assertEqual(summary["superseded_run_ids"], ["RUN-Q1-001"])
            self.assertIn("RESULT-E017", {item.rule_id for item in stale})

            moved = run_script("index_result.py", "--project", str(project), "--follow-lineage")
            self.assertEqual(moved.returncode, 0, moved.stdout + moved.stderr)
            self.assertIn("RUN-Q1-001 -> RUN-Q1-002", moved.stdout)
            index = json.loads((project / "results" / "RESULTS_INDEX.json").read_text(encoding="utf-8"))
            self.assertEqual(index["results"][0]["run_id"], "RUN-Q1-002")
            self.assertEqual(index["results"][0]["value"], 0.5)

            findings, _ = check_project(project, "computation")
            self.assertEqual([item for item in findings if item.severity == "error"], [])

    def test_a_new_run_never_overwrites_an_existing_run_id(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            record_official(project)
            clash = run_script("record_run.py", "--project", str(project), "--run-id", "RUN-Q1-001",
                               "--", sys.executable, "code/solve.py")
            self.assertNotEqual(clash.returncode, 0)
            self.assertIn("append-only", clash.stderr)

    def test_draft_model_passes_working_and_frozen_model_must_be_complete(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            record_official(project)
            working, _ = check_project(project, "model-design")
            self.assertEqual([item for item in working if item.severity == "error"], [])
            state_path = project / ".cumcm" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["mode"] = "finalizing"
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            frozen, _ = check_project(project, "model-design")
            rules = {item.rule_id for item in frozen}
            self.assertIn("MODEL-E005", rules)  # missing variables/inputs/outputs/verification_plan

    def test_frozen_verification_plan_must_be_backed_by_recorded_assertions(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            record_official(project)
            model_path = project / "model" / "MODEL_CONTRACT.json"
            model = json.loads(model_path.read_text(encoding="utf-8"))
            model["components"][0].update({
                "variables": [{"name": "candidate"}], "inputs": ["SRC-001"], "outputs": ["RES-Q1-001"],
                "verification_plan": ["enumeration coverage"],
            })
            model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            state_path = project / ".cumcm" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["mode"] = "finalizing"
            state["stages"]["intake"] = "in_progress"
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            matched, _ = check_project(project, "computation")
            self.assertNotIn("MODEL-E009", {item.rule_id for item in matched})
            self.assertNotIn("MODEL-W010", {item.rule_id for item in matched})

            model["components"][0]["verification_plan"] = ["a check nobody executed"]
            model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            unmatched, _ = check_project(project, "computation")
            self.assertIn("MODEL-W010", {item.rule_id for item in unmatched})


class ProvenanceIntegrityTests(unittest.TestCase):
    """A run may only claim what it actually produced and actually verified."""

    def test_a_leftover_assertion_file_is_never_recorded_as_this_runs_verdict(self):
        """`recorded` means this run computed the verdict, so a stale file cannot supply it.

        Without this the whole declared/recorded split is decorative: point --assert-file
        at yesterday's verdicts and they satisfy a frozen verification plan.
        """
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            record_official(project)
            stale = project / "results" / "assertions.json"
            os.utime(stale, (946684800, 946684800))          # 2000-01-01
            before = stale.read_text(encoding="utf-8")

            (project / "code" / "quiet.py").write_text(
                'import json, pathlib\n'
                'pathlib.Path("results/q1_output.json").write_text(json.dumps({"minimum_cost": 1.5, "count": 3}))\n',
                encoding="utf-8",
            )
            refused = run_script(
                "record_run.py", "--project", str(project), "--run-id", "RUN-STALE", "--official",
                "--capability", "CAP-Q1-001", "--source", "code/quiet.py",
                "--output", "results/q1_output.json:claim",
                "--assert-file", "results/assertions.json",
                "--", sys.executable, "code/quiet.py",
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("not rewritten by this run", refused.stderr)
            self.assertFalse((project / "runs" / "RUN-STALE" / "RUN_MANIFEST.json").exists())
            self.assertEqual(stale.read_text(encoding="utf-8"), before)

    def test_a_source_the_run_creates_is_not_the_code_that_ran(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            (project / "code").mkdir(exist_ok=True)
            (project / "code" / "driver.py").write_text(
                'import json, pathlib\n'
                'pathlib.Path("code/generated.py").write_text("# made during the run")\n'
                'pathlib.Path("results").mkdir(exist_ok=True)\n'
                'pathlib.Path("results/q1_output.json").write_text(json.dumps({"minimum_cost": 1.5}))\n',
                encoding="utf-8",
            )
            refused = run_script(
                "record_run.py", "--project", str(project), "--run-id", "RUN-GEN", "--official",
                "--capability", "CAP-Q1-001", "--source", "code/generated.py",
                "--output", "results/q1_output.json:claim", "--", sys.executable, "code/driver.py",
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("does not exist before the run", refused.stderr)
            self.assertFalse((project / "runs" / "RUN-GEN" / "RUN_MANIFEST.json").exists())

    def test_a_leftover_file_is_never_recorded_as_this_runs_claim_output(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            record_official(project)
            leftover = json.loads((project / "results" / "q1_output.json").read_text(encoding="utf-8"))

            (project / "code" / "noop.py").write_text(NO_OP, encoding="utf-8")
            refused = run_script(
                "record_run.py", "--project", str(project), "--run-id", "RUN-NOOP", "--official",
                "--capability", "CAP-Q1-001", "--source", "code/noop.py",
                "--output", "results/q1_output.json:claim", "--", sys.executable, "code/noop.py",
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("did not write", refused.stderr)
            self.assertFalse((project / "runs" / "RUN-NOOP" / "RUN_MANIFEST.json").exists())
            # the earlier run's output is untouched and still belongs to it
            self.assertEqual(json.loads((project / "results" / "q1_output.json").read_text(encoding="utf-8")), leftover)

    def test_an_untouched_diagnostic_output_only_warns(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            (project / "notes.txt").write_text("kept\n", encoding="utf-8")
            (project / "code" / "noop.py").write_text(NO_OP, encoding="utf-8")
            recorded = run_script("record_run.py", "--project", str(project), "--run-id", "RUN-DIAG",
                                  "--source", "code/noop.py", "--output", "notes.txt:diagnostic",
                                  "--", sys.executable, "code/noop.py")
            self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)
            self.assertIn("was not rewritten", recorded.stderr)
            self.assertTrue((project / "runs" / "RUN-DIAG" / "RUN_MANIFEST.json").is_file())

    def test_a_rerun_never_inherits_the_parents_assertion_verdicts(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            record_official(project)
            parent = json.loads((project / "runs" / "RUN-Q1-001" / "RUN_MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual([item["name"] for item in parent["assertions"]], ["enumeration coverage"])

            (project / "code" / "solve.py").write_text(SOLVER.replace("4.25", "0.5"), encoding="utf-8")
            again = run_script("record_run.py", "--project", str(project), "--rerun", "RUN-Q1-001", "--official")
            self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
            child = json.loads((project / "runs" / "RUN-Q1-002" / "RUN_MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual(child["assertions"], [])
            self.assertIn("NOT inherited", again.stderr)

    def test_an_exploratory_rerun_does_not_retire_the_official_run_it_branched_from(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            record_official(project)
            (project / "code" / "solve.py").write_text(SOLVER.replace("4.25", "0.5"), encoding="utf-8")
            # a successful rerun that was never promoted: it replaces nothing
            probe = run_script("record_run.py", "--project", str(project), "--rerun", "RUN-Q1-001",
                               "--run-id", "RUN-PROBE")
            self.assertEqual(probe.returncode, 0, probe.stdout + probe.stderr)
            manifest = json.loads((project / "runs" / "RUN-PROBE" / "RUN_MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["parent_run_id"], "RUN-Q1-001")
            self.assertFalse(manifest["official_run"])

            findings, summary = check_project(project, "computation")
            self.assertEqual(summary["superseded_run_ids"], [])
            self.assertNotIn("RESULT-E017", {item.rule_id for item in findings})

    def test_a_failed_rerun_cannot_even_be_recorded_against_a_claim_output(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            record_official(project)
            (project / "code" / "broken.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
            refused = run_script("record_run.py", "--project", str(project), "--rerun", "RUN-Q1-001",
                                 "--run-id", "RUN-BAD", "--", sys.executable, "code/broken.py")
            self.assertNotEqual(refused.returncode, 0)
            self.assertFalse((project / "runs" / "RUN-BAD" / "RUN_MANIFEST.json").exists())
            _, summary = check_project(project, "computation")
            self.assertEqual(summary["superseded_run_ids"], [])

    def test_follow_lineage_ignores_a_failed_sibling(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            record_official(project)
            (project / "code" / "broken.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
            run_script("record_run.py", "--project", str(project), "--rerun", "RUN-Q1-001",
                       "--run-id", "RUN-BAD", "--", sys.executable, "code/broken.py")
            (project / "code" / "solve.py").write_text(SOLVER.replace("4.25", "0.5"), encoding="utf-8")
            run_script("record_run.py", "--project", str(project), "--rerun", "RUN-Q1-001", "--official",
                       "--run-id", "RUN-GOOD", "--assert-file", "results/assertions.json")
            moved = run_script("index_result.py", "--project", str(project), "--follow-lineage")
            self.assertEqual(moved.returncode, 0, moved.stdout + moved.stderr)
            index = json.loads((project / "results" / "RESULTS_INDEX.json").read_text(encoding="utf-8"))
            self.assertEqual(index["results"][0]["run_id"], "RUN-GOOD")

    def test_a_team_input_is_frozen_while_official_material_stays_in_place(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            (project / "data").mkdir(exist_ok=True)
            (project / "data" / "cleaned.csv").write_text("a,b\n1,2\n", encoding="utf-8")
            recorded = run_script(
                "record_run.py", "--project", str(project), "--run-id", "RUN-IN", "--official",
                "--capability", "CAP-Q1-001", "--source", "code/solve.py",
                "--input", "problem/official/problem.txt:formal",
                "--input", "data/cleaned.csv:formal",
                "--output", "results/q1_output.json:claim",
                "--assert-file", "results/assertions.json", "--", sys.executable, "code/solve.py",
            )
            self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)
            manifest = json.loads((project / "runs" / "RUN-IN" / "RUN_MANIFEST.json").read_text(encoding="utf-8"))
            by_path = {item["path"]: item for item in manifest["inputs"]}
            self.assertIn("problem/official/problem.txt", by_path)
            self.assertFalse(by_path["problem/official/problem.txt"]["frozen"])
            self.assertIn("runs/RUN-IN/inputs/data/cleaned.csv", by_path)
            self.assertTrue(by_path["runs/RUN-IN/inputs/data/cleaned.csv"]["frozen"])

            run_script("index_result.py", "--project", str(project), "--result-id", "RES-Q1-001",
                       "--run", "RUN-IN", "--locator", "results/q1_output.json#/minimum_cost",
                       "--name", "Minimum cost", "--unit", "cost", "--scope", "declared candidates only")
            # History remains intact, but this is no longer current official evidence.
            (project / "data" / "cleaned.csv").write_text("a,b\n9,9\n", encoding="utf-8")
            findings, _ = check_project(project, "computation")
            self.assertIn("RUN-E020", {item.rule_id for item in findings})
            self.assertEqual((project / "runs/RUN-IN/inputs/data/cleaned.csv").read_text(), "a,b\n1,2\n")


class LineageTests(unittest.TestCase):
    def test_two_successful_official_reruns_of_one_parent_are_ambiguous(self):
        """A fork is a judgement about the work, so the tool refuses instead of guessing."""
        import index_result
        runs = {
            "RUN-001": {"official_run": True, "status": "completed", "exit_code": 0,
                        "parent_run_id": None, "finished_at": "2026-09-01T10:00:00Z"},
            "RUN-002": {"official_run": True, "status": "completed", "exit_code": 0,
                        "parent_run_id": "RUN-001", "finished_at": "2026-09-01T11:00:00Z"},
            "RUN-003": {"official_run": True, "status": "completed", "exit_code": 0,
                        "parent_run_id": "RUN-001", "finished_at": "2026-09-01T12:00:00Z"},
        }
        with self.assertRaises(ValueError) as caught:
            index_result.newest_descendant(runs, "RUN-001")
        self.assertIn("ambiguous", str(caught.exception))
        self.assertIn("RUN-002", str(caught.exception))
        self.assertIn("RUN-003", str(caught.exception))
        # an unforked chain still resolves
        del runs["RUN-003"]
        self.assertEqual(index_result.newest_descendant(runs, "RUN-001"), "RUN-002")


class MachineDerivedEvidenceTests(unittest.TestCase):
    """What a run says about itself must come from the run, not from the caller."""

    def freeze_state(self, project: Path) -> None:
        state_path = project / ".cumcm" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["mode"] = "finalizing"
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def complete_model(self, project: Path) -> None:
        model_path = project / "model" / "MODEL_CONTRACT.json"
        model = json.loads(model_path.read_text(encoding="utf-8"))
        model["components"][0].update({
            "variables": [{"name": "candidate"}], "inputs": ["SRC-001"], "outputs": ["RES-Q1-001"],
            "verification_plan": ["enumeration coverage"],
        })
        model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def test_a_hand_typed_verdict_cannot_satisfy_a_verification_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            recorded = run_script(
                "record_run.py", "--project", str(project), "--run-id", "RUN-Q1-001", "--official",
                "--capability", "CAP-Q1-001", "--source", "code/solve.py",
                "--output", "results/q1_output.json:claim",
                "--assert", "enumeration coverage=pass",          # typed, not produced
                "--", sys.executable, "code/solve.py",
            )
            self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)
            manifest = json.loads((project / "runs" / "RUN-Q1-001" / "RUN_MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["assertions"][0]["source"], "declared")

            run_script("index_result.py", "--project", str(project), "--result-id", "RES-Q1-001",
                       "--run", "RUN-Q1-001", "--locator", "results/q1_output.json#/minimum_cost",
                       "--name", "Minimum cost", "--unit", "cost", "--scope", "declared candidates only")
            self.complete_model(project)
            working, _ = check_project(project, "computation")
            self.assertIn("RUN-W003", {item.rule_id for item in working})
            self.freeze_state(project)
            frozen, _ = check_project(project, "computation")
            self.assertIn("MODEL-E009", {item.rule_id for item in frozen})

    def test_a_verdict_the_run_wrote_itself_does_satisfy_it(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            record_official(project)
            manifest = json.loads((project / "runs" / "RUN-Q1-001" / "RUN_MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["assertions"][0]["source"], "recorded")
            self.complete_model(project)
            self.freeze_state(project)
            findings, _ = check_project(project, "computation")
            rules = {item.rule_id for item in findings}
            self.assertNotIn("MODEL-E009", rules)
            self.assertNotIn("RUN-W003", rules)

    def test_source_moving_under_a_running_command_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            (project / "code" / "self_editing.py").write_text(SELF_EDITING, encoding="utf-8")
            refused = run_script(
                "record_run.py", "--project", str(project), "--run-id", "RUN-DRIFT", "--official",
                "--capability", "CAP-Q1-001", "--source", "code/self_editing.py",
                "--output", "results/q1_output.json:claim",
                "--", sys.executable, "code/self_editing.py",
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("changed while the run was executing", refused.stderr)
            self.assertIn("code/self_editing.py", refused.stderr)
            self.assertFalse((project / "runs" / "RUN-DRIFT" / "RUN_MANIFEST.json").exists())

    def test_seeds_are_recorded_so_a_simulation_can_be_reproduced(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            recorded = run_script("record_run.py", "--project", str(project), "--run-id", "RUN-SEED",
                                  "--source", "code/solve.py", "--seed", "42", "--seed", "bootstrap=7",
                                  "--", sys.executable, "code/solve.py")
            self.assertEqual(recorded.returncode, 0, recorded.stdout + recorded.stderr)
            manifest = json.loads((project / "runs" / "RUN-SEED" / "RUN_MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["seeds"], [{"name": "seed", "value": "42", "source": "declared"}, {"name": "bootstrap", "value": "7", "source": "declared"}])


class CandidateSelectionTests(unittest.TestCase):
    """The full Problem Analysis -> candidates -> exploratory evaluation -> selection chain.

    Model Design proposes A and B with a reason and a discriminating observation;
    cheap exploratory runs evaluate each; one is selected with a rationale that
    cites those runs; only then does the selected model get an official run.
    """

    def with_candidates(self, project: Path, selected: str = "CAND-ENUM", **overrides) -> dict:
        model_path = project / "model" / "MODEL_CONTRACT.json"
        model = json.loads(model_path.read_text(encoding="utf-8"))
        component = model["components"][0]
        component["candidates"] = [
            {
                "candidate_id": "CAND-ENUM", "method": "complete enumeration",
                "why_considered": "the declared candidate set is finite and small",
                "discriminating_evidence": ["whether the greedy pick equals the enumerated minimum"],
                "status": "selected" if selected == "CAND-ENUM" else "rejected",
                "evaluation_run_ids": ["RUN-EVAL-ENUM"],
                "decision_rationale": "enumeration found a strictly lower cost than the greedy rule",
            },
            {
                "candidate_id": "CAND-GREEDY", "method": "greedy first-fit",
                "why_considered": "constant time, and adequate if the set is already ordered by cost",
                "discriminating_evidence": ["whether the greedy pick equals the enumerated minimum"],
                "status": "selected" if selected == "CAND-GREEDY" else "rejected",
                "evaluation_run_ids": ["RUN-EVAL-GREEDY"],
                "decision_rationale": "greedy returned 3.0 against the enumerated 1.5, so it is not admissible",
            },
        ]
        for key, value in overrides.items():
            for candidate in component["candidates"]:
                candidate[key] = value
        model_path.write_text(json.dumps(model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_accepted_snapshot(project, "model-design", ["model/MODEL_CONTRACT.json"])
        return model

    def evaluate_both(self, project: Path) -> None:
        (project / "code" / "greedy.py").write_text(GREEDY, encoding="utf-8")
        enum_run = run_script("record_run.py", "--project", str(project), "--run-id", "RUN-EVAL-ENUM",
                              "--candidate", "CAND-ENUM", "--purpose", "evaluate complete enumeration",
                              "--", sys.executable, "code/solve.py")
        greedy_run = run_script("record_run.py", "--project", str(project), "--run-id", "RUN-EVAL-GREEDY",
                                "--candidate", "CAND-GREEDY", "--purpose", "evaluate the greedy rule",
                                "--", sys.executable, "code/greedy.py")
        assert enum_run.returncode == 0, enum_run.stdout + enum_run.stderr
        assert greedy_run.returncode == 0, greedy_run.stdout + greedy_run.stderr

    def test_exploratory_runs_are_bound_to_the_candidate_they_evaluate(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            self.evaluate_both(project)
            manifest = json.loads((project / "runs" / "RUN-EVAL-GREEDY" / "RUN_MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["candidate_ids"], ["CAND-GREEDY"])
            self.assertFalse(manifest["official_run"])
            # both candidates were evaluated at zero declaration cost, while the project
            # is still in model-design and no formal result exists yet
            findings, _ = check_project(project, "model-design")
            self.assertEqual([item for item in findings if item.severity == "error"], [])
            self.assertEqual(
                sorted(path.parent.name for path in (project / "runs").glob("*/RUN_MANIFEST.json")),
                ["RUN-EVAL-ENUM", "RUN-EVAL-GREEDY"],
            )

    def test_the_selected_candidate_and_its_evidence_appear_in_the_report(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            self.evaluate_both(project)
            self.with_candidates(project)
            record_official(project)
            findings, summary = check_project(project, "computation")
            self.assertEqual([item for item in findings if item.severity == "error"], [])
            comparison = summary["model_candidates"][0]
            self.assertEqual(comparison["model_id"], "MODEL-Q1-001")
            statuses = {item["candidate_id"]: item["status"] for item in comparison["candidates"]}
            self.assertEqual(statuses, {"CAND-ENUM": "selected", "CAND-GREEDY": "rejected"})
            evidence = {item["candidate_id"]: item["evaluation_run_ids"] for item in comparison["candidates"]}
            self.assertEqual(evidence["CAND-ENUM"], ["RUN-EVAL-ENUM"])

    def test_a_selection_without_any_evaluation_run_is_flagged(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            self.evaluate_both(project)
            self.with_candidates(project, evaluation_run_ids=[])
            record_official(project)
            findings, _ = check_project(project, "computation")
            self.assertIn("MODEL-W014", {item.rule_id for item in findings})

    def test_two_selected_candidates_or_none_is_an_unresolved_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            self.evaluate_both(project)
            self.with_candidates(project, status="under_evaluation")
            done = run_script("record_run.py", "--project", str(project), "--official", "--", sys.executable, "code/solve.py")
            self.assertNotEqual(done.returncode, 0)
            self.assertIn("unresolved", done.stderr)
            findings, _ = check_project(project, "computation")
            self.assertIn("MODEL-E013", {item.rule_id for item in findings})

    def test_a_candidate_without_discriminating_evidence_is_flagged(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            self.evaluate_both(project)
            self.with_candidates(project, discriminating_evidence=[])
            record_official(project)
            findings, _ = check_project(project, "computation")
            self.assertIn("MODEL-W012", {item.rule_id for item in findings})

    def test_freezing_turns_an_unjustified_selection_into_a_blocking_error(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            self.evaluate_both(project)
            self.with_candidates(project, decision_rationale=None)
            record_official(project)
            working, _ = check_project(project, "computation")
            self.assertNotIn("MODEL-E014", {item.rule_id for item in working if item.severity == "error"})
            state_path = project / ".cumcm" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["mode"] = "finalizing"
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            frozen, _ = check_project(project, "computation")
            self.assertIn("MODEL-E014", {item.rule_id for item in frozen if item.severity == "error"})


class IterationTests(unittest.TestCase):
    def passed_state(self, project: Path, through: str) -> None:
        order = ["intake", "problem-analysis", "model-design", "computation"]
        state_path = project / ".cumcm" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for stage in order[: order.index(through) + 1]:
            state["stages"][stage] = "passed"
        state["current_stage"] = through
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def test_reopening_a_stage_is_one_command_and_invalidates_downstream(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            record_official(project)
            self.passed_state(project, "computation")
            for stage in ("intake", "problem-analysis", "model-design", "computation"):
                done = run_script("record_decision.py", "--project", str(project), "--stage", stage,
                                  "--decision", "accepted", "--decision-id", f"DEC-{stage}",
                                  "--reviewer", "fixture", "--task-turn-ref", "t1", "--summary", f"accepted {stage}")
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertTrue((project / ".cumcm" / "snapshots" / "computation.json").is_file())

            reopened = run_script("record_decision.py", "--project", str(project), "--stage", "model-design",
                                  "--decision", "revision_requested", "--decision-id", "DEC-REOPEN",
                                  "--reviewer", "fixture", "--task-turn-ref", "t2", "--summary", "model must change")
            self.assertEqual(reopened.returncode, 0, reopened.stdout + reopened.stderr)
            state = json.loads((project / ".cumcm" / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["current_stage"], "model-design")
            self.assertEqual(state["stages"]["model-design"], "needs_revision")
            self.assertEqual(state["stages"]["computation"], "needs_revision")
            self.assertFalse((project / ".cumcm" / "snapshots" / "computation.json").exists())
            self.assertTrue((project / ".cumcm" / "snapshots" / "intake.json").is_file())
            # Reopening requires renewed human review, not unrelated structural repair.
            findings, report = check_project(project, "computation", "preflight")
            self.assertEqual([item for item in findings if item.severity == "error" and not item.gate_only], [])
            self.assertEqual(report["gate_status"], "awaiting_review")

    def test_an_optional_contract_never_blocks_a_decision_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            self.assertFalse((project / "model" / "CROSS_QUESTION_LEDGER.json").exists())
            done = run_script("record_decision.py", "--project", str(project), "--stage", "model-design",
                              "--decision", "accepted", "--decision-id", "DEC-MD",
                              "--reviewer", "fixture", "--task-turn-ref", "t1", "--summary", "accepted")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_exploratory_runs_do_not_invalidate_an_accepted_computation_decision(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            record_official(project)
            self.passed_state(project, "computation")
            for stage in ("intake", "problem-analysis", "model-design", "computation"):
                run_script("record_decision.py", "--project", str(project), "--stage", stage,
                           "--decision", "accepted", "--decision-id", f"DEC-{stage}",
                           "--reviewer", "fixture", "--task-turn-ref", "t1", "--summary", "accepted")
            _, before = check_project(project, "computation")
            self.assertIn("computation", before["stages_with_current_decision"])
            run_script("record_run.py", "--project", str(project), "--run-id", "RUN-LATER",
                       "--", sys.executable, "code/solve.py")
            _, after = check_project(project, "computation")
            self.assertIn("computation", after["stages_with_current_decision"])


class CompileRecorderTests(unittest.TestCase):
    @unittest.skipIf(shutil.which("xelatex") is None, "xelatex is not installed")
    def test_record_compile_reads_page_count_hash_and_log_checks_from_the_engine(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            (project / "paper").mkdir(exist_ok=True)
            (project / "paper" / "main.tex").write_text(MINIMAL_TEX, encoding="utf-8")
            manifest = envelope("latex_template_manifest")
            manifest.update({
                "template_id": "test-minimal", "template_version": "0.6.0", "mode": "contest_ctex",
                "engine": "xelatex", "competition": "CUMCM", "competition_year": 2026,
                "official_compliance": "unverified", "official_template_source": None,
                "main_path": "paper/main.tex", "metadata_path": "paper/main.tex",
                "section_files": [], "subproblem_sections": [], "required_files": ["paper/main.tex"],
                "placeholder_markers": ["CUMCM-TODO"], "template_source": "test",
            })
            write_json(project, "paper/LATEX_TEMPLATE_MANIFEST.json", manifest)
            compiled = run_script("record_compile.py", "--project", str(project))
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            receipt = json.loads((project / "delivery" / "COMPILE_RECEIPT.json").read_text(encoding="utf-8"))
            attempt = receipt["attempts"][0]
            self.assertEqual(attempt["exit_code"], 0)
            self.assertEqual(attempt["page_count"], 1)
            self.assertEqual(attempt["glyph_check"], "pass")
            self.assertEqual(len(attempt["pdf_sha256"]), 64)
            self.assertEqual(receipt["source_snapshot"]["entrypoint"], "paper/main.tex")
            self.assertTrue((project / attempt["pdf_path"]).is_file())
            self.assertTrue((project / "delivery" / "compile.log").is_file())

    @unittest.skipIf(shutil.which("xelatex") is None, "xelatex is not installed")
    def test_update_quality_refreshes_the_layout_report_machine_fields(self):
        """The recorder writes the report block; nothing else may hand-write these."""
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            (project / "paper").mkdir(exist_ok=True)
            (project / "paper" / "main.tex").write_text(MINIMAL_TEX, encoding="utf-8")
            manifest = envelope("latex_template_manifest")
            manifest.update({
                "template_id": "test-minimal", "template_version": "0.6.0", "mode": "contest_ctex",
                "engine": "xelatex", "competition": "CUMCM", "competition_year": 2026,
                "official_compliance": "unverified", "official_template_source": None,
                "main_path": "paper/main.tex", "metadata_path": "paper/main.tex",
                "section_files": [], "subproblem_sections": [], "required_files": ["paper/main.tex"],
                "placeholder_markers": ["CUMCM-TODO"], "template_source": "test",
            })
            write_json(project, "paper/LATEX_TEMPLATE_MANIFEST.json", manifest)
            stale = {"path": "paper/main.pdf", "sha256": "0" * 64}
            quality = envelope("paper_quality_report")
            quality.update({
                "paper_status": "candidate",
                "paper_artifact": stale,
                "content_report": {"artifact": stale, "summary": "draft", "questions": [
                    {"subproblem_id": "Q1", "status": "pass", "notes": "answered"}]},
                "layout_report": {"artifact": stale, "page_count": 99, "rendered_pages": [], "checks": []},
                "open_issues": [],
            })
            write_json(project, "paper/PAPER_QUALITY_REPORT.json", quality)
            compiled = run_script("record_compile.py", "--project", str(project), "--update-quality")
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            self.assertIn("layout_report", compiled.stdout)
            refreshed = json.loads((project / "paper" / "PAPER_QUALITY_REPORT.json").read_text(encoding="utf-8"))
            layout = refreshed["layout_report"]
            self.assertEqual(layout["page_count"], 1)
            self.assertEqual(layout["rendered_pages"], [1])
            self.assertTrue(layout["checks"])
            self.assertNotEqual(layout["artifact"]["sha256"], stale["sha256"])
            self.assertEqual(refreshed["paper_artifact"], layout["artifact"])
            self.assertNotIn("layout_review", refreshed)

    @unittest.skipUnless(ctex_available(), "the ctex document class is not installed")
    def test_record_compile_derives_page_count_and_layout_checks_from_the_engine(self):
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            plan = envelope("paper_plan")
            plan.update({
                "authoring_task_ref": "fixture-paper-task",
                "claim_selection": [{"claim_id": "CLM-Q1-001", "subproblem_id": "Q1", "purpose": "answer Q1"}],
                "representation_plan": [],
                "paper_structure": [{"section_id": "SEC-Q1", "title": "候选集枚举", "purpose": "answer Q1",
                                     "subproblem_ids": ["Q1"], "claim_ids": ["CLM-Q1-001"]}],
            })
            write_json(project, "paper/PAPER_PLAN.json", plan)
            write_json(project, "validation/CLAIM_LEDGER.json", {
                "claims": [{"claim_id": "CLM-Q1-001"}],
                "conclusion_check": {"decision": "accepted", "reviewer_kind": "human_user",
                    "reviewer": "fixture-user", "reviewed_at": "2026-09-07", "presented_claim_ids": ["CLM-Q1-001"]}})
            write_accepted_snapshot(project, "validation", ["validation/CLAIM_LEDGER.json"])
            init = run_script("init_latex_paper.py", "--project", str(project), "--competition-year", "2026",
                              "--title", "候选集枚举下的最小成本", "--keywords", "枚举; 最小成本; 候选集")
            self.assertEqual(init.returncode, 0, init.stdout + init.stderr)
            compiled = run_script("record_compile.py", "--project", str(project))
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            receipt = json.loads((project / "delivery" / "COMPILE_RECEIPT.json").read_text(encoding="utf-8"))
            attempt = receipt["attempts"][0]
            self.assertEqual(attempt["exit_code"], 0)
            self.assertGreaterEqual(attempt["page_count"], 1)
            self.assertEqual(attempt["glyph_check"], "pass")
            self.assertTrue(attempt["pdf_sha256"])
            self.assertEqual(receipt["source_snapshot"]["entrypoint"], "paper/main.tex")
            self.assertTrue((project / attempt["pdf_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
