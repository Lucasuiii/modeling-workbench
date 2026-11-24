#!/usr/bin/env python3
"""Inspect rendered PDF text for workflow leakage and reader-facing number overload."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from workflow_checks import WORKFLOW_VERSION, sha256


BLOCKING_PATTERNS = {
    # Workflow IDs have a fixed shape (PREFIX-[Qn-]NNN); a bare "MODEL-A" in prose is not one.
    "PAPER-TEXT-E001": re.compile(r"\b(?:SRC|FACT|CAP|MODEL|RUN|RES|CLM|FIG)-(?:[A-Z]+\d+-)?\d{3}\b", re.ASCII),
    "PAPER-TEXT-E002": re.compile(r"\b(?:supported_not_reproduced|partially_supported|not_supported|not_applicable|missing_evidence|not_checked)\b", re.I | re.ASCII),
    "PAPER-TEXT-E003": re.compile(r"(?:validation\s*门禁|workflow\s*gate|claim-bearing|\bvalidation\s+ID\b)", re.I),
    "PAPER-TEXT-E004": re.compile(r"(?:file:///|/(?:Users|home)/[^\s/]+/|/private/var/folders/|[A-Za-z]:\\(?:Users|Documents and Settings)\\)", re.I),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def excerpt(text: str, start: int, end: int) -> str:
    left = max(0, start - 55)
    right = min(len(text), end + 75)
    return re.sub(r"\s+", " ", text[left:right]).strip()


def extract_pdf_text(pdf: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="cumcm-paper-text-") as temp:
        output = Path(temp) / "paper.txt"
        completed = subprocess.run(
            ["pdftotext", "-enc", "UTF-8", "-layout", str(pdf), str(output)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            raise ValueError(f"pdftotext failed: {completed.stderr.strip()}")
        return output.read_text(encoding="utf-8")


def inspect_text(text: str) -> tuple[list[dict], list[dict]]:
    blocking: list[dict] = []
    flags: list[dict] = []
    pages = text.removesuffix("\f").split("\f")
    for number, page in enumerate(pages, 1):
        if not page.strip():
            flags.append({"rule_id": "PAPER-TEXT-W003", "location": f"page:{number}",
                          "excerpt": "No extractable text. Inspect the rendered page.",
                          "resolution_status": "open", "resolution": None})
    for rule_id, pattern in BLOCKING_PATTERNS.items():
        for match in pattern.finditer(text):
            blocking.append(
                {
                    "rule_id": rule_id,
                    "location": f"text-offset:{match.start()}",
                    "excerpt": excerpt(text, match.start(), match.end()),
                }
            )

    for match in re.finditer(r"(?<![A-Za-z0-9])[-+]?\d+\.\d{7,}(?![A-Za-z0-9])", text):
        flags.append(
            {
                "rule_id": "PAPER-TEXT-W001",
                "location": f"text-offset:{match.start()}",
                "excerpt": excerpt(text, match.start(), match.end()),
                "resolution_status": "open",
                "resolution": None,
            }
        )

    cursor = 0
    for sentence in re.split(r"(?<=[。！？；])|\n{2,}", text):
        clean = re.sub(r"\s+", " ", sentence).strip()
        if not clean:
            cursor += len(sentence)
            continue
        numeric_tokens = re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?(?![A-Za-z])", clean)
        if len(numeric_tokens) >= 6:
            flags.append(
                {
                    "rule_id": "PAPER-TEXT-W002",
                    "location": f"text-offset:{cursor}",
                    "excerpt": clean[:220],
                    "resolution_status": "open",
                    "resolution": None,
                }
            )
        cursor += len(sentence)
    return blocking, flags


def build_report(project: Path, pdf: Path, output: Path) -> dict:
    project = project.resolve()
    pdf = pdf.resolve()
    try:
        rel_pdf = pdf.relative_to(project).as_posix()
    except ValueError as exc:
        raise ValueError("PDF must be inside the project") from exc
    if not pdf.is_file() or pdf.stat().st_size == 0:
        raise ValueError(f"PDF is missing or empty: {pdf}")
    text = extract_pdf_text(pdf)
    blocking, flags = inspect_text(text)
    status = "blocked" if blocking else "needs_review" if flags else "pass"
    report = {
        "schema_version": WORKFLOW_VERSION,
        "artifact_type": "paper_visible_text_report",
        "project_id": json.loads((project / ".cumcm/state.json").read_text(encoding="utf-8"))["project_id"],
        "updated_at": utc_now(),
        "producer": {"kind": "script", "name": "paper_visible_text_check.py", "version": WORKFLOW_VERSION},
        "paper_artifact": {"path": rel_pdf, "sha256": sha256(pdf)},
        "status": status,
        "blocking_matches": blocking,
        "review_flags": flags,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the visible text of the final CUMCM PDF")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    output = args.output or project / "paper" / "PAPER_VISIBLE_TEXT_REPORT.json"
    try:
        report = build_report(project, args.pdf, output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": report["status"], "blocking": len(report["blocking_matches"]), "review_flags": len(report["review_flags"])}, ensure_ascii=False))
    return 1 if report["blocking_matches"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
