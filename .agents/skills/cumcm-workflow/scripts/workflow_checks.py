#!/usr/bin/env python3
"""Deterministic v0.6 evidence, freshness, and cross-artifact checks.

The checks in this module establish structure, provenance, recorded execution,
and declared relationships. They do not establish mathematical correctness.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from json_pointer import resolve_json_pointer

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from provenance import digest_records, sha256_file, snapshot_matches


STAGES = [
    "intake",
    "problem-analysis",
    "model-design",
    "computation",
    "validation",
    "paper",
    "delivery",
]
STAGE_STATUSES = {
    "not_started",
    "in_progress",
    "passed",
    "needs_revision",
}
EVIDENCE_STATES = {
    "not_checked",
    "missing_evidence",
    "supported_not_reproduced",
    "reproduced",
    "partially_supported",
    "contradicted",
    "ambiguous",
    "not_applicable",
}
REVIEW_DECISIONS = {"unreviewed", "accepted", "accepted_with_concerns", "revision_requested"}
GATE_MODES = {"preflight", "enforce"}
WORKFLOW_VERSION = "0.6.0"
WORKFLOW_MODES = {"working", "finalizing"}
REQUIRED_CONTEXT_EXCLUSIONS = {
    "originating_task_transcript",
    "debug_history",
    "failed_runs",
    "prior_review_prose",
}

CONTRACT_PATHS = {
    "state": ".cumcm/state.json",
    "sources": "problem/SOURCE_MANIFEST.json",
    "facts": "analysis/PROBLEM_FACTS.json",
    "capabilities": "analysis/TASK_CAPABILITIES.json",
    "model": "model/MODEL_CONTRACT.json",
    "cross_question": "model/CROSS_QUESTION_LEDGER.json",
    "results": "results/RESULTS_INDEX.json",
    "independent_review_package": "validation/independent-review-package/REVIEW_PACKAGE_MANIFEST.json",
    "independent_review_result": "validation/INDEPENDENT_REVIEW_RESULT.json",
    "claims": "validation/CLAIM_LEDGER.json",
    "figures": "figures/FIGURE_MANIFEST.json",
    "paper_plan": "paper/PAPER_PLAN.json",
    "latex_template": "paper/LATEX_TEMPLATE_MANIFEST.json",
    "paper_quality": "paper/PAPER_QUALITY_REPORT.json",
    "paper_revisions": "paper/PAPER_REVISION_LOG.json",
    "paper_visible_text": "paper/PAPER_VISIBLE_TEXT_REPORT.json",
    "delivery": "delivery/DELIVERY_MANIFEST.json",
    "compile_receipt": "delivery/COMPILE_RECEIPT.json",
    "handoff_modeling_computation": "handoffs/modeling-computation/HANDOFF.json",
    "handoff_computation_validation": "handoffs/computation-validation/HANDOFF.json",
    "handoff_validation_paper": "handoffs/validation-paper/HANDOFF.json",
    "handoff_paper_delivery": "handoffs/paper-delivery/HANDOFF.json",
}

STAGE_CONTRACTS = {
    "intake": ("state", "sources"),
    "problem-analysis": ("state", "sources", "facts", "capabilities"),
    "model-design": ("state", "sources", "facts", "capabilities", "model"),
    "computation": ("state", "sources", "facts", "capabilities", "model", "results"),
    "validation": (
        "state", "sources", "facts", "capabilities", "model", "results",
        "independent_review_package", "independent_review_result", "claims",
    ),
    "paper": (
        "state", "sources", "facts", "capabilities", "model", "results",
        "independent_review_package", "independent_review_result", "claims",
        "paper_plan", "latex_template", "paper_quality", "paper_visible_text",
    ),
    "delivery": (
        "state", "sources", "facts", "capabilities", "model", "results",
        "independent_review_package", "independent_review_result", "claims",
        "paper_plan", "latex_template", "paper_quality", "paper_visible_text",
        "delivery", "compile_receipt",
    ),
}

# Contracts that only a frozen (finalizing) project must carry.
FINALIZING_CONTRACTS = {
    "model-design": ("cross_question",),
    "computation": ("cross_question",),
    "validation": ("cross_question",),
    "paper": ("cross_question",),
    "delivery": ("cross_question",),
}

# Contracts that are never required but are checked whenever the project has them,
# from the stage where they first make sense.
OPTIONAL_CONTRACTS = {
    "cross_question": "model-design",
    "figures": "validation",
    "paper_revisions": "paper",
}

PAPER_CONTRACTS = ("paper_plan", "latex_template", "paper_quality", "paper_visible_text")

SCHEMA_FILES = {
    "state": "workflow-state.schema.json",
    "sources": "source-manifest.schema.json",
    "facts": "problem-facts.schema.json",
    "capabilities": "task-capabilities.schema.json",
    "model": "model-contract.schema.json",
    "cross_question": "cross-question-ledger.schema.json",
    "results": "results-index.schema.json",
    "independent_review_package": "independent-review-package.schema.json",
    "independent_review_result": "independent-review-result.schema.json",
    "claims": "claim-ledger.schema.json",
    "figures": "figure-manifest.schema.json",
    "paper_plan": "paper-plan.schema.json",
    "latex_template": "latex-template-manifest.schema.json",
    "paper_quality": "paper-quality-report.schema.json",
    "paper_revisions": "paper-revision-log.schema.json",
    "paper_visible_text": "paper-visible-text-report.schema.json",
    "delivery": "delivery-manifest.schema.json",
    "compile_receipt": "compile-receipt.schema.json",
    "run": "run-manifest.schema.json",
    "handoff_modeling_computation": "handoff.schema.json",
    "handoff_computation_validation": "handoff.schema.json",
    "handoff_validation_paper": "handoff.schema.json",
    "handoff_paper_delivery": "handoff.schema.json",
}

STRONG_CLAIM_PATTERNS = {
    "global_optimality": re.compile(r"\bglobal(?:ly)? optimal\b|全局最优", re.I),
    "unbiasedness": re.compile(r"\bunbiased\b|无偏", re.I),
    "equivalence": re.compile(r"\bequivalent\b|统计等价|等价", re.I),
    "causality": re.compile(r"\bcausal(?:ity)?\b|因果", re.I),
    "robustness": re.compile(r"\brobust(?:ness)?\b|鲁棒", re.I),
}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: str
    evidence_type: str
    owning_stage: str
    path: str
    message: str
    pointer: str = ""
    related_ids: list[str] = field(default_factory=list)
    remediation: str = ""
    gate_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def finding(
    rule_id: str,
    severity: str,
    evidence_type: str,
    stage: str,
    path: str,
    message: str,
    *,
    pointer: str = "",
    related_ids: Iterable[str] = (),
    remediation: str = "",
    gate_only: bool = False,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=severity,
        evidence_type=evidence_type,
        owning_stage=stage,
        path=path,
        message=message,
        pointer=pointer,
        related_ids=list(related_ids),
        remediation=remediation,
        gate_only=gate_only,
    )


def sha256(path: Path) -> str:
    return sha256_file(path)


def safe_project_path(root: Path, rel: Any) -> Path | None:
    if not isinstance(rel, str) or not rel.strip():
        return None
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def read_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)


def check_schema(data: Any, schema_name: str, stage: str, path: str) -> list[Finding]:
    schema_dir = Path(__file__).resolve().parents[1] / "schemas"
    schema_path = schema_dir / SCHEMA_FILES[schema_name]
    schema, error = read_json(schema_path)
    if error:
        return [finding("SCHEMA-E001", "error", "structural", stage, path, f"cannot load schema: {error}")]
    common_path = schema_dir / "common.schema.json"
    common, common_error = read_json(common_path)
    if common_error:
        return [finding("SCHEMA-E001", "error", "structural", stage, path, f"cannot load common schema: {common_error}")]
    common_resource = Resource.from_contents(common)
    registry = Registry().with_resource(common_path.as_uri(), common_resource)
    registry = registry.with_resource(common.get("$id", common_path.as_uri()), common_resource)
    validator = Draft202012Validator(schema, registry=registry)
    findings: list[Finding] = []
    for issue in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path)):
        pointer = "" if not issue.absolute_path else "/" + "/".join(str(part) for part in issue.absolute_path)
        findings.append(
            finding(
                "SCHEMA-E002",
                "error",
                "structural",
                stage,
                path,
                issue.message,
                pointer=pointer,
            )
        )
    return findings


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def item_id(item: Any, *keys: str) -> str:
    if not isinstance(item, dict):
        return ""
    for key in keys:
        value = item.get(key)
        if nonempty(value):
            return value.strip()
    return ""


def ids(items: Any, *keys: str) -> set[str]:
    return {ident for item in as_list(items) if (ident := item_id(item, *keys))}


def require_fields(
    items: Any,
    fields: tuple[str, ...],
    id_keys: tuple[str, ...],
    prefix: str,
    stage: str,
    path: str,
) -> list[Finding]:
    findings: list[Finding] = []
    if not isinstance(items, list):
        return [finding(f"{prefix}-E001", "error", "structural", stage, path, "expected a list")]
    seen: set[str] = set()
    for index, item in enumerate(items):
        pointer = f"/{index}"
        if not isinstance(item, dict):
            findings.append(
                finding(f"{prefix}-E002", "error", "structural", stage, path, "item must be an object", pointer=pointer)
            )
            continue
        ident = item_id(item, *id_keys)
        if not ident:
            findings.append(
                finding(f"{prefix}-E003", "error", "structural", stage, path, "item has no stable ID", pointer=pointer)
            )
        elif ident in seen:
            findings.append(
                finding(
                    f"{prefix}-E004",
                    "error",
                    "structural",
                    stage,
                    path,
                    f"duplicate ID: {ident}",
                    pointer=pointer,
                    related_ids=[ident],
                )
            )
        seen.add(ident)
        for name in fields:
            value = item.get(name)
            if value is None or value == "" or value == []:
                findings.append(
                    finding(
                        f"{prefix}-E005",
                        "error",
                        "structural",
                        stage,
                        path,
                        f"{ident or f'item {index}'} missing {name}",
                        pointer=f"{pointer}/{name}",
                        related_ids=[ident] if ident else [],
                    )
                )
    return findings


def check_envelope(data: Any, expected_type: str, stage: str, path: str) -> list[Finding]:
    if not isinstance(data, dict):
        return [finding("ENV-E001", "error", "structural", stage, path, "contract must be a JSON object")]
    findings: list[Finding] = []
    if data.get("schema_version") != WORKFLOW_VERSION:
        findings.append(
            finding(
                "ENV-E002",
                "error",
                "structural",
                stage,
                path,
                f"schema_version must be {WORKFLOW_VERSION}",
                pointer="/schema_version",
            )
        )
    if data.get("artifact_type") != expected_type:
        findings.append(
            finding(
                "ENV-E003",
                "error",
                "structural",
                stage,
                path,
                f"artifact_type must be {expected_type}",
                pointer="/artifact_type",
            )
        )
    if not nonempty(data.get("project_id")):
        findings.append(finding("ENV-E004", "error", "structural", stage, path, "project_id is required"))
    return findings


def check_state(data: Any, path: str, mode: str = "working") -> list[Finding]:
    findings = check_envelope(data, "workflow_state", "intake", path)
    if not isinstance(data, dict):
        return findings
    if data.get("workflow_version") != WORKFLOW_VERSION:
        findings.append(finding("STATE-E001", "error", "structural", "intake", path, f"workflow_version must be {WORKFLOW_VERSION}"))
    if data.get("mode") not in WORKFLOW_MODES:
        findings.append(finding("STATE-E009", "error", "structural", "intake", path, "mode must be working or finalizing"))
    implementation = data.get("implementation")
    if not isinstance(implementation, dict):
        findings.append(finding("STATE-E010", "error", "structural", "intake", path, "implementation preference is required"))
    else:
        preferred = implementation.get("preferred")
        fallback = implementation.get("fallback")
        if preferred not in {"matlab", "python"} or fallback not in {"matlab", "python"} or preferred == fallback:
            findings.append(finding("STATE-E011", "error", "structural", "intake", path, "implementation preferred/fallback must be distinct MATLAB/Python values"))
        if implementation.get("selection") not in {"auto", "matlab", "python"}:
            findings.append(finding("STATE-E012", "error", "structural", "intake", path, "implementation selection is invalid"))
    current = data.get("current_stage")
    stages = data.get("stages")
    if current not in STAGES:
        findings.append(finding("STATE-E002", "error", "structural", "intake", path, "current_stage is invalid"))
    if not isinstance(stages, dict):
        findings.append(finding("STATE-E003", "error", "structural", "intake", path, "stages must be an object"))
        return findings
    for stage in STAGES:
        if stage not in stages:
            findings.append(finding("STATE-E004", "error", "structural", "intake", path, f"missing stage: {stage}"))
        elif stages[stage] not in STAGE_STATUSES:
            findings.append(finding("STATE-E005", "error", "structural", "intake", path, f"invalid status for {stage}"))
    extra = sorted(set(stages) - set(STAGES))
    if extra:
        findings.append(finding("STATE-E006", "error", "structural", "intake", path, f"unknown stages: {', '.join(extra)}"))
    if current in STAGES:
        index = STAGES.index(current)
        for prior in STAGES[:index]:
            if stages.get(prior) != "passed":
                severity = "error" if mode == "finalizing" else "warning"
                findings.append(
                    finding("STATE-E007", severity, "structural", prior, path, f"prior stage must pass before {current}: {prior}")
                )
        for later in STAGES[index + 1 :]:
            # needs_revision downstream is the normal state after reopening an upstream stage.
            if stages.get(later) == "passed":
                findings.append(
                    finding("STATE-E008", "error", "structural", later, path, f"downstream stage is still marked passed while {current} is open: {later}")
                )
    return findings


def check_sources(data: Any, root: Path, path: str) -> list[Finding]:
    findings = check_envelope(data, "source_manifest", "intake", path)
    if not isinstance(data, dict):
        return findings
    sources = data.get("sources")
    findings.extend(require_fields(sources, ("path", "origin", "acquisition"), ("source_id",), "SOURCE", "intake", path))
    for index, source in enumerate(as_list(sources)):
        if not isinstance(source, dict):
            continue
        ident = item_id(source, "source_id")
        rel = source.get("path")
        file_path = safe_project_path(root, rel)
        if file_path is None:
            findings.append(finding("SOURCE-E006", "error", "structural", "intake", path, f"unsafe source path: {rel}", related_ids=[ident]))
            continue
        if not file_path.is_file():
            findings.append(finding("SOURCE-E007", "error", "structural", "intake", path, f"missing source file: {rel}", related_ids=[ident]))
            continue
        recorded_hash = source.get("sha256")
        if source.get("origin") in {"official", "organizer_attachment"}:
            if not nonempty(recorded_hash) or recorded_hash != sha256(file_path):
                findings.append(finding("SOURCE-E008", "error", "structural", "intake", path, f"official source hash is missing or mismatched: {rel}", related_ids=[ident]))
        elif nonempty(recorded_hash) and recorded_hash != sha256(file_path):
            findings.append(finding("SOURCE-W008", "warning", "structural", "intake", path, f"optional source hash is stale: {rel}", related_ids=[ident]))
        if source.get("size") is not None and source.get("size") != file_path.stat().st_size:
            findings.append(finding("SOURCE-W009", "warning", "structural", "intake", path, f"source size metadata is stale: {rel}", related_ids=[ident]))
        if source.get("mutable") is not False and source.get("origin") in {"official", "organizer_attachment"}:
            findings.append(finding("SOURCE-E010", "error", "semantic", "intake", path, f"official source must declare mutable=false: {ident}"))
        acquisition = source.get("acquisition")
        if source.get("origin") in {"official", "organizer_attachment"}:
            if not isinstance(acquisition, dict) or acquisition.get("provided_by_user") is not True:
                findings.append(finding("SOURCE-E011", "error", "semantic", "intake", path, f"official material must be supplied or explicitly identified by the user: {ident}"))
            elif acquisition.get("method") not in {"user_local_file", "user_supplied_url"}:
                findings.append(finding("SOURCE-E012", "error", "semantic", "intake", path, f"official material cannot come from autonomous search: {ident}"))
    return findings


def check_facts(data: Any, source_ids: set[str], path: str) -> list[Finding]:
    findings = check_envelope(data, "problem_facts", "problem-analysis", path)
    if not isinstance(data, dict):
        return findings
    subproblems = data.get("subproblems")
    facts = data.get("facts")
    findings.extend(require_fields(subproblems, ("request", "expected_output"), ("subproblem_id", "id"), "SUBPROBLEM", "problem-analysis", path))
    findings.extend(require_fields(facts, ("statement", "source_id", "location"), ("fact_id", "id"), "FACT", "problem-analysis", path))
    for fact in as_list(facts):
        if not isinstance(fact, dict):
            continue
        ident = item_id(fact, "fact_id", "id")
        source_id = fact.get("source_id")
        if source_id not in source_ids:
            findings.append(finding("FACT-E006", "error", "structural", "problem-analysis", path, f"{ident} cites unknown source: {source_id}", related_ids=[ident, str(source_id)]))
        if fact.get("extraction_method") == "ocr" and fact.get("render_verified") is not True:
            findings.append(finding("FACT-E007", "error", "visual", "problem-analysis", path, f"OCR-routed fact lacks rendered-page verification: {ident}", related_ids=[ident]))
    return findings


def check_acceptance_checks(
    data: Any,
    capability_passed_assertions: dict[str, set[str]],
    path: str,
    mode: str,
) -> list[Finding]:
    """A capability is delivered when the program says so, not when the agent says so.

    `acceptance_checks` used to be free text, which meant "did we actually do the task"
    was the one question this workflow could not answer -- it is written up in
    docs/limitations.md as unsolvable. It is solvable: a check judged `recorded` names an
    assertion the solving program must write out through --assert-file, which the run
    manifest already carries with source `recorded`. The judgement stays with the author,
    who has to phrase the check so a program can fail it; the verdict becomes machine fact.
    """
    findings: list[Finding] = []
    if not isinstance(data, dict):
        return findings
    frozen = mode == "finalizing"
    for capability in as_list(data.get("capabilities")):
        if not isinstance(capability, dict):
            continue
        ident = item_id(capability, "capability_id")
        if capability.get("lifecycle_state") not in {"executed", "validated"}:
            continue
        passed = capability_passed_assertions.get(ident, set())
        for check in as_list(capability.get("acceptance_checks")):
            if not isinstance(check, dict) or check.get("judge") != "recorded":
                continue
            name = check.get("assertion_name")
            check_id = item_id(check, "check_id")
            if not nonempty(name):
                findings.append(finding("CAP-E012", "error", "structural", "computation", path, f"{check_id} is judged by a recorded assertion but does not name one", related_ids=[ident, check_id]))
            elif str(name) not in passed:
                findings.append(
                    finding(
                        "CAP-E012",
                        "error" if frozen else "warning",
                        "execution",
                        "computation",
                        path,
                        f"{ident} declares it executed, but no official run recorded a passing assertion named {name} for {check_id}",
                        related_ids=[ident, check_id],
                    )
                )
    return findings


def check_capability_coverage(
    capabilities: Any,
    model: Any,
    paper_quality: Any,
    path: str,
    mode: str,
) -> list[Finding]:
    """Nothing stopped a capability from being declared and then quietly dropped.

    The failure it guards is the one where the agent narrows the task until it fits what
    it can do: every downstream check then verifies faithfulness to a shrunken reading,
    and none of them can see that the reading shrank. So every declared capability must
    be claimed by some model component, and none may still be unfinished once the paper
    calls itself final.
    """
    findings: list[Finding] = []
    if not isinstance(capabilities, dict):
        return findings
    declared = {
        item_id(capability, "capability_id"): capability
        for capability in as_list(capabilities.get("capabilities"))
        if isinstance(capability, dict) and item_id(capability, "capability_id")
    }
    if not declared:
        return findings
    if isinstance(model, dict):
        claimed: set[str] = set()
        for component in as_list(model.get("components")):
            if isinstance(component, dict):
                claimed.update(str(value) for value in as_list(component.get("capability_ids")))
        unclaimed = sorted(set(declared) - claimed)
        if unclaimed:
            findings.append(
                finding(
                    "CAP-E013",
                    "error" if mode == "finalizing" else "warning",
                    "semantic",
                    "model-design",
                    path,
                    f"no model component takes on these capabilities: {', '.join(unclaimed)}",
                    related_ids=unclaimed,
                )
            )
    if isinstance(paper_quality, dict) and paper_quality.get("paper_status") == "final":
        unfinished = sorted(
            ident for ident, capability in declared.items()
            if capability.get("lifecycle_state") in {"planned", "blocked"}
        )
        if unfinished:
            findings.append(
                finding(
                    "CAP-E014",
                    "error",
                    "semantic",
                    "paper",
                    path,
                    f"the paper calls itself final while these capabilities are unfinished: {', '.join(unfinished)}",
                    related_ids=unfinished,
                )
            )
    return findings


def check_capabilities(data: Any, root: Path, fact_ids: set[str], subproblem_ids: set[str], path: str) -> list[Finding]:
    findings = check_envelope(data, "task_capabilities", "problem-analysis", path)
    if not isinstance(data, dict):
        return findings
    capabilities = data.get("capabilities")
    findings.extend(
        require_fields(
            capabilities,
            ("subproblem_id", "objective", "required_output", "acceptance_checks"),
            ("capability_id",),
            "CAP",
            "problem-analysis",
            path,
        )
    )
    owned_subproblems: set[str] = set()
    for capability in as_list(capabilities):
        if not isinstance(capability, dict):
            continue
        ident = item_id(capability, "capability_id")
        subproblem = capability.get("subproblem_id")
        if subproblem not in subproblem_ids:
            findings.append(finding("CAP-E006", "error", "structural", "problem-analysis", path, f"{ident} names unknown subproblem: {subproblem}", related_ids=[ident]))
        else:
            owned_subproblems.add(str(subproblem))
        for fact_id in as_list(capability.get("fact_ids")):
            if fact_id not in fact_ids:
                findings.append(finding("CAP-E007", "error", "structural", "problem-analysis", path, f"{ident} names unknown fact: {fact_id}", related_ids=[ident, str(fact_id)]))
        checks = capability.get("acceptance_checks")
        if not isinstance(checks, list) or not checks:
            findings.append(finding("CAP-E008", "error", "semantic", "problem-analysis", path, f"{ident} has no observable acceptance check", related_ids=[ident]))
        if capability.get("lifecycle_state") in {"implemented", "executed", "validated"}:
            entry_points = as_list(capability.get("code_entry_points"))
            if not entry_points:
                findings.append(finding("CAP-E010", "error", "execution", "computation", path, f"implemented capability has no code entry point: {ident}", related_ids=[ident]))
            for entry_point in entry_points:
                rel = str(entry_point).split(":", 1)[0]
                code_path = safe_project_path(root, rel)
                if code_path is None or not code_path.is_file():
                    findings.append(finding("CAP-E011", "error", "execution", "computation", path, f"capability code entry point is missing: {entry_point}", related_ids=[ident]))
    missing = sorted(subproblem_ids - owned_subproblems)
    if missing:
        findings.append(finding("CAP-E009", "error", "semantic", "problem-analysis", path, f"subproblems without capability ownership: {', '.join(missing)}", related_ids=missing))
    return findings


DRAFT_MODEL_FIELDS = ("capability_ids", "method", "scope")
FROZEN_MODEL_FIELDS = ("capability_ids", "variables", "inputs", "outputs", "method", "scope", "verification_plan")


def check_model(data: Any, capability_ids: set[str], path: str, mode: str) -> list[Finding]:
    """Working mode accepts a draft contract; finalizing requires the frozen one."""
    findings = check_envelope(data, "model_contract", "model-design", path)
    if not isinstance(data, dict):
        return findings
    frozen = mode == "finalizing"
    components = data.get("components")
    findings.extend(
        require_fields(
            components,
            FROZEN_MODEL_FIELDS if frozen else DRAFT_MODEL_FIELDS,
            ("model_id",),
            "MODEL",
            "model-design",
            path,
        )
    )
    owned: set[str] = set()
    for component in as_list(components):
        if not isinstance(component, dict):
            continue
        ident = item_id(component, "model_id")
        for capability_id in as_list(component.get("capability_ids")):
            if capability_id not in capability_ids:
                findings.append(finding("MODEL-E006", "error", "structural", "model-design", path, f"{ident} owns unknown capability: {capability_id}", related_ids=[ident, str(capability_id)]))
            else:
                owned.add(capability_id)
        if frozen and len(as_list(component.get("candidates"))) < 2:
            findings.append(finding("MODEL-W007", "warning", "semantic", "model-design", path, f"frozen model compares fewer than two candidates for {ident}", related_ids=[ident]))
    missing = sorted(capability_ids - owned)
    if missing:
        # Ownership is the answer-the-question invariant; it blocks only once the model is frozen.
        severity = "error" if frozen else "warning"
        findings.append(finding("MODEL-E008", severity, "semantic", "model-design", path, f"capabilities without model ownership: {', '.join(missing)}", related_ids=missing))
    return findings


def check_selection_check(data: Any, path: str) -> list[Finding]:
    """The person confirms the model choice before anything expensive is computed.

    This is the earliest and cheapest of the three checkpoints: nothing has been run,
    so a rejection costs only the conversation. It is also the one with the most
    leverage, because the judgement criterion is settled here and every result
    downstream inherits it.
    """
    findings: list[Finding] = []
    if not isinstance(data, dict):
        return findings
    declared: list[str] = []
    for component in as_list(data.get("components")):
        if not isinstance(component, dict):
            continue
        for candidate in as_list(component.get("candidates")):
            if isinstance(candidate, dict):
                candidate_id = item_id(candidate, "candidate_id")
                if candidate_id:
                    declared.append(candidate_id)
    if not declared and not data.get("selection_check"):
        return findings
    check = data.get("selection_check")
    if not isinstance(check, dict) or check.get("decision") != "accepted" or check.get("reviewer_kind") != "human_user":
        findings.append(finding("MODEL-E016", "error", "semantic", "model-design", path, "the model choice must be confirmed before it is computed against", gate_only=True))
        return findings
    if not nonempty(check.get("reviewer")) or not nonempty(check.get("reviewed_at")):
        findings.append(finding("MODEL-E017", "error", "semantic", "model-design", path, "an accepted selection check lacks reviewer or review time"))
    presented = {str(value) for value in as_list(check.get("presented_candidate_ids"))}
    unseen = sorted(set(declared) - presented)
    if unseen:
        findings.append(finding("MODEL-E018", "error", "semantic", "model-design", path, f"the model choice was accepted without these candidates being presented: {', '.join(unseen)}", related_ids=unseen))
    if check.get("reviewer_kind") == "human_user" and not presented:
        findings.append(finding("MODEL-E019", "error", "semantic", "model-design", path, "a selection check attributed to a person must record the candidates presented to them"))
    return findings


def require_resolved_model(data: dict) -> None:
    """Only the candidate decision must be complete before official computation.

    Do not require future official runs or the full finalizing contract here.
    """
    components = data.get("components")
    if not isinstance(components, list) or not components:
        raise ValueError("model comparison is unresolved: no model components")
    for component in components:
        candidates = component.get("candidates", []) if isinstance(component, dict) else []
        if (not isinstance(candidates, list) or not candidates
                or any(not isinstance(c, dict) or c.get("status") not in {"selected", "rejected"} for c in candidates)
                or sum(c.get("status") == "selected" for c in candidates) != 1):
            raise ValueError("model comparison is unresolved: each component needs exactly one selected candidate and all others rejected")


def require_human_checkpoint(root: Path, stage: str) -> None:
    """Action boundary, not a full finalizing check (which needs future runs).

    Reuse the existing contract and snapshot; no new receipt or hash layer.
    These are honest records of a conversation, not authentication of a human.
    """
    names = {"model-design": ("model", "selection_check"),
             "validation": ("claims", "conclusion_check"),
             "delivery": ("delivery", "final_check")}
    name, field = names[stage]
    rel = CONTRACT_PATHS[name]
    data, error = read_json(root / rel)
    if error or not isinstance(data, dict):
        raise ValueError(f"show the {stage} material and wait for the user; missing {rel}")
    check = data.get(field)
    if not isinstance(check, dict):
        raise ValueError(f"{stage} awaits the user; no checkpoint recorded")
    if check.get("decision") != "accepted" or check.get("reviewer_kind") != "human_user":
        raise ValueError(f"{stage} awaits the user's explicit decision; model self-review cannot approve it")
    checks = {"model-design": lambda: check_selection_check(data, rel),
              "validation": lambda: check_conclusion_check(data, rel),
              "delivery": lambda: check_final_check(data, rel, data.get("compile"))}
    if stage == "model-design":
        require_resolved_model(data)
    errors = [item for item in checks[stage]() if item.severity == "error"]
    if errors:
        raise ValueError(errors[0].message)
    snapshot_path = root / ".cumcm" / "snapshots" / f"{stage}.json"
    if not snapshot_path.is_file():
        raise ValueError(f"{stage} has no approval snapshot; record the user's reply with record_decision.py --confirm-human")
    if snapshot_path.exists():
        snapshot, error = read_json(snapshot_path)
        records = snapshot.get("artifacts", []) if isinstance(snapshot, dict) else []
        record = next((item for item in records if item.get("path") == rel), None)
        if error or not record or any(
            not isinstance(item, dict)
            or (target := safe_project_path(root, item.get("path"))) is None
            or not target.is_file() or item.get("sha256") != sha256(target)
            for item in records
        ):
            raise ValueError(f"{stage} material changed after approval; show the revision and obtain a new decision")


def check_model_candidates(
    data: Any,
    run_ids: set[str],
    run_candidates: dict[str, set[str]],
    path: str,
    mode: str,
    runs_known: bool,
) -> list[Finding]:
    """Check that a model was chosen, not merely asserted.

    A candidate declares why it is worth considering and what evidence would tell
    it apart. Selecting one is only meaningful if some run actually evaluated it,
    so the selection is checked against the runs that named the candidate.
    """
    findings: list[Finding] = []
    if not isinstance(data, dict):
        return findings
    frozen = mode == "finalizing"
    for component in as_list(data.get("components")):
        if not isinstance(component, dict):
            continue
        ident = item_id(component, "model_id")
        candidates = [item for item in as_list(component.get("candidates")) if isinstance(item, dict)]
        if not candidates:
            continue
        seen: set[str] = set()
        selected = [item for item in candidates if item.get("status") == "selected"]
        for candidate in candidates:
            candidate_id = item_id(candidate, "candidate_id")
            if not candidate_id:
                findings.append(finding("MODEL-E010", "error", "structural", "model-design", path, f"{ident} has a candidate without an ID", related_ids=[ident]))
                continue
            if candidate_id in seen:
                findings.append(finding("MODEL-E011", "error", "structural", "model-design", path, f"{ident} has a duplicate candidate ID: {candidate_id}", related_ids=[ident, candidate_id]))
            seen.add(candidate_id)
            if not as_list(candidate.get("discriminating_evidence")):
                findings.append(finding("MODEL-W012", "warning", "semantic", "model-design", path, f"{candidate_id} does not say what evidence would tell it apart from the other candidates", related_ids=[ident, candidate_id]))
            evaluation_runs = [str(value) for value in as_list(candidate.get("evaluation_run_ids"))]
            for run_id in evaluation_runs if runs_known else []:
                if run_id not in run_ids:
                    findings.append(finding("MODEL-E015", "error", "structural", "model-design", path, f"{candidate_id} cites an unknown evaluation run: {run_id}", related_ids=[ident, candidate_id, run_id]))
                elif candidate_id not in run_candidates.get(run_id, set()):
                    findings.append(finding("MODEL-W016", "warning", "structural", "model-design", path, f"{run_id} does not declare that it evaluated {candidate_id}; record it with record_run.py --candidate", related_ids=[ident, candidate_id, run_id]))
            if candidate.get("status") in {"selected", "rejected"} and not nonempty(candidate.get("decision_rationale")):
                severity = "error" if frozen else "warning"
                findings.append(finding("MODEL-E014", severity, "semantic", "model-design", path, f"{candidate_id} is {candidate.get('status')} without a recorded reason", related_ids=[ident, candidate_id]))
            if runs_known and candidate.get("status") == "selected" and not evaluation_runs:
                severity = "error" if frozen else "warning"
                findings.append(
                    finding(
                        "MODEL-W014",
                        severity,
                        "numerical",
                        "model-design",
                        path,
                        f"{candidate_id} was selected without citing any run that evaluated it",
                        related_ids=[ident, candidate_id],
                        remediation="evaluate candidates with record_run.py --candidate <id>, then cite those runs in evaluation_run_ids",
                    )
                )
        if len(selected) != 1:
            severity = "error" if frozen else "warning"
            findings.append(
                finding(
                    "MODEL-E013",
                    severity,
                    "semantic",
                    "model-design",
                    path,
                    f"{ident} must end with exactly one selected candidate; found {len(selected)}",
                    related_ids=[ident],
                )
            )
        elif nonempty(component.get("method")) and nonempty(selected[0].get("method")):
            if selected[0]["method"].strip().casefold() not in component["method"].strip().casefold():
                findings.append(finding("MODEL-W017", "warning", "semantic", "model-design", path, f"{ident} method does not mention the selected candidate's method", related_ids=[ident]))
    return findings


def check_model_verification(
    data: Any,
    capability_assertions: dict[str, set[str]],
    path: str,
) -> list[Finding]:
    """A frozen verification plan must be backed by assertions an official run recorded."""
    findings: list[Finding] = []
    if not isinstance(data, dict):
        return findings
    for component in as_list(data.get("components")):
        if not isinstance(component, dict):
            continue
        ident = item_id(component, "model_id")
        plan = [str(entry.get("assertion_name", "")) if isinstance(entry, dict) else str(entry)
                for entry in as_list(component.get("verification_plan"))]
        recorded: set[str] = set()
        for capability_id in as_list(component.get("capability_ids")):
            recorded |= capability_assertions.get(str(capability_id), set())
        if not recorded:
            findings.append(
                finding(
                    "MODEL-E009",
                    "error",
                    "numerical",
                    "model-design",
                    path,
                    f"frozen model has no executed verification: {ident} owns no assertion an official run recorded itself",
                    related_ids=[ident],
                )
            )
            continue
        folded = " ".join(sorted(recorded)).casefold()
        unmatched = [entry for entry in plan if entry.strip() and entry.strip().casefold() not in folded]
        if unmatched:
            findings.append(
                finding(
                    "MODEL-W010",
                    "warning",
                    "numerical",
                    "model-design",
                    path,
                    f"{ident} verification plan entries have no matching recorded assertion: {', '.join(unmatched)}",
                    related_ids=[ident],
                )
            )
    return findings


def check_cross_question(data: Any, subproblem_ids: set[str], path: str) -> list[Finding]:
    findings = check_envelope(data, "cross_question_ledger", "model-design", path)
    if not isinstance(data, dict):
        return findings
    items = data.get("shared_items")
    findings.extend(require_fields(items, ("name", "producer", "consumers", "definition", "unit"), ("shared_id",), "CROSS", "model-design", path))
    signatures: dict[str, tuple[Any, Any]] = {}
    for item in as_list(items):
        if not isinstance(item, dict):
            continue
        ident = item_id(item, "shared_id")
        for subproblem in [item.get("producer"), *as_list(item.get("consumers"))]:
            if subproblem not in subproblem_ids and subproblem != "official_source":
                findings.append(finding("CROSS-E006", "error", "structural", "model-design", path, f"{ident} names unknown subproblem: {subproblem}", related_ids=[ident]))
        name = str(item.get("name", "")).strip().casefold()
        signature = (item.get("definition"), item.get("unit"))
        if name in signatures and signatures[name] != signature:
            findings.append(finding("CROSS-E007", "error", "semantic", "model-design", path, f"shared name has incompatible definition or unit: {item.get('name')}", related_ids=[ident]))
        signatures[name] = signature
    return findings


def live_path_of(frozen: Any) -> str | None:
    """runs/<id>/source/code/solve.py -> code/solve.py (None if not a frozen path)."""
    parts = str(frozen).split("/")
    if len(parts) > 3 and parts[0] == "runs" and parts[2] in {"source", "outputs", "inputs"}:
        return "/".join(parts[3:])
    return None


def superseded_run_ids(root: Path) -> set[str]:
    """A run is superseded when a later run names it as its parent.

    Derived, never written back: stamping the old manifest would change its hash
    and stale every accepted decision that bound it.
    """
    superseded: set[str] = set()
    for manifest_path in discover_run_manifests(root):
        manifest, error = read_json(manifest_path)
        if error or not isinstance(manifest, dict):
            continue
        # A failed or exploratory rerun replaces nothing: it cannot back a result,
        # so letting it retire its parent would invalidate the only usable evidence.
        if manifest.get("official_run") is not True or manifest.get("status") != "completed" or manifest.get("exit_code") != 0:
            continue
        parent = manifest.get("parent_run_id")
        if nonempty(parent) and str(parent) != str(manifest.get("run_id")):
            superseded.add(str(parent))
    return superseded


def discover_run_manifests(root: Path) -> list[Path]:
    runs = root / "runs"
    return sorted(runs.glob("*/RUN_MANIFEST.json")) if runs.is_dir() else []


def check_run(data: Any, root: Path, rel_path: str, capability_ids: set[str], superseded: bool = False) -> list[Finding]:
    """Official runs carry the formal evidence burden; exploratory runs are kept but never block.

    A superseded run is history: its frozen evidence must still verify, but the
    workspace has legitimately moved on from the files it read.
    """
    findings = check_envelope(data, "run_manifest", "computation", rel_path)
    if not isinstance(data, dict):
        return findings
    official_run = data.get("official_run") is True
    # Exploratory runs exist so that Deferred Model Selection is cheap. They are
    # recorded, never trusted, and never allowed to block the formal chain.
    sev = "error" if official_run else "warning"

    structural = ("run_id", "argv", "working_directory", "started_at", "finished_at", "exit_code", "status", "official_run", "implementation", "outputs")
    # An exploratory run has no capability and no formal input yet -- that is what makes it
    # exploratory. Reporting their absence produced two warnings per exploratory run and
    # nothing actionable, which is how a checker teaches people to skim past its output.
    formal = ("purpose", "capability_ids", "inputs", "environment", "stdout_path", "stderr_path")
    if not official_run:
        formal = tuple(name for name in formal if name not in ("capability_ids", "inputs"))
    for field_name in structural:
        if data.get(field_name) in (None, "", []):
            findings.append(finding("RUN-E001", "error", "execution", "computation", rel_path, f"missing run field: {field_name}", pointer=f"/{field_name}"))
    for field_name in formal:
        if data.get(field_name) in (None, "", []):
            findings.append(finding("RUN-E001", sev, "execution", "computation", rel_path, f"missing run field: {field_name}", pointer=f"/{field_name}"))

    if official_run and (data.get("status") != "completed" or data.get("exit_code") != 0):
        findings.append(finding("RUN-E002", "error", "execution", "computation", rel_path, "official run must record completed status and exit code 0"))
    elif not official_run and (data.get("status") != "completed" or data.get("exit_code") != 0):
        findings.append(finding("RUN-W002", "info", "execution", "computation", rel_path, "exploratory run did not complete; it cannot support claims"))

    implementation = data.get("implementation")
    if not isinstance(implementation, dict):
        findings.append(finding("RUN-E017", sev, "execution", "computation", rel_path, "run lacks implementation selection and source binding"))
    else:
        language = implementation.get("selected_language")
        if language not in {"matlab", "python"}:
            findings.append(finding("RUN-E018", sev, "execution", "computation", rel_path, "selected_language must be matlab or python"))
        entry_point = safe_project_path(root, str(implementation.get("entry_point", "")).split(":", 1)[0])
        if entry_point is None or not entry_point.is_file():
            findings.append(finding("RUN-E019", sev, "execution", "computation", rel_path, "selected implementation entry point is missing"))
        snapshot = implementation.get("source_snapshot")
        if official_run and not snapshot_matches(root, snapshot):
            findings.append(finding("RUN-E021", "error", "execution", "computation", rel_path, "frozen source evidence is missing or was altered"))
        elif official_run and not superseded and isinstance(snapshot, dict):
            # The frozen copy is immutable, so staleness now means the working tree
            # moved on from the run that backs the formal results.
            from canonical_evidence import live_evidence_drift
            drifted = live_evidence_drift(root, data)
            if drifted:
                findings.append(
                    finding(
                        "RUN-E020",
                        "error",
                        "execution",
                        "computation",
                        rel_path,
                        "the working tree no longer matches this official run: " + ", ".join(sorted(drifted)),
                        remediation=f"record_run.py --rerun {data.get('run_id')} --official",
                    )
                )
        argv = [str(value).casefold() for value in as_list(data.get("argv"))]
        if language == "matlab" and argv and not any("matlab" in value for value in argv):
            findings.append(finding("RUN-E021", sev, "execution", "computation", rel_path, "MATLAB implementation is not bound to a MATLAB command"))
        if language == "python" and argv and not any("python" in value for value in argv):
            findings.append(finding("RUN-E022", sev, "execution", "computation", rel_path, "Python implementation is not bound to a Python command"))

    if official_run and not as_list(data.get("capability_ids")):
        findings.append(finding("RUN-E023", "error", "structural", "computation", rel_path, "official run must name at least one capability"))
    for capability_id in as_list(data.get("capability_ids")):
        if capability_id not in capability_ids:
            findings.append(finding("RUN-E003", sev, "structural", "computation", rel_path, f"run names unknown capability: {capability_id}", related_ids=[str(capability_id)]))

    for kind in ("inputs", "outputs"):
        required_hash_roles = {"formal_input", "claim_bearing_output"}
        allowed_roles = {"formal_input", "auxiliary_input"} if kind == "inputs" else {"claim_bearing_output", "intermediate_output", "diagnostic_output"}
        values = data.get(kind)
        if not isinstance(values, list) or (kind == "outputs" and not values):
            findings.append(finding("RUN-E004", sev, "execution", "computation", rel_path, f"{kind} must be a {'nonempty ' if kind == 'outputs' else ''}list"))
            continue
        for entry in values:
            if not isinstance(entry, dict):
                findings.append(finding("RUN-E005", sev, "structural", "computation", rel_path, f"{kind} entry must be an object"))
                continue
            file_path = safe_project_path(root, entry.get("path"))
            if file_path is None or not file_path.is_file() or file_path.stat().st_size == 0:
                findings.append(finding("RUN-E006", sev, "execution", "computation", rel_path, f"missing or empty {kind[:-1]}: {entry.get('path')}"))
                continue
            role = entry.get("evidence_role")
            if role not in allowed_roles:
                findings.append(finding("RUN-E016", sev, "structural", "computation", rel_path, f"missing or invalid evidence_role for {kind[:-1]}: {entry.get('path')}"))
                continue
            recorded_hash = entry.get("sha256")
            if role in required_hash_roles:
                if not nonempty(recorded_hash):
                    findings.append(finding("RUN-E015", sev, "execution", "computation", rel_path, f"required hash is missing for {role}: {entry.get('path')}"))
                elif recorded_hash != sha256(file_path):
                    # Inputs are hashed in place, so a superseded run legitimately
                    # points at material the workspace has since regenerated.
                    drift_sev = "warning" if (superseded and kind == "inputs") else sev
                    findings.append(finding("RUN-E007", drift_sev, "execution", "computation", rel_path, f"hash mismatch for {kind[:-1]}: {entry.get('path')}"))
            elif nonempty(recorded_hash) and recorded_hash != sha256(file_path):
                findings.append(finding("RUN-W007", "warning", "execution", "computation", rel_path, f"optional hash is stale for {role}: {entry.get('path')}"))
            if entry.get("size") is not None and entry.get("size") != file_path.stat().st_size:
                findings.append(finding("RUN-W013", "warning", "execution", "computation", rel_path, f"size metadata is stale for {kind[:-1]}; run refresh_evidence.py: {entry.get('path')}"))

    for log_name in ("stdout_path", "stderr_path"):
        log_path = safe_project_path(root, data.get(log_name))
        if log_path is None or not log_path.is_file():
            findings.append(finding("RUN-E012", sev, "execution", "computation", rel_path, f"missing recorded log: {data.get(log_name)}"))

    assertions = data.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        if official_run:
            findings.append(finding("RUN-W001", "warning", "numerical", "computation", rel_path, "official run records no assertions"))
    if isinstance(assertions, list) and assertions and official_run and not any(isinstance(item, dict) and item.get("source") == "recorded" for item in assertions):
        findings.append(
            finding(
                "RUN-W003",
                "warning",
                "numerical",
                "computation",
                rel_path,
                "every assertion on this official run was declared on the command line, not recorded by the run",
                remediation="have the program write its own verdicts and pass them with record_run.py --assert-file",
            )
        )
    # Independent of the one above: an official run whose assertions are all declared AND
    # one of them failed used to report only the provenance warning, because these were
    # branches of one chain. A failed check must be reported whoever wrote the verdict.
    failed_assertions = [
        (index, item) for index, item in enumerate(assertions, 1)
        if isinstance(item, dict) and item.get("passed") is not True
    ] if isinstance(assertions, list) else []
    if failed_assertions:
        # A failed assertion inside an exploratory run is a finding about the experiment,
        # not about the formal chain, so it never blocks.
        labels = []
        for index, item in failed_assertions:
            name = item.get("name")
            safe_name = ""
            if isinstance(name, str):
                safe_name = "".join(char if char.isprintable() else "?" for char in name.strip())[:80]
            labels.append(f"#{index} ({safe_name or 'unnamed'})")
        findings.append(finding("RUN-E008", sev, "numerical", "computation", rel_path,
                                "failed assertions: " + ", ".join(labels)))
    return findings




def check_results(
    data: Any,
    root: Path,
    run_ids: set[str],
    official_run_ids: set[str],
    run_output_roles: dict[str, dict[str, str]],
    path: str,
    superseded_ids: set[str] | None = None,
) -> list[Finding]:
    superseded_ids = superseded_ids or set()
    findings = check_envelope(data, "results_index", "computation", path)
    if not isinstance(data, dict):
        return findings
    if as_list(data.get("results")):
        from canonical_evidence import resolve_official_computation
        try:
            resolve_official_computation(root, data)
        except (ValueError, OSError) as exc:
            findings.append(finding("RESULT-E018", "error", "execution", "computation", path,
                                    f"current official evidence is invalid: {exc}"))
    results = data.get("results")
    findings.extend(require_fields(results, ("name", "unit", "run_id", "output_locator", "scope", "evidence_state"), ("result_id",), "RESULT", "computation", path))
    for result in as_list(results):
        if not isinstance(result, dict):
            continue
        ident = item_id(result, "result_id")
        if result.get("run_id") not in run_ids:
            findings.append(finding("RESULT-E006", "error", "execution", "computation", path, f"{ident} names unknown run: {result.get('run_id')}", related_ids=[ident]))
        elif result.get("run_id") not in official_run_ids:
            findings.append(finding("RESULT-E016", "error", "execution", "computation", path, f"{ident} must reference a successful official run", related_ids=[ident]))
        elif str(result.get("run_id")) in superseded_ids:
            findings.append(
                finding(
                    "RESULT-E017",
                    "error",
                    "execution",
                    "computation",
                    path,
                    f"{ident} still cites {result.get('run_id')}, which a later run superseded",
                    related_ids=[ident, str(result.get("run_id"))],
                    remediation="index_result.py --follow-lineage, or say why the earlier run is the one you mean",
                )
            )
        if result.get("evidence_state") not in EVIDENCE_STATES:
            findings.append(finding("RESULT-E007", "error", "structural", "computation", path, f"{ident} has invalid evidence_state", related_ids=[ident]))
        locator = result.get("output_locator")
        if not nonempty(locator) or "#" not in locator:
            findings.append(finding("RESULT-E008", "error", "execution", "computation", path, f"{ident} output_locator must be path#JSON-pointer", related_ids=[ident]))
            continue
        rel, pointer = locator.split("#", 1)
        run_id = result.get("run_id")
        declared_outputs = run_output_roles.get(str(run_id), {})
        if rel not in declared_outputs:
            findings.append(finding("RESULT-E014", "error", "execution", "computation", path, f"{ident} locator is not a declared output of run {run_id}: {rel}", related_ids=[ident, str(run_id)]))
        elif declared_outputs[rel] != "claim_bearing_output":
            findings.append(finding("RESULT-E015", "error", "execution", "computation", path, f"{ident} locator must reference a claim_bearing_output: {rel}", related_ids=[ident, str(run_id)]))
        output_path = safe_project_path(root, rel)
        if output_path is None or not output_path.is_file():
            findings.append(finding("RESULT-E009", "error", "execution", "computation", path, f"{ident} output file is missing: {rel}", related_ids=[ident]))
            continue
        output_data, error = read_json(output_path)
        if error:
            findings.append(finding("RESULT-E010", "error", "execution", "computation", path, f"{ident} output is not readable JSON: {error}", related_ids=[ident]))
            continue
        stored_value, found = resolve_json_pointer(output_data, pointer)
        if not found:
            findings.append(finding("RESULT-E011", "error", "execution", "computation", path, f"{ident} JSON pointer does not resolve: {pointer}", related_ids=[ident]))
        elif "value" in result and result.get("value") != stored_value:
            findings.append(finding("RESULT-E012", "error", "numerical", "computation", path, f"{ident} indexed value differs from executed output", related_ids=[ident]))
    return findings


def check_independent_review_package(data: Any, root: Path, path: str) -> list[Finding]:
    findings = check_envelope(data, "independent_review_package", "validation", path)
    if not isinstance(data, dict):
        return findings
    excluded = {str(value) for value in as_list(data.get("context_excluded"))}
    missing_exclusions = sorted(REQUIRED_CONTEXT_EXCLUSIONS - excluded)
    if missing_exclusions:
        findings.append(
            finding(
                "IREVIEW-E001",
                "error",
                "semantic",
                "validation",
                path,
                "review package must record the prior reasoning it excluded: " + ", ".join(missing_exclusions),
                remediation="rebuild the package with build_independent_review_package.py",
            )
        )
    for field in ("package_root", "review_skill_path", "review_request_path"):
        target = safe_project_path(root, data.get(field))
        if target is None or not target.exists():
            findings.append(finding("IREVIEW-E002", "error", "structural", "validation", path, f"independent review package is missing {field}: {data.get(field)}"))
    files = as_list(data.get("files"))
    roles = {str(item.get("role")) for item in files if isinstance(item, dict)}
    required_roles = {"official_input", "problem_contract", "model_contract", "computation_source", "run_record", "executed_output", "review_instruction"}
    missing_roles = sorted(required_roles - roles)
    if missing_roles:
        findings.append(finding("IREVIEW-E003", "error", "structural", "validation", path, f"independent review package misses roles: {', '.join(missing_roles)}"))
    # Official files already copied as official_input retain that role after dedup.
    from canonical_evidence import resolve_official_computation
    try:
        inputs = {rel for run in resolve_official_computation(root) for rel in run["formal_inputs"]}
        source_manifest, _ = read_json(root / "problem/SOURCE_MANIFEST.json")
        official = {str(item.get("path")) for item in as_list((source_manifest or {}).get("sources"))
                    if isinstance(item, dict) and item.get("origin") in {"official", "organizer_attachment"}}
        for rel in sorted(inputs - official):
            expected_role = "formal_input"
            if not any(isinstance(item, dict) and item.get("source_path") == rel and item.get("role") == expected_role for item in files):
                findings.append(finding("IREVIEW-E003", "error", "structural", "validation", path,
                                        f"review package must include {rel} as {expected_role}"))
    except (ValueError, OSError) as exc:
        findings.append(finding("IREVIEW-E025", "error", "execution", "validation", path,
                                f"review package current evidence is invalid: {exc}"))
    digest_entries: list[dict[str, str]] = []
    upstream_entries: list[dict[str, str]] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        target = safe_project_path(root, item.get("path"))
        if target is None or not target.is_file() or target.stat().st_size == 0:
            findings.append(finding("IREVIEW-E004", "error", "structural", "validation", path, f"review package file is missing: {item.get('path')}"))
            continue
        actual = sha256(target)
        if item.get("sha256") != actual:
            findings.append(finding("IREVIEW-E015", "error", "execution", "validation", path, f"review package file hash mismatch: {item.get('path')}"))
        entry = {"path": str(item.get("path")), "sha256": actual}
        if not str(item.get("path", "")).endswith("INDEPENDENT_REVIEW_RESULT_TEMPLATE.json"):
            digest_entries.append(entry)
        if item.get("source_path"):
            upstream = safe_project_path(root, item.get("source_path"))
            if upstream is None or not upstream.is_file() or sha256(upstream) != item.get("sha256"):
                findings.append(finding("IREVIEW-E025", "error", "execution", "validation", path, f"review package is stale against upstream: {item.get('source_path')}"))
            elif item.get("role") != "review_instruction":
                upstream_entries.append({"path": str(item.get("source_path")), "sha256": sha256(upstream)})
    if digest_entries and data.get("package_digest") != digest_records(digest_entries):
        findings.append(finding("IREVIEW-E016", "error", "execution", "validation", path, "independent review package digest is stale"))
    if upstream_entries and data.get("upstream_digest") != digest_records(upstream_entries):
        findings.append(finding("IREVIEW-E017", "error", "execution", "validation", path, "independent review upstream digest is stale"))
    if data.get("review_mode") == "targeted":
        previous = safe_project_path(root, data.get("previous_review_path"))
        targeted_file = next(
            (item for item in files if isinstance(item, dict) and str(item.get("path", "")).endswith("/TARGETED_FINDINGS.json")),
            None,
        )
        targeted_path = safe_project_path(root, targeted_file.get("path")) if isinstance(targeted_file, dict) else None
        targeted_data, targeted_error = read_json(targeted_path) if targeted_path is not None and targeted_path.is_file() else (None, "missing")
        required_targeted_fields = {"finding_id", "category", "location", "evidence", "recommendation"}
        packaged_findings = as_list(targeted_data.get("findings") if isinstance(targeted_data, dict) else [])
        packaged_ids = {
            item_id(item, "finding_id")
            for item in packaged_findings
            if isinstance(item, dict)
        }
        target_ids = {str(value) for value in as_list(data.get("target_finding_ids"))}
        targeted_is_self_contained = (
            isinstance(targeted_data, dict)
            and targeted_data.get("review_mode") == "targeted"
            and nonempty(targeted_data.get("source_review_id"))
            and bool(packaged_findings)
            and all(
                isinstance(item, dict)
                and set(item) == required_targeted_fields
                and all(nonempty(item.get(field)) for field in required_targeted_fields)
                for item in packaged_findings
            )
        )
        if previous is None or not previous.is_file() or not target_ids or targeted_error or packaged_ids != target_ids or not targeted_is_self_contained:
            findings.append(finding("IREVIEW-E018", "error", "semantic", "validation", path, "targeted re-review requires previous-review provenance and a self-contained target P0 finding brief"))
    selection = data.get("reviewer_selection")
    if not isinstance(selection, dict) or selection.get("status") != "recorded":
        findings.append(finding("IREVIEW-E005", "error", "structural", "validation", path, "the review package must record which task reviews it before validation", gate_only=True))
    elif not all(nonempty(selection.get(field)) for field in ("reviewer", "originating_task_ref", "task_ref")):
        findings.append(finding("IREVIEW-E006", "error", "structural", "validation", path, "recorded reviewer selection lacks reviewer, originating-task, or reviewer-task reference"))
    elif selection.get("originating_task_ref") == selection.get("task_ref"):
        findings.append(finding("IREVIEW-E026", "error", "semantic", "validation", path, "originating and reviewer task references must differ"))
    return findings


def check_independent_review_result(data: Any, root: Path, path: str, package: Any) -> list[Finding]:
    findings = check_envelope(data, "independent_review_result", "validation", path)
    if not isinstance(data, dict):
        return findings
    expected_package = CONTRACT_PATHS["independent_review_package"]
    if data.get("package_manifest_path") != expected_package:
        findings.append(finding("IREVIEW-E007", "error", "structural", "validation", path, "independent review result names a different package manifest"))
    if isinstance(package, dict):
        if data.get("package_digest") != package.get("package_digest"):
            findings.append(finding("IREVIEW-E019", "error", "execution", "validation", path, "review result is bound to a stale review package"))
        if data.get("review_mode") != package.get("review_mode"):
            findings.append(finding("IREVIEW-E020", "error", "structural", "validation", path, "review result mode differs from the package mode"))
    context = data.get("reviewer_context")
    if not isinstance(context, dict):
        return findings
    unanswered = sorted(
        field
        for field in ("reviewer_kind", "different_conversation", "independence_grade")
        if context.get(field) is None
    )
    if unanswered:
        findings.append(
            finding(
                "IREVIEW-E027",
                "error",
                "semantic",
                "validation",
                path,
                "reviewer independence must be positively asserted, not left at the template default: " + ", ".join(unanswered),
            )
        )
    if context.get("different_conversation") is not True or context.get("reviewer_kind") == "same_context_model" or context.get("independence_grade") == "correlated_self_review":
        findings.append(finding("IREVIEW-E009", "error", "semantic", "validation", path, "same-context or correlated self-review cannot satisfy the independent review gate"))
    selection = package.get("reviewer_selection") if isinstance(package, dict) else None
    if isinstance(selection, dict):
        if selection.get("reviewer") != context.get("reviewer") or selection.get("task_ref") != context.get("task_ref"):
            findings.append(finding("IREVIEW-E010", "error", "structural", "validation", path, "imported reviewer identity does not match the recorded selection"))
    raw_path = safe_project_path(root, data.get("raw_review_path"))
    if raw_path is None or not raw_path.is_file() or raw_path.stat().st_size == 0:
        findings.append(finding("IREVIEW-E011", "error", "structural", "validation", path, "raw independent review is missing"))
    review_findings = [item for item in as_list(data.get("findings")) if isinstance(item, dict)]
    open_p0 = [item_id(item, "finding_id") for item in review_findings if item.get("severity") == "P0" and item.get("status") == "open"]
    open_p1 = [item_id(item, "finding_id") for item in review_findings if item.get("severity") == "P1" and item.get("status") == "open"]
    open_p2 = [item_id(item, "finding_id") for item in review_findings if item.get("severity") == "P2" and item.get("status") == "open"]
    verdict = data.get("verdict")
    if verdict == "revision_required":
        if not open_p0:
            findings.append(finding("IREVIEW-E021", "error", "semantic", "validation", path, "revision_required is valid only when at least one P0 finding remains open"))
        findings.append(finding("IREVIEW-E012", "error", "semantic", "model-design", path, "open P0 finding requires revision; return to the earliest affected stage", related_ids=open_p0))
    elif verdict in {"accepted", "accepted_with_concerns"} and open_p0:
        findings.append(finding("IREVIEW-E022", "error", "semantic", "validation", path, "an accepted verdict cannot retain an open P0 finding", related_ids=open_p0))
    elif verdict == "inconclusive":
        findings.append(finding("IREVIEW-E013", "error", "semantic", "validation", path, "independent review is inconclusive"))
    for finding_id in open_p1:
        findings.append(finding("IREVIEW-W001", "warning", "semantic", "validation", path, f"review concern remains open: {finding_id}", related_ids=[finding_id]))
    for finding_id in open_p2:
        findings.append(finding("IREVIEW-I001", "info", "semantic", "validation", path, f"review suggestion remains open: {finding_id}", related_ids=[finding_id]))
    if data.get("review_mode") == "targeted":
        previous_path = safe_project_path(root, data.get("previous_review_path"))
        if previous_path is None or not previous_path.is_file():
            findings.append(finding("IREVIEW-E023", "error", "structural", "validation", path, "targeted re-review cannot locate its previous review"))
        else:
            previous, error = read_json(previous_path)
            previous_p0 = {
                item_id(item, "finding_id")
                for item in as_list(previous.get("findings") if isinstance(previous, dict) else [])
                if isinstance(item, dict) and item.get("severity") == "P0" and item.get("status") == "open"
            }
            targets = set(str(value) for value in as_list(data.get("target_finding_ids")))
            if error or not previous_p0.issubset(targets):
                findings.append(finding("IREVIEW-E024", "error", "semantic", "validation", path, "targeted re-review does not cover every prior open P0 finding", related_ids=sorted(previous_p0 - targets)))
    return findings


def claim_certificate_types(text: str) -> set[str]:
    return {name for name, pattern in STRONG_CLAIM_PATTERNS.items() if pattern.search(text)}


def check_conclusion_check(data: dict[str, Any], path: str) -> list[Finding]:
    """The person confirms the conclusions before anyone writes them up.

    This is the cheap place to say no: a rejection here costs a recomputation, the same
    rejection at delivery costs a rewritten paper. What the person is shown is the claim
    text, its scope and its evidence state -- not run ids or hashes, which nobody can
    audit by eye and which only dilute the few things they can.
    """
    findings: list[Finding] = []
    check = data.get("conclusion_check")
    if not isinstance(check, dict) or check.get("decision") != "accepted" or check.get("reviewer_kind") != "human_user":
        findings.append(finding("CLAIM-E021", "error", "semantic", "validation", path, "the conclusions must be confirmed before the paper is written", gate_only=True))
        return findings
    if not nonempty(check.get("reviewer")) or not nonempty(check.get("reviewed_at")):
        findings.append(finding("CLAIM-E022", "error", "semantic", "validation", path, "an accepted conclusion check lacks reviewer or review time"))
    presented = {str(item) for item in as_list(check.get("presented_claim_ids"))}
    declared = {item_id(claim, "claim_id") for claim in as_list(data.get("claims")) if isinstance(claim, dict)}
    declared.discard("")
    unseen = sorted(declared - presented)
    if unseen:
        findings.append(finding("CLAIM-E023", "error", "semantic", "validation", path, f"conclusions were accepted without being presented: {', '.join(unseen)}", related_ids=unseen))
    return findings


def check_claims(
    data: Any,
    known_ids: dict[str, set[str]],
    path: str,
    superseded_ids: set[str] | None = None,
) -> list[Finding]:
    superseded_ids = superseded_ids or set()
    findings = check_envelope(data, "claim_ledger", "validation", path)
    if not isinstance(data, dict):
        return findings
    claims = data.get("claims")
    findings.extend(require_fields(claims, ("text", "claim_type", "scope", "evidence_state"), ("claim_id",), "CLAIM", "validation", path))
    review = data.get("independent_review")
    if review is not None and (not isinstance(review, dict) or review.get("decision") not in {"accepted", "accepted_with_concerns"}):
        findings.append(finding("CLAIM-E006", "error", "semantic", "validation", path, "claim ledger references a non-accepted independent logic pass"))
    findings.extend(check_conclusion_check(data, path))
    for claim in as_list(claims):
        if not isinstance(claim, dict):
            continue
        ident = item_id(claim, "claim_id")
        text = str(claim.get("text", ""))
        state = claim.get("evidence_state")
        if state not in EVIDENCE_STATES:
            findings.append(finding("CLAIM-E007", "error", "structural", "validation", path, f"{ident} has invalid evidence_state", related_ids=[ident]))
        refs = claim.get("evidence", {})
        if not isinstance(refs, dict):
            findings.append(finding("CLAIM-E008", "error", "structural", "validation", path, f"{ident} evidence must be an object", related_ids=[ident]))
            refs = {}
        mapping = {
            "fact_ids": "facts",
            "model_ids": "models",
            "run_ids": "runs",
            "result_ids": "results",
            "figure_ids": "figures",
        }
        referenced = 0
        for field_name, known_name in mapping.items():
            for ref in as_list(refs.get(field_name)):
                referenced += 1
                if ref not in known_ids.get(known_name, set()):
                    findings.append(finding("CLAIM-E009", "error", "structural", "validation", path, f"{ident} names unknown {known_name[:-1]}: {ref}", related_ids=[ident, str(ref)]))
                elif known_name == "runs" and str(ref) in superseded_ids:
                    findings.append(finding("CLAIM-W020", "warning", "execution", "validation", path, f"{ident} cites {ref}, which a later run superseded", related_ids=[ident, str(ref)]))
        if state in {"supported_not_reproduced", "reproduced", "partially_supported"} and referenced == 0:
            findings.append(finding("CLAIM-E010", "error", "semantic", "validation", path, f"{ident} requires linked evidence", related_ids=[ident]))
        certificate_types = claim_certificate_types(text)
        certificates = as_list(claim.get("certificates"))
        declared_types = {item.get("type") for item in certificates if isinstance(item, dict)}
        missing = sorted(certificate_types - declared_types)
        if missing and state in {"supported_not_reproduced", "reproduced", "partially_supported"}:
            findings.append(finding("CLAIM-E011", "error", "semantic", "validation", path, f"strong claim lacks certificate declaration: {', '.join(missing)}", related_ids=[ident]))
        all_known_evidence = set().union(*known_ids.values()) if known_ids else set()
        for certificate in certificates:
            if not isinstance(certificate, dict) or not nonempty(certificate.get("type")):
                findings.append(finding("CLAIM-E015", "error", "structural", "validation", path, f"{ident} has malformed certificate", related_ids=[ident]))
                continue
            evidence_ids = as_list(certificate.get("evidence_ids"))
            if not nonempty(certificate.get("description")) or not evidence_ids:
                findings.append(finding("CLAIM-E016", "error", "semantic", "validation", path, f"{ident} certificate lacks description or evidence IDs: {certificate.get('type')}", related_ids=[ident]))
            for evidence_id in evidence_ids:
                if evidence_id not in all_known_evidence:
                    findings.append(finding("CLAIM-E017", "error", "structural", "validation", path, f"{ident} certificate names unknown evidence: {evidence_id}", related_ids=[ident, str(evidence_id)]))
            if certificate.get("type") == "global_optimality" and not nonempty(certificate.get("scope")):
                findings.append(finding("CLAIM-E018", "error", "semantic", "validation", path, f"{ident} global-optimality certificate lacks feasible-set scope", related_ids=[ident]))
            if certificate.get("type") == "robustness" and certificate.get("method") not in {"perturbation", "sensitivity", "out_of_sample", "stress_test"}:
                findings.append(finding("CLAIM-E019", "error", "semantic", "validation", path, f"{ident} robustness certificate lacks a recognized validation method", related_ids=[ident]))
        if state == "reproduced" and not as_list(refs.get("run_ids")):
            findings.append(finding("CLAIM-E012", "error", "execution", "validation", path, f"reproduced claim has no run evidence: {ident}", related_ids=[ident]))
        if state == "reproduced" and not isinstance(claim.get("reproduction"), dict):
            findings.append(finding("CLAIM-E013", "error", "execution", "validation", path, f"reproduced claim lacks claim-specific rerun comparison: {ident}", related_ids=[ident]))
        claim_review = claim.get("review")
        if claim_review is not None and (not isinstance(claim_review, dict) or claim_review.get("decision") not in {"accepted", "accepted_with_concerns"}):
            findings.append(finding("CLAIM-W014", "warning", "semantic", "validation", path, f"optional claim-level review is not accepted: {ident}", related_ids=[ident]))
    return findings


def check_figures(data: Any, root: Path, result_ids: set[str], run_ids: set[str], path: str, superseded_ids: set[str] | None = None) -> list[Finding]:
    superseded_ids = superseded_ids or set()
    findings = check_envelope(data, "figure_manifest", "paper", path)
    if not isinstance(data, dict):
        return findings
    figures = data.get("figures")
    findings.extend(require_fields(figures, ("kind", "purpose", "path", "caption_claims"), ("figure_id",), "FIGURE", "paper", path))
    for figure in as_list(figures):
        if not isinstance(figure, dict):
            continue
        ident = item_id(figure, "figure_id")
        kind = figure.get("kind")
        figure_path = safe_project_path(root, figure.get("path"))
        if figure_path is None or not figure_path.is_file() or figure_path.stat().st_size == 0:
            findings.append(finding("FIGURE-E010", "error", "visual", "paper", path, f"missing or empty figure file: {figure.get('path')}", related_ids=[ident]))
        elif nonempty(figure.get("sha256")) and figure.get("sha256") != sha256(figure_path):
            findings.append(finding("FIGURE-W011", "warning", "structural", "paper", path, f"figure changed since its manifest entry was recorded: {figure.get('path')}", related_ids=[ident]))
        for result_id in as_list(figure.get("result_ids")):
            if result_id not in result_ids:
                findings.append(finding("FIGURE-E006", "error", "structural", "paper", path, f"{ident} names unknown result: {result_id}", related_ids=[ident, str(result_id)]))
        for run_id in as_list(figure.get("run_ids")):
            if run_id not in run_ids:
                findings.append(finding("FIGURE-E007", "error", "structural", "paper", path, f"{ident} names unknown run: {run_id}", related_ids=[ident, str(run_id)]))
            elif str(run_id) in superseded_ids:
                findings.append(finding("FIGURE-W013", "warning", "structural", "paper", path, f"{ident} cites {run_id}, which a later run superseded", related_ids=[ident, str(run_id)]))
        if kind != "conceptual" and not as_list(figure.get("result_ids")):
            findings.append(finding("FIGURE-E008", "error", "semantic", "paper", path, f"quantitative figure lacks result provenance: {ident}", related_ids=[ident]))
        review = figure.get("visual_review")
        if review is not None and (not isinstance(review, dict) or review.get("decision") != "accepted"):
            findings.append(finding("FIGURE-W009", "warning", "visual", "paper", path, f"optional figure review is not accepted: {ident}", related_ids=[ident]))
    return findings


def check_delivery(data: Any, root: Path, path: str) -> list[Finding]:
    findings = check_envelope(data, "delivery_manifest", "delivery", path)
    if not isinstance(data, dict):
        return findings
    source_policy = data.get("source_policy")
    if not isinstance(source_policy, dict) or source_policy.get("mode") != "user_supplied_only" or source_policy.get("network_lookup_performed") is not False:
        findings.append(finding("DELIVERY-E013", "error", "semantic", "delivery", path, "delivery compliance review must use user-supplied materials only and must not perform autonomous network lookup"))
    elif as_list(source_policy.get("missing_user_materials")):
        findings.append(finding("DELIVERY-E014", "error", "semantic", "delivery", path, "delivery is blocked_missing_user_material; request the listed materials from the user"))
    deliverables = data.get("deliverables")
    required_roles = {"final_pdf", "editable_latex_source", "computation_source"}
    if not isinstance(deliverables, dict) or not required_roles.issubset(deliverables):
        findings.append(finding("DELIVERY-E015", "error", "structural", "delivery", path, "delivery must declare final PDF, editable LaTeX source, and computation source"))
    else:
        for role in sorted(required_roles):
            item = deliverables.get(role)
            if not isinstance(item, dict):
                continue
            artifact_path = safe_project_path(root, item.get("path"))
            entrypoint = safe_project_path(root, item.get("entrypoint"))
            if artifact_path is None or not artifact_path.exists() or entrypoint is None or not entrypoint.is_file():
                findings.append(finding("DELIVERY-E016", "error", "structural", "delivery", path, f"declared {role} or its entrypoint is missing"))
            if role != "final_pdf" and item.get("editable") is not True:
                findings.append(finding("DELIVERY-E017", "error", "semantic", "delivery", path, f"{role} must be delivered in editable form"))

    files = data.get("files")
    findings.extend(require_fields(files, ("path", "role", "size"), ("path",), "DELIVERY", "delivery", path))
    for item in as_list(files):
        if not isinstance(item, dict):
            continue
        rel = item.get("path")
        file_path = safe_project_path(root, rel)
        if file_path is None or not file_path.is_file() or file_path.stat().st_size == 0:
            findings.append(finding("DELIVERY-E006", "error", "structural", "delivery", path, f"missing or empty delivery file: {rel}"))
            continue
        recorded_hash = item.get("sha256")
        if item.get("role") == "final_pdf":
            if not nonempty(recorded_hash) or recorded_hash != sha256(file_path):
                findings.append(finding("DELIVERY-E007", "error", "structural", "delivery", path, f"final PDF hash is missing or mismatched: {rel}"))
        elif nonempty(recorded_hash) and recorded_hash != sha256(file_path):
            findings.append(finding("DELIVERY-W007", "warning", "structural", "delivery", path, f"optional delivery hash is stale: {rel}"))
        if item.get("size") != file_path.stat().st_size:
            findings.append(finding("DELIVERY-W008", "warning", "structural", "delivery", path, f"delivery size metadata is stale: {rel}"))
    compile_record = data.get("compile")
    if not isinstance(compile_record, dict) or compile_record.get("exit_code") != 0 or not compile_record.get("command"):
        findings.append(finding("DELIVERY-E009", "error", "execution", "delivery", path, "successful compile record is required"))
    elif safe_project_path(root, compile_record.get("log_path")) is None or not safe_project_path(root, compile_record.get("log_path")).is_file():
        findings.append(finding("DELIVERY-E012", "error", "execution", "delivery", path, "compile log is missing"))
    unresolved = as_list(data.get("unresolved_errors"))
    if unresolved:
        findings.append(finding("DELIVERY-E010", "error", "semantic", "delivery", path, "delivery contains unresolved errors"))
    findings.extend(check_final_check(data, path, compile_record))
    from delivery_archives import check_archives
    state, _ = read_json(root / ".cumcm/state.json")
    severity = "warning" if isinstance(state, dict) and state.get("mode") == "working" else "error"
    findings.extend(finding("DELIVERY-E021", severity, "structural", "delivery", path, problem)
                    for problem in check_archives(root, data))
    from submission_check import check_submission
    findings.extend(finding("DELIVERY-E022", severity, "structural", "delivery", path, problem)
                    for problem in check_submission(root, data))
    return findings


def check_final_check(data: dict[str, Any], path: str, compile_record: Any) -> list[Finding]:
    """The last approval before submission, and the only one left in this half.

    The trial that motivated this collapsed four separate approvals into one typed
    sentence, and recorded a human as having reviewed a PDF nobody had opened. So the
    decision now carries the pages that were actually rendered for the reviewer, and
    human_user is not claimable without them.
    """
    findings: list[Finding] = []
    check = data.get("final_check")
    if not isinstance(check, dict) or check.get("decision") != "accepted" or check.get("reviewer_kind") != "human_user":
        findings.append(finding("DELIVERY-E011", "error", "semantic", "delivery", path, "the final check before submission must be accepted", gate_only=True))
        return findings
    if not nonempty(check.get("reviewer")) or not nonempty(check.get("reviewed_at")):
        findings.append(finding("DELIVERY-E018", "error", "semantic", "delivery", path, "an accepted final check lacks reviewer or review time"))
    presented = {page for page in as_list(check.get("presented_pages")) if isinstance(page, int)}
    page_count = compile_record.get("page_count") if isinstance(compile_record, dict) else None
    rendered = set(range(1, page_count + 1)) if isinstance(page_count, int) and page_count > 0 else set()
    if check.get("reviewer_kind") == "human_user" and not presented:
        findings.append(finding("DELIVERY-E019", "error", "semantic", "delivery", path, "a final check attributed to a person must record the pages presented to them; record_compile.py renders them"))
    missing = sorted(rendered - presented)
    if presented and missing:
        findings.append(finding("DELIVERY-E020", "error", "visual", "delivery", path, f"the final check did not present every rendered page: {', '.join(str(page) for page in missing)}", related_ids=[str(page) for page in missing]))
    return findings


def check_bound_artifact(root: Path, artifact: Any, stage: str, path: str, rule_prefix: str) -> list[Finding]:
    if not isinstance(artifact, dict):
        return [finding(f"{rule_prefix}-E001", "error", "structural", stage, path, "artifact binding must be an object")]
    rel = artifact.get("path")
    file_path = safe_project_path(root, rel)
    if file_path is None or not file_path.is_file() or file_path.stat().st_size == 0:
        return [finding(f"{rule_prefix}-E002", "error", "structural", stage, path, f"bound artifact is missing or empty: {rel}")]
    if artifact.get("sha256") != sha256(file_path):
        return [finding(f"{rule_prefix}-E003", "error", "structural", stage, path, f"bound artifact hash mismatch: {rel}")]
    return []


def check_paper_plan(
    data: Any,
    path: str,
    subproblem_ids: set[str],
    claim_ids: set[str],
    result_ids: set[str],
    figure_ids: set[str],
) -> list[Finding]:
    findings = check_envelope(data, "paper_plan", "paper", path)
    if not isinstance(data, dict):
        return findings
    selected_claims: set[str] = set()
    for item in as_list(data.get("claim_selection")):
        if not isinstance(item, dict):
            continue
        claim_id = item_id(item, "claim_id")
        selected_claims.add(claim_id)
        if claim_id not in claim_ids:
            findings.append(finding("PPLAN-E002", "error", "structural", "paper", path, f"claim selection names unknown claim: {claim_id}", related_ids=[claim_id]))
        if item.get("subproblem_id") not in subproblem_ids:
            findings.append(finding("PPLAN-E003", "error", "structural", "paper", path, f"claim selection names unknown subproblem: {item.get('subproblem_id')}", related_ids=[claim_id]))

    visual_or_table = False
    for item in as_list(data.get("representation_plan")):
        if not isinstance(item, dict):
            continue
        medium = item.get("medium")
        visual_or_table = visual_or_table or medium in {"figure", "table"}
        for claim_id in as_list(item.get("claim_ids")):
            if claim_id not in selected_claims:
                findings.append(finding("PPLAN-E013", "error", "structural", "paper", path, f"representation names an unselected claim: {claim_id}", related_ids=[str(claim_id)]))
        for result_id in as_list(item.get("result_ids")):
            if result_id not in result_ids:
                findings.append(finding("PPLAN-E014", "error", "structural", "paper", path, f"representation names unknown result: {result_id}", related_ids=[str(result_id)]))
        artifact_id = item.get("artifact_id")
        if medium == "figure" and artifact_id and artifact_id not in figure_ids:
            findings.append(finding("PPLAN-W012", "warning", "visual", "paper", path, f"planned figure is not yet registered: {artifact_id}", related_ids=[str(artifact_id)]))
    if not visual_or_table:
        findings.append(finding("PPLAN-W001", "warning", "visual", "paper", path, "paper plan contains no table or figure; confirm that prose and equations are the clearest representation"))

    covered: set[str] = set()
    for section in as_list(data.get("paper_structure")):
        if not isinstance(section, dict):
            continue
        for subproblem in as_list(section.get("subproblem_ids")):
            if subproblem not in subproblem_ids:
                findings.append(finding("PPLAN-E007", "error", "structural", "paper", path, f"paper structure names unknown subproblem: {subproblem}", related_ids=[str(subproblem)]))
            else:
                covered.add(str(subproblem))
        for claim_id in as_list(section.get("claim_ids")):
            if claim_id not in selected_claims:
                findings.append(finding("PPLAN-E004", "error", "structural", "paper", path, f"paper structure names an unselected claim: {claim_id}", related_ids=[str(claim_id)]))
    missing_questions = sorted(subproblem_ids - covered)
    if missing_questions:
        findings.append(finding("PPLAN-E006", "error", "semantic", "paper", path, f"paper structure does not answer subproblems: {', '.join(missing_questions)}", related_ids=missing_questions))
    return findings


def check_paper_quality(
    data: Any,
    root: Path,
    path: str,
    subproblem_ids: set[str],
) -> list[Finding]:
    """Bind reviews to the exact PDF. Reviewer prose is recorded, not scored."""
    findings = check_envelope(data, "paper_quality_report", "paper", path)
    if not isinstance(data, dict):
        return findings
    paper = data.get("paper_artifact")
    findings.extend(check_bound_artifact(root, paper, "paper", path, "PQUALITY"))
    bound_hash = paper.get("sha256") if isinstance(paper, dict) else None
    bound_path = paper.get("path") if isinstance(paper, dict) else None
    content = data.get("content_report")
    layout = data.get("layout_report")
    for name, report in (("content", content), ("layout", layout)):
        if not isinstance(report, dict):
            continue
        artifact = report.get("artifact")
        if isinstance(artifact, dict) and (artifact.get("path") != bound_path or artifact.get("sha256") != bound_hash):
            findings.append(finding("PQUALITY-E004", "error", "structural", "paper", path, f"{name} report is bound to a different paper version"))
    if isinstance(content, dict):
        reviewed_questions = ids(content.get("questions"), "subproblem_id")
        missing = sorted(subproblem_ids - reviewed_questions)
        if missing:
            findings.append(finding("PQUALITY-E005", "error", "semantic", "paper", path, f"content report misses subproblems: {', '.join(missing)}", related_ids=missing))
        for question in as_list(content.get("questions")):
            if not isinstance(question, dict):
                continue
            subproblem = item_id(question, "subproblem_id")
            if question.get("status") == "fail":
                findings.append(finding("PQUALITY-W006", "warning", "semantic", "paper", path, f"paper content concern remains: {subproblem}", related_ids=[subproblem]))
            elif question.get("status") == "concern":
                findings.append(finding("PQUALITY-W016", "warning", "semantic", "paper", path, f"paper content can be improved: {subproblem}", related_ids=[subproblem]))
    if isinstance(layout, dict):
        for check in as_list(layout.get("checks")):
            if isinstance(check, dict) and "artifact" in check and check["artifact"] != paper:
                findings.append(finding("PQUALITY-E004", "error", "visual", "paper", path,
                                        f"layout check {check.get('check_id')} belongs to an older PDF; re-review it"))
        page_count = layout.get("page_count")
        pages = {page for page in as_list(layout.get("rendered_pages")) if isinstance(page, int)}
        if data.get("paper_status") == "final" and isinstance(page_count, int) and pages != set(range(1, page_count + 1)):
            findings.append(finding("PQUALITY-E008", "error", "visual", "paper", path, "final layout report must cover every rendered PDF page; record_compile.py renders them"))
        if any(isinstance(check, dict) and check.get("status") == "fail" for check in as_list(layout.get("checks"))):
            findings.append(finding("PQUALITY-E009", "error", "visual", "paper", path, "layout report contains failed checks"))
    issues = as_list(data.get("open_issues"))
    if data.get("paper_status") == "final":
        open_p0 = [item_id(issue, "issue_id") for issue in issues if isinstance(issue, dict) and issue.get("severity") == "P0" and issue.get("status") == "open"]
        if open_p0:
            findings.append(finding("PQUALITY-E011", "error", "semantic", "paper", path, f"final paper has open P0 issues: {', '.join(open_p0)}", related_ids=open_p0))
        for issue in issues:
            if not isinstance(issue, dict) or issue.get("status") != "open":
                continue
            issue_id = item_id(issue, "issue_id")
            if issue.get("severity") == "P1":
                findings.append(finding("PQUALITY-W011", "warning", "semantic", "paper", path, f"final paper retains a concern: {issue_id}", related_ids=[issue_id]))
            elif issue.get("severity") == "P2":
                findings.append(finding("PQUALITY-I011", "info", "semantic", "paper", path, f"final paper retains a suggestion: {issue_id}", related_ids=[issue_id]))
    return findings


def check_paper_visible_text(data: Any, root: Path, path: str, paper_quality: Any) -> list[Finding]:
    findings = check_envelope(data, "paper_visible_text_report", "paper", path)
    if not isinstance(data, dict):
        return findings
    artifact = data.get("paper_artifact")
    findings.extend(check_bound_artifact(root, artifact, "paper", path, "PTEXT"))
    quality_artifact = paper_quality.get("paper_artifact") if isinstance(paper_quality, dict) else None
    if isinstance(artifact, dict) and isinstance(quality_artifact, dict) and artifact != quality_artifact:
        findings.append(finding("PTEXT-E004", "error", "structural", "paper", path, "visible-text report is bound to a different PDF than the paper quality report"))
    if as_list(data.get("blocking_matches")):
        findings.append(finding("PTEXT-E005", "error", "semantic", "paper", path, "final PDF exposes workflow metadata, internal IDs, evidence states, or local paths"))
    open_flags = [flag for flag in as_list(data.get("review_flags")) if isinstance(flag, dict) and flag.get("resolution_status") == "open"]
    if open_flags:
        findings.append(finding("PTEXT-W006", "warning", "semantic", "paper", path, "visible-text report has numerical-presentation suggestions to review"))
    # The visible-text report is machine-produced. Blocking matches already fail, and
    # human acceptance lives in DELIVERY_MANIFEST.final_check; asking for a second
    # signature on a generated report only bought an extra self-attestation.
    return findings


def check_latex_template(
    data: Any,
    root: Path,
    path: str,
    subproblem_ids: set[str],
    paper_quality: Any,
    through_stage: str,
) -> list[Finding]:
    findings: list[Finding] = check_envelope(data, "latex_template_manifest", "paper", path)
    if not isinstance(data, dict):
        return findings
    required_files = as_list(data.get("required_files"))
    for rel in required_files:
        file_path = safe_project_path(root, rel)
        if file_path is None or not file_path.is_file() or file_path.stat().st_size == 0:
            findings.append(finding("LATEX-E001", "error", "structural", "paper", path, f"required LaTeX file is missing or empty: {rel}"))
    main_rel = data.get("main_path")
    main_path = safe_project_path(root, main_rel)
    main_text = ""
    if main_path is None or not main_path.is_file():
        findings.append(finding("LATEX-E002", "error", "structural", "paper", path, f"LaTeX main file is missing: {main_rel}"))
    else:
        main_text = main_path.read_text(encoding="utf-8", errors="replace")
    section_files = set(str(value) for value in as_list(data.get("section_files")))
    mappings = as_list(data.get("subproblem_sections"))
    mapped_ids: set[str] = set()
    mapped_pairs: set[tuple[str, str]] = set()
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        subproblem_id = item_id(mapping, "subproblem_id")
        rel = mapping.get("path")
        pair = (subproblem_id, str(rel))
        if pair in mapped_pairs:
            findings.append(finding("LATEX-E003", "error", "structural", "paper", path, f"duplicate LaTeX subproblem/section mapping: {subproblem_id} -> {rel}", related_ids=[subproblem_id]))
        mapped_ids.add(subproblem_id)
        mapped_pairs.add(pair)
        if rel not in section_files:
            findings.append(finding("LATEX-E004", "error", "structural", "paper", path, f"mapped subproblem section is absent from section_files: {rel}", related_ids=[subproblem_id]))
        rel_path = safe_project_path(root, rel)
        if rel_path is None or not rel_path.is_file():
            findings.append(finding("LATEX-E005", "error", "structural", "paper", path, f"mapped subproblem section is missing: {rel}", related_ids=[subproblem_id]))
        if nonempty(rel) and main_text:
            input_target = str(rel)
            if input_target.startswith("paper/"):
                input_target = input_target[len("paper/") :]
            input_target = input_target[:-4] if input_target.endswith(".tex") else input_target
            if f"\\input{{{input_target}}}" not in main_text:
                findings.append(finding("LATEX-E006", "error", "structural", "paper", path, f"main.tex does not include mapped subproblem section: {rel}", related_ids=[subproblem_id]))
    missing = sorted(subproblem_ids - mapped_ids)
    extra = sorted(mapped_ids - subproblem_ids)
    if missing or extra:
        details = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if extra:
            details.append(f"unknown {', '.join(extra)}")
        findings.append(finding("LATEX-E007", "error", "semantic", "paper", path, f"LaTeX subproblem mapping mismatch: {'; '.join(details)}", related_ids=[*missing, *extra]))

    quality_status = paper_quality.get("paper_status") if isinstance(paper_quality, dict) else None
    if quality_status == "final":
        markers = [str(value) for value in as_list(data.get("placeholder_markers")) if nonempty(value)]
        for rel in required_files:
            if not str(rel).endswith(".tex"):
                continue
            source = safe_project_path(root, rel)
            if source is None or not source.is_file():
                continue
            text = source.read_text(encoding="utf-8", errors="replace")
            present = [marker for marker in markers if marker in text]
            if present:
                findings.append(finding("LATEX-E008", "error", "semantic", "paper", path, f"final paper source still contains placeholder markers in {rel}: {', '.join(present)}"))
    if through_stage == "delivery" and data.get("official_compliance") != "verified_against_current_rules":
        findings.append(finding("LATEX-E009", "error", "visual", "delivery", path, "delivery requires the LaTeX scaffold to be reviewed against the current official rules", gate_only=True))
    return findings


def check_revision_log(data: Any, root: Path, path: str, paper_artifact: Any, issues: Any) -> list[Finding]:
    findings = check_envelope(data, "paper_revision_log", "paper", path)
    if not isinstance(data, dict):
        return findings
    snapshots: list[tuple[str, Any]] = [("initial_snapshot", data.get("initial_snapshot"))]
    revisions = as_list(data.get("revisions"))
    issue_items = {item_id(issue, "issue_id"): issue for issue in as_list(issues) if isinstance(issue, dict)}
    issue_ids = set(issue_items)
    verified_issue_ids: set[str] = set()
    seen: set[str] = set()
    previous_output: Any = data.get("initial_snapshot")
    for index, revision in enumerate(revisions):
        if not isinstance(revision, dict):
            continue
        revision_id = item_id(revision, "revision_id")
        if revision_id in seen:
            findings.append(finding("PREVISION-E001", "error", "structural", "paper", path, f"duplicate revision ID: {revision_id}", related_ids=[revision_id]))
        seen.add(revision_id)
        if revision.get("input") != previous_output:
            findings.append(finding("PREVISION-E002", "error", "structural", "paper", path, f"revision input does not match previous snapshot: {revision_id}", related_ids=[revision_id]))
        snapshots.extend(((f"revisions/{index}/input", revision.get("input")), (f"revisions/{index}/output", revision.get("output"))))
        previous_output = revision.get("output")
        for issue_id in as_list(revision.get("issue_ids")):
            if issue_id not in issue_ids:
                findings.append(finding("PREVISION-E003", "error", "structural", "paper", path, f"revision names unknown issue: {issue_id}", related_ids=[revision_id, str(issue_id)]))
            elif isinstance(revision.get("verification"), dict) and revision["verification"].get("decision") == "accepted":
                verified_issue_ids.add(str(issue_id))
    for label, snapshot in snapshots:
        for item in check_bound_artifact(root, snapshot, "paper", path, "PREVISION"):
            findings.append(finding(item.rule_id, item.severity, item.evidence_type, item.owning_stage, item.path, f"{label}: {item.message}"))
    if isinstance(paper_artifact, dict) and previous_output != paper_artifact:
        findings.append(finding("PREVISION-E004", "error", "structural", "paper", path, "latest revision snapshot does not match the paper quality report artifact"))
    unverified_closed = sorted(
        issue_id
        for issue_id, issue in issue_items.items()
        if issue.get("status") == "closed" and issue_id not in verified_issue_ids
    )
    if unverified_closed:
        findings.append(finding("PREVISION-E005", "error", "semantic", "paper", path, f"closed issues lack an accepted revision verification: {', '.join(unverified_closed)}", related_ids=unverified_closed))
    return findings


def check_compile_receipt(data: Any, root: Path, path: str, quality_report: Any, latex_template: Any, delivery: Any) -> list[Finding]:
    findings = check_envelope(data, "compile_receipt", "delivery", path)
    if not isinstance(data, dict):
        return findings
    attempts = {item_id(item, "attempt_id"): item for item in as_list(data.get("attempts")) if isinstance(item, dict)}
    selected_id = data.get("selected_attempt_id")
    selected = attempts.get(str(selected_id))
    if selected is None:
        findings.append(finding("COMPILE-E001", "error", "execution", "delivery", path, f"selected compile attempt does not exist: {selected_id}"))
        return findings
    source_snapshot = data.get("source_snapshot")
    if not snapshot_matches(root, source_snapshot):
        findings.append(finding("COMPILE-E015", "error", "execution", "delivery", path, "editable LaTeX source snapshot is missing or stale"))
    if isinstance(source_snapshot, dict) and isinstance(latex_template, dict):
        if source_snapshot.get("entrypoint") != latex_template.get("main_path"):
            findings.append(finding("COMPILE-E016", "error", "structural", "delivery", path, "compile source snapshot entrypoint differs from the LaTeX manifest"))
        required_sources = set(str(value) for value in as_list(latex_template.get("required_files")))
        snapped_sources = set(str(value) for value in as_list(source_snapshot.get("files")))
        if not required_sources.issubset(snapped_sources):
            findings.append(finding("COMPILE-E017", "error", "structural", "delivery", path, "compile source snapshot does not cover every required editable LaTeX file"))
    pdf_binding = {"path": selected.get("pdf_path"), "sha256": selected.get("pdf_sha256")}
    findings.extend(check_bound_artifact(root, pdf_binding, "delivery", path, "COMPILE"))
    log_path = safe_project_path(root, selected.get("log_path"))
    if log_path is None or not log_path.is_file():
        findings.append(finding("COMPILE-E004", "error", "execution", "delivery", path, "selected compile log is missing"))
    if selected.get("exit_code") != 0:
        findings.append(finding("COMPILE-E005", "error", "execution", "delivery", path, "selected compile attempt did not exit successfully"))
    if selected.get("font_check") != "pass" or selected.get("glyph_check") != "pass":
        findings.append(finding("COMPILE-E006", "error", "visual", "delivery", path, "delivery requires passing font and missing-glyph checks; record_compile.py derives them from the engine log"))
    if isinstance(latex_template, dict) and str(selected.get("engine", "")).casefold() != str(latex_template.get("engine", "")).casefold():
        findings.append(finding("COMPILE-E014", "error", "execution", "delivery", path, "selected compile engine differs from the LaTeX template manifest"))
    binding = data.get("layout_report_binding")
    if isinstance(binding, dict):
        quality_path = safe_project_path(root, binding.get("quality_report_path"))
        if quality_path is None or not quality_path.is_file():
            findings.append(finding("COMPILE-E007", "error", "structural", "delivery", path, "layout-review binding does not point to the current paper quality report"))
        if binding.get("pdf_sha256") != selected.get("pdf_sha256"):
            findings.append(finding("COMPILE-E008", "error", "structural", "delivery", path, "layout-review binding names a different PDF version"))
    if isinstance(quality_report, dict):
        if quality_report.get("paper_status") != "final":
            findings.append(finding("COMPILE-E013", "error", "semantic", "delivery", path, "delivery requires a paper quality report with paper_status=final"))
        paper = quality_report.get("paper_artifact")
        layout = quality_report.get("layout_report")
        if isinstance(paper, dict) and (paper.get("path") != selected.get("pdf_path") or paper.get("sha256") != selected.get("pdf_sha256")):
            findings.append(finding("COMPILE-E009", "error", "structural", "delivery", path, "selected compile PDF differs from the reviewed paper artifact"))
        if isinstance(layout, dict) and layout.get("page_count") != selected.get("page_count"):
            findings.append(finding("COMPILE-E010", "error", "visual", "delivery", path, "compile receipt page count differs from layout review"))
    if isinstance(delivery, dict):
        if delivery.get("compile_receipt_path") != path:
            findings.append(finding("COMPILE-E011", "error", "structural", "delivery", path, "delivery manifest does not point to this compile receipt"))
        summary = delivery.get("compile")
        if isinstance(summary, dict) and (summary.get("exit_code") != selected.get("exit_code") or summary.get("page_count") != selected.get("page_count")):
            findings.append(finding("COMPILE-E012", "error", "execution", "delivery", path, "delivery compile summary disagrees with selected compile attempt"))
    return findings


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


def load_contracts(root: Path, required: Iterable[str]) -> tuple[dict[str, Any], list[Finding]]:
    data: dict[str, Any] = {}
    findings: list[Finding] = []
    for name in required:
        rel = CONTRACT_PATHS[name]
        path = root / rel
        if not path.is_file():
            findings.append(
                finding(
                    "PROJECT-E001",
                    "error",
                    "structural",
                    owning_stage_for_contract(name),
                    rel,
                    f"required contract is missing: {rel}",
                )
            )
            continue
        value, error = read_json(path)
        if error:
            findings.append(
                finding(
                    "PROJECT-E002",
                    "error",
                    "structural",
                    owning_stage_for_contract(name),
                    rel,
                    f"invalid JSON: {error}",
                )
            )
            continue
        data[name] = value
    return data, findings


def owning_stage_for_contract(name: str) -> str:
    return {
        "state": "intake",
        "sources": "intake",
        "facts": "problem-analysis",
        "capabilities": "problem-analysis",
        "model": "model-design",
        "cross_question": "model-design",
        "results": "computation",
        "independent_review_package": "validation",
        "independent_review_result": "validation",
        "claims": "validation",
        "figures": "paper",
        "paper_plan": "paper",
        "latex_template": "paper",
        "paper_quality": "paper",
        "paper_revisions": "paper",
        "paper_visible_text": "paper",
        "delivery": "delivery",
        "compile_receipt": "delivery",
        "handoff_modeling_computation": "model-design",
        "handoff_computation_validation": "computation",
        "handoff_validation_paper": "validation",
        "handoff_paper_delivery": "paper",
    }[name]


def candidate_summary(model: Any) -> list[dict[str, Any]]:
    """A compact view of the model comparison, so the choice is visible in the report."""
    summary: list[dict[str, Any]] = []
    if not isinstance(model, dict):
        return summary
    for component in as_list(model.get("components")):
        if not isinstance(component, dict):
            continue
        candidates = [item for item in as_list(component.get("candidates")) if isinstance(item, dict)]
        if not candidates:
            continue
        summary.append(
            {
                "model_id": item_id(component, "model_id"),
                "candidates": [
                    {
                        "candidate_id": item_id(item, "candidate_id"),
                        "status": item.get("status"),
                        "evaluation_run_ids": [str(value) for value in as_list(item.get("evaluation_run_ids"))],
                    }
                    for item in candidates
                ],
            }
        )
    return summary


def check_project(
    root: Path,
    stage: str,
    gate_mode: str = "enforce",
    *,
    state_override: dict[str, Any] | None = None,
) -> tuple[list[Finding], dict[str, Any]]:
    """Deterministic evidence check through `stage`.

    v0.6 has exactly two knobs: the project mode (`working` / `finalizing`) decides
    which contracts must be complete, and `gate_mode` decides whether human-gated
    findings count toward the blocking total.
    """
    if stage not in STAGES:
        raise ValueError(f"unknown stage: {stage}")
    if gate_mode not in GATE_MODES:
        raise ValueError(f"unknown gate mode: {gate_mode}")
    state_preview = state_override
    if state_preview is None:
        state_preview, _ = read_json(root / CONTRACT_PATHS["state"])
    workflow_version = state_preview.get("workflow_version") if isinstance(state_preview, dict) else None
    workflow_mode = state_preview.get("mode") if isinstance(state_preview, dict) else None
    mode = workflow_mode if workflow_mode in WORKFLOW_MODES else "working"
    frozen = mode == "finalizing"

    required = list(STAGE_CONTRACTS[stage])
    if frozen:
        required.extend(FINALIZING_CONTRACTS.get(stage, ()))
        for threshold, name in (
            ("computation", "handoff_modeling_computation"),
            ("validation", "handoff_computation_validation"),
            ("paper", "handoff_validation_paper"),
            ("delivery", "handoff_paper_delivery"),
        ):
            if STAGES.index(stage) >= STAGES.index(threshold):
                required.append(name)
    contracts, findings = load_contracts(root, required)
    if state_override is not None and "state" in contracts:
        contracts["state"] = state_override

    for name, from_stage in OPTIONAL_CONTRACTS.items():
        if name in contracts or STAGES.index(stage) < STAGES.index(from_stage):
            continue
        optional_path = root / CONTRACT_PATHS[name]
        if not optional_path.is_file():
            continue
        value, error = read_json(optional_path)
        if error:
            findings.append(finding("PROJECT-E002", "error", "structural", owning_stage_for_contract(name), CONTRACT_PATHS[name], f"invalid optional contract: {error}"))
        else:
            contracts[name] = value

    project_ids = {
        value.get("project_id")
        for value in contracts.values()
        if isinstance(value, dict) and nonempty(value.get("project_id"))
    }
    if len(project_ids) > 1:
        findings.append(finding("PROJECT-E003", "error", "structural", "intake", ".", f"contracts contain mixed project IDs: {', '.join(sorted(project_ids))}"))

    source_ids: set[str] = set()
    fact_ids: set[str] = set()
    subproblem_ids: set[str] = set()
    capability_ids: set[str] = set()
    model_ids: set[str] = set()
    result_ids: set[str] = set()
    figure_ids: set[str] = set()
    claim_ids: set[str] = set()

    if "state" in contracts:
        findings.extend(check_schema(contracts["state"], "state", "intake", CONTRACT_PATHS["state"]))
        findings.extend(check_state(contracts["state"], CONTRACT_PATHS["state"], mode))
        if frozen:
            state_map = contracts["state"].get("stages", {}) if isinstance(contracts["state"], dict) else {}
            for required_stage in STAGES[: STAGES.index(stage) + 1]:
                if state_map.get(required_stage) != "passed":
                    findings.append(finding("STATE-E013", "error", "semantic", required_stage, CONTRACT_PATHS["state"], f"finalizing enforce requires passed state through {stage}: {required_stage}", gate_only=True))
    for name, contract in contracts.items():
        if isinstance(contract, dict) and contract.get("schema_version") != WORKFLOW_VERSION:
            findings.append(finding("PROJECT-E004", "error", "structural", owning_stage_for_contract(name), CONTRACT_PATHS[name], f"contract schema_version must be {WORKFLOW_VERSION}"))
    if "sources" in contracts:
        findings.extend(check_schema(contracts["sources"], "sources", "intake", CONTRACT_PATHS["sources"]))
        findings.extend(check_sources(contracts["sources"], root, CONTRACT_PATHS["sources"]))
        source_ids = ids(contracts["sources"].get("sources"), "source_id") if isinstance(contracts["sources"], dict) else set()
    if "facts" in contracts:
        findings.extend(check_schema(contracts["facts"], "facts", "problem-analysis", CONTRACT_PATHS["facts"]))
        findings.extend(check_facts(contracts["facts"], source_ids, CONTRACT_PATHS["facts"]))
        if isinstance(contracts["facts"], dict):
            fact_ids = ids(contracts["facts"].get("facts"), "fact_id", "id")
            subproblem_ids = ids(contracts["facts"].get("subproblems"), "subproblem_id", "id")
    if "capabilities" in contracts:
        findings.extend(check_schema(contracts["capabilities"], "capabilities", "problem-analysis", CONTRACT_PATHS["capabilities"]))
        findings.extend(check_capabilities(contracts["capabilities"], root, fact_ids, subproblem_ids, CONTRACT_PATHS["capabilities"]))
        capability_ids = ids(contracts["capabilities"].get("capabilities"), "capability_id") if isinstance(contracts["capabilities"], dict) else set()
    if "model" in contracts:
        findings.extend(check_schema(contracts["model"], "model", "model-design", CONTRACT_PATHS["model"]))
        findings.extend(check_model(contracts["model"], capability_ids, CONTRACT_PATHS["model"], mode))
        model_ids = ids(contracts["model"].get("components"), "model_id") if isinstance(contracts["model"], dict) else set()
    if "cross_question" in contracts:
        findings.extend(check_schema(contracts["cross_question"], "cross_question", "model-design", CONTRACT_PATHS["cross_question"]))
        findings.extend(check_cross_question(contracts["cross_question"], subproblem_ids, CONTRACT_PATHS["cross_question"]))

    run_ids: set[str] = set()
    official_run_ids: set[str] = set()
    run_output_roles: dict[str, dict[str, str]] = {}
    executed_capability_ids: set[str] = set()
    capability_assertions: dict[str, set[str]] = {}
    capability_passed_assertions: dict[str, set[str]] = {}
    capability_backends: dict[str, dict[str, list[str]]] = {}
    run_candidates: dict[str, set[str]] = {}
    run_count = 0
    superseded_ids: set[str] = set()
    if STAGES.index(stage) >= STAGES.index("computation"):
        superseded_ids = superseded_run_ids(root)
        run_paths = discover_run_manifests(root)
        if not run_paths:
            findings.append(finding("RUN-E009", "error", "execution", "computation", "runs/", "no run manifests found; record one with record_run.py"))
        for run_path in run_paths:
            rel = run_path.relative_to(root).as_posix()
            run, error = read_json(run_path)
            if error:
                findings.append(finding("RUN-E010", "error", "structural", "computation", rel, f"invalid run JSON: {error}"))
                continue
            run_count += 1
            findings.extend(check_schema(run, "run", "computation", rel))
            if isinstance(run, dict) and nonempty(run.get("run_id")):
                if run["run_id"] in run_ids:
                    findings.append(finding("RUN-E011", "error", "structural", "computation", rel, f"duplicate run ID: {run['run_id']}"))
                run_ids.add(run["run_id"])
                is_official = run.get("official_run") is True and run.get("status") == "completed" and run.get("exit_code") == 0
                if is_official:
                    official_run_ids.add(run["run_id"])
                    # A verdict typed on the command line is a note, not evidence that
                    # the run verified anything, so it cannot satisfy a verification plan.
                    names = {
                        str(item.get("name"))
                        for item in as_list(run.get("assertions"))
                        if isinstance(item, dict) and nonempty(item.get("name")) and item.get("source") == "recorded"
                    }
                    passed_names = {
                        str(item.get("name"))
                        for item in as_list(run.get("assertions"))
                        if isinstance(item, dict) and nonempty(item.get("name"))
                        and item.get("source") == "recorded" and item.get("passed") is True
                    }
                    # A run a later official run replaced verified the code it ran, not
                    # the code that replaced it. record_run.py already refuses to inherit
                    # a parent's assertions for that reason; the checker has to agree, or
                    # a superseded pass keeps satisfying a verification plan forever. The
                    # run stays an official run for every other consumer, so that citing
                    # it still reports the precise "superseded" finding rather than
                    # degrading into "unknown run".
                    if run["run_id"] not in superseded_ids:
                        for capability_id in as_list(run.get("capability_ids")):
                            capability_assertions.setdefault(str(capability_id), set()).update(names)
                            capability_passed_assertions.setdefault(str(capability_id), set()).update(passed_names)
                executed_capability_ids.update(str(value) for value in as_list(run.get("capability_ids")))
                run_candidates[run["run_id"]] = {str(value) for value in as_list(run.get("candidate_ids"))}
                if is_official:
                    implementation = run.get("implementation")
                    language = implementation.get("selected_language") if isinstance(implementation, dict) else None
                    if nonempty(language) and run["run_id"] not in superseded_ids:
                        for capability_id in as_list(run.get("capability_ids")):
                            capability_backends.setdefault(str(capability_id), {}).setdefault(str(language), []).append(str(run["run_id"]))
                run_output_roles[run["run_id"]] = {
                    str(entry.get("path")): str(entry.get("evidence_role"))
                    for entry in as_list(run.get("outputs"))
                    if isinstance(entry, dict) and nonempty(entry.get("path"))
                }
            findings.extend(check_run(run, root, rel, capability_ids, str(run.get("run_id")) in superseded_ids))
        if "capabilities" in contracts and isinstance(contracts["capabilities"], dict):
            for capability in as_list(contracts["capabilities"].get("capabilities")):
                if not isinstance(capability, dict) or capability.get("lifecycle_state") not in {"executed", "validated"}:
                    continue
                capability_id = item_id(capability, "capability_id")
                if capability_id not in executed_capability_ids:
                    findings.append(finding("RUN-E014", "error", "execution", "computation", CONTRACT_PATHS["capabilities"], f"capability declares execution without a run: {capability_id}", related_ids=[capability_id]))
    # One official task, one backend. The selector and the docs said so; nothing checked it.
    for capability_id, backends in sorted(capability_backends.items()):
        if len(backends) < 2:
            continue
        detail = "; ".join(f"{language}: {', '.join(sorted(runs))}" for language, runs in sorted(backends.items()))
        findings.append(
            finding(
                "RUN-E024",
                "error" if frozen else "warning",
                "execution",
                "computation",
                CONTRACT_PATHS["results"],
                f"{capability_id} has current official runs in more than one backend ({detail})",
                related_ids=[capability_id],
                remediation="pick one backend for the task and retire the other run, or say the user asked for cross-implementation validation",
            )
        )

    if "model" in contracts and STAGES.index(stage) >= STAGES.index("model-design"):
        # Run references only make sense once runs are in scope for this check.
        runs_known = STAGES.index(stage) >= STAGES.index("computation")
        findings.extend(check_model_candidates(contracts["model"], run_ids, run_candidates, CONTRACT_PATHS["model"], mode, runs_known))
        findings.extend(check_selection_check(contracts["model"], CONTRACT_PATHS["model"]))
    if frozen and "model" in contracts and STAGES.index(stage) >= STAGES.index("computation"):
        findings.extend(check_model_verification(contracts["model"], capability_assertions, CONTRACT_PATHS["model"]))
    if "capabilities" in contracts:
        findings.extend(check_acceptance_checks(contracts["capabilities"], capability_passed_assertions, CONTRACT_PATHS["capabilities"], mode))
        findings.extend(check_capability_coverage(contracts["capabilities"], contracts.get("model"), contracts.get("paper_quality"), CONTRACT_PATHS["capabilities"], mode))
    if "results" in contracts:
        findings.extend(check_schema(contracts["results"], "results", "computation", CONTRACT_PATHS["results"]))
        findings.extend(check_results(contracts["results"], root, run_ids, official_run_ids, run_output_roles, CONTRACT_PATHS["results"], superseded_ids))
        result_ids = ids(contracts["results"].get("results"), "result_id") if isinstance(contracts["results"], dict) else set()
        if "capabilities" in contracts and isinstance(contracts["capabilities"], dict):
            for capability in as_list(contracts["capabilities"].get("capabilities")):
                if not isinstance(capability, dict):
                    continue
                capability_id = item_id(capability, "capability_id")
                for result_id in as_list(capability.get("result_ids")):
                    if result_id not in result_ids:
                        findings.append(finding("RESULT-E013", "error", "structural", "computation", CONTRACT_PATHS["capabilities"], f"{capability_id} expects unknown result: {result_id}", related_ids=[capability_id, str(result_id)]))
    if "independent_review_package" in contracts:
        findings.extend(check_schema(contracts["independent_review_package"], "independent_review_package", "validation", CONTRACT_PATHS["independent_review_package"]))
        findings.extend(check_independent_review_package(contracts["independent_review_package"], root, CONTRACT_PATHS["independent_review_package"]))
    if "independent_review_result" in contracts:
        findings.extend(check_schema(contracts["independent_review_result"], "independent_review_result", "validation", CONTRACT_PATHS["independent_review_result"]))
        findings.extend(check_independent_review_result(contracts["independent_review_result"], root, CONTRACT_PATHS["independent_review_result"], contracts.get("independent_review_package")))
    if "figures" in contracts:
        findings.extend(check_schema(contracts["figures"], "figures", "paper", CONTRACT_PATHS["figures"]))
        if isinstance(contracts["figures"], dict):
            figure_ids = ids(contracts["figures"].get("figures"), "figure_id")
        findings.extend(check_figures(contracts["figures"], root, result_ids, run_ids, CONTRACT_PATHS["figures"], superseded_ids))
    if "claims" in contracts:
        findings.extend(check_schema(contracts["claims"], "claims", "validation", CONTRACT_PATHS["claims"]))
        known = {"facts": fact_ids, "models": model_ids, "runs": run_ids, "results": result_ids, "figures": figure_ids}
        findings.extend(check_claims(contracts["claims"], known, CONTRACT_PATHS["claims"], superseded_ids))
        if isinstance(contracts["claims"], dict):
            claim_ids = ids(contracts["claims"].get("claims"), "claim_id")
    known_evidence_ids = set().union(fact_ids, model_ids, run_ids, result_ids, figure_ids, claim_ids)
    if "paper_plan" in contracts:
        findings.extend(check_schema(contracts["paper_plan"], "paper_plan", "paper", CONTRACT_PATHS["paper_plan"]))
        findings.extend(check_paper_plan(contracts["paper_plan"], CONTRACT_PATHS["paper_plan"], subproblem_ids, claim_ids, result_ids, figure_ids))
    if "paper_quality" in contracts:
        findings.extend(check_schema(contracts["paper_quality"], "paper_quality", "paper", CONTRACT_PATHS["paper_quality"]))
        findings.extend(check_paper_quality(contracts["paper_quality"], root, CONTRACT_PATHS["paper_quality"], subproblem_ids))
    if "latex_template" in contracts:
        findings.extend(check_schema(contracts["latex_template"], "latex_template", "paper", CONTRACT_PATHS["latex_template"]))
        findings.extend(check_latex_template(contracts["latex_template"], root, CONTRACT_PATHS["latex_template"], subproblem_ids, contracts.get("paper_quality"), stage))
    if "paper_revisions" in contracts:
        findings.extend(check_schema(contracts["paper_revisions"], "paper_revisions", "paper", CONTRACT_PATHS["paper_revisions"]))
        quality = contracts.get("paper_quality")
        paper_artifact = quality.get("paper_artifact") if isinstance(quality, dict) else None
        issues = quality.get("open_issues") if isinstance(quality, dict) else []
        findings.extend(check_revision_log(contracts["paper_revisions"], root, CONTRACT_PATHS["paper_revisions"], paper_artifact, issues))
    if "paper_visible_text" in contracts:
        findings.extend(check_schema(contracts["paper_visible_text"], "paper_visible_text", "paper", CONTRACT_PATHS["paper_visible_text"]))
        findings.extend(check_paper_visible_text(contracts["paper_visible_text"], root, CONTRACT_PATHS["paper_visible_text"], contracts.get("paper_quality")))
    if "delivery" in contracts:
        findings.extend(check_schema(contracts["delivery"], "delivery", "delivery", CONTRACT_PATHS["delivery"]))
        findings.extend(check_delivery(contracts["delivery"], root, CONTRACT_PATHS["delivery"]))
    if "compile_receipt" in contracts:
        findings.extend(check_schema(contracts["compile_receipt"], "compile_receipt", "delivery", CONTRACT_PATHS["compile_receipt"]))
        findings.extend(check_compile_receipt(contracts["compile_receipt"], root, CONTRACT_PATHS["compile_receipt"], contracts.get("paper_quality"), contracts.get("latex_template"), contracts.get("delivery")))

    for name, transition in (
        ("handoff_modeling_computation", "modeling-computation"),
        ("handoff_computation_validation", "computation-validation"),
        ("handoff_validation_paper", "validation-paper"),
        ("handoff_paper_delivery", "paper-delivery"),
    ):
        if name in contracts:
            findings.extend(check_schema(contracts[name], name, owning_stage_for_contract(name), CONTRACT_PATHS[name]))
            findings.extend(check_handoff(contracts[name], root, CONTRACT_PATHS[name], transition))
    findings.extend(check_task_separation(contracts))

    if frozen:
        findings.extend(check_decision_log(root, contracts.get("state")))

    pending_review_count = sum(item.severity == "error" and item.gate_only for item in findings)
    automated_error_count = sum(item.severity == "error" and not item.gate_only for item in findings)
    formal_gate_required = gate_mode == "enforce"
    blocking_error_count = automated_error_count + (pending_review_count if formal_gate_required else 0)
    if automated_error_count:
        gate_status = "blocked"
    elif pending_review_count:
        gate_status = "awaiting_review"
    else:
        gate_status = "working_ready" if not frozen else "passed"

    summary = {
        "project_ids": sorted(project_ids),
        "stage": stage,
        "workflow_version": workflow_version,
        "workflow_mode": workflow_mode,
        "gate_mode": gate_mode,
        "gate_status": gate_status,
        "pending_review_count": pending_review_count,
        "blocking_error_count": blocking_error_count,
        "contracts_loaded": sorted(contracts),
        "run_count": run_count,
        "official_run_count": len(official_run_ids),
        "superseded_run_ids": sorted(superseded_ids),
        "model_candidates": candidate_summary(contracts.get("model")),
        "stages_with_current_decision": trusted_stage_snapshots(root, stage),
        "finding_counts": {
            level: sum(item.severity == level for item in findings)
            for level in ("error", "warning", "info")
        },
        "evidence_boundary": (
            "Passing establishes declared structure, traceability, preserved execution, "
            "and recorded reviews only; it does not prove mathematical correctness."
        ),
    }
    return findings, summary
