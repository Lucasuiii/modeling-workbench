#!/usr/bin/env python3
"""Deterministic v0.6 evidence, freshness, and cross-artifact checks.

The checks in this module establish structure, provenance, recorded execution,
and declared relationships. They do not establish mathematical correctness.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Iterable

from canonical_evidence import official_successors, successful_official
from json_pointer import resolve_json_pointer
from provenance import digest_records, sha256_file, snapshot_matches

from workflow_validation.common import (
    Finding,
    as_list,
    check_envelope,
    check_schema,
    finding,
    ids,
    item_id,
    nonempty,
    read_json,
    require_fields,
    safe_project_path,
    sha256,
)
from workflow_validation.computation import (
    check_results,
    check_run,
    discover_run_manifests,
    superseded_run_ids,
)
from workflow_validation.contracts import (
    CONTRACT_PATHS,
    EVIDENCE_STATES,
    FINALIZING_CONTRACTS,
    GATE_MODES,
    OPTIONAL_CONTRACTS,
    PAPER_CONTRACTS,
    REVIEW_DECISIONS,
    SCHEMA_FILES,
    STAGES,
    STAGE_CONTRACTS,
    STAGE_STATUSES,
    WORKFLOW_MODES,
    WORKFLOW_VERSION,
)
from workflow_validation.lifecycle import (
    CUT_CONSUMERS,
    TRANSITIONS_FOR_CHECK,
    check_decision_log,
    check_handoff,
    check_task_separation,
    consuming_task_ref,
    stage_scope_paths,
    trusted_stage_snapshots,
)
from workflow_validation.modeling import (
    DRAFT_MODEL_FIELDS,
    FROZEN_MODEL_FIELDS,
    candidate_summary,
    check_acceptance_checks,
    check_capabilities,
    check_capability_coverage,
    check_cross_question,
    check_facts,
    check_model,
    check_model_candidates,
    check_model_verification,
    check_selection_check,
    require_resolved_model,
)
from workflow_validation.paper_delivery import (
    check_bound_artifact,
    check_compile_receipt,
    check_delivery,
    check_figures,
    check_final_check,
    check_latex_template,
    check_paper_plan,
    check_paper_quality,
    check_paper_visible_text,
    check_revision_log,
)
from workflow_validation.review import (
    REQUIRED_CONTEXT_EXCLUSIONS,
    STRONG_CLAIM_PATTERNS,
    check_claims,
    check_conclusion_check,
    check_independent_review_package,
    check_independent_review_result,
    claim_certificate_types,
)


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


def require_delegated_prerequisites(root: Path, stage: str) -> list[str]:
    """Check independent evidence and return extra files to bind to a delegated decision."""
    if stage not in {"validation", "delivery"}:
        return []
    names = ["independent_review_package", "independent_review_result", "handoff_computation_validation"]
    if stage == "delivery":
        names += ["paper_quality", "latex_template", "delivery", "compile_receipt", "paper_visible_text",
                  "paper_plan", "handoff_validation_paper", "handoff_paper_delivery"]
    objects = {}
    for name in names:
        rel = CONTRACT_PATHS[name]
        obj, error = read_json(root / rel)
        if error or not isinstance(obj, dict):
            raise ValueError(f"delegated {stage} requires current {rel}")
        objects[name] = obj
    findings = []
    for name in names:
        findings.extend(check_schema(objects[name], name, owning_stage_for_contract(name), CONTRACT_PATHS[name]))
    schema_errors = [item for item in findings if item.severity == "error"]
    if schema_errors:
        raise ValueError(f"delegated {stage} prerequisites failed: {schema_errors[0].rule_id}: {schema_errors[0].message}")
    package, review = objects["independent_review_package"], objects["independent_review_result"]
    findings.extend(check_independent_review_package(package, root, CONTRACT_PATHS["independent_review_package"]))
    findings.extend(check_independent_review_result(review, root, CONTRACT_PATHS["independent_review_result"], package))
    findings.extend(check_handoff(objects["handoff_computation_validation"], root, CONTRACT_PATHS["handoff_computation_validation"], "computation-validation"))
    findings.extend(check_task_separation(objects))
    if review.get("verdict") not in {"accepted", "accepted_with_concerns"}:
        raise ValueError("delegated decision requires an accepted independent review")
    extra = [CONTRACT_PATHS[name] for name in names]
    if stage == "delivery":
        quality, latex, delivery, receipt = (objects[n] for n in ("paper_quality", "latex_template", "delivery", "compile_receipt"))
        for name, transition in (("handoff_validation_paper", "validation-paper"),
                                 ("handoff_paper_delivery", "paper-delivery")):
            findings.extend(check_handoff(objects[name], root, CONTRACT_PATHS[name], transition))
        findings.extend(check_paper_visible_text(objects["paper_visible_text"], root, CONTRACT_PATHS["paper_visible_text"], quality))
        facts, error = read_json(root / CONTRACT_PATHS["facts"])
        if error or not isinstance(facts, dict):
            raise ValueError("delegated delivery requires current problem facts")
        subproblem_ids = ids(facts.get("subproblems"), "subproblem_id")
        findings.extend(check_paper_quality(quality, root, CONTRACT_PATHS["paper_quality"], subproblem_ids))
        findings.extend(check_delivery(delivery, root, CONTRACT_PATHS["delivery"]))
        findings.extend(check_compile_receipt(receipt, root, CONTRACT_PATHS["compile_receipt"], quality, latex, delivery))
        layout = quality.get("layout_report")
        count = layout.get("page_count") if isinstance(layout, dict) else None
        if quality.get("paper_status") != "final" or not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError("delegated delivery requires a final reviewed paper and rendered pages")
        pages = layout.get("rendered_pages")
        if (not isinstance(pages, list) or any(not isinstance(page, int) or isinstance(page, bool) for page in pages)
                or set(pages) != set(range(1, count + 1))):
            raise ValueError("delegated delivery requires every rendered page")
        page_files = {}
        for path in (root / ".cumcm/tmp/pages").glob("page-*.png"):
            match = re.fullmatch(r"page-(\d+)\.png", path.name)
            if match:
                page_files.setdefault(int(match.group(1)), []).append(path)
        for page in range(1, count + 1):
            paths = page_files.get(page, [])
            if len(paths) != 1 or paths[0].read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
                raise ValueError(f"delegated delivery requires rendered page {page}")
            extra.append(paths[0].relative_to(root).as_posix())
    errors = [item for item in findings if item.severity == "error" and not item.gate_only]
    if errors:
        raise ValueError(f"delegated {stage} prerequisites failed: {errors[0].rule_id}: {errors[0].message}")
    return extra


def require_human_checkpoint(root: Path, stage: str) -> None:
    """Action boundary, not a full finalizing check (which needs future runs).

    Reuse the existing contract and snapshot; no new receipt or hash layer.
    These are honest records of a conversation, not authentication of a human.
    """
    if (root / ".cumcm/pending-decision.json").exists():
        raise ValueError("interrupted decision pending; run record_decision.py --project <p> --recover")
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
    if check.get("decision") != "accepted" or check.get("reviewer_kind") not in {"human_user", "lead_agent"}:
        raise ValueError(f"{stage} awaits the user's explicit decision; model self-review cannot approve it")
    if check.get("reviewer_kind") == "lead_agent":
        authority_rel = f".cumcm/delegations/{stage}.json"
        authority, authority_error = read_json(root / authority_rel)
        if authority_error or not isinstance(authority, dict) or authority.get("stage") != stage or not nonempty(authority.get("user_turn_ref")):
            raise ValueError(f"{stage} has no valid user delegation")
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
        if check.get("reviewer_kind") == "lead_agent":
            if not any(item.get("path") == authority_rel for item in records if isinstance(item, dict)):
                raise ValueError(f"{stage} snapshot does not bind user delegation")
            try:
                events = [json.loads(line) for line in (root / ".cumcm/decisions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
                matching = [event for event in events if event.get("decision_id") == snapshot.get("decision_id")]
            except (OSError, ValueError, AttributeError):
                matching = []
            if (len(matching) != 1 or matching[0].get("stage") != stage or matching[0].get("decision") != "accepted"
                    or matching[0].get("delegated") is not True or matching[0].get("reviewer") != check.get("reviewer")
                    or matching[0].get("task_turn_ref") != authority.get("user_turn_ref") or matching[0].get("scope") != records):
                raise ValueError(f"{stage} delegated decision does not match its authorization and snapshot")
        if error or not record or any(
            not isinstance(item, dict)
            or (target := safe_project_path(root, item.get("path"))) is None
            or not target.is_file() or item.get("sha256") != sha256(target)
            for item in records
        ):
            raise ValueError(f"{stage} material changed after approval; show the revision and obtain a new decision")
    if check.get("reviewer_kind") == "lead_agent":
        required = set(stage_scope_paths(root, stage) + require_delegated_prerequisites(root, stage))
        if not required.issubset({item.get("path") for item in records if isinstance(item, dict)}):
            raise ValueError(f"{stage} snapshot does not bind all required delegated evidence")


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
        value, error = read_json(path, exact=name in {"results", "claims"})
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
    if (root / ".cumcm/pending-decision.json").exists():
        findings.append(finding("STATE-E014", "error", "structural", stage, ".cumcm/pending-decision.json",
                                "interrupted decision pending", remediation="record_decision.py --project <p> --recover"))
    if state_override is not None and "state" in contracts:
        contracts["state"] = state_override

    for name, from_stage in OPTIONAL_CONTRACTS.items():
        if name in contracts or STAGES.index(stage) < STAGES.index(from_stage):
            continue
        optional_path = root / CONTRACT_PATHS[name]
        if not optional_path.is_file():
            continue
        value, error = read_json(optional_path, exact=name in {"results", "claims"})
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
                is_official = successful_official(run)
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
    for checkpoint, contract, field in (("model-design", "model", "selection_check"), ("validation", "claims", "conclusion_check"), ("delivery", "delivery", "final_check")):
        data = contracts.get(contract)
        check = data.get(field) if isinstance(data, dict) else None
        if STAGES.index(stage) >= STAGES.index(checkpoint) and isinstance(check, dict) and check.get("reviewer_kind") == "lead_agent":
            try:
                require_human_checkpoint(root, checkpoint)
            except ValueError as exc:
                findings.append(finding("AUTH-E001", "error", "semantic", checkpoint, CONTRACT_PATHS[contract], str(exc), gate_only=True))
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
        results_data = contracts.get("results")
        items = as_list(results_data.get("results")) if isinstance(results_data, dict) else []
        indexed = {item["result_id"]: item for item in items if isinstance(item, dict) and isinstance(item.get("result_id"), str)}
        findings.extend(check_claims(contracts["claims"], known, CONTRACT_PATHS["claims"], superseded_ids, root, indexed))
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
