#!/usr/bin/env python3
"""Build compact, freshness-bound cross-stage handoffs for fresh-context tasks."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import evidence_json
from canonical_evidence import resolve_official_computation
from official_materials import classified_official_materials
from provenance import digest_records, sha256_file, snapshot_matches


WORKFLOW_VERSION = "0.6.0"
TRANSITIONS = {
    "modeling-computation": ("model-design", "computation"),
    "computation-validation": ("computation", "validation"),
    "validation-paper": ("validation", "paper"),
    "paper-delivery": ("paper", "delivery"),
}
# The two transitions that must cross a task boundary: the reviewer must not be the
# task that produced the evidence, and the paper must not be written by the task that
# reviewed it. Self-reported task refs are a paste guard, not proof of separation.
CUT_TRANSITIONS = ("computation-validation", "validation-paper")
BASE_PATHS = {
    "modeling-computation": [
        ("problem/SOURCE_MANIFEST.json", "source_manifest"),
        ("analysis/PROBLEM_FACTS.json", "problem"),
        ("analysis/TASK_CAPABILITIES.json", "capabilities"),
        ("model/MODEL_CONTRACT.json", "model"),
    ],
    "computation-validation": [
        ("model/MODEL_CONTRACT.json", "model"),
        ("results/RESULTS_INDEX.json", "results"),
    ],
    "validation-paper": [
        ("problem/SOURCE_MANIFEST.json", "source_manifest"),
        ("analysis/PROBLEM_FACTS.json", "problem"),
        ("model/MODEL_CONTRACT.json", "model"),
        ("results/RESULTS_INDEX.json", "results"),
        ("validation/INDEPENDENT_REVIEW_RESULT.json", "review"),
        ("validation/CLAIM_LEDGER.json", "claims"),
    ],
    "paper-delivery": [
        ("problem/SOURCE_MANIFEST.json", "source_manifest"),
        ("results/RESULTS_INDEX.json", "results"),
        ("paper/PAPER_PLAN.json", "paper_plan"),
        ("paper/LATEX_TEMPLATE_MANIFEST.json", "latex_source"),
        ("paper/PAPER_QUALITY_REPORT.json", "paper_quality"),
        ("paper/PAPER_VISIBLE_TEXT_REPORT.json", "visible_text"),
        ("delivery/COMPILE_RECEIPT.json", "compile_receipt"),
    ],
}


OPTIONAL_PATHS = {
    "modeling-computation": [("model/CROSS_QUESTION_LEDGER.json", "cross_question")],
    "validation-paper": [("model/CROSS_QUESTION_LEDGER.json", "cross_question")],
}


def official_sources(root: Path) -> list[dict[str, Any]]:
    sources = read_object(root, "problem/SOURCE_MANIFEST.json")
    return [
        item for item in sources.get("sources", [])
        if isinstance(item, dict) and item.get("origin") in {"official", "organizer_attachment"}
    ]


def official_paper_materials(root: Path) -> list[dict[str, Any]]:
    return classified_official_materials(official_sources(root))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_object(root: Path, rel: str) -> dict[str, Any]:
    path = root / rel
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {rel}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {rel}")
    return value


def add_artifact(root: Path, records: list[dict[str, str]], rel: str, role: str) -> None:
    path = (root / rel).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"handoff path escapes project: {rel}") from exc
    if not path.is_file():
        raise ValueError(f"handoff artifact is missing: {rel}")
    if rel not in {item["path"] for item in records}:
        records.append({"path": rel, "role": role, "sha256": sha256_file(path)})


def values(value: Any) -> list[Any]:
    if value is None or value == "" or value == []:
        return []
    return value if isinstance(value, list) else [value]


REPRESENTATION_PATTERNS = {
    "trend": ("trend", "time series", "trajectory", "curve", "growth", "趋势", "时间序列", "轨迹", "曲线", "增长", "变化率"),
    "multi_group_comparison": ("comparison", "compare", "versus", "group", "scenario", "policy", "对比", "比较", "组别", "方案", "策略"),
    "distribution": ("distribution", "density", "quantile", "histogram", "variance", "分布", "密度", "分位数", "直方图", "方差"),
    "sensitivity": ("sensitivity", "perturbation", "stress", "robust", "敏感性", "扰动", "压力测试", "鲁棒"),
    "model_performance": ("performance", "accuracy", "error", "residual", "loss", "fit", "性能", "准确率", "误差", "残差", "损失", "拟合"),
    "spatial_network_cluster": ("spatial", "geographic", "network", "graph", "cluster", "空间", "地理", "网络", "图结构", "聚类"),
}


def representation_candidates(claims: dict[str, Any], results: dict[str, Any], supported_states: set[str]) -> list[dict[str, Any]]:
    result_by_id = {
        str(item.get("result_id")): item
        for item in results.get("results", [])
        if isinstance(item, dict)
    }
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for claim in claims.get("claims", []):
        if not isinstance(claim, dict) or claim.get("evidence_state") not in supported_states:
            continue
        evidence = claim.get("evidence") if isinstance(claim.get("evidence"), dict) else {}
        result_ids = [str(value) for value in evidence.get("result_ids", [])]
        linked = [result_by_id[result_id] for result_id in result_ids if result_id in result_by_id]
        text_parts = [claim.get("text"), claim.get("claim_type")]
        for result in linked:
            text_parts.extend((result.get("name"), result.get("scope"), result.get("validation_checks")))
        searchable = json.dumps(text_parts, ensure_ascii=False).casefold()
        kinds = {
            kind for kind, patterns in REPRESENTATION_PATTERNS.items()
            if any(pattern.casefold() in searchable for pattern in patterns)
        }
        if len(result_ids) > 1 or any(isinstance(item.get("value"), (list, dict)) and len(item.get("value")) > 1 for item in linked):
            kinds.add("multi_group_comparison")
        for kind in sorted(kinds):
            key = (str(claim.get("claim_id")), kind)
            if key in seen:
                continue
            seen.add(key)
            media = ["table", "figure"] if kind == "multi_group_comparison" else ["figure", "table"]
            candidates.append(
                {
                    "candidate_id": f"{claim.get('claim_id')}:{kind}",
                    "kind": kind,
                    "claim_ids": [claim.get("claim_id")],
                    "result_ids": result_ids,
                    "suggested_media": media,
                    "reason": f"verified evidence indicates {kind.replace('_', ' ')} structure",
                }
            )
    return candidates


def review_lineage(root: Path, current: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Merge structured findings newest-first; the latest status wins per finding ID."""
    merged: dict[str, dict[str, Any]] = {}
    lineage_paths = ["validation/INDEPENDENT_REVIEW_RESULT.json"]
    seen_paths: set[str] = set()
    review = current
    while True:
        for item in review.get("findings", []):
            if not isinstance(item, dict) or not item.get("finding_id"):
                continue
            merged.setdefault(str(item["finding_id"]), item)
        previous = review.get("previous_review_path") if review.get("review_mode") == "targeted" else None
        if not previous:
            break
        rel = str(previous)
        if rel in seen_paths:
            raise ValueError(f"review lineage contains a cycle: {rel}")
        seen_paths.add(rel)
        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"review lineage path escapes project: {rel}") from exc
        if not candidate.is_file():
            raise ValueError(f"review lineage file is missing: {rel}")
        review = read_object(root, rel)
        lineage_paths.append(rel)
    return list(merged.values()), lineage_paths


