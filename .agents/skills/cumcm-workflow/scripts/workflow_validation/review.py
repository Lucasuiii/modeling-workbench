"""Independent review packages, verdicts and claim evidence."""

from __future__ import annotations

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
    require_fields,
    safe_project_path,
    sha256,
)
from .contracts import CONTRACT_PATHS, EVIDENCE_STATES


REQUIRED_CONTEXT_EXCLUSIONS = {
    "originating_task_transcript",
    "debug_history",
    "failed_runs",
    "prior_review_prose",
}


STRONG_CLAIM_PATTERNS = {
    "global_optimality": re.compile(r"\bglobal(?:ly)? optimal\b|全局最优", re.I),
    "unbiasedness": re.compile(r"\bunbiased\b|无偏", re.I),
    "equivalence": re.compile(r"\bequivalent\b|统计等价|等价", re.I),
    "causality": re.compile(r"\bcausal(?:ity)?\b|因果", re.I),
    "robustness": re.compile(r"\brobust(?:ness)?\b|鲁棒", re.I),
}


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
    if not isinstance(check, dict) or check.get("decision") != "accepted" or check.get("reviewer_kind") not in {"human_user", "lead_agent"}:
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
    superseded_ids: set[str],
    root: Path,
    indexed: dict[str, dict],
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
        if state == "reproduced":
            from canonical_evidence import check_reproduction
            try:
                check_reproduction(root, claim, indexed)
            except (KeyError, TypeError, ValueError, OSError, AttributeError) as exc:
                findings.append(finding("CLAIM-E013", "error", "execution", "validation", path,
                                        f"{ident} has no verified rerun comparison: {exc}", related_ids=[ident]))
        claim_review = claim.get("review")
        if claim_review is not None and (not isinstance(claim_review, dict) or claim_review.get("decision") not in {"accepted", "accepted_with_concerns"}):
            findings.append(finding("CLAIM-W014", "warning", "semantic", "validation", path, f"optional claim-level review is not accepted: {ident}", related_ids=[ident]))
    return findings
