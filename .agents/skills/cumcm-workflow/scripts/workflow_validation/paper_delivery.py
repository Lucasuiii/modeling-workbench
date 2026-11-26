"""Figures, paper sources, rendered artifacts and delivery checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from provenance import snapshot_matches

from .common import (
    Finding,
    as_list,
    check_envelope,
    finding,
    ids,
    item_id,
    nonempty,
    read_json,
    require_fields,
    safe_project_path,
    sha256,
)


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
    if not isinstance(check, dict) or check.get("decision") != "accepted" or check.get("reviewer_kind") not in {"human_user", "lead_agent"}:
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
        findings.append(finding("PTEXT-W006", "warning", "semantic", "paper", path, "visible-text report has open flags; inspect the indicated text or rendered pages"))
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
