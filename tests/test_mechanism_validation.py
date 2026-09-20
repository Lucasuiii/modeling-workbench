"""Package regression tests and executable examples for scoped validation.

The examples demonstrate falsifiable checks through the recorder, not an LLM
benchmark. Only package integration tests are expected to fail on the baseline.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents/skills/cumcm-workflow"
sys.path.insert(0, str(SKILL / "scripts"))

import build_independent_review_package as builder
from provenance import sha256_file
from recorder_fixtures import make_project, run_script
from workflow_fixtures import build_valid_project, write_accepted_snapshot
from workflow_checks import check_independent_review_package, check_independent_review_result, check_project


class MechanismPackageTests(unittest.TestCase):
    def prepare(self, root):
        build_valid_project(root)
        shutil.rmtree(root / builder.PACKAGE_REL)
        path = builder.build(root)
        return json.loads(path.read_text())

    def test_guide_is_canonical_frozen_and_tamper_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = self.prepare(root)
            rel = (builder.PACKAGE_REL / "mechanism-validation.md").as_posix()
            record = next(item for item in manifest["files"] if item["path"] == rel)
            copied = root / rel
            self.assertEqual(copied.read_bytes(), (SKILL / "references/mechanism-validation.md").read_bytes())
            self.assertEqual(record["sha256"], sha256_file(copied))
            self.assertEqual(record["role"], "review_instruction")
            self.assertNotIn("source_path", record)  # no false project-relative source
            rules = lambda: {f.rule_id for f in check_independent_review_package(manifest, root, "package")}
            self.assertEqual(rules(), {"IREVIEW-E005"})  # reviewer still unselected
            copied.write_text(copied.read_text() + "\nChanged instruction.\n")
            self.assertTrue({"IREVIEW-E015", "IREVIEW-E016"}.issubset(rules()))

    def test_rebuild_with_changed_canonical_guide_stales_old_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "project"
            root.mkdir()
            before = self.prepare(root)
            review = json.loads((root / "validation/INDEPENDENT_REVIEW_RESULT.json").read_text())
            review["package_digest"] = before["package_digest"]
            self.assertNotIn("IREVIEW-E019", {f.rule_id for f in check_independent_review_result(review, root, "review", before)})
            # Isolated installed skill: never modify the actual canonical source.
            installed = Path(temp) / "installed"
            shutil.copytree(SKILL / "assets", installed / "assets")
            shutil.copytree(SKILL / "references", installed / "references")
            guide = installed / "references/mechanism-validation.md"
            guide.write_text(guide.read_text() + "\nRevised tolerance guidance.\n")
            with mock.patch.object(builder, "__file__", str(installed / "scripts/build_independent_review_package.py")):
                after = json.loads(builder.build(root, refresh=True).read_text())
            self.assertNotEqual(before["package_digest"], after["package_digest"])
            self.assertEqual(before["upstream_digest"], after["upstream_digest"])
            self.assertIn("IREVIEW-E019", {f.rule_id for f in check_independent_review_result(review, root, "review", after)})
            self.assertEqual({f.rule_id for f in check_independent_review_package(after, root, "package")}, {"IREVIEW-E005"})


class MechanismDryRunTests(unittest.TestCase):
    def exercise(self, mechanism):
        for variant in ("bad", "good", "not_applicable"):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as temp:
                project = make_project(Path(temp))
                # Synthetic approval belongs only to this test fixture.
                cap_path = project / "analysis/TASK_CAPABILITIES.json"
                caps = json.loads(cap_path.read_text())
                caps["capabilities"][0]["acceptance_checks"][0]["assertion_name"] = "answer matches scoped definition"
                cap_path.write_text(json.dumps(caps))
                model_path = project / "model/MODEL_CONTRACT.json"
                model = json.loads(model_path.read_text())
                model["components"][0]["verification_plan"] = ["answer matches scoped definition"]
                model_path.write_text(json.dumps(model))
                write_accepted_snapshot(project, "model-design", ["model/MODEL_CONTRACT.json"])
                shutil.copy2(ROOT / "tests/fixtures/mechanism_probe.py", project / "code/solve.py")
                done = run_script("record_run.py", "--project", str(project), "--official",
                    "--run-id", "RUN-PROBE", "--capability", "CAP-Q1-001", "--source", "code/solve.py",
                    "--output", "results/answer.json:claim", "--output", "results/diagnostics.json:diagnostic",
                    "--assert-file", "results/assertions.json", "--", sys.executable, "code/solve.py", mechanism, variant)
                self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
                run = json.loads((project / "runs/RUN-PROBE/RUN_MANIFEST.json").read_text())
                assertions = {a["name"]: a for a in run["assertions"]}
                self.assertTrue(assertions["weak check"]["passed"])
                measured = assertions["answer matches scoped definition"]
                self.assertEqual(measured["source"], "recorded")
                self.assertEqual(measured["passed"], variant != "bad")
                caps["capabilities"][0]["lifecycle_state"] = "executed"
                cap_path.write_text(json.dumps(caps))
                findings, _ = check_project(project, "computation")
                for rule in ("CAP-E012", "RUN-E008"):
                    self.assertEqual(rule in {f.rule_id for f in findings}, variant == "bad")

    def test_continuous_tangent_event(self):
        self.exercise("event")

    def test_exported_discrete_plan(self):
        self.exercise("rounding")

    def test_grouped_evaluation_unit(self):
        self.exercise("groups")


if __name__ == "__main__":
    unittest.main()