def paper_limitations(
    facts: dict[str, Any],
    model: dict[str, Any],
    claims: dict[str, Any],
    review_findings: list[dict[str, Any]],
    supported_states: set[str],
) -> dict[str, list[dict[str, Any]]]:
    claim_items: list[dict[str, Any]] = []
    for claim in claims.get("claims", []):
        if not isinstance(claim, dict) or claim.get("evidence_state") not in supported_states:
            continue
        for item in values(claim.get("limitations")):
            claim_items.append({"claim_id": claim.get("claim_id"), "value": item})

    concerns = [
        {
            key: item.get(key)
            for key in ("finding_id", "status", "category", "location", "evidence", "recommendation")
        }
        for item in review_findings
        if isinstance(item, dict) and item.get("severity") == "P1" and item.get("status") in {"open", "accepted_concern"}
    ]

    applicability: list[dict[str, Any]] = []
    for component in model.get("components", []):
        if not isinstance(component, dict):
            continue
        for field in ("applicability", "applicability_conditions", "assumptions", "known_limitations", "limitations"):
            for item in values(component.get(field)):
                applicability.append({"model_id": component.get("model_id"), "kind": field, "value": item})
    for assumption in facts.get("assumptions", []):
        applicability.append({"model_id": None, "kind": "problem_assumption", "value": assumption})
    return {
        "claim_limitations": claim_items,
        "review_concerns": concerns,
        "model_applicability": applicability,
    }


