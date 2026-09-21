#!/usr/bin/env python3
"""Classify user-supplied official paper materials by their declared role."""

from __future__ import annotations

import re
from typing import Any, Iterable


TEMPLATE_ROLES = {
    "paper_template",
    "format_template",
    "paper_format_template",
    "official_submission_template",
    "论文格式模板",
    "格式模板",
    "official_paper_template",
    "latex_template",
    "word_template",
    "submission_template",
    "论文模板",
    "官方论文模板",
    "提交模板",
}
RULE_ROLES = {
    "paper_format",
    "format_rule",
    "format_rules",
    "format_requirements",
    "formatting_instructions",
    "submission_rule",
    "submission_rules",
    "competition_rule",
    "competition_rules",
    "论文格式",
    "格式要求",
    "格式说明",
    "提交规则",
    "比赛规则",
}
FORMAT_NAME_HINTS = ("format", "rule", "template", "格式", "规则", "模板")


def normalize_role(value: Any) -> str:
    text = str(value).strip().casefold()
    return re.sub(r"[\s\-/]+", "_", text)


def declared_roles(source: dict[str, Any]) -> set[str]:
    values: list[Any] = []
    for key in ("artifact_role", "material_role", "role"):
        if source.get(key) not in (None, ""):
            values.append(source[key])
    authoritative = source.get("authoritative_for")
    if isinstance(authoritative, list):
        values.extend(authoritative)
    elif authoritative not in (None, ""):
        values.append(authoritative)
    return {normalize_role(value) for value in values if str(value).strip()}


def classify_official_material(source: dict[str, Any]) -> str | None:
    """Return the paper-facing role without treating a filename as authority."""
    if source.get("origin") not in {"official", "organizer_attachment"}:
        return None
    roles = declared_roles(source)
    if roles & {normalize_role(value) for value in TEMPLATE_ROLES}:
        return "paper_template"
    if roles & {normalize_role(value) for value in RULE_ROLES}:
        return "format_or_submission_rule"

    # A filename hint is useful for routing, but is not strong enough to make a
    # PDF/DOC/DOCX block generic initialization as if it were an adaptable template.
    name = str(source.get("path", "")).casefold()
    if any(token in name for token in FORMAT_NAME_HINTS):
        return "unclassified_format_material"
    return None


def classified_official_materials(sources: Iterable[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        role = classify_official_material(source)
        if role is None:
            continue
        records.append(
            {
                "source_id": source.get("source_id"),
                "path": source.get("path"),
                "role": role,
                "authoritative_for": source.get("authoritative_for", []),
            }
        )
    return sorted(records, key=lambda item: str(item.get("path", "")))
