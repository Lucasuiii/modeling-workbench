#!/usr/bin/env python3
"""Inventory official input files and record automatic byte identity without modifying them."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
from datetime import datetime, timezone
from pathlib import Path

from workflow_validation.contracts import WORKFLOW_VERSION


EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(root: Path, output: Path) -> list[dict]:
    output_resolved = output.resolve()
    records = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        if path.resolve() == output_resolved:
            continue
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return records


def inventory_sources(source_root: Path, project_root: Path, output: Path, origin: str) -> list[dict]:
    output_resolved = output.resolve()
    records = []
    for path in sorted(source_root.rglob("*")):
        if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.parts):
            continue
        if path.resolve() == output_resolved:
            continue
        try:
            rel = path.resolve().relative_to(project_root.resolve()).as_posix()
        except ValueError as exc:
            raise ValueError(f"source file is outside project root: {path}") from exc
        records.append(
            {
                "source_id": f"SRC-{len(records) + 1:03d}",
                "path": rel,
                "size": path.stat().st_size,
                "sha256": sha256(path),
                "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "origin": origin,
                "acquisition": {
                    "method": "user_local_file" if origin in {"official", "organizer_attachment", "external_reference"} else "derived",
                    "provided_by_user": origin in {"official", "organizer_attachment", "external_reference"},
                    "source_reference": None,
                },
                "authoritative_for": [],
                "derived_from": None,
                "mutable": origin not in {"official", "organizer_attachment"},
            }
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument(
        "--origin",
        choices=("official", "organizer_attachment", "external_reference", "team_created"),
        default="official",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        parser.error(f"root is not a directory: {root}")
    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        parser.error(f"project root is not a directory: {project_root}")
    try:
        records = inventory_sources(root, project_root, args.output, args.origin)
    except ValueError as exc:
        parser.error(str(exc))
    payload = {
        "schema_version": WORKFLOW_VERSION,
        "artifact_type": "source_manifest",
        "project_id": args.project_id,
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "producer": {"kind": "script", "name": "inventory_artifacts.py", "version": WORKFLOW_VERSION},
        "sources": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"inventoried {len(records)} files -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
