#!/usr/bin/env python3
"""Measure contest submission files using project-declared current official rules.

The receipt is part of DELIVERY_MANIFEST, never an assertion of visual compliance
or a receipt from the organizer. Recording does not submit anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

from official_materials import classified_official_materials
from refresh_evidence import write_atomic

MANIFEST = "delivery/DELIVERY_MANIFEST.json"


def local_file(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError("submission paths must be project-relative")
    path = (root / value).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"missing or unsafe submission file: {value}")
    return path


def measure(root: Path, value: str) -> dict:
    path = local_file(root, value)
    sha = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
            md5.update(chunk)
            size += len(chunk)
    if not size:
        raise ValueError(f"empty submission file: {value}")
    return {"path": value, "sha256": sha.hexdigest(), "md5": md5.hexdigest(), "size": size}


def run_tool(argv: list[str]) -> str:
    try:
        return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"PDF inspection failed: {exc}") from exc


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def positive(value, label: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def inspect_submission(root: Path, delivery: dict) -> tuple[dict, list[str]]:
    """Return measured facts and failures, without changing any file."""
    rules = delivery["submission"]["rules"]
    if not isinstance(rules, dict):
        raise ValueError("submission.rules must be an object")
    source_manifest = json.loads((root / "problem/SOURCE_MANIFEST.json").read_text())
    official = {item["path"] for item in classified_official_materials(source_manifest.get("sources", []))
                if item["role"] in {"paper_template", "format_or_submission_rule"}}
    sources = rules["sources"]
    if not isinstance(sources, list) or not sources or any(p not in official for p in sources):
        raise ValueError("rules.sources must cite declared official format/submission materials")
    source_records = [measure(root, p) for p in sources]
    pdf_rel = delivery["deliverables"]["final_pdf"]["path"]
    pdf = local_file(root, pdf_rel)
    if pdf.suffix.lower() != ".pdf":
        raise ValueError("final submission must be a PDF")
    before = measure(root, pdf_rel)
    errors = []
    receipt_rel = delivery["compile_receipt_path"]
    receipt = json.loads(local_file(root, receipt_rel).read_text())
    selected = next((a for a in receipt["attempts"] if a.get("attempt_id") == receipt["selected_attempt_id"]), None)
    if not selected or selected.get("exit_code") != 0:
        raise ValueError("submission requires a selected successful compilation")
    compiled = measure(root, selected["pdf_path"])
    if before["sha256"] != selected.get("pdf_sha256") or compiled["sha256"] != before["sha256"]:
        errors.append("submission PDF bytes differ from the selected compiled PDF")
    if pdf.name != rules["pdf_name"]:
        errors.append("final PDF filename differs from the declared official submission name")
    info = run_tool(["pdfinfo", str(pdf)])
    match = re.search(r"^Pages:\s+(\d+)\s*$", info, re.MULTILINE)
    if not match:
        raise ValueError("pdfinfo did not report page count")
    count = int(match.group(1))
    pages = run_tool(["pdftotext", "-layout", str(pdf), "-"]).split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    if len(pages) != count or any(not text.strip() for text in pages):
        raise ValueError("PDF has empty or unextractable pages; inspect images/OCR manually before recording")
    cover = positive(rules["cover_pages"], "cover_pages")
    if count <= cover:
        raise ValueError("PDF contains no abstract/body after its cover")
    tokens = rules["identity_tokens"]
    if not isinstance(tokens, list) or not tokens or any(not isinstance(t, str) or not compact(t) for t in tokens):
        raise ValueError("identity_tokens must list the actual non-empty team/person/institution identifiers")
    # XMP and the document information dictionary are both outside the cover.
    metadata = info + run_tool(["pdfinfo", "-meta", str(pdf)])
    for token in tokens:
        if compact(token).casefold() in compact(metadata).casefold():
            errors.append("identity information found in PDF metadata")
        for number, page in enumerate(pages[cover:], cover + 1):
            if compact(token).casefold() in compact(page).casefold():
                errors.append(f"identity information found outside the cover on page {number}")
    abstract = rules["abstract"]
    maximum = positive(abstract["max_pages"], "abstract.max_pages")
    boundaries = []
    for field in ("start_marker", "body_marker"):
        marker = abstract[field]
        if not isinstance(marker, str) or not compact(marker):
            raise ValueError(f"abstract.{field} must be non-empty")
        hits = [(index, compact(page).find(compact(marker))) for index, page in enumerate(pages)
                if index >= cover and compact(marker) in compact(page)]
        if len(hits) != 1 or compact(pages[hits[0][0]]).count(compact(marker)) != 1:
            raise ValueError(f"abstract.{field} must occur exactly once after the cover")
        boundaries.append(hits[0])
    start, end = boundaries
    if start[0] != cover or end <= start:
        errors.append("abstract/body order differs from cover -> abstract -> body")
    # A body heading may share the last abstract page. Count that page when
    # non-whitespace text precedes the heading; otherwise the abstract ends before it.
    abstract_pages = end[0] - start[0] + (1 if end[1] > 0 else 0)
    if abstract_pages > maximum:
        errors.append(f"abstract occupies {abstract_pages} pages; maximum is {maximum}")
    attachments = rules["attachments"]
    if not isinstance(attachments, list):
        raise ValueError("attachments must be a list (empty when none are to be submitted)")
    measured_attachments = []
    for item in attachments:
        path = local_file(root, item["path"])
        record = measure(root, item["path"])
        measured_attachments.append(record)
        if path.name != item["name"]:
            errors.append(f"attachment filename mismatch: {item['path']}")
        if record["size"] > positive(item["max_bytes"], "attachment.max_bytes"):
            errors.append(f"attachment exceeds byte limit: {item['path']}")
        formats = item["formats"]
        if not isinstance(formats, list) or not formats or any(f not in ("zip", "rar", "7z") for f in formats):
            raise ValueError("attachment formats must name allowed zip/rar/7z containers")
        with path.open("rb") as stream:
            magic = stream.read(8)
        kind = ("zip" if zipfile.is_zipfile(path) else "rar" if magic.startswith((b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00"))
                else "7z" if magic.startswith(b"7z\xbc\xaf\x27\x1c") else None)
        if kind not in formats or path.suffix.lower() != f".{kind}":
            errors.append(f"attachment container/extension not allowed: {item['path']}")
    if before != measure(root, pdf_rel):
        raise ValueError("PDF changed during inspection")
    return {"pdf": before, "rule_files": source_records, "compile_receipt": measure(root, receipt_rel),
            "rules_sha256": hashlib.sha256(json.dumps(rules, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            "page_count": count, "abstract_pages": abstract_pages, "attachments": measured_attachments}, errors


def is_huawei(root: Path) -> bool:
    path = root / "paper/LATEX_TEMPLATE_MANIFEST.json"
    if not path.is_file():
        return False
    name = str(json.loads(path.read_text()).get("competition", "")).casefold()
    return any(token in name for token in ("华为", "huawei", "研究生数学建模", "gmcm", "cpgmcm", "cpmcm"))


def check_submission(root: Path, delivery: dict) -> list[str]:
    try:
        if "submission" not in delivery:
            return ["Huawei delivery requires current submission rules and a recorded file check"] if is_huawei(root) else []
        observed, errors = inspect_submission(root, delivery)
        if delivery["submission"].get("recorded") != observed:
            errors.append("submission record is missing or stale; do not reuse a previously submitted MD5")
        return errors
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return [f"cannot verify submission: {exc}"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--record", action="store_true", help="record successful measured checks in the existing delivery manifest")
    args = parser.parse_args()
    root = args.project.resolve()
    try:
        path = root / MANIFEST
        data = json.loads(path.read_text())
        observed, errors = inspect_submission(root, data)
        old = data["submission"].get("recorded")
        if old is not None and old != observed:
            errors.append("existing submission record differs; stop and resolve the previously frozen/submitted version before replacing it")
        if args.record and not errors:
            if old is None:
                data["submission"]["recorded"] = observed
                write_atomic(path, data)
        print(json.dumps({"observed": observed, "errors": errors,
                          "scope": "file checks only; official layout, completeness of identity tokens and image text require visual review"}, ensure_ascii=False, indent=2))
        return 1 if errors else 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
