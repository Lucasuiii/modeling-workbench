"""Run history, frozen evidence and indexed numerical results."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from canonical_evidence import official_successors
import evidence_json
from json_pointer import resolve_json_pointer
from provenance import snapshot_matches

from .common import (
    Finding,
    as_list,
    check_envelope,
    finding,
    item_id,
    nonempty,
    read_json,
    require_fields,
    safe_project_path,
    sha256,
)
from .contracts import EVIDENCE_STATES


def superseded_run_ids(root: Path) -> set[str]:
    """A run is superseded when a later run names it as its parent.

    Derived, never written back: stamping the old manifest would change its hash
    and stale every accepted decision that bound it.
    """
    manifests = (read_json(path)[0] for path in discover_run_manifests(root))
    return set(official_successors(m for m in manifests if isinstance(m, dict)))


def discover_run_manifests(root: Path) -> list[Path]:
    runs = root / "runs"
    return sorted(runs.glob("*/RUN_MANIFEST.json")) if runs.is_dir() else []


def check_run(data: Any, root: Path, rel_path: str, capability_ids: set[str], superseded: bool = False) -> list[Finding]:
    """Official runs carry the formal evidence burden; exploratory runs are kept but never block.

    A superseded run is history: its frozen evidence must still verify, but the
    workspace has legitimately moved on from the files it read.
    """
    findings = check_envelope(data, "run_manifest", "computation", rel_path)
    if not isinstance(data, dict):
        return findings
    official_run = data.get("official_run") is True
    # Exploratory runs exist so that Deferred Model Selection is cheap. They are
    # recorded, never trusted, and never allowed to block the formal chain.
    sev = "error" if official_run else "warning"

    structural = ("run_id", "argv", "working_directory", "started_at", "finished_at", "exit_code", "status", "official_run", "implementation", "outputs")
    # An exploratory run has no capability and no formal input yet -- that is what makes it
    # exploratory. Reporting their absence produced two warnings per exploratory run and
    # nothing actionable, which is how a checker teaches people to skim past its output.
    formal = ("purpose", "capability_ids", "inputs", "environment", "stdout_path", "stderr_path")
    if not official_run:
        formal = tuple(name for name in formal if name not in ("capability_ids", "inputs"))
    for field_name in structural:
        if data.get(field_name) in (None, "", []):
            findings.append(finding("RUN-E001", "error", "execution", "computation", rel_path, f"missing run field: {field_name}", pointer=f"/{field_name}"))
    for field_name in formal:
        if data.get(field_name) in (None, "", []):
            findings.append(finding("RUN-E001", sev, "execution", "computation", rel_path, f"missing run field: {field_name}", pointer=f"/{field_name}"))

    if official_run and (data.get("status") != "completed" or data.get("exit_code") != 0):
        findings.append(finding("RUN-E002", "error", "execution", "computation", rel_path, "official run must record completed status and exit code 0"))
    elif not official_run and (data.get("status") != "completed" or data.get("exit_code") != 0):
        findings.append(finding("RUN-W002", "info", "execution", "computation", rel_path, "exploratory run did not complete; it cannot support claims"))

    implementation = data.get("implementation")
    if not isinstance(implementation, dict):
        findings.append(finding("RUN-E017", sev, "execution", "computation", rel_path, "run lacks implementation selection and source binding"))
    else:
        language = implementation.get("selected_language")
        if language not in {"matlab", "python"}:
            findings.append(finding("RUN-E018", sev, "execution", "computation", rel_path, "selected_language must be matlab or python"))
        entry_point = safe_project_path(root, str(implementation.get("entry_point", "")).split(":", 1)[0])
        if entry_point is None or not entry_point.is_file():
            findings.append(finding("RUN-E019", sev, "execution", "computation", rel_path, "selected implementation entry point is missing"))
        snapshot = implementation.get("source_snapshot")
        if official_run and not snapshot_matches(root, snapshot):
            findings.append(finding("RUN-E021", "error", "execution", "computation", rel_path, "frozen source evidence is missing or was altered"))
        elif official_run and not superseded and isinstance(snapshot, dict):
            # The frozen copy is immutable, so staleness now means the working tree
            # moved on from the run that backs the formal results.
            from canonical_evidence import live_evidence_drift
            drifted = live_evidence_drift(root, data)
            if drifted:
                findings.append(
                    finding(
                        "RUN-E020",
                        "error",
                        "execution",
                        "computation",
                        rel_path,
                        "the working tree no longer matches this official run: " + ", ".join(sorted(drifted)),
                        remediation=f"record_run.py --rerun {data.get('run_id')} --official",
                    )
                )
        argv = [str(value).casefold() for value in as_list(data.get("argv"))]
        if language == "matlab" and argv and not any("matlab" in value for value in argv):
            findings.append(finding("RUN-E021", sev, "execution", "computation", rel_path, "MATLAB implementation is not bound to a MATLAB command"))
        if language == "python" and argv and not any("python" in value for value in argv):
            findings.append(finding("RUN-E022", sev, "execution", "computation", rel_path, "Python implementation is not bound to a Python command"))

    if official_run and not as_list(data.get("capability_ids")):
        findings.append(finding("RUN-E023", "error", "structural", "computation", rel_path, "official run must name at least one capability"))
    for capability_id in as_list(data.get("capability_ids")):
        if capability_id not in capability_ids:
            findings.append(finding("RUN-E003", sev, "structural", "computation", rel_path, f"run names unknown capability: {capability_id}", related_ids=[str(capability_id)]))

    for kind in ("inputs", "outputs"):
        required_hash_roles = {"formal_input", "claim_bearing_output"}
        allowed_roles = {"formal_input", "auxiliary_input"} if kind == "inputs" else {"claim_bearing_output", "intermediate_output", "diagnostic_output"}
        values = data.get(kind)
        if not isinstance(values, list) or (kind == "outputs" and not values):
            findings.append(finding("RUN-E004", sev, "execution", "computation", rel_path, f"{kind} must be a {'nonempty ' if kind == 'outputs' else ''}list"))
            continue
        for entry in values:
            if not isinstance(entry, dict):
                findings.append(finding("RUN-E005", sev, "structural", "computation", rel_path, f"{kind} entry must be an object"))
                continue
            file_path = safe_project_path(root, entry.get("path"))
            if file_path is None or not file_path.is_file() or file_path.stat().st_size == 0:
                findings.append(finding("RUN-E006", sev, "execution", "computation", rel_path, f"missing or empty {kind[:-1]}: {entry.get('path')}"))
                continue
            role = entry.get("evidence_role")
            if role not in allowed_roles:
                findings.append(finding("RUN-E016", sev, "structural", "computation", rel_path, f"missing or invalid evidence_role for {kind[:-1]}: {entry.get('path')}"))
                continue
            recorded_hash = entry.get("sha256")
            if role in required_hash_roles:
                if not nonempty(recorded_hash):
                    findings.append(finding("RUN-E015", sev, "execution", "computation", rel_path, f"required hash is missing for {role}: {entry.get('path')}"))
                elif recorded_hash != sha256(file_path):
                    # Inputs are hashed in place, so a superseded run legitimately
                    # points at material the workspace has since regenerated.
                    drift_sev = "warning" if (superseded and kind == "inputs") else sev
                    findings.append(finding("RUN-E007", drift_sev, "execution", "computation", rel_path, f"hash mismatch for {kind[:-1]}: {entry.get('path')}"))
            elif nonempty(recorded_hash) and recorded_hash != sha256(file_path):
                findings.append(finding("RUN-W007", "warning", "execution", "computation", rel_path, f"optional hash is stale for {role}: {entry.get('path')}"))
            if entry.get("size") is not None and entry.get("size") != file_path.stat().st_size:
                findings.append(finding("RUN-W013", "warning", "execution", "computation", rel_path, f"size metadata is stale for {kind[:-1]}; run refresh_evidence.py: {entry.get('path')}"))

    for log_name in ("stdout_path", "stderr_path"):
        log_path = safe_project_path(root, data.get(log_name))
        if log_path is None or not log_path.is_file():
            findings.append(finding("RUN-E012", sev, "execution", "computation", rel_path, f"missing recorded log: {data.get(log_name)}"))

    assertions = data.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        if official_run:
            findings.append(finding("RUN-W001", "warning", "numerical", "computation", rel_path, "official run records no assertions"))
    if isinstance(assertions, list) and assertions and official_run and not any(isinstance(item, dict) and item.get("source") == "recorded" for item in assertions):
        findings.append(
            finding(
                "RUN-W003",
                "warning",
                "numerical",
                "computation",
                rel_path,
                "every assertion on this official run was declared on the command line, not recorded by the run",
                remediation="have the program write its own verdicts and pass them with record_run.py --assert-file",
            )
        )
    # Independent of the one above: an official run whose assertions are all declared AND
    # one of them failed used to report only the provenance warning, because these were
    # branches of one chain. A failed check must be reported whoever wrote the verdict.
    failed_assertions = [
        (index, item) for index, item in enumerate(assertions, 1)
        if isinstance(item, dict) and item.get("passed") is not True
    ] if isinstance(assertions, list) else []
    if failed_assertions:
        # A failed assertion inside an exploratory run is a finding about the experiment,
        # not about the formal chain, so it never blocks.
        labels = []
        for index, item in failed_assertions:
            name = item.get("name")
            safe_name = ""
            if isinstance(name, str):
                safe_name = "".join(char if char.isprintable() else "?" for char in name.strip())[:80]
            labels.append(f"#{index} ({safe_name or 'unnamed'})")
        findings.append(finding("RUN-E008", sev, "numerical", "computation", rel_path,
                                "failed assertions: " + ", ".join(labels)))
    return findings




def check_results(
    data: Any,
    root: Path,
    run_ids: set[str],
    official_run_ids: set[str],
    run_output_roles: dict[str, dict[str, str]],
    path: str,
    superseded_ids: set[str] | None = None,
) -> list[Finding]:
    superseded_ids = superseded_ids or set()
    findings = check_envelope(data, "results_index", "computation", path)
    if not isinstance(data, dict):
        return findings
    if as_list(data.get("results")):
        from canonical_evidence import resolve_official_computation
        try:
            resolve_official_computation(root, data)
        except (ValueError, OSError) as exc:
            findings.append(finding("RESULT-E018", "error", "execution", "computation", path,
                                    f"current official evidence is invalid: {exc}"))
    results = data.get("results")
    findings.extend(require_fields(results, ("name", "unit", "run_id", "output_locator", "scope", "evidence_state"), ("result_id",), "RESULT", "computation", path))
    for result in as_list(results):
        if not isinstance(result, dict):
            continue
        ident = item_id(result, "result_id")
        if result.get("run_id") not in run_ids:
            findings.append(finding("RESULT-E006", "error", "execution", "computation", path, f"{ident} names unknown run: {result.get('run_id')}", related_ids=[ident]))
        elif result.get("run_id") not in official_run_ids:
            findings.append(finding("RESULT-E016", "error", "execution", "computation", path, f"{ident} must reference a successful official run", related_ids=[ident]))
        elif str(result.get("run_id")) in superseded_ids:
            findings.append(
                finding(
                    "RESULT-E017",
                    "error",
                    "execution",
                    "computation",
                    path,
                    f"{ident} still cites {result.get('run_id')}, which a later run superseded",
                    related_ids=[ident, str(result.get("run_id"))],
                    remediation="index_result.py --follow-lineage, or say why the earlier run is the one you mean",
                )
            )
        if result.get("evidence_state") not in EVIDENCE_STATES:
            findings.append(finding("RESULT-E007", "error", "structural", "computation", path, f"{ident} has invalid evidence_state", related_ids=[ident]))
        locator = result.get("output_locator")
        if not nonempty(locator) or "#" not in locator:
            findings.append(finding("RESULT-E008", "error", "execution", "computation", path, f"{ident} output_locator must be path#JSON-pointer", related_ids=[ident]))
            continue
        rel, pointer = locator.split("#", 1)
        run_id = result.get("run_id")
        declared_outputs = run_output_roles.get(str(run_id), {})
        if rel not in declared_outputs:
            findings.append(finding("RESULT-E014", "error", "execution", "computation", path, f"{ident} locator is not a declared output of run {run_id}: {rel}", related_ids=[ident, str(run_id)]))
        elif declared_outputs[rel] != "claim_bearing_output":
            findings.append(finding("RESULT-E015", "error", "execution", "computation", path, f"{ident} locator must reference a claim_bearing_output: {rel}", related_ids=[ident, str(run_id)]))
        output_path = safe_project_path(root, rel)
        if output_path is None or not output_path.is_file():
            findings.append(finding("RESULT-E009", "error", "execution", "computation", path, f"{ident} output file is missing: {rel}", related_ids=[ident]))
            continue
        output_data, error = read_json(output_path, exact=True)
        if error:
            findings.append(finding("RESULT-E010", "error", "execution", "computation", path, f"{ident} output is not readable JSON: {error}", related_ids=[ident]))
            continue
        stored_value, found = resolve_json_pointer(output_data, pointer)
        if not found:
            findings.append(finding("RESULT-E011", "error", "execution", "computation", path, f"{ident} JSON pointer does not resolve: {pointer}", related_ids=[ident]))
        elif "value" in result and not evidence_json.equal(result["value"], stored_value):
            findings.append(finding("RESULT-E012", "error", "numerical", "computation", path, f"{ident} indexed value differs from executed output", related_ids=[ident]))
    return findings
