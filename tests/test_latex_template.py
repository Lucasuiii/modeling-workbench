from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".agents" / "skills" / "cumcm-workflow" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from init_latex_paper import initialize  # noqa: E402
from test_paper_pipeline import build_paper_ready_project  # noqa: E402
from workflow_fixtures import envelope, write_json, write_accepted_snapshot  # noqa: E402
from workflow_checks import check_latex_template, check_project  # noqa: E402


def build_inputs(root: Path, problem_ids: tuple[str, ...] = ("Q1", "Q2"), plan_ids: tuple[str, ...] | None = None) -> None:
    state = envelope("workflow_state")
    state.update(
        {
            "workflow_version": "0.6.0",
            "mode": "working",
            "implementation": {"preferred": "matlab", "fallback": "python", "selection": "auto"},
            "current_stage": "paper",
            "stages": {
                "intake": "passed",
                "problem-analysis": "passed",
                "model-design": "passed",
                "computation": "passed",
                "validation": "passed",
                "paper": "in_progress",
                "delivery": "not_started",
            },
        }
    )
    write_json(root, ".cumcm/state.json", state)
    facts = envelope("problem_facts")
    facts.update(
        {
            "subproblems": [
                {"subproblem_id": ident, "request": f"Solve {ident}", "expected_output": f"Result {ident}"}
                for ident in problem_ids
            ],
            "facts": [],
            "definitions": [],
            "ambiguities": [],
            "assumptions": [],
        }
    )
    write_json(root, "analysis/PROBLEM_FACTS.json", facts)
    layer = {"status": "included", "summary": "planned", "evidence_ids": [], "rationale": None}
    plan = envelope("paper_plan")
    plan.update(
        {
            "authoring_task_ref": "fixture-paper-task",
            "claim_selection": [
                {"claim_id": f"CLM-{ident}", "subproblem_id": ident, "purpose": f"answer {ident}"}
                for ident in problem_ids
            ],
            "representation_plan": [],
            "paper_structure": [
                {"section_id": f"SEC-{ident}", "title": ident, "purpose": f"answer {ident}", "subproblem_ids": [ident], "claim_ids": [f"CLM-{ident}"]}
                for ident in (plan_ids if plan_ids is not None else problem_ids)
            ],
            "reference_reviews": [],
            "reader_narrative": {
                "one_sentence_contribution": "Synthetic reader-facing paper plan.",
                "judge_reading_path": ["problem", "model", "result"],
                "internal_metadata_policy": "sidecar_only",
            },
            "claims_evidence_matrix": [],
            "question_argument_chains": [
                {
                    "subproblem_id": ident,
                    "layers": {
                        name: dict(layer)
                        for name in (
                            "problem_interpretation",
                            "assumptions_boundaries",
                            "variables_parameters",
                            "objective_constraints",
                            "derivation",
                            "algorithm",
                            "results",
                            "validation",
                            "limitations",
                        )
                    },
                }
                for ident in (plan_ids if plan_ids is not None else problem_ids)
            ],
            "figure_plan": [],
            "page_budget": [{"section": "paper", "purpose": "complete argument", "target_pages": 8.0}],
        }
    )
    write_json(root, "paper/PAPER_PLAN.json", plan)
    write_json(root, "validation/CLAIM_LEDGER.json", {
        "claims": [{"claim_id": f"CLM-{ident}"} for ident in problem_ids],
        "conclusion_check": {"decision": "accepted", "reviewer_kind": "human_user",
                             "reviewer": "fixture-user", "reviewed_at": "2026-09-07",
                             "presented_claim_ids": [f"CLM-{ident}" for ident in problem_ids]},
    })

    write_accepted_snapshot(root, "validation", ["validation/CLAIM_LEDGER.json"])


