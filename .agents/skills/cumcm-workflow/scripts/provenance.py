#!/usr/bin/env python3
"""Small deterministic digest helpers for v0.8 snapshots and handoffs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest_records(records: Iterable[dict]) -> str:
    canonical = [
        {"path": str(item["path"]), "sha256": str(item["sha256"])}
        for item in records
    ]
    canonical.sort(key=lambda item: item["path"])
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def tree_snapshot(root: Path, paths: Iterable[str], *, entrypoint: str | None = None) -> dict:
    root = root.resolve()
    records: list[dict[str, str]] = []
    normalized = sorted({str(path) for path in paths})
    for rel in normalized:
        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"snapshot path escapes project: {rel}") from exc
        if not candidate.is_file():
            raise ValueError(f"snapshot file is missing: {rel}")
        records.append({"path": rel, "sha256": sha256_file(candidate)})
    if not records:
        raise ValueError("snapshot requires at least one file")
    snapshot = {
        "algorithm": "sha256-tree-v1",
        "digest": digest_records(records),
        "files": [item["path"] for item in records],
    }
    if entrypoint is not None:
        snapshot["entrypoint"] = entrypoint
    return snapshot


def snapshot_matches(root: Path, snapshot: object) -> bool:
    if not isinstance(snapshot, dict) or snapshot.get("algorithm") != "sha256-tree-v1":
        return False
    files = snapshot.get("files")
    if not isinstance(files, list) or not files:
        return False
    try:
        current = tree_snapshot(root, [str(path) for path in files])
    except (OSError, ValueError):
        return False
    return current["digest"] == snapshot.get("digest")
