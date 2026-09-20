"""Cross-contest paper plumbing, not certification of any organizer's rules.

Fixtures contain synthetic approvals and claims; the compile/ZIP test uses real
tools. No contest project or user approval is created by these tests.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".agents/skills/cumcm-workflow/scripts"))

from init_latex_paper import initialize
from test_latex_template import build_inputs
from test_paper_pipeline import build_paper_ready_project
from recorder_fixtures import run_script
from workflow_fixtures import write_json
from workflow_checks import check_project, check_schema
from delivery_archives import build_archives, check_archives
from provenance import snapshot_matches


class CrossCompetitionTests(unittest.TestCase):
    def test_schema_accepts_other_competitions_but_rejects_blank_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_inputs(root)
            path = initialize(root, "Model comparison", 2026, "forecast; regression")
            manifest = json.loads(path.read_text())
            for competition in ("CUMCM", "MCM/ICM", "MathorCup", "华为杯", "Statistical Modeling"):
                manifest["competition"] = competition
                self.assertEqual(check_schema(manifest, "latex_template", "paper", "manifest"), [])
            for competition in ("", "   ", None):
                manifest["competition"] = competition
                self.assertTrue(check_schema(manifest, "latex_template", "paper", "manifest"))

    def test_cli_selects_english_scaffold_and_preserves_real_competition(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_inputs(root)
            done = run_script("init_latex_paper.py", "--project", str(root),
                              "--competition", "MCM/ICM", "--language", "en",
                              "--competition-year", "2026", "--title", "Demand under uncertainty",
                              "--keywords", "demand; uncertainty")
            self.assertEqual(done.returncode, 0, done.stderr)
            manifest = json.loads((root / "paper/LATEX_TEMPLATE_MANIFEST.json").read_text())
            self.assertEqual(manifest["competition"], "MCM/ICM")
            self.assertEqual(manifest["mode"], "contest_article")
            self.assertEqual(manifest["official_compliance"], "unverified")
            self.assertEqual(manifest["template_source"],
                             f"repo_asset:{manifest['template_id']}@{manifest['template_version']}")
            self.assertEqual(check_schema(manifest, "latex_template", "paper", "manifest"), [])

    def test_defaults_keep_existing_cumcm_interface(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_inputs(root)
            manifest = json.loads(initialize(root, "Model comparison", 2026, "regression").read_text())
            self.assertEqual(manifest["competition"], "CUMCM")
            self.assertEqual(manifest["mode"], "contest_ctex")
            self.assertEqual(manifest["schema_version"], "0.6.0")

    def test_invalid_options_write_no_paper_sources(self):
        for competition, language in ((" ", "en"), ("MCM\nICM", "en"), ("MCM", "fr")):
            with self.subTest(competition=competition, language=language), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                build_inputs(root)
                with self.assertRaises(ValueError):
                    initialize(root, "Model comparison", 2026, "regression",
                               competition=competition, language=language)
                self.assertFalse((root / "paper/main.tex").exists())

    def test_english_initialization_still_requires_current_human_checkpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_inputs(root)
            (root / ".cumcm/snapshots/validation.json").unlink()
            with self.assertRaises(ValueError):
                initialize(root, "Model comparison", 2026, "regression", competition="MCM", language="en")
            self.assertFalse((root / "paper/main.tex").exists())

    def test_official_template_priority_and_no_overwrite_apply_in_both_languages(self):
        for language in ("zh", "en"):
            with self.subTest(language=language), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                build_inputs(root)
                write_json(root, "problem/SOURCE_MANIFEST.json", {"sources": [{
                    "path": "problem/official/template.tex", "origin": "official",
                    "authoritative_for": ["paper_template"],
                }]})
                with self.assertRaisesRegex(ValueError, "official paper template"):
                    initialize(root, "Model comparison", 2026, "regression", competition="APMCM", language=language)
                self.assertFalse((root / "paper/main.tex").exists())
                (root / "problem/SOURCE_MANIFEST.json").unlink()
                initialize(root, "Model comparison", 2026, "regression", competition="APMCM", language=language)
                before = (root / "paper/main.tex").read_bytes()
                with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                    initialize(root, "Another model", 2026, "regression", competition="MCM", language=language)
                self.assertEqual(before, (root / "paper/main.tex").read_bytes())

    def test_non_cumcm_finalizing_keeps_compliance_and_stale_review_gates(self):
        for competition, language in (("MCM/ICM", "en"), ("MathorCup", "zh"), ("Statistical Modeling", "zh")):
            with self.subTest(competition=competition), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                build_paper_ready_project(root, competition=competition, language=language)
                findings, summary = check_project(root, "delivery", "enforce")
                self.assertEqual([f for f in findings if f.severity == "error"], [])
                self.assertEqual(summary["gate_status"], "passed")
                path = root / "paper/LATEX_TEMPLATE_MANIFEST.json"
                manifest = json.loads(path.read_text())
                manifest["official_compliance"] = "unverified"
                write_json(root, "paper/LATEX_TEMPLATE_MANIFEST.json", manifest)
                findings, summary = check_project(root, "delivery", "enforce")
                self.assertIn("LATEX-E009", {f.rule_id for f in findings})
                self.assertNotEqual(summary["gate_status"], "passed")
                manifest["official_compliance"] = "verified_against_current_rules"
                manifest["competition"] = "Changed competition"
                write_json(root, "paper/LATEX_TEMPLATE_MANIFEST.json", manifest)
                findings, summary = check_project(root, "delivery", "enforce")
                self.assertNotEqual(summary["gate_status"], "passed")
                self.assertTrue(any(f.rule_id.startswith(("DECISION-", "HANDOFF-")) for f in findings))

    @unittest.skipUnless(all(shutil.which(tool) for tool in ("xelatex", "pdfinfo", "pdftoppm", "pdftotext")),
                         "XeLaTeX and Poppler are required for real compile/render/packaging")
    def test_english_scaffold_compiles_renders_and_packages_bound_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_inputs(root, problem_ids=("Q1",))
            initialize(root, "Demand under uncertainty", 2026, "demand; uncertainty", competition="MCM/ICM", language="en")
            done = run_script("record_compile.py", "--project", str(root))
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            receipt = json.loads((root / "delivery/COMPILE_RECEIPT.json").read_text())
            attempt = receipt["attempts"][0]
            self.assertEqual(attempt["glyph_check"], "pass")
            self.assertEqual(attempt["font_check"], "pass")
            self.assertFalse(attempt["warnings"])
            self.assertGreater(attempt["page_count"], 0)
            self.assertTrue(snapshot_matches(root, receipt["source_snapshot"]))
            self.assertEqual(len(list((root / ".cumcm/tmp/pages").glob('*.png'))), attempt["page_count"])
            text = subprocess.check_output(["pdftotext", str(root / attempt["pdf_path"]), "-"], text=True)
            self.assertIn("Abstract", text)
            self.assertIn("Keywords", text)
            self.assertIn("Demand under uncertainty", text)
            self.assertNotIn("CUMCM", text)
            self.assertFalse(any('\u4e00' <= c <= '\u9fff' for c in text))
            delivery = {"files": [], "deliverables": {"editable_latex_source": {
                "archive": "delivery/paper-source.zip", "entrypoint": "paper/main.tex",
            }}}
            build_archives(root, delivery)
            self.assertEqual(check_archives(root, delivery), [])
            with zipfile.ZipFile(root / "delivery/paper-source.zip") as archive:
                self.assertTrue(set(receipt["source_snapshot"]["files"]).issubset(archive.namelist()))
                self.assertEqual(archive.read("paper/main.tex"), (root / "paper/main.tex").read_bytes())
            (root / "paper/macros.tex").write_text("% changed after compile\n")
            with self.assertRaisesRegex(ValueError, "stale"):
                build_archives(root, delivery)


if __name__ == "__main__":
    unittest.main()