class LatexTemplateTests(unittest.TestCase):
    def test_dynamic_sections_and_manifest_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_inputs(root)
            manifest_path = initialize(root, "2026 B test", 2026, "model; validation")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                {item["subproblem_id"] for item in manifest["subproblem_sections"]},
                {"Q1", "Q2"},
            )
            for rel in manifest["required_files"]:
                self.assertTrue((root / rel).is_file(), rel)
            main = (root / manifest["main_path"]).read_text(encoding="utf-8")
            self.assertIn(r"\input{sections/10_sec_q1}", main)
            self.assertIn(r"\input{sections/20_sec_q2}", main)

    def test_paper_structure_drives_order_and_supports_shared_or_split_sections(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_inputs(root, problem_ids=("Q1", "Q2", "Q3"))
            plan_path = root / "paper/PAPER_PLAN.json"
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            plan["paper_structure"] = [
                {
                    "section_id": "SEC-SHARED",
                    "title": "共同机理与统一变量",
                    "purpose": "建立问题一和问题二共享的守恒机制。",
                    "subproblem_ids": ["Q1", "Q2"],
                    "claim_ids": ["CLM-Q1", "CLM-Q2"],
                },
                {
                    "section_id": "SEC-Q2-ALGORITHM",
                    "title": "约束算法与收敛判据",
                    "purpose": "完成问题二的算法推导并解释已有收敛证据。",
                    "subproblem_ids": ["Q2"],
                    "claim_ids": ["CLM-Q2"],
                },
                {
                    "section_id": "SEC-Q3-RESULT",
                    "title": "方案比较与结论边界",
                    "purpose": "用已验证结果回答问题三并说明适用范围。",
                    "subproblem_ids": ["Q3"],
                    "claim_ids": ["CLM-Q3"],
                },
            ]
            write_json(root, "paper/PAPER_PLAN.json", plan)

            manifest_path = initialize(root, "Synthetic structured paper", 2026, "守恒机制；约束优化；收敛分析；方案比较")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            main = (root / "paper/main.tex").read_text(encoding="utf-8")
            inputs = [
                r"\input{sections/10_sec_shared}",
                r"\input{sections/20_sec_q2_algorithm}",
                r"\input{sections/30_sec_q3_result}",
            ]
            self.assertEqual(sorted((main.index(value), value) for value in inputs), [(main.index(value), value) for value in inputs])

            mappings = {(item["subproblem_id"], item["path"]) for item in manifest["subproblem_sections"]}
            self.assertIn(("Q1", "paper/sections/10_sec_shared.tex"), mappings)
            self.assertIn(("Q2", "paper/sections/10_sec_shared.tex"), mappings)
            self.assertIn(("Q2", "paper/sections/20_sec_q2_algorithm.tex"), mappings)
            latex_findings = check_latex_template(
                manifest,
                root,
                "paper/LATEX_TEMPLATE_MANIFEST.json",
                {"Q1", "Q2", "Q3"},
                {},
                "paper",
            )
            self.assertFalse({"LATEX-E003", "LATEX-E006", "LATEX-E007"} & {item.rule_id for item in latex_findings})

            shared = (root / "paper/sections/10_sec_shared.tex").read_text(encoding="utf-8")
            all_planned = "\n".join(
                (root / rel).read_text(encoding="utf-8")
                for rel in manifest["section_files"]
                if rel not in {
                    "paper/sections/00_abstract.tex",
                    "paper/sections/98_references.tex",
                    "paper/sections/99_appendix.tex",
                }
            )
            self.assertIn(r"\section{共同机理与统一变量}", shared)
            self.assertIn("% Writing purpose: 建立问题一和问题二共享的守恒机制。", shared)
            self.assertIn("% Supported claims (sidecar only): CLM-Q1, CLM-Q2", shared)
            self.assertNotIn(r"\subsection{任务、机制与路线}", all_planned)
            self.assertNotIn(r"\subsection{模型、推导与求解}", all_planned)
            self.assertNotIn(r"\subsection{结果、检验与结论边界}", all_planned)
            rendered_source = "\n".join(line for line in shared.splitlines() if not line.lstrip().startswith("%"))
            self.assertNotIn("CLM-Q1", rendered_source)
            self.assertNotIn("SEC-SHARED", rendered_source)

            metadata = (root / "paper/metadata.tex").read_text(encoding="utf-8")
            self.assertIn("守恒机制；约束优化；收敛分析；方案比较", metadata)
            self.assertNotIn("可复现计算", metadata)
            self.assertNotIn("证据链", metadata)

    def test_workflow_oriented_keyword_defaults_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_inputs(root)
            with self.assertRaisesRegex(ValueError, "actual problem"):
                initialize(root, "No filler keywords", 2026, "数学建模；可复现计算；证据链")

    def test_refuses_to_overwrite_existing_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_inputs(root)
            initialize(root, "first", 2026, "first")
            with self.assertRaisesRegex(ValueError, "refusing to overwrite"):
                initialize(root, "second", 2026, "second")

    def test_plan_must_exactly_cover_problem_questions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_inputs(root, problem_ids=("Q1", "Q2"), plan_ids=("Q1",))
            with self.assertRaisesRegex(ValueError, "exactly cover"):
                initialize(root, "mismatch", 2026, "mismatch")

    def test_rule_document_does_not_block_generic_scaffold(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_inputs(root)
            official = root / "problem/official/提交格式说明.pdf"
            official.parent.mkdir(parents=True, exist_ok=True)
            official.write_bytes(b"official rules")
            manifest = envelope("source_manifest")
            manifest["sources"] = [
                {
                    "source_id": "SRC-FORMAT",
                    "path": "problem/official/提交格式说明.pdf",
                    "origin": "official",
                    "authoritative_for": ["format_rules", "submission_rules"],
                }
            ]
            write_json(root, "problem/SOURCE_MANIFEST.json", manifest)
            before = official.read_bytes()
            output = initialize(root, "碳化硅外延层厚度测量", 2026, "薄膜干涉；色散模型")
            generated = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(official.read_bytes(), before)
            self.assertTrue((root / "paper/main.tex").is_file())
            self.assertEqual(generated["official_compliance"], "unverified")

    def test_declared_official_paper_template_blocks_generic_scaffold(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_inputs(root)
            official = root / "problem/official/paper-template.tex"
            official.parent.mkdir(parents=True, exist_ok=True)
            official.write_text("% official template\n", encoding="utf-8")
            manifest = envelope("source_manifest")
            manifest["sources"] = [
                {
                    "source_id": "SRC-TEMPLATE",
                    "path": "problem/official/paper-template.tex",
                    "origin": "official",
                    "authoritative_for": ["paper_template"],
                }
            ]
            write_json(root, "problem/SOURCE_MANIFEST.json", manifest)
            with self.assertRaisesRegex(ValueError, "official paper template"):
                initialize(root, "碳化硅外延层厚度测量", 2026, "薄膜干涉；色散模型")
            self.assertFalse((root / "paper/main.tex").exists())

    def test_template_filename_without_role_metadata_does_not_decide_behavior(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_inputs(root)
            official = root / "problem/official/论文模板说明.pdf"
            official.parent.mkdir(parents=True, exist_ok=True)
            official.write_bytes(b"ambiguous official document")
            manifest = envelope("source_manifest")
            manifest["sources"] = [
                {
                    "source_id": "SRC-AMBIGUOUS",
                    "path": "problem/official/论文模板说明.pdf",
                    "origin": "official",
                    "authoritative_for": [],
                }
            ]
            write_json(root, "problem/SOURCE_MANIFEST.json", manifest)
            output = initialize(root, "碳化硅外延层厚度测量", 2026, "薄膜干涉；色散模型")
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["official_compliance"], "unverified")

    def test_reader_facing_title_placeholder_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_inputs(root)
            with self.assertRaisesRegex(ValueError, "actual problem"):
                initialize(root, "全国大学生数学建模竞赛论文", 2026, "薄膜干涉；色散模型")

    def test_final_placeholder_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            manifest = json.loads((root / "paper/LATEX_TEMPLATE_MANIFEST.json").read_text(encoding="utf-8"))
            section = root / manifest["subproblem_sections"][0]["path"]
            section.write_text(section.read_text(encoding="utf-8") + "\n% CUMCM-TODO\n", encoding="utf-8")
            findings, _ = check_project(root, "paper")
            self.assertIn("LATEX-E008", {item.rule_id for item in findings})

    def test_delivery_requires_current_official_format_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            path = root / "paper" / "LATEX_TEMPLATE_MANIFEST.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["official_compliance"] = "unverified"
            manifest["official_template_source"] = None
            write_json(root, "paper/LATEX_TEMPLATE_MANIFEST.json", manifest)
            findings, _ = check_project(root, "delivery", "preflight")
            item = next(item for item in findings if item.rule_id == "LATEX-E009")
            self.assertTrue(item.gate_only)

    def test_compile_engine_must_match_template(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            path = root / "delivery" / "COMPILE_RECEIPT.json"
            receipt = json.loads(path.read_text(encoding="utf-8"))
            receipt["attempts"][0]["engine"] = "lualatex"
            write_json(root, "delivery/COMPILE_RECEIPT.json", receipt)
            findings, _ = check_project(root, "delivery")
            self.assertIn("COMPILE-E014", {item.rule_id for item in findings})


if __name__ == "__main__":
    unittest.main()