def paper_payload(root: Path) -> dict[str, Any]:
    facts = read_object(root, "analysis/PROBLEM_FACTS.json")
    model = read_object(root, "model/MODEL_CONTRACT.json")
    results = evidence_json.read(root / "results/RESULTS_INDEX.json")
    claims = read_object(root, "validation/CLAIM_LEDGER.json")
    review = read_object(root, "validation/INDEPENDENT_REVIEW_RESULT.json")
    lineage_findings, _ = review_lineage(root, review)
    supported_states = {"supported_not_reproduced", "reproduced", "partially_supported"}
    verified_results = [
        {key: item.get(key) for key in ("result_id", "name", "value", "unit", "scope", "evidence_state", "output_locator")}
        for item in results.get("results", [])
        if isinstance(item, dict) and item.get("evidence_state") in supported_states
    ]
    verified_ids = {result["result_id"] for result in verified_results}
    selected_claims = [
        {**{key: item.get(key) for key in ("claim_id", "text", "scope", "evidence_state", "limitations")},
         "result_ids": [rid for rid in item.get("evidence", {}).get("result_ids", []) if rid in verified_ids]}
        for item in claims.get("claims", [])
        if isinstance(item, dict) and item.get("evidence_state") in supported_states
    ]
    materials = official_paper_materials(root)
    return {
        "next_task": (
            "For each subproblem, frame the modeling decision a reader needs to understand in the section purpose. "
            "Follow the claim's result_ids to the indexed output_locator. Use the most revealing observation, "
            "comparison or derivation to explain the decision and its limits. If no comparison was evaluated, "
            "identify the missing evidence. Before delivery, answer the reader's question from the draft alone."
        ),
        "problem_summary": [
            {"subproblem_id": item.get("subproblem_id"), "request": item.get("request"), "expected_output": item.get("expected_output")}
            for item in facts.get("subproblems", []) if isinstance(item, dict)
        ],
        "model_summary": [
            {"model_id": item.get("model_id"), "method": item.get("method"), "scope": item.get("scope")}
            for item in model.get("components", []) if isinstance(item, dict)
        ],
        "verified_results": verified_results,
        "claims": selected_claims,
        "limitations": paper_limitations(facts, model, claims, lineage_findings, supported_states),
        "representation_candidates": representation_candidates(claims, results, supported_states),
        "official_format_files": [item.get("path") for item in materials],
        "official_materials": materials,
    }


def build_payload(root: Path, transition: str, state: dict[str, Any]) -> dict[str, Any]:
    if transition == "modeling-computation":
        return {"implementation": state.get("implementation"), "next_task": "select one backend, implement, execute, and preserve the official run"}
    if transition == "computation-validation":
        official = resolve_official_computation(root)
        return {"official_run_ids": [item["run_id"] for item in official], "next_task": "review the packaged computation without reading debug history"}
    if transition == "validation-paper":
        return paper_payload(root)
    quality = read_object(root, "paper/PAPER_QUALITY_REPORT.json")
    latex = read_object(root, "paper/LATEX_TEMPLATE_MANIFEST.json")
    receipt = read_object(root, "delivery/COMPILE_RECEIPT.json")
    computation = resolve_official_computation(root)
    source_snapshot = receipt.get("source_snapshot")
    if not snapshot_matches(root, source_snapshot):
        raise ValueError("paper-delivery requires a current compile-bound editable LaTeX source snapshot")
    if not isinstance(source_snapshot, dict) or source_snapshot.get("entrypoint") != latex.get("main_path"):
        raise ValueError("paper-delivery compile source snapshot does not match the LaTeX entry point")
    if not set(str(path) for path in latex.get("required_files", [])).issubset(
        set(str(path) for path in source_snapshot.get("files", []))
    ):
        raise ValueError("paper-delivery compile source snapshot does not cover every required LaTeX file")
    attempts = {
        str(item.get("attempt_id")): item
        for item in receipt.get("attempts", [])
        if isinstance(item, dict)
    }
    selected = attempts.get(str(receipt.get("selected_attempt_id")))
    approved_pdf = quality.get("paper_artifact")
    if (
        not isinstance(selected, dict)
        or selected.get("exit_code") != 0
        or not isinstance(approved_pdf, dict)
        or selected.get("pdf_path") != approved_pdf.get("path")
        or selected.get("pdf_sha256") != approved_pdf.get("sha256")
    ):
        raise ValueError("paper-delivery reviewed PDF is not the successful compile receipt's selected PDF")
    return {
        "approved_pdf": approved_pdf,
        "editable_latex": {
            "manifest_path": "paper/LATEX_TEMPLATE_MANIFEST.json",
            "entrypoint": latex.get("main_path"),
            "required_source_files": latex.get("required_files", []),
            "source_snapshot": source_snapshot,
        },
        "computation_evidence": [
            {
                "run_id": item["run_id"],
                "run_manifest_path": item["manifest_path"],
                "source_snapshot": item["source_snapshot"],
                "source_files": item["source_files"],
            }
            for item in computation
        ],
        "official_materials": official_paper_materials(root),
        "official_compliance": latex.get("official_compliance"),
    }


