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


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ValidatorTests(unittest.TestCase):
    def test_inventory_hashes_files_and_excludes_output(self):
        module = load("inventory_artifacts")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "problem.pdf").write_bytes(b"official")
            output = root / "SOURCE_MANIFEST.json"
            records = module.inventory(root, output)
            self.assertEqual([r["path"] for r in records], ["problem.pdf"])
            self.assertEqual(records[0]["sha256"], hashlib.sha256(b"official").hexdigest())

    def test_source_inventory_uses_project_relative_paths_and_source_ids(self):
        module = load("inventory_artifacts")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            official = root / "problem" / "official"
            official.mkdir(parents=True)
            (official / "B.pdf").write_bytes(b"official")
            output = root / "problem" / "SOURCE_MANIFEST.json"
            records = module.inventory_sources(official, root, output, "official")
            self.assertEqual(records[0]["source_id"], "SRC-001")
            self.assertEqual(records[0]["path"], "problem/official/B.pdf")
            self.assertEqual(records[0]["media_type"], "application/pdf")
            self.assertFalse(records[0]["mutable"])

    def test_inventory_cli_emits_current_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            official = root / "problem" / "official"
            official.mkdir(parents=True)
            (official / "B.pdf").write_bytes(b"official")
            output = root / "problem" / "SOURCE_MANIFEST.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "inventory_artifacts.py"),
                    "--root",
                    str(official),
                    "--output",
                    str(output),
                    "--project-root",
                    str(root),
                    "--project-id",
                    "TEST-2026-B",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "0.8.0")


if __name__ == "__main__":
    unittest.main()
