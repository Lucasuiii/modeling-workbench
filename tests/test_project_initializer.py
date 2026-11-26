from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".agents" / "skills" / "cumcm-workflow" / "scripts"


def load_initializer():
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("init_project", SCRIPTS / "init_project.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ProjectInitializerTests(unittest.TestCase):
    def test_startup_authority_is_scoped_and_requires_an_explicit_reply(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            official = root / "problem.txt"
            official.write_text("synthetic input", encoding="utf-8")
            project = root / "workspace"
            command = [sys.executable, str(SCRIPTS / "init_project.py"), "--project", str(project),
                       "--project-id", "example", "--official", str(official), "--delegate-stage", "model-design",
                       "--delegate-stage", "validation"]
            missing = subprocess.run(command, capture_output=True)
            self.assertNotEqual(missing.returncode, 0)
            self.assertFalse(project.exists())
            subprocess.run([*command, "--user-turn-ref", "startup-reply"], check=True, capture_output=True)
            directory = project / ".cumcm/delegations"
            self.assertEqual({p.stem for p in directory.glob("*.json")}, {"model-design", "validation"})
            for path in directory.glob("*.json"):
                grant = json.loads(path.read_bytes())
                self.assertEqual((grant["stage"], grant["user_turn_ref"]), (path.stem, "startup-reply"))
            status = subprocess.run([sys.executable, str(SCRIPTS / "project_status.py"),
                                     "--project", str(project), "--json"], check=True, capture_output=True)
            report = json.loads(status.stdout)
            self.assertEqual(report["current_stage"], "intake")
            self.assertEqual(report["decision_owners"], {"model-design": "delegated_lead_agent",
                             "validation": "delegated_lead_agent", "delivery": "human_user"})
            self.assertFalse((project / ".cumcm/decisions.jsonl").exists())

    def test_one_command_creates_complete_intake_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            official = root / "official"
            (official / "attachments").mkdir(parents=True)
            problem_bytes = b"synthetic official statement"
            data_bytes = b"x,y\n1,2\n"
            (official / "B.txt").write_bytes(problem_bytes)
            (official / "attachments" / "data.csv").write_bytes(data_bytes)
            (official / ".DS_Store").write_bytes(b"metadata")
            project = root / "project"

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "init_project.py"),
                    "--project", str(project),
                    "--project-id", "CUMCM-2026-B",
                    "--official", str(official),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("intake preflight: working_ready", completed.stdout)
            expected_directories = {
                ".cumcm/tmp", ".cumcm/snapshots", "problem/official", "analysis", "model", "code", "data",
                "runs", "results", "validation", "figures", "paper", "delivery", "handoffs",
            }
            for rel in expected_directories:
                self.assertTrue((project / rel).is_dir(), rel)
            self.assertFalse((project / "problem" / "official" / ".DS_Store").exists())

            state = json.loads((project / ".cumcm" / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["workflow_version"], "0.6.0")
            self.assertEqual(state["mode"], "working")
            self.assertEqual(state["implementation"], {"preferred": "matlab", "fallback": "python", "selection": "auto"})
            self.assertEqual(state["current_stage"], "intake")
            self.assertEqual(state["stages"]["intake"], "in_progress")
            self.assertTrue(all(
                status == "not_started"
                for stage, status in state["stages"].items()
                if stage != "intake"
            ))

            manifest = json.loads((project / "problem" / "SOURCE_MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual([item["source_id"] for item in manifest["sources"]], ["SRC-001", "SRC-002"])
            by_path = {item["path"]: item for item in manifest["sources"]}
            self.assertEqual(
                by_path["problem/official/B.txt"]["sha256"],
                hashlib.sha256(problem_bytes).hexdigest(),
            )
            self.assertEqual(
                by_path["problem/official/attachments/data.csv"]["sha256"],
                hashlib.sha256(data_bytes).hexdigest(),
            )
            self.assertTrue(all(item["mutable"] is False for item in manifest["sources"]))
            self.assertTrue(all(item["origin"] == "official" for item in manifest["sources"]))

            init_report = json.loads((project / ".cumcm" / "init-report.json").read_text(encoding="utf-8"))
            self.assertEqual(init_report["source_count"], 2)
            self.assertEqual(init_report["gate_status"], "working_ready")
            self.assertEqual(init_report["skipped_source_metadata"], [".DS_Store"])
            validation = json.loads((project / ".cumcm" / "validation-report.json").read_text(encoding="utf-8"))
            self.assertEqual(validation["project_root"], str(project.resolve()))
            self.assertEqual(validation["summary"]["blocking_error_count"], 0)
            self.assertEqual(validation["summary"]["gate_status"], "working_ready")

    def test_initializer_does_not_modify_official_inputs(self):
        module = load_initializer()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            official = root / "official"
            official.mkdir()
            source = official / "problem.pdf"
            source.write_bytes(b"immutable official bytes")
            before = source.read_bytes()
            module.initialize(root / "project", "TEST-2026-A", official)
            self.assertEqual(source.read_bytes(), before)

    def test_existing_nonempty_target_is_rejected_without_changes(self):
        module = load_initializer()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            official = root / "official"
            official.mkdir()
            (official / "problem.txt").write_text("problem", encoding="utf-8")
            project = root / "project"
            project.mkdir()
            retained = project / "keep.txt"
            retained.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                module.initialize(project, "TEST-2026-A", official)
            self.assertEqual(retained.read_text(encoding="utf-8"), "keep")
            self.assertEqual(list(project.iterdir()), [retained])

    def test_empty_target_is_supported(self):
        module = load_initializer()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            official = root / "problem.txt"
            official.write_text("problem", encoding="utf-8")
            project = root / "project"
            project.mkdir()
            result = module.initialize(project, "TEST-2026-A", official)
            self.assertEqual(result["source_count"], 1)
            self.assertTrue((project / "problem" / "official" / "problem.txt").is_file())
            report = json.loads((project / ".cumcm" / "init-report.json").read_text(encoding="utf-8"))

    def test_empty_official_directory_is_rejected_without_project(self):
        module = load_initializer()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            official = root / "official"
            official.mkdir()
            project = root / "project"
            with self.assertRaisesRegex(ValueError, "no usable files"):
                module.initialize(project, "TEST-2026-A", official)
            self.assertFalse(project.exists())

    def test_symlink_in_official_tree_is_rejected(self):
        module = load_initializer()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outside = root / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            official = root / "official"
            official.mkdir()
            (official / "problem.txt").write_text("problem", encoding="utf-8")
            (official / "linked.txt").symlink_to(outside)
            project = root / "project"
            with self.assertRaisesRegex(ValueError, "symlinks"):
                module.initialize(project, "TEST-2026-A", official)
            self.assertFalse(project.exists())


if __name__ == "__main__":
    unittest.main()
