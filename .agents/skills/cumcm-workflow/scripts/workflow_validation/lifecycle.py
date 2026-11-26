"""Handoffs, decision logs and the artifacts bound to each stage."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from provenance import digest_records

from .common import (
    Finding,
    as_list,
    check_envelope,
    finding,
    item_id,
    nonempty,
    read_json,
    safe_project_path,
    sha256,
)
from .computation import discover_run_manifests
from .contracts import CONTRACT_PATHS, OPTIONAL_CONTRACTS, PAPER_CONTRACTS, STAGES


def check_handoff(data: Any, root: Path, path: str, expected_transition: str) -> list[Finding]:
    findings = check_envelope(data, "stage_handoff", TRANSITIONS_FOR_CHECK[expected_transition][0], path)
    if not isinstance(data, dict):
        return findings
    upstream, downstream = TRANSITIONS_FOR_CHECK[expected_transition]
    if data.get("transition") != expected_transition or data.get("upstream_stage") != upstream or data.get("downstream_stage") != downstream:
        findings.append(finding("HANDOFF-E001", "error", "structural", upstream, path, "handoff transition metadata is inconsistent"))
    records: list[dict[str, str]] = []
    for item in as_list(data.get("canonical_artifacts")):
        if not isinstance(item, dict):
            continue
        target = safe_project_path(root, item.get("path"))
        if target is None or not target.is_file():
            findings.append(finding("HANDOFF-E002", "error", "structural", upstream, path, f"handoff artifact is missing: {item.get('path')}"))
            continue
        actual = sha256(target)
        if actual != item.get("sha256"):
            findings.append(finding("HANDOFF-E003", "error", "execution", upstream, path, f"handoff is stale because upstream changed: {item.get('path')}"))
        records.append({"path": str(item.get("path")), "sha256": actual})
    if records and data.get("upstream_digest") != digest_records(records):
        findings.append(finding("HANDOFF-E004", "error", "execution", upstream, path, "handoff upstream digest is stale"))
    if expected_transition == "validation-paper":
        payload = data.get("payload")
        required = {"problem_summary", "model_summary", "verified_results", "claims", "limitations", "representation_candidates", "official_format_files", "official_materials"}
        if not isinstance(payload, dict) or not required.issubset(payload):
            findings.append(finding("HANDOFF-E005", "error", "structural", "validation", path, "paper handoff lacks the compact canonical paper brief"))
    if expected_transition == "paper-delivery":
        payload = data.get("payload")
        required = {"approved_pdf", "editable_latex", "computation_evidence", "official_materials", "official_compliance"}
        roles = {
            str(item.get("role"))
            for item in as_list(data.get("canonical_artifacts"))
            if isinstance(item, dict)
        }
        canonical_roles = {"results", "official_run", "computation_source", "compile_receipt", "editable_source", "approved_pdf"}
        if not isinstance(payload, dict) or not required.issubset(payload):
            findings.append(finding("HANDOFF-E006", "error", "structural", "paper", path, "delivery handoff lacks final PDF, editable-source binding, computation evidence, or official-material status"))
        elif not as_list(payload.get("computation_evidence")):
            findings.append(finding("HANDOFF-E007", "error", "execution", "paper", path, "delivery handoff contains no canonical official computation source chain"))
        if not canonical_roles.issubset(roles):
            findings.append(finding("HANDOFF-E008", "error", "structural", "paper", path, "delivery handoff does not bind every required canonical delivery role"))
    return findings


CUT_CONSUMERS = {
    "handoff_computation_validation": ("computation-validation", "validation", "independent_review_result"),
    "handoff_validation_paper": ("validation-paper", "paper", "paper_plan"),
}


def consuming_task_ref(name: str, contract: Any) -> Any:
    """The task ref the downstream artifact reports for itself."""
    if not isinstance(contract, dict):
        return None
    if name == "independent_review_result":
        context = contract.get("reviewer_context")
        return context.get("task_ref") if isinstance(context, dict) else None
    return contract.get("authoring_task_ref")


def check_task_separation(contracts: dict[str, Any]) -> list[Finding]:
    """Two handoffs must cross a task boundary: evidence -> review, and review -> paper.

    The refs are self-reported, so this is a paste guard rather than proof; it catches
    the case the workflow actually cares about, one task doing both sides of a cut.
    Handoff contracts load only while finalizing, so these findings never appear in
    working mode and carry no mode branch of their own.
    """
    findings: list[Finding] = []
    for name, (transition, stage, consumer_name) in CUT_CONSUMERS.items():
        handoff = contracts.get(name)
        if not isinstance(handoff, dict):
            continue
        path = CONTRACT_PATHS[name]
        produced = handoff.get("producing_task_ref")
        consumer = contracts.get(consumer_name)
        consumed = consuming_task_ref(consumer_name, consumer)
        if not nonempty(produced):
            findings.append(
                finding(
                    "HANDOFF-E009",
                    "error",
                    "structural",
                    stage,
                    path,
                    f"{transition} handoff does not record the task that produced it; rebuild it with build_handoff.py --task-ref",
                )
            )
        elif nonempty(consumed) and str(produced) == str(consumed):
            findings.append(
                finding(
                    "HANDOFF-E010",
                    "error",
                    "semantic",
                    stage,
                    path,
                    f"{transition} was produced and consumed by the same task ({produced}); this cut must be crossed in a fresh task",
                )
            )
    return findings


TRANSITIONS_FOR_CHECK = {
    "modeling-computation": ("model-design", "computation"),
    "computation-validation": ("computation", "validation"),
    "validation-paper": ("validation", "paper"),
    "paper-delivery": ("paper", "delivery"),
}


def trusted_stage_snapshots(root: Path, through_stage: str) -> list[str]:
    trusted: list[str] = []
    chain_current = True
    for stage in STAGES[: STAGES.index(through_stage) + 1]:
        if not chain_current:
            break
        snapshot_path = root / ".cumcm" / "snapshots" / f"{stage}.json"
        snapshot, error = read_json(snapshot_path)
        if error or not isinstance(snapshot, dict) or snapshot.get("decision") != "accepted":
            chain_current = False
            break
        records = snapshot.get("artifacts")
        if not isinstance(records, list) or not records:
            chain_current = False
            break
        actual: list[dict[str, str]] = []
        current = True
        for item in records:
            if not isinstance(item, dict):
                current = False
                break
            target = safe_project_path(root, item.get("path"))
            if target is None or not target.is_file() or sha256(target) != item.get("sha256"):
                current = False
                break
            actual.append({"path": str(item.get("path")), "sha256": str(item.get("sha256"))})
        if current and snapshot.get("snapshot_digest") == digest_records(actual):
            trusted.append(stage)
        else:
            chain_current = False
    return trusted


def stage_scope_paths(root: Path, stage: str) -> list[str]:
    mapping = {
        "intake": [CONTRACT_PATHS["sources"]],
        "problem-analysis": [CONTRACT_PATHS["facts"], CONTRACT_PATHS["capabilities"]],
        "model-design": [CONTRACT_PATHS["model"], CONTRACT_PATHS["cross_question"]],
        "computation": [CONTRACT_PATHS["results"]],
        "validation": [CONTRACT_PATHS["independent_review_package"], CONTRACT_PATHS["independent_review_result"], CONTRACT_PATHS["claims"]],
        "paper": [CONTRACT_PATHS["figures"], *(CONTRACT_PATHS[name] for name in PAPER_CONTRACTS)],
        "delivery": [CONTRACT_PATHS["delivery"], CONTRACT_PATHS["compile_receipt"]],
    }
    optional_paths = {CONTRACT_PATHS[name] for name in OPTIONAL_CONTRACTS}
    # An optional contract only enters a decision scope when the project actually has it.
    paths = [rel for rel in mapping[stage] if rel not in optional_paths or (root / rel).is_file()]
    if stage == "computation":
        # Only official runs enter a formal decision scope. Exploratory runs must be
        # free to appear and change without invalidating an accepted stage.
        for manifest_path in discover_run_manifests(root):
            manifest, error = read_json(manifest_path)
            if error or not isinstance(manifest, dict) or manifest.get("official_run") is not True:
                continue
            paths.append(manifest_path.relative_to(root).as_posix())
            implementation = manifest.get("implementation")
            snapshot = implementation.get("source_snapshot") if isinstance(implementation, dict) else None
            if isinstance(snapshot, dict):
                paths.extend(str(value) for value in as_list(snapshot.get("files")))
    elif stage == "paper":
        latex, _ = read_json(root / CONTRACT_PATHS["latex_template"])
        quality, _ = read_json(root / CONTRACT_PATHS["paper_quality"])
        if isinstance(latex, dict):
            paths.extend(str(value) for value in as_list(latex.get("required_files")))
        if isinstance(quality, dict) and isinstance(quality.get("paper_artifact"), dict):
            paths.append(str(quality["paper_artifact"].get("path")))
    elif stage == "delivery":
        delivery, _ = read_json(root / CONTRACT_PATHS["delivery"])
        if isinstance(delivery, dict):
            paths.extend(str(item.get("path")) for item in as_list(delivery.get("files")) if isinstance(item, dict))
    return list(dict.fromkeys(paths))


def check_decision_log(root: Path, state: Any) -> list[Finding]:
    path = ".cumcm/decisions.jsonl"
    log_path = root / path
    if not log_path.is_file():
        return [finding("DECISION-E001", "error", "semantic", "intake", path, "finalizing project has no append-only decision log", gate_only=True)]
    findings: list[Finding] = []
    events: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line_number, raw in enumerate(log_path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            findings.append(finding("DECISION-E002", "error", "structural", "intake", path, f"invalid JSON on line {line_number}: {exc}"))
            continue
        if not isinstance(event, dict):
            findings.append(finding("DECISION-E003", "error", "structural", "intake", path, f"decision event on line {line_number} is not an object"))
            continue
        decision_id = item_id(event, "decision_id")
        if not decision_id or decision_id in seen_ids:
            findings.append(finding("DECISION-E004", "error", "structural", "intake", path, f"missing or duplicate decision_id on line {line_number}: {decision_id}"))
        seen_ids.add(decision_id)
        if event.get("stage") not in STAGES or event.get("decision") not in {"accepted", "revision_requested"}:
            findings.append(finding("DECISION-E007", "error", "structural", "intake", path, f"invalid stage or decision on line {line_number}", related_ids=[decision_id]))
        for required_field in ("reviewer", "task_turn_ref", "user_visible_summary", "decided_at"):
            if not nonempty(event.get(required_field)):
                findings.append(finding("DECISION-E011", "error", "structural", "intake", path, f"decision event lacks {required_field} on line {line_number}", related_ids=[decision_id]))
        if not isinstance(event.get("scope"), list) or not event.get("scope"):
            findings.append(finding("DECISION-E012", "error", "structural", "intake", path, f"decision event has no artifact scope on line {line_number}", related_ids=[decision_id]))
        else:
            for entry in event["scope"]:
                if not isinstance(entry, dict) or safe_project_path(root, entry.get("path")) is None or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256", ""))):
                    findings.append(finding("DECISION-E013", "error", "structural", "intake", path, f"decision event has an invalid scope entry on line {line_number}", related_ids=[decision_id]))
        events.append(event)
    latest: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("stage") in STAGES:
            latest[str(event["stage"])] = event
    state_map = state.get("stages", {}) if isinstance(state, dict) else {}
    for stage in STAGES:
        if state_map.get(stage) != "passed":
            continue
        event = latest.get(stage)
        if event is None or event.get("decision") != "accepted":
            findings.append(finding("DECISION-E008", "error", "semantic", stage, path, f"passed stage lacks a latest accepted decision: {stage}", gate_only=True))
            continue
        snapshot_path = root / ".cumcm" / "snapshots" / f"{stage}.json"
        snapshot, snapshot_error = read_json(snapshot_path)
        expected_scope = [
            {"path": str(entry.get("path")), "sha256": str(entry.get("sha256"))}
            for entry in as_list(event.get("scope")) if isinstance(entry, dict)
        ]
        if snapshot_error or not isinstance(snapshot, dict):
            findings.append(finding("DECISION-E014", "error", "structural", stage, path, f"passed stage lacks its derived snapshot: {stage}"))
        elif snapshot.get("decision_id") != event.get("decision_id") or snapshot.get("decision") != "accepted" or snapshot.get("snapshot_digest") != digest_records(expected_scope):
            findings.append(finding("DECISION-E015", "error", "structural", stage, path, f"stage snapshot is not bound to the latest accepted decision: {stage}"))
        scope = {entry.get("path"): entry.get("sha256") for entry in as_list(event.get("scope")) if isinstance(entry, dict)}
        for rel in stage_scope_paths(root, stage):
            artifact = safe_project_path(root, rel)
            if artifact is None or not artifact.is_file():
                findings.append(finding("DECISION-E009", "error", "structural", stage, path, f"decision scope target is missing: {rel}"))
            elif scope.get(rel) != sha256(artifact):
                findings.append(finding("DECISION-E010", "error", "structural", stage, path, f"accepted decision is stale or does not cover current artifact: {rel}"))
    return findings
