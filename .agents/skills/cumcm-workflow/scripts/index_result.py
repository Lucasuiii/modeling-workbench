#!/usr/bin/env python3
"""Index a formal result by reading its value out of the executed output.

The value is never transcribed by hand: it is resolved through the same
`path#/json-pointer` locator the checker will later re-resolve, so RESULT-E012
(indexed value differs from executed output) becomes structurally impossible.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKFLOW_VERSION = "0.6.0"
EVIDENCE_STATES = (
    "not_checked", "missing_evidence", "supported_not_reproduced", "reproduced",
    "partially_supported", "contradicted", "ambiguous", "not_applicable",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read {path}: {exc}")
    if not isinstance(value, dict):
        raise SystemExit(f"expected a JSON object: {path}")
    return value


def resolve_pointer(data: Any, pointer: str) -> Any:
    from json_pointer import resolve_json_pointer
    value, found = resolve_json_pointer(data, pointer)
    if not found:
        raise SystemExit(f"JSON pointer does not resolve: {pointer}")
    return value


def all_runs(root: Path) -> dict[str, dict[str, Any]]:
    runs: dict[str, dict[str, Any]] = {}
    for manifest_path in sorted((root / "runs").glob("*/RUN_MANIFEST.json")):
        manifest = read_object(manifest_path)
        run_id = str(manifest.get("run_id", "")).strip()
        if run_id:
            runs[run_id] = manifest
    return runs


def successful_official(manifest: dict[str, Any]) -> bool:
    return manifest.get("official_run") is True and manifest.get("status") == "completed" and manifest.get("exit_code") == 0


def newest_descendant(runs: dict[str, dict[str, Any]], run_id: str) -> str:
    """Walk parent links forward through successful official runs only.

    A failed or exploratory rerun replaces nothing. Multiple successful official
    children are ambiguous; the caller must choose a branch explicitly.
    """
    children: dict[str, list[str]] = {}
    for rid, manifest in runs.items():
        parent = str(manifest.get("parent_run_id", "")).strip()
        if parent and parent != rid and successful_official(manifest):
            children.setdefault(parent, []).append(rid)
    seen = {run_id}
    current = run_id
    while current in children:
        candidates = sorted(children[current], key=lambda rid: (str(runs[rid].get("finished_at", "")), rid))
        if len(candidates) > 1:
            # Two successful official reruns of the same parent is a fork, not a chain.
            # Both superseded it, and which one the result should follow is a judgement
            # about the work; guessing "newest" would quietly re-point evidence at a
            # branch nobody chose.
            raise ValueError(
                f"lineage from {current} is ambiguous: {', '.join(candidates)} all supersede it; "
                "name the run you mean with --run-id instead of --follow-lineage"
            )
        current = candidates[0]
        if current in seen:
            break
        seen.add(current)
    return current


def frozen_locator(manifest: dict[str, Any], run_id: str, locator: str) -> str:
    """Accept the path the program writes to and store the immutable frozen copy."""
    rel, _, pointer = locator.partition("#")
    roles = {str(entry.get("path")): entry.get("evidence_role") for entry in manifest.get("outputs", []) if isinstance(entry, dict)}
    if roles.get(rel) == "claim_bearing_output":
        return locator
    candidate = f"runs/{run_id}/outputs/{rel}"
    if roles.get(candidate) == "claim_bearing_output":
        return f"{candidate}#{pointer}"
    return locator


def find_run(root: Path, run_id: str) -> dict[str, Any]:
    for manifest_path in sorted((root / "runs").glob("*/RUN_MANIFEST.json")):
        manifest = read_object(manifest_path)
        if str(manifest.get("run_id")) == run_id:
            return manifest
    raise SystemExit(f"no run manifest declares run_id {run_id}")


def write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temp_name = stream.name
    os.replace(temp_name, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Add or refresh one entry in results/RESULTS_INDEX.json")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--result-id")
    parser.add_argument("--run")
    parser.add_argument("--locator", help="project-relative path#/json-pointer into a claim-bearing output")
    parser.add_argument("--name")
    parser.add_argument("--unit", default="")
    parser.add_argument("--scope")
    parser.add_argument("--precision")
    parser.add_argument("--display-rounding", type=int)
    parser.add_argument("--check", action="append", default=[], help="validation check name; repeat as needed")
    parser.add_argument("--evidence-state", choices=EVIDENCE_STATES, default="supported_not_reproduced")
    parser.add_argument("--supersedes")
    parser.add_argument("--remove", help="drop this result_id from the index")
    parser.add_argument("--refresh", action="store_true", help="re-resolve every indexed value from its locator")
    parser.add_argument("--follow-lineage", action="store_true", help="re-point every result at the run that superseded the one it cites")
    args = parser.parse_args()

    root = args.project.resolve()
    if not root.is_dir():
        parser.error(f"project is not a directory: {root}")
    index_path = root / "results" / "RESULTS_INDEX.json"
    if index_path.is_file():
        index = read_object(index_path)
    else:
        index = {
            "schema_version": WORKFLOW_VERSION,
            "artifact_type": "results_index",
            "project_id": read_object(root / ".cumcm" / "state.json")["project_id"],
            "updated_at": utc_now(),
            "producer": {"kind": "script", "name": "index_result.py", "version": WORKFLOW_VERSION},
            "results": [],
        }
    results = [item for item in index.get("results", []) if isinstance(item, dict)]

    if args.remove:
        remaining = [item for item in results if str(item.get("result_id")) != args.remove]
        if len(remaining) == len(results):
            parser.error(f"no such result: {args.remove}")
        results = remaining
    elif args.follow_lineage:
        runs = all_runs(root)
        moved = 0
        for item in results:
            current = str(item.get("run_id", ""))
            newest = newest_descendant(runs, current)
            if newest == current:
                continue
            manifest = runs[newest]
            locator = str(item.get("output_locator", ""))
            live = locator.partition("#")[0]
            for prefix in (f"runs/{current}/outputs/",):
                if live.startswith(prefix):
                    live = live[len(prefix):]
            item["run_id"] = newest
            item["output_locator"] = frozen_locator(manifest, newest, f"{live}#{locator.partition('#')[2]}")
            rel, _, pointer = item["output_locator"].partition("#")
            item["value"] = resolve_pointer(read_object(root / rel), pointer)
            moved += 1
            print(f"{item['result_id']}: {current} -> {newest}")
        if not moved:
            print("no indexed result cites a superseded run")
    elif args.refresh:
        for item in results:
            locator = str(item.get("output_locator", ""))
            rel, _, pointer = locator.partition("#")
            item["value"] = resolve_pointer(read_object(root / rel), pointer)
    else:
        for required in ("result_id", "run", "locator", "name", "scope"):
            if not getattr(args, required.replace("-", "_")):
                parser.error(f"--{required.replace('_', '-')} is required when indexing a result")
        if "#" not in args.locator:
            parser.error("--locator must be path#/json-pointer")
        manifest = find_run(root, args.run)
        if manifest.get("official_run") is not True or manifest.get("exit_code") != 0 or manifest.get("status") != "completed":
            parser.error(f"{args.run} is not a successful official run; re-record it with record_run.py --official")
        roles = {str(entry.get("path")): entry.get("evidence_role") for entry in manifest.get("outputs", []) if isinstance(entry, dict)}
        probe = frozen_locator(manifest, args.run, args.locator).partition("#")[0]
        if roles.get(probe) != "claim_bearing_output":
            parser.error(f"{args.locator.partition('#')[0]} is not a claim-bearing output of {args.run}")
        locator = frozen_locator(manifest, args.run, args.locator)
        rel, _, pointer = locator.partition("#")
        if locator != args.locator:
            print(f"locator points at the frozen copy: {locator}")
        value = resolve_pointer(read_object(root / rel), pointer)
        entry = {
            "result_id": args.result_id,
            "name": args.name,
            "value": value,
            "unit": args.unit,
            "precision": args.precision,
            "display_rounding": args.display_rounding,
            "run_id": args.run,
            "output_locator": locator,
            "scope": args.scope,
            "evidence_state": args.evidence_state,
            "validation_checks": args.check,
            "supersedes": args.supersedes,
        }
        results = [item for item in results if str(item.get("result_id")) != args.result_id] + [entry]

    index["results"] = sorted(results, key=lambda item: str(item.get("result_id")))
    index["updated_at"] = utc_now()
    index["schema_version"] = WORKFLOW_VERSION
    write_atomic(index_path, index)
    print(f"results indexed: {len(index['results'])} -> {index_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
