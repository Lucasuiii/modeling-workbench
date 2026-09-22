#!/usr/bin/env python3
"""Build a read-only, conclusion-withheld package for pre-validation review."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from canonical_evidence import resolve_official_computation
from workflow_checks import REQUIRED_CONTEXT_EXCLUSIONS, WORKFLOW_VERSION, read_json, safe_project_path
from provenance import digest_records, sha256_file


PACKAGE_REL = Path("validation/independent-review-package")
TARGETED_FINDINGS_NAME = "TARGETED_FINDINGS.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def require_object(path: Path) -> dict[str, Any]:
    value, error = read_json(path)
    if error or not isinstance(value, dict):
        raise ValueError(f"cannot read JSON object {path}: {error or 'not an object'}")
    return value


def copy_material(project: Path, staging: Path, rel: str, role: str, records: list[dict[str, Any]], seen: set[str]) -> None:
    if rel in seen:
        return
    source = safe_project_path(project, rel)
    if source is None or not source.is_file() or source.stat().st_size == 0:
        raise ValueError(f"required review material is missing or unsafe: {rel}")
    destination = staging / "materials" / rel
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    package_path = (PACKAGE_REL / "materials" / rel).as_posix()
    records.append({"path": package_path, "source_path": rel, "role": role, "size": destination.stat().st_size, "sha256": sha256_file(destination)})
    seen.add(rel)


def targeted_findings_from(prior: dict[str, Any], target_ids: list[str]) -> list[dict[str, str]]:
    available = {
        str(item.get("finding_id")): item
        for item in prior.get("findings", [])
        if isinstance(item, dict) and item.get("severity") == "P0" and item.get("status") == "open"
    }
    missing = sorted(set(target_ids) - set(available))
    if missing:
        raise ValueError(f"targeted findings are not open P0 entries in the previous review: {', '.join(missing)}")
    fields = ("finding_id", "category", "location", "evidence", "recommendation")
    return [{field: str(available[finding_id].get(field, "")) for field in fields} for finding_id in target_ids]


def build(project: Path, *, review_mode: str = "auto", previous_review_path: str | None = None, target_finding_ids: list[str] | None = None, refresh: bool = False) -> Path:
    project = project.resolve()
    destination = project / PACKAGE_REL
    target_finding_ids = sorted(set(target_finding_ids or []))
    current_review = project / "validation" / "INDEPENDENT_REVIEW_RESULT.json"
    prior_review: dict[str, Any] | None = None
    if review_mode == "auto" and current_review.is_file():
        prior = require_object(current_review)
        if prior.get("verdict") == "revision_required":
            prior_review = prior
            review_mode = "targeted"
            previous_review_path = previous_review_path or "validation/INDEPENDENT_REVIEW_RESULT.json"
            if not target_finding_ids:
                target_finding_ids = sorted(
                    str(item.get("finding_id")) for item in prior.get("findings", [])
                    if isinstance(item, dict) and item.get("severity") == "P0" and item.get("status") == "open"
                )
            refresh = True
        else:
            review_mode = "full"
    elif review_mode == "auto":
        review_mode = "full"
    if review_mode not in {"full", "targeted"}:
        raise ValueError("review_mode must be auto, full, or targeted")
    if destination.exists() and not refresh:
        raise ValueError(f"refusing to overwrite existing review package: {destination}")
    if review_mode == "targeted" and (not previous_review_path or not target_finding_ids):
        raise ValueError("targeted review requires previous_review_path and target_finding_ids")
    if review_mode == "targeted" and previous_review_path == "validation/INDEPENDENT_REVIEW_RESULT.json" and current_review.is_file():
        prior = prior_review or require_object(current_review)
        prior_review = prior
        history_dir = project / "validation" / "review-history"
        history_dir.mkdir(parents=True, exist_ok=True)
        safe_id = "".join(char if char.isalnum() or char in "-_" else "_" for char in str(prior.get("review_id", "previous-review")))
        archived_review = history_dir / f"{safe_id}.json"
        if archived_review.exists() and archived_review.read_bytes() != current_review.read_bytes():
            raise ValueError(f"review history target already exists with different content: {archived_review}")
        if not archived_review.exists():
            shutil.copy2(current_review, archived_review)
        previous_review_path = archived_review.relative_to(project).as_posix()
    if review_mode == "targeted" and prior_review is None:
        previous = safe_project_path(project, previous_review_path)
        if previous is None or not previous.is_file():
            raise ValueError(f"targeted review cannot read previous review: {previous_review_path}")
        prior_review = require_object(previous)
    targeted_findings = targeted_findings_from(prior_review, target_finding_ids) if prior_review is not None else []

    state = require_object(project / ".cumcm/state.json")
    if state.get("workflow_version") != WORKFLOW_VERSION:
        raise ValueError(f"independent review packaging requires workflow {WORKFLOW_VERSION}")
    project_id = str(state.get("project_id", ""))
    if not project_id:
        raise ValueError("workflow state has no project_id")

    sources = require_object(project / "problem/SOURCE_MANIFEST.json")
    results = require_object(project / "results/RESULTS_INDEX.json")
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    validation_dir = project / "validation"
    validation_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="independent-review-", dir=validation_dir) as temp:
        staging = Path(temp) / "package"
        staging.mkdir()
        asset_root = Path(__file__).resolve().parents[1] / "assets" / "independent-review"
        # Freeze the canonical guide with the other instructions. It is not a
        # project-relative evidence source; package_digest binds its content.
        instruction_sources = [asset_root / "SKILL.md", asset_root / "REVIEW_REQUEST.md",
                               asset_root.parents[1] / "references" / "mechanism-validation.md"]
        for source in instruction_sources:
            name = source.name
            shutil.copy2(source, staging / name)
            records.append(
                {
                    "path": (PACKAGE_REL / name).as_posix(),
                    "role": "review_instruction",
                    "size": (staging / name).stat().st_size,
                    "sha256": sha256_file(staging / name),
                }
            )

        contract_roles = {
            "problem/SOURCE_MANIFEST.json": "problem_contract",
            "analysis/PROBLEM_FACTS.json": "problem_contract",
            "analysis/TASK_CAPABILITIES.json": "problem_contract",
            "model/MODEL_CONTRACT.json": "model_contract",
            "results/RESULTS_INDEX.json": "run_record",
        }
        for rel, role in contract_roles.items():
            copy_material(project, staging, rel, role, records, seen)
        # Narrative notes help a reviewer but are not contracts; include them only if present.
        optional_roles = {
            "model/CROSS_QUESTION_LEDGER.json": "model_contract",
            "model/VALIDATION_PLAN.md": "model_contract",
            "model/MODEL_CANDIDATES.md": "model_contract",
            "model/OPTIMALITY_SCOPE.md": "model_contract",
            "analysis/ASSUMPTIONS.md": "problem_contract",
            "analysis/SYMBOLS.md": "problem_contract",
        }
        for rel, role in optional_roles.items():
            if (project / rel).is_file():
                copy_material(project, staging, rel, role, records, seen)

        for source in sources.get("sources", []):
            if isinstance(source, dict) and source.get("origin") in {"official", "organizer_attachment"}:
                copy_material(project, staging, str(source.get("path")), "official_input", records, seen)

        for evidence in resolve_official_computation(project, results):
            copy_material(project, staging, evidence["manifest_path"], "run_record", records, seen)
            for rel in evidence["source_files"]:
                copy_material(project, staging, rel, "computation_source", records, seen)
            for rel in evidence["formal_inputs"]:
                copy_material(project, staging, rel, "formal_input", records, seen)
            for rel in evidence["claim_bearing_outputs"]:
                copy_material(project, staging, rel, "executed_output", records, seen)

        if review_mode == "targeted":
            targeted_payload = {
                "review_mode": "targeted",
                "source_review_id": prior_review.get("review_id") if prior_review else None,
                "findings": targeted_findings,
            }
            targeted_path = staging / TARGETED_FINDINGS_NAME
            targeted_path.write_text(json.dumps(targeted_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            records.append(
                {
                    "path": (PACKAGE_REL / TARGETED_FINDINGS_NAME).as_posix(),
                    "role": "review_instruction",
                    "size": targeted_path.stat().st_size,
                    "sha256": sha256_file(targeted_path),
                }
            )

        result_template = {
            "schema_version": WORKFLOW_VERSION,
            "artifact_type": "independent_review_result",
            "project_id": project_id,
            "updated_at": None,
            "producer": {"kind": "external_tool", "name": "selected independent reviewer", "version": None},
            "review_id": "REPLACE",
            "package_manifest_path": (PACKAGE_REL / "REVIEW_PACKAGE_MANIFEST.json").as_posix(),
            "package_digest": "REPLACE_AFTER_PACKAGE_BUILD",
            "review_mode": review_mode,
            "previous_review_path": previous_review_path,
            "target_finding_ids": target_finding_ids,
            # Independence is never pre-answered by the packager. The reviewer or the
            # user must positively assert each field; leaving a null fails IREVIEW-E027.
            "reviewer_context": {
                "reviewer_kind": None,
                "reviewer": "REPLACE",
                "model": "REPLACE",
                "task_ref": "REPLACE",
                "different_conversation": None,
                "independence_grade": None,
            },
            "verdict": "inconclusive",
            "findings": [],
            "raw_review_path": "validation/INDEPENDENT_REVIEW_RAW.md",
            "reviewed_files": [],
        }
        generated_at = utc_now()
        package_digest = digest_records(records)
        upstream_records = [
            {"path": str(item["source_path"]), "sha256": str(item["sha256"])}
            for item in records if item.get("source_path")
        ]
        result_template["package_digest"] = package_digest
        (staging / "INDEPENDENT_REVIEW_RESULT_TEMPLATE.json").write_text(
            json.dumps(result_template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        records.append(
            {
                "path": (PACKAGE_REL / "INDEPENDENT_REVIEW_RESULT_TEMPLATE.json").as_posix(),
                "role": "review_instruction",
                "size": (staging / "INDEPENDENT_REVIEW_RESULT_TEMPLATE.json").stat().st_size,
                "sha256": sha256_file(staging / "INDEPENDENT_REVIEW_RESULT_TEMPLATE.json"),
            }
        )
        manifest = {
            "schema_version": WORKFLOW_VERSION,
            "artifact_type": "independent_review_package",
            "project_id": project_id,
            "updated_at": generated_at,
            "producer": {"kind": "script", "name": "build_independent_review_package.py", "version": WORKFLOW_VERSION},
            "package_root": PACKAGE_REL.as_posix(),
            "review_skill_path": (PACKAGE_REL / "SKILL.md").as_posix(),
            "review_request_path": (PACKAGE_REL / "REVIEW_REQUEST.md").as_posix(),
            "review_mode": review_mode,
            "previous_review_path": previous_review_path,
            "target_finding_ids": target_finding_ids,
            "upstream_digest": digest_records(upstream_records),
            "package_digest": package_digest,
            # A truthful statement about what the packager excluded, not a claim
            # about what the reviewer happens to believe.
            "context_excluded": sorted(REQUIRED_CONTEXT_EXCLUSIONS),
            "files": sorted(records, key=lambda item: item["path"]),
            "reviewer_selection": {"status": "unreviewed", "reviewer": None, "model": None, "originating_task_ref": None, "task_ref": None},
        }
        (staging / "REVIEW_PACKAGE_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if destination.exists():
            old_manifest = require_object(destination / "REVIEW_PACKAGE_MANIFEST.json")
            old_digest = old_manifest.get("package_digest")
            if not isinstance(old_digest, str) or not old_digest:
                raise ValueError("existing review package manifest has no package_digest")
            archive_root = project / "validation" / "review-archive"
            archive_root.mkdir(parents=True, exist_ok=True)
            archived = archive_root / f"package-{old_digest[:12]}"
            if archived.exists():
                raise ValueError(f"review package archive already exists: {archived}")
            shutil.move(destination, archived)
        shutil.copytree(staging, destination)
    return destination / "REVIEW_PACKAGE_MANIFEST.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the user-routed independent review package before validation")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--review-mode", choices=("auto", "full", "targeted"), default="auto")
    parser.add_argument("--previous-review-path")
    parser.add_argument("--target-finding-id", action="append", default=[])
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    try:
        manifest = build(args.project, review_mode=args.review_mode, previous_review_path=args.previous_review_path, target_finding_ids=args.target_finding_id, refresh=args.refresh)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"created independent review package: {manifest}")
    print("stop here: the user must choose a separate reviewer and return the structured result")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
