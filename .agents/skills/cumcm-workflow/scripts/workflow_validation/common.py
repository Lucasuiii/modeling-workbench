"""Finding, local artifact access and shared schema checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

import evidence_json
from provenance import sha256_file

from .contracts import SCHEMA_FILES, WORKFLOW_VERSION


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


def read_json(path: Path, *, exact: bool = False) -> tuple[Any | None, str | None]:
    try:
        if exact:
            return evidence_json.read(path), None
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, ValueError) as exc:
        return None, str(exc)


def check_schema(data: Any, schema_name: str, stage: str, path: str) -> list[Finding]:
    schema_dir = Path(__file__).resolve().parents[2] / "schemas"
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
