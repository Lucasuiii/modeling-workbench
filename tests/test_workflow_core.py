from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".agents" / "skills" / "cumcm-workflow" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from workflow_checks import check_project  # noqa: E402
from provenance import digest_records, tree_snapshot  # noqa: E402


from workflow_fixtures import digest, review, envelope, write_json, write_accepted_snapshot, build_valid_project

class WorkflowCoreTests(unittest.TestCase):
    def run_check(self, root: Path):
        findings, summary = check_project(root, "validation")
        return findings, summary

    def test_complete_project_passes_without_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            findings, summary = self.run_check(root)
            self.assertEqual([f for f in findings if f.severity == "error"], [])
            self.assertEqual(summary["run_count"], 1)

    def test_all_json_schemas_are_valid_draft_2020_12(self):
        schema_dir = ROOT / ".agents" / "skills" / "cumcm-workflow" / "schemas"
        schemas = sorted(schema_dir.glob("*.schema.json"))
        expected = {
            "claim-ledger.schema.json",
            "common.schema.json",
            "compile-receipt.schema.json",
            "cross-question-ledger.schema.json",
            "delivery-manifest.schema.json",
            "figure-manifest.schema.json",
            "independent-review-package.schema.json",
            "independent-review-result.schema.json",
            "latex-template-manifest.schema.json",
            "model-contract.schema.json",
            "paper-plan.schema.json",
            "paper-quality-report.schema.json",
            "paper-revision-log.schema.json",
            "paper-visible-text-report.schema.json",
            "problem-facts.schema.json",
            "results-index.schema.json",
            "run-manifest.schema.json",
            "source-manifest.schema.json",
            "task-capabilities.schema.json",
            "workflow-state.schema.json",
            "handoff.schema.json",
        }
        self.assertEqual({path.name for path in schemas}, expected)
        for path in schemas:
            with self.subTest(schema=path.name):
                Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))

    def test_dispatcher_writes_machine_readable_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "cumcm_check.py"),
                    "--project",
                    str(root),
                    "--stage",
                    "validation",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            report = json.loads((root / ".cumcm" / "validation-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["finding_counts"]["error"], 0)
            self.assertIn("does not prove mathematical correctness", report["summary"]["evidence_boundary"])

    def test_source_hash_change_is_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            (root / "problem" / "official" / "problem.txt").write_text("changed", encoding="utf-8")
            findings, _ = self.run_check(root)
            self.assertIn("SOURCE-E008", {item.rule_id for item in findings})

    def test_source_size_mismatch_is_warning_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            path = root / "problem" / "SOURCE_MANIFEST.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["sources"][0]["size"] += 1
            write_json(root, "problem/SOURCE_MANIFEST.json", data)
            findings, _ = self.run_check(root)
            finding_by_rule = {item.rule_id: item for item in findings}
            self.assertEqual(finding_by_rule["SOURCE-W009"].severity, "warning")
            self.assertEqual(
                [item for item in findings if item.severity == "error" and item.rule_id != "DECISION-E010"],
                [],
            )

    def test_nonofficial_source_may_omit_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            reference = root / "problem" / "references" / "background.txt"
            reference.parent.mkdir(parents=True)
            reference.write_text("user supplied background reference\n", encoding="utf-8")
            path = root / "problem" / "SOURCE_MANIFEST.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["sources"].append(
                {
                    "source_id": "SRC-REF-001",
                    "path": "problem/references/background.txt",
                    "size": reference.stat().st_size,
                    "media_type": "text/plain",
                    "origin": "external_reference",
                    "acquisition": {
                        "method": "user_local_file",
                        "provided_by_user": True,
                        "source_reference": None,
                    },
                    "authoritative_for": [],
                    "derived_from": None,
                    "mutable": True,
                }
            )
            write_json(root, "problem/SOURCE_MANIFEST.json", data)
            findings, _ = self.run_check(root)
            source_errors = [item for item in findings if item.rule_id.startswith("SOURCE-") and item.severity == "error"]
            self.assertEqual(source_errors, [])

    def test_fact_cannot_cite_an_unknown_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            path = root / "analysis" / "PROBLEM_FACTS.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["facts"][0]["source_id"] = "SRC-UNKNOWN"
            write_json(root, "analysis/PROBLEM_FACTS.json", data)
            findings, _ = self.run_check(root)
            self.assertIn("FACT-E006", {item.rule_id for item in findings})

    def test_implemented_capability_code_entry_must_exist(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            path = root / "analysis" / "TASK_CAPABILITIES.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["capabilities"][0]["code_entry_points"] = ["code/missing.py:main"]
            write_json(root, "analysis/TASK_CAPABILITIES.json", data)
            findings, _ = self.run_check(root)
            self.assertIn("CAP-E011", {item.rule_id for item in findings})

    def test_run_output_hash_must_match(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            path = root / "runs" / "RUN-Q1-001" / "RUN_MANIFEST.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["outputs"][0]["sha256"] = "0" * 64
            write_json(root, "runs/RUN-Q1-001/RUN_MANIFEST.json", data)
            findings, _ = self.run_check(root)
            self.assertIn("RUN-E007", {item.rule_id for item in findings})

    def test_run_size_mismatch_is_warning_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            path = root / "runs" / "RUN-Q1-001" / "RUN_MANIFEST.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["outputs"][0]["size"] += 1
            write_json(root, "runs/RUN-Q1-001/RUN_MANIFEST.json", data)
            findings, _ = self.run_check(root)
            finding_by_rule = {item.rule_id: item for item in findings}
            self.assertEqual(finding_by_rule["RUN-W013"].severity, "warning")
            self.assertEqual(
                [item for item in findings if item.severity == "error" and item.rule_id != "DECISION-E010"],
                [],
            )

    def test_auxiliary_input_and_intermediate_output_may_omit_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            auxiliary = root / "runs" / "RUN-Q1-001" / "notes.txt"
            intermediate = root / "runs" / "RUN-Q1-001" / "outputs" / "preview.txt"
            auxiliary.write_text("non-result-affecting note\n", encoding="utf-8")
            intermediate.write_text("presentation preview\n", encoding="utf-8")
            path = root / "runs" / "RUN-Q1-001" / "RUN_MANIFEST.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["inputs"].append(
                {
                    "path": "runs/RUN-Q1-001/notes.txt",
                    "evidence_role": "auxiliary_input",
                    "size": auxiliary.stat().st_size,
                    "media_type": "text/plain",
                }
            )
            data["outputs"].append(
                {
                    "path": "runs/RUN-Q1-001/outputs/preview.txt",
                    "evidence_role": "intermediate_output",
                    "size": intermediate.stat().st_size,
                    "media_type": "text/plain",
                }
            )
            write_json(root, "runs/RUN-Q1-001/RUN_MANIFEST.json", data)
            findings, _ = self.run_check(root)
            self.assertEqual(
                [item for item in findings if item.severity == "error" and item.rule_id != "DECISION-E010"],
                [],
            )

    def test_run_records_require_explicit_evidence_roles(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            path = root / "runs" / "RUN-Q1-001" / "RUN_MANIFEST.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["inputs"][0].pop("evidence_role")
            data["outputs"][0].pop("evidence_role")
            write_json(root, "runs/RUN-Q1-001/RUN_MANIFEST.json", data)
            findings, _ = self.run_check(root)
            self.assertIn("SCHEMA-E002", {item.rule_id for item in findings})

    def test_indexed_result_must_use_claim_bearing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            path = root / "runs" / "RUN-Q1-001" / "RUN_MANIFEST.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["outputs"][0]["evidence_role"] = "intermediate_output"
            data["outputs"][0].pop("sha256")
            write_json(root, "runs/RUN-Q1-001/RUN_MANIFEST.json", data)
            findings, _ = self.run_check(root)
            self.assertIn("RESULT-E015", {item.rule_id for item in findings})

    def test_stale_optional_hash_is_warning_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            intermediate = root / "runs" / "RUN-Q1-001" / "outputs" / "preview.txt"
            intermediate.write_text("presentation preview\n", encoding="utf-8")
            path = root / "runs" / "RUN-Q1-001" / "RUN_MANIFEST.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["outputs"].append(
                {
                    "path": "runs/RUN-Q1-001/outputs/preview.txt",
                    "evidence_role": "intermediate_output",
                    "sha256": "0" * 64,
                    "size": intermediate.stat().st_size,
                    "media_type": "text/plain",
                }
            )
            write_json(root, "runs/RUN-Q1-001/RUN_MANIFEST.json", data)
            findings, _ = self.run_check(root)
            finding_by_rule = {item.rule_id: item for item in findings}
            self.assertEqual(finding_by_rule["RUN-W007"].severity, "warning")
            self.assertEqual(
                [item for item in findings if item.severity == "error" and item.rule_id != "DECISION-E010"],
                [],
            )

    def test_figure_hash_drift_is_warning_during_paper_editing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            (root / "figures" / "policy-cost.png").write_bytes(b"edited figure bytes")
            findings, _ = check_project(root, "validation")
            finding_by_rule = {item.rule_id: item for item in findings}
            self.assertEqual(finding_by_rule["FIGURE-W011"].severity, "warning")
            self.assertEqual([item for item in findings if item.severity == "error"], [])

    def test_figure_cannot_use_unindexed_result(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            path = root / "figures" / "FIGURE_MANIFEST.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["figures"][0]["result_ids"] = ["RES-UNKNOWN"]
            write_json(root, "figures/FIGURE_MANIFEST.json", data)
            findings, _ = self.run_check(root)
            self.assertIn("FIGURE-E006", {item.rule_id for item in findings})

    def test_global_overclaim_requires_certificate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            path = root / "validation" / "CLAIM_LEDGER.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["claims"][0]["text"] = "This is the globally optimal policy."
            write_json(root, "validation/CLAIM_LEDGER.json", data)
            findings, _ = self.run_check(root)
            self.assertIn("CLAIM-E011", {item.rule_id for item in findings})

    def test_certificate_declaration_requires_real_evidence_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            path = root / "validation" / "CLAIM_LEDGER.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["claims"][0]["text"] = "This is the globally optimal policy."
            data["claims"][0]["certificates"] = [
                {
                    "type": "global_optimality",
                    "description": "Synthetic certificate declaration",
                    "evidence_ids": ["UNKNOWN-EVIDENCE"],
                    "scope": "all feedback policies",
                }
            ]
            write_json(root, "validation/CLAIM_LEDGER.json", data)
            findings, _ = self.run_check(root)
            self.assertIn("CLAIM-E017", {item.rule_id for item in findings})

    def test_robustness_claim_requires_a_validation_method(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            path = root / "validation" / "CLAIM_LEDGER.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["claims"][0]["text"] = "The result is robust."
            data["claims"][0]["certificates"] = [
                {
                    "type": "robustness",
                    "description": "Declared without a sensitivity method",
                    "evidence_ids": ["RES-Q1-001"],
                    "scope": "synthetic fixture",
                }
            ]
            write_json(root, "validation/CLAIM_LEDGER.json", data)
            findings, _ = self.run_check(root)
            self.assertIn("CLAIM-E019", {item.rule_id for item in findings})

    def test_validated_capability_requires_an_execution_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            path = root / "analysis" / "TASK_CAPABILITIES.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["capabilities"].append(
                {
                    "capability_id": "CAP-Q1-002",
                    "subproblem_id": "Q1",
                    "objective": "Second declared computation",
                    "required_output": "Second result",
                    "fact_ids": ["FACT-Q1-001"],
                    "acceptance_checks": [{
                        "check_id": "ACC-SYN-001", "judge": "human",
                        "assertion": "the synthetic fixture is judged by a person, not a script",
                    }],
                    "model_ids": ["MODEL-Q1-001"],
                    "code_entry_points": ["code/solve.py:main"],
                    "result_ids": [],
                    "lifecycle_state": "validated",
                    "blocking_issues": [],
                }
            )
            write_json(root, "analysis/TASK_CAPABILITIES.json", data)
            model_path = root / "model" / "MODEL_CONTRACT.json"
            model = json.loads(model_path.read_text(encoding="utf-8"))
            model["components"][0]["capability_ids"].append("CAP-Q1-002")
            write_json(root, "model/MODEL_CONTRACT.json", model)
            findings, _ = self.run_check(root)
            self.assertIn("RUN-E014", {item.rule_id for item in findings})

    def test_core_project_can_be_checked_through_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            for stage in (
                "intake",
                "problem-analysis",
                "model-design",
                "computation",
                "validation",
            ):
                with self.subTest(stage=stage):
                    findings, _ = check_project(root, stage)
                    self.assertEqual([item for item in findings if item.severity == "error"], [])

    def test_cross_question_unit_conflict_is_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            path = root / "model" / "CROSS_QUESTION_LEDGER.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["shared_items"] = [
                {
                    "shared_id": "SHARED-001",
                    "name": "time",
                    "producer": "Q1",
                    "consumers": ["Q1"],
                    "definition": "elapsed time",
                    "unit": "s",
                    "transformation": None,
                    "uncertainty_propagation": None,
                    "authoritative_artifact": "RES-Q1-001",
                    "conflict_status": "clear",
                },
                {
                    "shared_id": "SHARED-002",
                    "name": "time",
                    "producer": "Q1",
                    "consumers": ["Q1"],
                    "definition": "elapsed time",
                    "unit": "day",
                    "transformation": None,
                    "uncertainty_propagation": None,
                    "authoritative_artifact": "RES-Q1-001",
                    "conflict_status": "unresolved",
                },
            ]
            write_json(root, "model/CROSS_QUESTION_LEDGER.json", data)
            findings, _ = self.run_check(root)
            self.assertIn("CROSS-E007", {item.rule_id for item in findings})

    def test_indexed_value_must_match_executed_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_valid_project(root)
            path = root / "results" / "RESULTS_INDEX.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["results"][0]["value"] = 99.0
            write_json(root, "results/RESULTS_INDEX.json", data)
            findings, _ = self.run_check(root)
            self.assertIn("RESULT-E012", {item.rule_id for item in findings})


if __name__ == "__main__":
    unittest.main()
