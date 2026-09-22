#!/usr/bin/env python3
"""Answer the only question that matters after a change: what must be redone?

The expensive work in a contest is re-running computation, re-doing an independent
review and re-writing paper sections -- not re-reading JSON. So this walks the
existing ID graph

    official source -> fact -> capability -> model
    source file     -> official run -> result -> claim -> paper section -> PDF

backwards from the changed files and names the specific runs, findings and
sections that are actually affected. It never suppresses a check; cumcm_check.py
still validates everything.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

STAGE_ORDER = ["intake", "problem-analysis", "model-design", "computation", "validation", "paper", "delivery"]


def read(root: Path, rel: str) -> dict[str, Any]:
    path = root / rel
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def live_path_of(frozen: str) -> str | None:
    """runs/<id>/source/code/solve.py -> code/solve.py (None if not a frozen path)."""
    parts = frozen.split("/")
    if len(parts) > 3 and parts[0] == "runs" and parts[2] in {"source", "outputs", "inputs"}:
        return "/".join(parts[3:])
    return None


def normalize_changed_path(root: Path, value: str) -> str:
    declared = value.strip()
    candidate = Path(declared)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(f"changed path resolves outside project: {value}") from exc


def build_plan(root: Path, changed: list[str]) -> dict[str, Any]:
    root = root.resolve()
    changed_set = {normalize_changed_path(root, path) for path in changed if path.strip()}
    sources = read(root, "problem/SOURCE_MANIFEST.json")
    facts = read(root, "analysis/PROBLEM_FACTS.json")
    capabilities = read(root, "analysis/TASK_CAPABILITIES.json")
    model = read(root, "model/MODEL_CONTRACT.json")
    results_index = read(root, "results/RESULTS_INDEX.json")
    claims = read(root, "validation/CLAIM_LEDGER.json")
    review = read(root, "validation/INDEPENDENT_REVIEW_RESULT.json")
    plan = read(root, "paper/PAPER_PLAN.json")
    latex = read(root, "paper/LATEX_TEMPLATE_MANIFEST.json")
    receipt = read(root, "delivery/COMPILE_RECEIPT.json")

    actions: dict[str, list[str]] = {stage: [] for stage in STAGE_ORDER}
    unaffected: dict[str, list[str]] = {stage: [] for stage in STAGE_ORDER}

    # --- official sources -------------------------------------------------
    touched_sources = {
        str(item.get("source_id"))
        for item in as_list(sources.get("sources"))
        if isinstance(item, dict) and str(item.get("path")) in changed_set
    }
    fact_items = [item for item in as_list(facts.get("facts")) if isinstance(item, dict)]
    all_facts = {str(item.get("fact_id") or item.get("id")) for item in fact_items}
    stale_facts = {
        str(item.get("fact_id") or item.get("id"))
        for item in fact_items
        if str(item.get("source_id")) in touched_sources
    }
    # A touched official source without a complete source_id -> fact edge is
    # ambiguous. Invalidation planning must fail conservative, not miss work.
    mapped_sources = {str(item.get("source_id")) for item in fact_items}
    if touched_sources - mapped_sources:
        stale_facts = set(all_facts)
    if touched_sources:
        actions["intake"].append(f"re-verify official inventory for {', '.join(sorted(touched_sources))}")
        if stale_facts:
            actions["problem-analysis"].append(f"re-extract facts: {', '.join(sorted(stale_facts))}")
        else:
            actions["problem-analysis"].append("re-extract facts affected by the changed official source")

    capability_items = [item for item in as_list(capabilities.get("capabilities")) if isinstance(item, dict)]
    all_capabilities = {str(item.get("capability_id")) for item in capability_items}
    stale_capabilities = {
        str(item.get("capability_id"))
        for item in capability_items
        if {str(value) for value in as_list(item.get("fact_ids"))} & stale_facts
    }
    mapped_facts = set().union(
        *({str(value) for value in as_list(item.get("fact_ids"))} for item in capability_items),
        set(),
    )
    if stale_facts - mapped_facts:
        stale_capabilities = set(all_capabilities)
    if touched_sources:
        detail = ", ".join(sorted(stale_capabilities)) or "all capabilities with unresolved source dependencies"
        actions["problem-analysis"].append(f"re-derive capabilities: {detail}")

    model_changed = "model/MODEL_CONTRACT.json" in changed_set
    model_items = [item for item in as_list(model.get("components")) if isinstance(item, dict)]
    all_models = {str(item.get("model_id")) for item in model_items}
    stale_models = {
        str(item.get("model_id"))
        for item in model_items
        if {str(value) for value in as_list(item.get("capability_ids"))} & stale_capabilities
        or {str(value) for value in as_list(item.get("inputs"))} & (touched_sources | stale_facts)
    }
    if model_changed:
        stale_models = set(all_models)
        actions["model-design"].append("re-review changed model contract and its downstream evidence")
    mapped_capabilities = set().union(
        *({str(value) for value in as_list(item.get("capability_ids"))} for item in model_items),
        set(),
    )
    if stale_capabilities - mapped_capabilities:
        stale_models = set(all_models)
    if touched_sources:
        detail = ", ".join(sorted(stale_models)) or "all models with unresolved capability dependencies"
        actions["model-design"].append(f"re-evaluate models: {detail}")

    # --- runs whose recorded source tree or formal inputs moved -----------
    stale_runs: set[str] = set()
    official_runs: dict[str, dict[str, Any]] = {}
    manifests: list[dict[str, Any]] = []
    for manifest_path in sorted((root / "runs").glob("*/RUN_MANIFEST.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(manifest, dict):
            manifests.append(manifest)
    # A superseded run is history. Never propose re-running it.
    superseded = {
        str(m.get("parent_run_id")) for m in manifests
        if str(m.get("parent_run_id", "")).strip() and str(m.get("parent_run_id")) != str(m.get("run_id"))
        and m.get("official_run") is True and m.get("status") == "completed" and m.get("exit_code") == 0
    }
    for manifest in manifests:
        if manifest.get("official_run") is not True or str(manifest.get("run_id")) in superseded:
            continue
        run_id = str(manifest.get("run_id"))
        official_runs[run_id] = manifest
        snapshot = manifest.get("implementation", {}).get("source_snapshot", {})
        # Source is frozen inside the run directory, so watch the live counterpart:
        # runs/<id>/source/code/solve.py is evidence for code/solve.py.
        watched = set()
        for value in as_list(snapshot.get("files")):
            watched.add(str(value))
            live = live_path_of(str(value))
            if live:
                watched.add(live)
        for entry in as_list(manifest.get("inputs")):
            if not isinstance(entry, dict) or entry.get("evidence_role") != "formal_input":
                continue
            watched.add(str(entry.get("path")))
            live = live_path_of(str(entry.get("path")))
            if live:
                watched.add(live)
        if watched & changed_set:
            stale_runs.add(run_id)
    stale_candidate_ids = {
        str(candidate.get("candidate_id"))
        for component in model_items
        if str(component.get("model_id")) in stale_models
        for candidate in as_list(component.get("candidates"))
        if isinstance(candidate, dict)
    }
    upstream_runs = {
        run_id
        for run_id, manifest in official_runs.items()
        if {str(value) for value in as_list(manifest.get("capability_ids"))} & stale_capabilities
        or {str(value) for value in as_list(manifest.get("candidate_ids"))} & stale_candidate_ids
    }
    if touched_sources and official_runs and not upstream_runs and not stale_runs:
        upstream_runs = set(official_runs)
    if model_changed:
        upstream_runs.update(official_runs)
    stale_runs.update(upstream_runs)
    # Propagate along declared output -> formal input edges, including frozen
    # copies. A historical input requires an explicit binding decision, not a
    # blind rerun with the old arguments.
    def aliases(path: str) -> set[str]:
        result = {path}
        while live := live_path_of(path):
            result.add(live)
            path = live
        return result

    inputs = {
        rid: set().union(*(aliases(str(e.get("path"))) for e in as_list(m.get("inputs"))
                          if isinstance(e, dict) and e.get("evidence_role") == "formal_input"), set())
        for rid, m in official_runs.items()
    }
    outputs = {
        rid: set().union(*(aliases(str(e.get("path"))) for e in as_list(m.get("outputs"))
                          if isinstance(e, dict)), set())
        for rid, m in official_runs.items()
    }
    dependent_runs: set[str] = set()
    while True:
        affected_outputs = set().union(*(outputs[rid] for rid in stale_runs), set())
        newly_stale = {rid for rid in official_runs if rid not in stale_runs and inputs[rid] & affected_outputs}
        if not newly_stale:
            break
        dependent_runs.update(newly_stale)
        stale_runs.update(newly_stale)
    for run_id in sorted(dependent_runs):
        actions["computation"].append(
            f"refresh input bindings for {run_id} after upstream successors exist; "
            "review intentional historical inputs and do not blindly reuse frozen parent inputs"
        )
    for run_id in sorted(stale_runs):
        actions["computation"].append(f"re-run {run_id}: record_run.py --rerun {run_id} --official (appends a successor)")
    for run_id in sorted(set(official_runs) - stale_runs):
        unaffected["computation"].append(run_id)

    # --- results, claims, sections ---------------------------------------
    result_items = [item for item in as_list(results_index.get("results")) if isinstance(item, dict)]
    capability_result_ids = set().union(
        *(
            {str(value) for value in as_list(item.get("result_ids"))}
            for item in capability_items
            if str(item.get("capability_id")) in stale_capabilities
        ),
        set(),
    )
    stale_results = {
        str(item.get("result_id"))
        for item in result_items
        if str(item.get("run_id")) in stale_runs or str(item.get("result_id")) in capability_result_ids
    }
    if touched_sources and result_items and not stale_results:
        stale_results = {str(item.get("result_id")) for item in result_items}
    if "results/RESULTS_INDEX.json" in changed_set:
        stale_results.update(str(item.get("result_id")) for item in result_items)
        actions["validation"].append("re-review changed results index and rebuild dependent evidence")
    lineage_results = {str(item.get("result_id")) for item in result_items
                       if str(item.get("run_id")) in stale_runs | superseded}
    if lineage_results:
        actions["computation"].append(
            f"after successful successors exist, re-point results: index_result.py --follow-lineage ({', '.join(sorted(lineage_results))})"
        )
    if stale_results - lineage_results or "results/RESULTS_INDEX.json" in changed_set:
        actions["computation"].append("revalidate/reindex dependent results against their current official runs and locators; refresh values only after evidence validation")

    claim_items = [item for item in as_list(claims.get("claims")) if isinstance(item, dict)]
    stale_claims: set[str] = set()
    for claim in claim_items:
        evidence = claim.get("evidence") if isinstance(claim.get("evidence"), dict) else {}
        touched = {str(value) for value in as_list(evidence.get("result_ids"))} & stale_results
        touched |= {str(value) for value in as_list(evidence.get("run_ids"))} & stale_runs
        touched |= {str(value) for value in as_list(evidence.get("fact_ids"))} & stale_facts
        touched |= {str(value) for value in as_list(evidence.get("model_ids"))} & stale_models
        if touched:
            stale_claims.add(str(claim.get("claim_id")))
    if touched_sources and claim_items and not stale_claims:
        stale_claims = {str(item.get("claim_id")) for item in claim_items}
    if "validation/CLAIM_LEDGER.json" in changed_set or "results/RESULTS_INDEX.json" in changed_set:
        stale_claims.update(str(item.get("claim_id")) for item in claim_items)
    if stale_claims:
        actions["validation"].append(f"re-establish evidence for claims: {', '.join(sorted(stale_claims))}")

    findings = [item for item in as_list(review.get("findings")) if isinstance(item, dict)]
    targeted = sorted(
        str(item.get("finding_id"))
        for item in findings
        if (stale_results | stale_runs | stale_claims)
        & {token.strip(" ,;()") for token in str(item.get("location", "")).replace("#", " ").split()}
    )
    if stale_runs or stale_claims:
        if targeted:
            actions["validation"].append(f"targeted re-review covers: {', '.join(targeted)}")
        actions["validation"].append("rebuild the package: build_independent_review_package.py --review-mode auto --refresh")
        untouched = sorted({str(item.get("finding_id")) for item in findings} - set(targeted))
        if untouched:
            unaffected["validation"].extend(untouched)

    section_files: dict[str, set[str]] = {}
    for item in as_list(latex.get("subproblem_sections")):
        if isinstance(item, dict):
            section_files.setdefault(str(item.get("subproblem_id")), set()).add(str(item.get("path")))
    section_paths: dict[str, set[str]] = {}
    for item in as_list(latex.get("section_paths")):
        if isinstance(item, dict):
            section_paths.setdefault(str(item.get("section_id")), set()).add(str(item.get("path")))
    all_sections = set(as_list(latex.get("section_files"))) | set().union(*section_files.values(), set())
    stale_sections: set[str] = set()
    incomplete = False
    for section in as_list(plan.get("paper_structure")):
        if not isinstance(section, dict):
            continue
        if {str(value) for value in as_list(section.get("claim_ids"))} & stale_claims:
            paths = section_paths.get(str(section.get("section_id")), set())
            if len(paths) == 1 and paths.issubset(all_sections):
                stale_sections.update(paths)
            else:
                subproblems = as_list(section.get("subproblem_ids"))
                if not paths and subproblems and all(str(s) in section_files for s in subproblems):
                    stale_sections.update(set().union(*(section_files[str(s)] for s in subproblems)))
                else:
                    # No trustworthy edge for this section: include all declared
                    # sections, even when another stale section was mapped.
                    incomplete = True
    if stale_claims and (incomplete or not stale_sections):
        stale_sections.update(all_sections)
    paper_contract_changed = bool(changed_set & {"paper/PAPER_PLAN.json", "paper/LATEX_TEMPLATE_MANIFEST.json"})
    if paper_contract_changed or "validation/CLAIM_LEDGER.json" in changed_set:
        stale_sections.update(all_sections)
        actions["paper"].append("re-review all sections and rebuild paper handoff after contract change")
    changed_tex = sorted(path for path in changed_set if path.endswith((".tex", ".bib")))
    for path in changed_tex:
        stale_sections.add(path)
    if stale_sections:
        actions["paper"].append(f"rewrite or re-review: {', '.join(sorted(stale_sections))}")
    elif stale_claims:
        actions["paper"].append("rewrite or re-review all paper sections whose dependency mapping is incomplete")
    untouched_sections = sorted(all_sections - stale_sections)
    if untouched_sections:
        unaffected["paper"].extend(untouched_sections)

    compile_inputs = set(as_list(receipt.get("source_snapshot", {}).get("files")))
    if stale_sections or stale_claims or stale_runs or stale_models or changed_tex or compile_inputs & changed_set or changed_set & {"model/MODEL_CONTRACT.json", "results/RESULTS_INDEX.json", "validation/CLAIM_LEDGER.json", "paper/PAPER_PLAN.json", "paper/LATEX_TEMPLATE_MANIFEST.json"}:
        actions["delivery"].append("recompile and rebind: record_compile.py --update-quality")
        if receipt:
            actions["delivery"].append("the previous PDF/source binding is void until the recompile succeeds")

    return {
        "changed_paths": sorted(changed_set),
        "stale_facts": sorted(stale_facts),
        "stale_capabilities": sorted(stale_capabilities),
        "stale_models": sorted(stale_models),
        "stale_official_runs": sorted(stale_runs),
        "stale_results": sorted(stale_results),
        "stale_claims": sorted(stale_claims),
        "stale_sections": sorted(stale_sections),
        "actions": {stage: actions[stage] for stage in STAGE_ORDER if actions[stage]},
        "unaffected": {stage: sorted(set(unaffected[stage])) for stage in STAGE_ORDER if unaffected[stage]},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="List the work a change actually invalidates")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--changed", action="append", default=[], required=True, help="project-relative changed path; repeat as needed")
    parser.add_argument("--json", action="store_true", help="print the machine-readable plan only")
    args = parser.parse_args()
    root = args.project.resolve()
    if not root.is_dir():
        parser.error(f"project is not a directory: {root}")
    try:
        plan = build_plan(root, args.changed)
    except ValueError as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    print("changed: " + ", ".join(plan["changed_paths"]))
    if not plan["actions"]:
        print("nothing downstream is invalidated by these paths")
    for stage, items in plan["actions"].items():
        print(f"\n{stage}")
        for item in items:
            print(f"  - {item}")
    if plan["unaffected"]:
        print("\nnot affected (do not redo):")
        for stage, items in plan["unaffected"].items():
            print(f"  {stage}: {', '.join(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
