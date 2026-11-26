"""Problem facts, capabilities, model selection and verification plans."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import (
    Finding,
    as_list,
    check_envelope,
    finding,
    item_id,
    nonempty,
    require_fields,
    safe_project_path,
)


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
    if not isinstance(check, dict) or check.get("decision") != "accepted" or check.get("reviewer_kind") not in {"human_user", "lead_agent"}:
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
        elif isinstance(component.get("method"), str):
            # Prose can paraphrase a method or discuss a rejected baseline.
            # A complete competing label is a concrete inconsistency we can report.
            method = component["method"].strip().casefold()
            matches = [candidate for candidate in candidates
                       if isinstance(candidate.get("method"), str)
                       and method and candidate["method"].strip().casefold() == method]
            if matches and selected[0] not in matches:
                findings.append(finding(
                    "MODEL-W017", "warning", "semantic", "model-design", path,
                    f"{ident} method names an alternative to the selected candidate",
                    related_ids=[ident, item_id(selected[0], "candidate_id"),
                                 *(item_id(candidate, "candidate_id") for candidate in matches)],
                ))
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
