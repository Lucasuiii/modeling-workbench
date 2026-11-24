#!/usr/bin/env python3
"""Resolve the one canonical RESULTS_INDEX -> official run -> source chain.

Every formal consumer -- the computation handoff, the independent review package
and paper->delivery -- goes through here, so "the run behind this result" means
the same thing in all of them, superseded runs included.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from fractions import Fraction
from pathlib import Path
from typing import Any

from json_pointer import resolve_json_pointer
from provenance import snapshot_matches, sha256_file


def successful_official(run: dict) -> bool:
    return run.get("official_run") is True and run.get("status") == "completed" and run.get("exit_code") == 0


def official_successors(manifests: Iterable[dict]) -> dict[str, list[str]]:
    """Only completed official children retire a parent. A fork has multiple successors."""
    children: dict[str, list[str]] = {}
    for run in manifests:
        parent = run.get("parent_run_id")
        child = run.get("run_id")
        if successful_official(run) and isinstance(parent, str) and parent.strip() and isinstance(child, str) and child and parent != child:
            children.setdefault(parent, []).append(child)
    return children


def current_descendant(children: dict[str, list[str]], run_id: str) -> str:
    seen = set()
    while run_id in children:
        if run_id in seen:
            raise ValueError(f"cycle in official run lineage at {run_id}")
        seen.add(run_id)
        candidates = sorted(children[run_id])
        if len(candidates) != 1:
            raise ValueError(f"lineage from {run_id} is ambiguous: {', '.join(candidates)}; "
                             "use --run with the result ID and locator to select a branch")
        run_id = candidates[0]
    return run_id


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def live_path_of(frozen: str) -> str | None:
    parts = frozen.split("/", 3)
    if len(parts) == 4 and parts[0] == "runs" and parts[2] in {"source", "inputs", "outputs"}:
        return parts[3]
    return None


def execution_inputs(run: dict) -> Iterator[str]:
    """Declared source and formal input paths, including historical bindings."""
    snapshot = (run.get("implementation") or {}).get("source_snapshot") or {}
    yield from snapshot.get("files", [])
    for entry in run.get("inputs", []):
        if isinstance(entry, dict) and entry.get("evidence_role") == "formal_input":
            yield entry.get("path")


def live_evidence_drift(project: Path, run: dict[str, Any]) -> list[str]:
    """Compare current source/team inputs with their preserved execution bytes.

    Strip only this run's freeze layer: an explicitly historical upstream input
    remains bound to the declared upstream snapshot, not its latest live output.
    """
    project = project.resolve()
    drifted = []
    for frozen in execution_inputs(run):
        if not isinstance(frozen, str):
            continue
        live = live_path_of(frozen)
        if not live or frozen.split("/", 3)[2] == "outputs":
            continue
        frozen_file, live_file = (project / frozen).resolve(), (project / live).resolve()
        if (not frozen_file.is_relative_to(project) or not live_file.is_relative_to(project)
                or not frozen_file.is_file() or not live_file.is_file()
                or sha256_file(live_file) != sha256_file(frozen_file)):
            drifted.append(live)
    return sorted(set(drifted))


def resolve_official_computation(project: Path, results: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return referenced successful official runs or fail on any broken formal link."""
    project = project.resolve()
    results = results or read_object(project / "results" / "RESULTS_INDEX.json")
    result_items = results.get("results")
    if not isinstance(result_items, list) or not result_items:
        raise ValueError("RESULTS_INDEX.json must contain at least one formal result")

    referenced: set[str] = set()
    for item in result_items:
        if not isinstance(item, dict) or not str(item.get("run_id", "")).strip():
            raise ValueError("every formal result must reference a run_id")
        referenced.add(str(item["run_id"]))

    manifests: dict[str, tuple[str, dict[str, Any]]] = {}
    for manifest_path in sorted((project / "runs").glob("*/RUN_MANIFEST.json")):
        rel = manifest_path.relative_to(project).as_posix()
        run = read_object(manifest_path)
        run_id = str(run.get("run_id", "")).strip()
        if not run_id:
            continue
        if run_id in manifests:
            raise ValueError(f"duplicate run_id in RUN_MANIFEST files: {run_id}")
        manifests[run_id] = (rel, run)
    superseded = official_successors(run for _, run in manifests.values())

    resolved: list[dict[str, Any]] = []
    for run_id in sorted(referenced):
        candidate = manifests.get(run_id)
        if candidate is None:
            raise ValueError(f"formal result references a missing run: {run_id}")
        manifest_path, run = candidate
        if not successful_official(run):
            raise ValueError(f"formal result references a run that is not a successful official run: {run_id}")
        if run_id in superseded:
            raise ValueError(
                f"formal result references {run_id}, which a later official run superseded; "
                "re-point it with index_result.py --follow-lineage"
            )
        implementation = run.get("implementation") if isinstance(run.get("implementation"), dict) else {}
        snapshot = implementation.get("source_snapshot")
        if not snapshot_matches(project, snapshot):
            raise ValueError(f"formal result references an official run with a missing or stale source snapshot: {run_id}")

        # All formal files matter, including inputs not directly used by a locator.
        for collection, role in (("inputs", "formal_input"), ("outputs", "claim_bearing_output")):
            entries = run.get(collection, [])
            if not isinstance(entries, list):
                raise ValueError(f"invalid {collection} in official run {run_id}")
            for entry in entries:
                if not isinstance(entry, dict):
                    raise ValueError(f"invalid file record in official run {run_id}")
                if entry.get("evidence_role") != role:
                    continue
                rel = entry.get("path")
                if not isinstance(rel, str) or not rel or Path(rel).is_absolute():
                    raise ValueError(f"formal file integrity: invalid path in {run_id}")
                target = (project / rel).resolve()
                try:
                    target.relative_to(project)
                    valid = target.is_file() and sha256_file(target) == entry.get("sha256")
                except (ValueError, OSError):
                    valid = False
                if not valid:
                    raise ValueError(f"formal file SHA256 integrity failure in {run_id}: {rel}")

        drifted = live_evidence_drift(project, run)
        if drifted:
            raise ValueError(f"current official evidence is stale in {run_id}; rerun required: {', '.join(drifted)}")

        output_roles = {
            str(entry.get("path")): entry.get("evidence_role")
            for entry in run.get("outputs", [])
            if isinstance(entry, dict) and entry.get("path")
        }
        for result in result_items:
            if not isinstance(result, dict) or str(result.get("run_id")) != run_id:
                continue
            locator = str(result.get("output_locator", ""))
            output_path = locator.split("#", 1)[0] if "#" in locator else ""
            if not output_path or output_roles.get(output_path) != "claim_bearing_output":
                raise ValueError(
                    f"formal result does not locate a claim-bearing output of official run {run_id}: "
                    f"{result.get('result_id')}"
                )

            pointer = locator.split("#", 1)[1]
            try:
                output = json.loads((project / output_path).read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ValueError(f"cannot read formal result output: {output_path}") from exc
            actual_value, found = resolve_json_pointer(output, pointer)
            if not found:
                raise ValueError(f"formal result JSON pointer does not resolve: {locator}")
            if "value" in result and result["value"] != actual_value:
                raise ValueError(f"formal result value differs from frozen output: {locator}")

        resolved.append(
            {
                "run_id": run_id,
                "manifest_path": manifest_path,
                "manifest": run,
                "source_snapshot": snapshot,
                "source_files": [str(path) for path in snapshot.get("files", [])],
                "formal_inputs": [
                    str(entry.get("path"))
                    for entry in run.get("inputs", [])
                    if isinstance(entry, dict) and entry.get("evidence_role") == "formal_input"
                ],
                "claim_bearing_outputs": [
                    str(entry.get("path"))
                    for entry in run.get("outputs", [])
                    if isinstance(entry, dict) and entry.get("evidence_role") == "claim_bearing_output"
                ],
            }
        )
    return resolved


def check_reproduction(project: Path, claim: dict, indexed: dict[str, dict]) -> None:
    """Compare claim-bound outputs from two distinct, current executions."""
    reproduction = claim.get("reproduction")
    comparisons = reproduction.get("comparisons") if isinstance(reproduction, dict) else None
    if not isinstance(comparisons, list) or not comparisons:
        raise ValueError("supply a comparison of independently indexed results")
    evidence = claim.get("evidence", {})
    cited_results = set(evidence.get("result_ids", []))
    cited_runs = set(evidence.get("run_ids", []))
    covered = set()
    for comparison in comparisons:
        first, second = (indexed[comparison[key]] for key in ("result_id", "comparison_result_id"))
        pair = [first, second]
        run_ids = {item["run_id"] for item in pair}
        result_ids = {item["result_id"] for item in pair}
        if len(run_ids) != 2 or not run_ids <= cited_runs or not result_ids <= cited_results:
            raise ValueError("cite both results and their two distinct runs in the claim")
        if first["unit"] != second["unit"] or first["scope"] != second["scope"]:
            raise ValueError("compared results must have the same unit and scope")
        resolve_official_computation(project, {"results": pair})
        values = []
        files = []
        for item in pair:
            rel, pointer = item["output_locator"].split("#", 1)
            prefix = f"runs/{item['run_id']}/outputs/"
            path = (project / rel).resolve()
            if not path.is_relative_to(project.resolve() / prefix) or not rel.startswith(prefix):
                raise ValueError("each comparison needs its own frozen output")
            value, found = resolve_json_pointer(json.loads(path.read_bytes()), pointer)
            if not found:
                raise ValueError("comparison output locator does not resolve")
            values.append(value)
            files.append(path)
        if files[0].samefile(files[1]):
            raise ValueError("the two runs share the same frozen output file")
        tolerance = comparison.get("absolute_tolerance", 0)
        if type(tolerance) not in (int, float) or Fraction(str(tolerance)) < 0:
            raise ValueError("absolute tolerance must be a finite, nonnegative number")
        if all(type(v) in (int, float) for v in values):
            # Compare serialized decimal values exactly at the tolerance boundary.
            a, b = (Fraction(str(v)) for v in values)
            matches = abs(a - b) <= Fraction(str(tolerance))
        else:
            if tolerance:
                raise ValueError("non-scalar or categorical outputs require exact comparison")
            left, right = (json.dumps(v, sort_keys=True, allow_nan=False) for v in values)
            matches = left == right
        if not matches:
            raise ValueError(f"reproduction comparison failed for {first['result_id']}")
        covered.update(result_ids)
    if covered != cited_results:
        raise ValueError("every formal result cited by a reproduced claim needs a comparison")
