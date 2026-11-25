"""A rate correction must propagate from declared inputs to the compiled paper."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from recorder_fixtures import make_project, run_script, write_json
from provenance import sha256_file


VOLUME_SOLVER = """import json
from pathlib import Path
days = json.loads(Path("days.json").read_bytes())
Path("results/volume.json").write_text(json.dumps({"average": sum(days) / len(days)}))
"""

FEE_SOLVER = """import json
from pathlib import Path
days = json.loads(Path("days.json").read_bytes())
rate = json.loads(Path("rate.json").read_bytes())
fee = sum(days) * rate
Path("results/fees.json").write_text(json.dumps({"freight": fee, "net": 180 - fee}))
"""

# These are paper labels and dependency links. All numbers printed in the paper
# are read from the result index produced by the shipped CLI.
QUESTIONS = (
    ("Q1", "Average", "volume.json#/average", "RUN-VOLUME", "items/day"),
    ("Q2", "Freight", "fees.json#/freight", "RUN-FEE", "yuan"),
    ("Q3", "Net", "fees.json#/net", "RUN-FEE", "yuan"),
)


@unittest.skipUnless(shutil.which("xelatex") and shutil.which("pdftotext"),
                     "the PDF integration test requires XeLaTeX and Poppler")
class FeeRevisionPipelineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = make_project(Path(temp.name))

    def cli(self, name, *args):
        process = run_script(name, "--project", str(self.root), *args)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        return process.stdout

    def index(self):
        rows = json.loads((self.root / "results/RESULTS_INDEX.json").read_bytes())["results"]
        return {row["result_id"]: row for row in rows}

    def write_sections(self, paths):
        index = self.index()
        for question, label, _, _, unit in QUESTIONS:
            path = f"paper/{question}.tex"
            if path in paths:
                value = index[f"RES-{question}"]["value"]
                (self.root / path).write_text(f"{label}: {value:g} {unit}.\\par\n", encoding="utf-8")

    def compile_and_read(self):
        self.cli("record_compile.py", "--no-render")
        receipt = json.loads((self.root / "delivery/COMPILE_RECEIPT.json").read_bytes())
        attempt = next(a for a in receipt["attempts"] if a["attempt_id"] == receipt["selected_attempt_id"])
        pdf = self.root / attempt["pdf_path"]
        self.assertEqual(attempt["pdf_sha256"], sha256_file(pdf))
        return subprocess.check_output(["pdftotext", str(pdf), "-"]).decode("utf-8").splitlines()

    def test_rate_change_reaches_the_pdf_without_replacing_the_volume_run(self):
        write_json(self.root, "days.json", [10, 30])
        write_json(self.root, "rate.json", 3)
        (self.root / "code/volume.py").write_text(VOLUME_SOLVER, encoding="utf-8")
        (self.root / "code/fees.py").write_text(FEE_SOLVER, encoding="utf-8")
        for run, stem, inputs, capabilities in (
            ("RUN-VOLUME", "volume", ["days.json"], ["Q1"]),
            ("RUN-FEE", "fees", ["days.json", "rate.json"], ["Q2", "Q3"]),
        ):
            arguments = []
            for path in inputs:
                arguments.extend(["--input", path + ":formal"])
            for question in capabilities:
                arguments.extend(["--capability", "CAP-" + question])
            source = f"code/{stem}.py"
            self.cli("record_run.py", "--official", "--run-id", run, "--source", source,
                     "--output", f"results/{stem}.json:claim", *arguments, "--", sys.executable, source)

        claims, sections, mappings = [], [], []
        for question, label, locator, run, unit in QUESTIONS:
            self.cli("index_result.py", "--result-id", f"RES-{question}", "--run", run,
                     "--locator", "results/" + locator, "--name", label, "--unit", unit, "--scope", "two days")
            claim = "CLM-" + question
            claims.append({"claim_id": claim, "evidence": {"result_ids": ["RES-" + question]}})
            sections.append({"subproblem_ids": [question], "claim_ids": [claim]})
            mappings.append({"subproblem_id": question, "path": f"paper/{question}.tex"})

        write_json(self.root, "validation/CLAIM_LEDGER.json", {"claims": claims})
        write_json(self.root, "paper/PAPER_PLAN.json", {"paper_structure": sections})
        paths = [m["path"] for m in mappings]
        write_json(self.root, "paper/LATEX_TEMPLATE_MANIFEST.json", {
            "engine": "xelatex", "main_path": "paper/main.tex", "required_files": ["paper/main.tex", *paths],
            "section_files": paths, "subproblem_sections": mappings,
        })
        (self.root / "paper/main.tex").write_text(
            r"\documentclass{article}\begin{document}\input{Q1}\input{Q2}\input{Q3}\end{document}",
            encoding="utf-8")
        self.write_sections(paths)
        before = self.compile_and_read()
        self.assertTrue({"Average: 20 items/day.", "Freight: 120 yuan.", "Net: 60 yuan."} <= set(before), before)
        volume_row = self.index()["RES-Q1"]
        first_section = (self.root / "paper/Q1.tex").read_bytes()

        write_json(self.root, "rate.json", 4)
        plan = json.loads(self.cli("plan_redo.py", "--changed", "rate.json", "--json"))
        self.assertEqual(plan["stale_official_runs"], ["RUN-FEE"])
        self.assertEqual(plan["stale_results"], ["RES-Q2", "RES-Q3"])
        self.assertEqual(plan["stale_claims"], ["CLM-Q2", "CLM-Q3"])
        self.assertEqual(plan["stale_sections"], ["paper/Q2.tex", "paper/Q3.tex"])
        self.cli("record_run.py", "--rerun", "RUN-FEE", "--run-id", "RUN-FEE-NEW", "--official")
        self.cli("index_result.py", "--follow-lineage")
        index = self.index()
        self.assertEqual(index["RES-Q1"], volume_row)
        for result_id in ("RES-Q2", "RES-Q3"):
            self.assertEqual(index[result_id]["run_id"], "RUN-FEE-NEW")
            self.assertTrue(index[result_id]["output_locator"].startswith("runs/RUN-FEE-NEW/outputs/"))

        self.write_sections(plan["stale_sections"])
        after = self.compile_and_read()
        self.assertEqual((self.root / "paper/Q1.tex").read_bytes(), first_section)
        self.assertTrue({"Average: 20 items/day.", "Freight: 160 yuan.", "Net: 20 yuan."} <= set(after), after)
        self.assertNotIn("Freight: 120 yuan.", after)
        self.assertNotIn("Net: 60 yuan.", after)