def build(root: Path, transition: str, task_ref: str | None = None) -> Path:
    root = root.resolve()
    if transition not in TRANSITIONS:
        raise ValueError(f"unknown transition: {transition}")
    state = read_object(root, ".cumcm/state.json")
    if state.get("workflow_version") != WORKFLOW_VERSION:
        raise ValueError(f"handoff builder requires workflow {WORKFLOW_VERSION}")
    from workflow_checks import require_human_checkpoint, check_project
    if transition == "modeling-computation":
        require_human_checkpoint(root, "model-design")
    elif transition == "validation-paper":
        require_human_checkpoint(root, "validation")
        findings, _ = check_project(root, "validation", "preflight")
        errors = [item for item in findings if item.severity == "error" and not item.gate_only]
        if errors:
            raise ValueError(f"validation is blocked: {errors[0].rule_id}: {errors[0].message}")
    records: list[dict[str, str]] = []
    for rel, role in BASE_PATHS[transition]:
        add_artifact(root, records, rel, role)
    # The cross-question ledger is optional in v0.6; bind it only when it exists.
    for rel, role in OPTIONAL_PATHS.get(transition, []):
        if (root / rel).is_file():
            add_artifact(root, records, rel, role)
    if transition == "modeling-computation":
        for source in official_sources(root):
            add_artifact(root, records, str(source.get("path")), "official_input")
    if transition == "computation-validation":
        for evidence in resolve_official_computation(root):
            add_artifact(root, records, evidence["manifest_path"], "official_run")
            for rel in evidence["source_files"]:
                add_artifact(root, records, str(rel), "computation_source")
            for rel in evidence["formal_inputs"]:
                add_artifact(root, records, rel, "formal_input")
            for rel in evidence["claim_bearing_outputs"]:
                add_artifact(root, records, rel, "claim_bearing_output")
    if transition == "validation-paper":
        current_review = read_object(root, "validation/INDEPENDENT_REVIEW_RESULT.json")
        _, lineage_paths = review_lineage(root, current_review)
        for rel in lineage_paths[1:]:
            add_artifact(root, records, rel, "review_lineage")
        for material in official_paper_materials(root):
            add_artifact(root, records, str(material.get("path")), str(material.get("role")))
    if transition == "paper-delivery":
        latex = read_object(root, "paper/LATEX_TEMPLATE_MANIFEST.json")
        for rel in latex.get("required_files", []):
            add_artifact(root, records, str(rel), "editable_source")
        quality = read_object(root, "paper/PAPER_QUALITY_REPORT.json")
        if isinstance(quality.get("paper_artifact"), dict):
            add_artifact(root, records, str(quality["paper_artifact"].get("path")), "approved_pdf")
        for evidence in resolve_official_computation(root):
            add_artifact(root, records, evidence["manifest_path"], "official_run")
            for rel in evidence["source_files"]:
                add_artifact(root, records, rel, "computation_source")
        for material in official_paper_materials(root):
            add_artifact(root, records, str(material.get("path")), str(material.get("role")))
    upstream, downstream = TRANSITIONS[transition]
    handoff = {
        "schema_version": WORKFLOW_VERSION,
        "artifact_type": "stage_handoff",
        "project_id": state.get("project_id"),
        "updated_at": utc_now(),
        "producer": {"kind": "script", "name": "build_handoff.py", "version": WORKFLOW_VERSION},
        "transition": transition,
        "upstream_stage": upstream,
        "downstream_stage": downstream,
        "producing_task_ref": task_ref or None,
        "upstream_digest": digest_records(records),
        "canonical_artifacts": sorted(records, key=lambda item: item["path"]),
        "payload": build_payload(root, transition, state),
        "excluded_history": ["full logs", "failed runs", "debug transcripts", "old review conversations"],
    }
    destination = root / "handoffs" / transition / "HANDOFF.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent, delete=False) as stream:
        stream.write(evidence_json.dumps(handoff))
        stream.write("\n")
        temp_name = stream.name
    os.replace(temp_name, destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a compact v0.6 cross-stage handoff")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--transition", required=True, choices=sorted(TRANSITIONS))
    parser.add_argument(
        "--task-ref",
        help="identifier of the task building this handoff; required for the two transitions that must cross a task boundary",
    )
    args = parser.parse_args()
    if args.transition in CUT_TRANSITIONS and not (args.task_ref or "").strip():
        parser.error(f"--task-ref is required for {args.transition}: the consuming stage must run in a different task")
    try:
        destination = build(args.project, args.transition, args.task_ref)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(f"wrote fresh handoff: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
