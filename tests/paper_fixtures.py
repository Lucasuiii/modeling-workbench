"""Shared paper-ready evidence fixtures for workflow tests."""
import hashlib
import json
from pathlib import Path

from workflow_fixtures import build_valid_project, envelope, review, write_json
from build_handoff import build as build_handoff
from init_latex_paper import initialize as initialize_latex
from provenance import digest_records, tree_snapshot
from workflow_checks import sha256, stage_scope_paths

def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def record_decisions(root: Path, stages: tuple[str, ...]) -> None:
    events = []
    for index, stage in enumerate(stages, 1):
        scope = [{"path": rel, "sha256": sha256(root / rel)} for rel in stage_scope_paths(root, stage)]
        event = {
            "decision_id": f"DEC-{index:03d}", "stage": stage, "decision": "accepted", "scope": scope,
            "reviewer": "fixture-reviewer", "task_turn_ref": f"fixture-turn-{index}",
            "user_visible_summary": f"Accepted fixture stage {stage}", "decided_at": "2026-08-30T12:00:00Z",
        }
        events.append(event)
        snapshot = {
            "snapshot_version": "0.6.0", "project_id": "SYNTHETIC-2024-B", "stage": stage,
            "decision_id": event["decision_id"], "decision": "accepted", "created_at": event["decided_at"],
            "artifacts": scope, "snapshot_digest": digest_records(scope),
        }
        write_json(root, f".cumcm/snapshots/{stage}.json", snapshot)
    decision_path = root / ".cumcm" / "decisions.jsonl"
    decision_path.parent.mkdir(parents=True, exist_ok=True)
    decision_path.write_text("".join(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n" for event in events), encoding="utf-8")


def build_paper_ready_project(
    root: Path, *, decisions: tuple[str, ...] | None = None,
    competition: str = "CUMCM", language: str = "zh",
) -> None:
    build_valid_project(root)
    paper_path = root / "paper" / "paper.pdf"
    paper_artifact = {"path": "paper/paper.pdf", "sha256": digest_file(paper_path)}

    included_layer = {
        "status": "included",
        "summary": "The paper records this part of the argument chain.",
        "evidence_ids": ["CLM-Q1-001"],
        "rationale": None,
    }
    plan = envelope("paper_plan")
    plan.update(
        {
            "authoring_task_ref": "fixture-paper-task",
            "claim_selection": [
                {"claim_id": "CLM-Q1-001", "subproblem_id": "Q1", "purpose": "answer Q1 directly"}
            ],
            "representation_plan": [
                {"item_id": "REP-Q1-001", "claim_ids": ["CLM-Q1-001"], "result_ids": ["RES-Q1-001"], "medium": "figure", "purpose": "show the restricted-policy comparison", "artifact_id": "FIG-Q1-001"}
            ],
            "paper_structure": [
                {"section_id": "SEC-Q1", "title": "Q1 solution", "purpose": "complete Q1 reasoning", "subproblem_ids": ["Q1"], "claim_ids": ["CLM-Q1-001"]}
            ],
            "reference_reviews": [
                {
                    "reference_id": "REF-001",
                    "source": "reviewed high-quality contest paper",
                    "quality_reasons": ["complete derivation and verification chain"],
                    "transferable_lessons": ["connect each conclusion to evidence"],
                    "non_transferable_limits": ["different problem and data"],
                }
            ],
            "reader_narrative": {
                "one_sentence_contribution": "The paper solves the declared restricted policy problem and explains the scope.",
                "judge_reading_path": ["problem", "mechanism", "model", "result", "meaning", "validation", "boundary"],
                "internal_metadata_policy": "sidecar_only",
            },
            "claims_evidence_matrix": [
                {
                    "claim_id": "CLM-Q1-001",
                    "subproblem_id": "Q1",
                    "planned_sections": ["Results"],
                    "evidence_ids": ["RES-Q1-001", "FIG-Q1-001"],
                    "status": "included",
                }
            ],
            "question_argument_chains": [
                {
                    "subproblem_id": "Q1",
                    "layers": {
                        name: dict(included_layer)
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
            ],
            "figure_plan": [
                {
                    "figure_id": "FIG-Q1-001",
                    "kind": "quantitative",
                    "purpose": "Explain the restricted-policy comparison.",
                    "claim_ids": ["CLM-Q1-001"],
                    "result_ids": ["RES-Q1-001"],
                    "required": True,
                    "decision_support": "Makes the policy comparison inspectable.",
                }
            ],
            "page_budget": [
                {"section": "Q1", "purpose": "Complete argument", "target_pages": 1.0}
            ],
        }
    )
    write_json(root, "paper/PAPER_PLAN.json", plan)

    initialize_latex(root, "Synthetic Modeling Paper", 2026, "synthetic; evidence",
                     competition=competition, language=language)
    for source in (root / "paper").rglob("*.tex"):
        text = source.read_text(encoding="utf-8")
        text = text.replace("CUMCM-TODO", "已完成").replace("\\placeholder{", "\\textbf{")
        source.write_text(text, encoding="utf-8")
    manifest_path = root / "paper" / "LATEX_TEMPLATE_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["official_compliance"] = "verified_against_current_rules"
    manifest["official_template_source"] = "fixture://current-rules"
    manifest["review"] = review()
    write_json(root, "paper/LATEX_TEMPLATE_MANIFEST.json", manifest)

    dimension = {"status": "pass", "notes": "Checked against linked evidence.", "evidence_ids": ["CLM-Q1-001"]}
    quality = envelope("paper_quality_report")
    quality.update(
        {
            "paper_status": "final",
            "paper_artifact": paper_artifact,
            "content_report": {
                "artifact": paper_artifact,
                "summary": "Content is coherent and evidence-bounded.",
                "abstract_synthesis": dict(dimension),
                "conclusion_directness": dict(dimension),
                "internal_metadata_separation": dict(dimension),
                "reference_style_transfer": dict(dimension),
                "questions": [
                    {
                        "subproblem_id": "Q1",
                        "status": "pass",
                        "notes": "Q1 directly answers the task and explains the result.",
                        "argument_chain": dict(dimension),
                        "mechanism_explanation": dict(dimension),
                        "derivation": dict(dimension),
                        "result_interpretation": dict(dimension),
                        "reader_facing_language": dict(dimension),
                        "numerical_presentation": dict(dimension),
                        "validation_strength": dict(dimension),
                        "limitations": dict(dimension),
                    }
                ],
            },
            "layout_report": {
                "artifact": paper_artifact,
                "page_count": 1,
                "rendered_pages": [1],
                "checks": [
                    {"check_id": "LAYOUT-001", "category": "cross_page", "status": "pass", "notes": "All rendered pages inspected."}
                ],
            },
            "open_issues": [],
        }
    )
    write_json(root, "paper/PAPER_QUALITY_REPORT.json", quality)

    revisions = envelope("paper_revision_log")
    revisions.update({"initial_snapshot": paper_artifact, "revisions": []})
    write_json(root, "paper/PAPER_REVISION_LOG.json", revisions)

    visible_text = envelope("paper_visible_text_report")
    visible_text.update(
        {
            "paper_artifact": paper_artifact,
            "status": "pass",
            "blocking_matches": [],
            "review_flags": [],
        }
    )
    write_json(root, "paper/PAPER_VISIBLE_TEXT_REPORT.json", visible_text)

    receipt = envelope("compile_receipt")
    receipt.update(
        {
            "source_snapshot": tree_snapshot(
                root,
                json.loads((root / "paper" / "LATEX_TEMPLATE_MANIFEST.json").read_text(encoding="utf-8"))["required_files"],
                entrypoint="paper/main.tex",
            ),
            "selected_attempt_id": "COMPILE-001",
            "attempts": [
                {
                    "attempt_id": "COMPILE-001",
                    "argv": ["xelatex", "paper.tex"],
                    "engine": "XeLaTeX",
                    "engine_version": "synthetic",
                    "exit_code": 0,
                    "log_path": "paper/compile.log",
                    "warnings": [],
                    "page_count": 1,
                    "pdf_path": "paper/paper.pdf",
                    "pdf_sha256": paper_artifact["sha256"],
                    "font_check": "pass",
                    "glyph_check": "pass",
                    "diagnostic_summary": "Synthetic compile succeeded.",
                    "completed_at": "2026-08-30T12:00:00Z",
                }
            ],
            "layout_report_binding": {
                "quality_report_path": "paper/PAPER_QUALITY_REPORT.json",
                "pdf_sha256": paper_artifact["sha256"],
            },
        }
    )
    write_json(root, "delivery/COMPILE_RECEIPT.json", receipt)
    delivery_path = root / "delivery" / "DELIVERY_MANIFEST.json"
    delivery = json.loads(delivery_path.read_text(encoding="utf-8"))
    delivery["compile_receipt_path"] = "delivery/COMPILE_RECEIPT.json"
    write_json(root, "delivery/DELIVERY_MANIFEST.json", delivery)

    state_path = root / ".cumcm" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["mode"] = "finalizing"
    state["current_stage"] = "delivery"
    state["stages"] = {stage: "passed" for stage in (
        "intake", "problem-analysis", "model-design", "computation", "validation", "paper", "delivery"
    )}
    write_json(root, ".cumcm/state.json", state)

    # Distinct refs on the two cut transitions: the reviewer is not the task that
    # produced the evidence, and the paper is not written by the task that reviewed it.
    producing_task_refs = {
        "computation-validation": "fixture-modeling-task",
        "validation-paper": "fixture-independent-task",
    }
    for transition in ("modeling-computation", "computation-validation", "validation-paper", "paper-delivery"):
        build_handoff(root, transition, producing_task_refs.get(transition))

    record_decisions(
        root,
        decisions
        if decisions is not None
        else ("intake", "problem-analysis", "model-design", "computation", "validation", "paper", "delivery"),
    )
