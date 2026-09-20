"""Shared synthetic workflow fixtures; approvals here are test data only."""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".agents/skills/cumcm-workflow/scripts"
sys.path.insert(0, str(SCRIPTS))
from provenance import digest_records, tree_snapshot

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def review(decision: str = "accepted") -> dict:
    return {
        "decision": decision,
        "reviewer": "fixture-reviewer" if decision != "unreviewed" else None,
        "reviewed_at": "2026-08-30T12:00:00Z" if decision != "unreviewed" else None,
        "scope": "fixture",
        "notes": None,
    }


def envelope(kind: str) -> dict:
    return {
        "schema_version": "0.6.0",
        "artifact_type": kind,
        "project_id": "SYNTHETIC-2024-B",
        "updated_at": "2026-08-30T12:00:00Z",
        "producer": {"kind": "script", "name": "test-fixture", "version": "0.6.0"},
    }


def write_json(root: Path, rel: str, data: dict) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_accepted_snapshot(root: Path, stage: str, paths: list[str]) -> None:
    """Synthetic accepted review; tests of the recorder itself use the real CLI."""
    records = [{"path": rel, "sha256": digest((root / rel).read_bytes())} for rel in paths]
    write_json(root, f".cumcm/snapshots/{stage}.json", {
        "snapshot_version": "0.6.0", "stage": stage, "decision": "accepted",
        "decision_id": f"FIXTURE-{stage}", "artifacts": records,
        "snapshot_digest": digest_records(records),
    })


def build_valid_project(root: Path) -> None:
    source_bytes = b"synthetic problem statement"
    source_path = root / "problem" / "official" / "problem.txt"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(source_bytes)

    code_path = root / "code" / "solve.py"
    code_path.parent.mkdir()
    code_path.write_text("print('synthetic')\n", encoding="utf-8")
    # v0.6 freezes the executed source into the run directory; the live file stays
    # where it is so the checker can spot the working tree drifting away from it.
    frozen_code = root / "runs" / "RUN-Q1-001" / "source" / "code" / "solve.py"
    frozen_code.parent.mkdir(parents=True)
    frozen_code.write_text("print('synthetic')\n", encoding="utf-8")

    output = {"restricted_policy_cost": 12.5}
    output_bytes = (json.dumps(output) + "\n").encode()
    output_path = root / "runs" / "RUN-Q1-001" / "outputs" / "result.json"
    output_path.parent.mkdir(parents=True)
    output_path.write_bytes(output_bytes)
    stdout_path = root / "runs" / "RUN-Q1-001" / "stdout.log"
    stderr_path = root / "runs" / "RUN-Q1-001" / "stderr.log"
    stdout_path.write_text("synthetic run complete\n", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")

    figure_bytes = b"synthetic figure bytes"
    figure_path = root / "figures" / "policy-cost.png"
    figure_path.parent.mkdir()
    figure_path.write_bytes(figure_bytes)

    paper_bytes = b"synthetic pdf bytes"
    paper_path = root / "paper" / "paper.pdf"
    paper_path.parent.mkdir()
    paper_path.write_bytes(paper_bytes)
    compile_log = root / "paper" / "compile.log"
    compile_log.write_text("compile succeeded\n", encoding="utf-8")

    state = envelope("workflow_state")
    state.update(
        {
            "workflow_version": "0.6.0",
            "mode": "working",
            "implementation": {"preferred": "matlab", "fallback": "python", "selection": "auto"},
            "current_stage": "validation",
            "stages": {
                "intake": "passed",
                "problem-analysis": "passed",
                "model-design": "passed",
                "computation": "passed",
                "validation": "passed",
                "paper": "not_started",
                "delivery": "not_started",
            },
        }
    )
    write_json(root, ".cumcm/state.json", state)

    sources = envelope("source_manifest")
    sources["sources"] = [
        {
            "source_id": "SRC-001",
            "path": "problem/official/problem.txt",
            "sha256": digest(source_bytes),
            "size": len(source_bytes),
            "media_type": "text/plain",
            "origin": "official",
            "acquisition": {"method": "user_local_file", "provided_by_user": True, "source_reference": None},
            "authoritative_for": ["FACT-Q1-001"],
            "derived_from": None,
            "mutable": False,
        }
    ]
    write_json(root, "problem/SOURCE_MANIFEST.json", sources)

    facts = envelope("problem_facts")
    facts.update(
        {
            "subproblems": [
                {
                    "subproblem_id": "Q1",
                    "request": "Optimize within a declared fixed policy class.",
                    "expected_output": "Restricted-class minimum cost",
                }
            ],
            "facts": [
                {
                    "fact_id": "FACT-Q1-001",
                    "statement": "The fixture uses a synthetic fixed policy class.",
                    "source_id": "SRC-001",
                    "location": "line 1",
                    "raw_value": "fixed",
                    "normalized_value": "fixed",
                    "unit": None,
                    "extraction_method": "native_text",
                    "render_verified": True,
                }
            ],
            "definitions": [],
            "ambiguities": [],
            "assumptions": [],
        }
    )
    write_json(root, "analysis/PROBLEM_FACTS.json", facts)

    capabilities = envelope("task_capabilities")
    capabilities["capabilities"] = [
        {
            "capability_id": "CAP-Q1-001",
            "subproblem_id": "Q1",
            "objective": "Enumerate the fixed policy class.",
            "required_output": "Minimum cost in that class",
            "fact_ids": ["FACT-Q1-001"],
            "acceptance_checks": [{
                "check_id": "ACC-Q1-001", "judge": "recorded", "assertion_name": "enumeration_covers_policy_class",
                "assertion": "the enumerated count equals the class cardinality; fewer means a policy was skipped",
            }],
            "model_ids": ["MODEL-Q1-001"],
            "code_entry_points": ["code/solve.py:main"],
            "result_ids": ["RES-Q1-001"],
            "lifecycle_state": "validated",
            "blocking_issues": [],
        }
    ]
    write_json(root, "analysis/TASK_CAPABILITIES.json", capabilities)

    model = envelope("model_contract")
    model["selection_check"] = {
        "decision": "accepted",
        "reviewer": "fixture-user",
        "reviewed_at": "2026-08-30T12:00:00Z",
        "reviewer_kind": "human_user",
        "presented_candidate_ids": ["CAND-Q1-ENUM", "CAND-Q1-DP"],
        "notes": "Both candidates and the discriminating evidence were shown before the choice.",
    }
    model["components"] = [
        {
            "model_id": "MODEL-Q1-001",
            "capability_ids": ["CAP-Q1-001"],
            "variables": [{"name": "policy", "domain": "finite fixed class"}],
            "inputs": ["SRC-001"],
            "outputs": ["RES-Q1-001"],
            "method": "complete enumeration",
            "scope": "fixed homogeneous policies only; excludes feedback policies",
            "verification_plan": ["compare enumerated count with class cardinality"],
            "candidates": [
                {
                    "candidate_id": "CAND-Q1-ENUM", "method": "complete enumeration",
                    "why_considered": "the declared policy class is finite and small",
                    "discriminating_evidence": ["cost of the best fixed policy versus the dynamic-program bound"],
                    "status": "selected", "evaluation_run_ids": ["RUN-Q1-001"],
                    "decision_rationale": "enumeration reaches the same cost as the bound at a fraction of the runtime",
                },
                {
                    "candidate_id": "CAND-Q1-DP", "method": "feedback-policy dynamic program",
                    "why_considered": "feedback policies could in principle beat any fixed policy",
                    "discriminating_evidence": ["whether the DP value is strictly below the enumerated minimum"],
                    "status": "rejected", "evaluation_run_ids": ["RUN-Q1-001"],
                    "decision_rationale": "the DP value matched the enumerated minimum, so feedback buys nothing here",
                },
            ],
            "strong_claims": [],
        }
    ]
    write_json(root, "model/MODEL_CONTRACT.json", model)

    cross = envelope("cross_question_ledger")
    cross["shared_items"] = []
    write_json(root, "model/CROSS_QUESTION_LEDGER.json", cross)

    run = envelope("run_manifest")
    run.update(
        {
            "run_id": "RUN-Q1-001",
            "purpose": "synthetic restricted-policy regression",
            "subproblem_id": "Q1",
            "capability_ids": ["CAP-Q1-001"],
            "candidate_ids": ["CAND-Q1-ENUM", "CAND-Q1-DP"],
            "argv": ["python3", "code/solve.py"],
            "working_directory": ".",
            "started_at": "2026-08-30T12:00:00Z",
            "finished_at": "2026-08-30T12:00:01Z",
            "exit_code": 0,
            "status": "completed",
            "official_run": True,
            "implementation": {
                "selected_language": "python",
                "selection_rationale": "existing Python fixture is the simplest reliable implementation",
                "entry_point": "runs/RUN-Q1-001/source/code/solve.py",
                "runtime": "Python 3 fixture",
                "dependencies": [],
                "matlab_toolboxes": [],
                "fallback_from": None,
                "source_snapshot": tree_snapshot(root, ["runs/RUN-Q1-001/source/code/solve.py"]),
            },
            "inputs": [
                {
                    "path": "problem/official/problem.txt",
                    "evidence_role": "formal_input",
                    "sha256": digest(source_bytes),
                    "size": len(source_bytes),
                    "media_type": "text/plain",
                }
            ],
            "outputs": [
                {
                    "path": "runs/RUN-Q1-001/outputs/result.json",
                    "evidence_role": "claim_bearing_output",
                    "sha256": digest(output_bytes),
                    "size": len(output_bytes),
                    "media_type": "application/json",
                }
            ],
            "environment": {"python": "3.x", "platform": "synthetic"},
            "stdout_path": "runs/RUN-Q1-001/stdout.log",
            "stderr_path": "runs/RUN-Q1-001/stderr.log",
            "assertions": [
                {"name": "enumeration coverage", "passed": True, "source": "recorded"},
                {"name": "enumeration_covers_policy_class", "passed": True, "source": "recorded"},
            ],
            "parent_run_id": None,
        }
    )
    write_json(root, "runs/RUN-Q1-001/RUN_MANIFEST.json", run)

    results = envelope("results_index")
    results["results"] = [
        {
            "result_id": "RES-Q1-001",
            "name": "Restricted policy minimum cost",
            "value": 12.5,
            "unit": "synthetic_cost",
            "precision": 0.1,
            "display_rounding": 1,
            "run_id": "RUN-Q1-001",
            "output_locator": "runs/RUN-Q1-001/outputs/result.json#/restricted_policy_cost",
            "scope": "fixed homogeneous policies only",
            "evidence_state": "supported_not_reproduced",
            "validation_checks": ["enumeration coverage"],
            "supersedes": None,
        }
    ]
    write_json(root, "results/RESULTS_INDEX.json", results)

    package_dir = root / "validation" / "independent-review-package"
    package_dir.mkdir(parents=True)
    package_materials = {
        "official.txt": ("official_input", b"official"),
        "problem.json": ("problem_contract", b"{}"),
        "model.json": ("model_contract", b"{}"),
        "solve.py": ("computation_source", b"print('review')\n"),
        "run.json": ("run_record", b"{}"),
        "output.json": ("executed_output", b"{}"),
        "SKILL.md": ("review_instruction", b"# reviewer skill\n"),
    }
    package_files = []
    for name, (role, payload) in package_materials.items():
        target = package_dir / name
        target.write_bytes(payload)
        package_files.append({"path": f"validation/independent-review-package/{name}", "role": role, "size": len(payload), "sha256": digest(payload)})
    (package_dir / "REVIEW_REQUEST.md").write_text("# Review request\n", encoding="utf-8")
    request_bytes = (package_dir / "REVIEW_REQUEST.md").read_bytes()
    package_files.append({"path": "validation/independent-review-package/REVIEW_REQUEST.md", "role": "review_instruction", "size": len(request_bytes), "sha256": digest(request_bytes)})
    package_digest = digest_records(package_files)
    independent_package = envelope("independent_review_package")
    independent_package.update(
        {
            "package_root": "validation/independent-review-package",
            "review_skill_path": "validation/independent-review-package/SKILL.md",
            "review_request_path": "validation/independent-review-package/REVIEW_REQUEST.md",
            "review_mode": "full",
            "previous_review_path": None,
            "target_finding_ids": [],
            "upstream_digest": "0" * 64,
            "package_digest": package_digest,
            "context_excluded": ["debug_history", "failed_runs", "originating_task_transcript", "prior_review_prose"],
            "files": package_files,
            "reviewer_selection": {
                "status": "recorded",
                "reviewer": "fixture-reviewer",
                "model": "fixture-model",
                "originating_task_ref": "fixture-origin-task",
                "task_ref": "fixture-independent-task",
            },
        }
    )
    write_json(root, "validation/independent-review-package/REVIEW_PACKAGE_MANIFEST.json", independent_package)
    (root / "validation" / "INDEPENDENT_REVIEW_RAW.md").write_text("# Independent review\nNo P0 findings.\n", encoding="utf-8")
    independent_result = envelope("independent_review_result")
    independent_result.update(
        {
            "review_id": "REVIEW-001",
            "package_manifest_path": "validation/independent-review-package/REVIEW_PACKAGE_MANIFEST.json",
            "package_digest": package_digest,
            "review_mode": "full",
            "previous_review_path": None,
            "target_finding_ids": [],
            "reviewer_context": {
                "reviewer_kind": "different_model",
                "reviewer": "fixture-reviewer",
                "model": "fixture-model",
                "task_ref": "fixture-independent-task",
                "different_conversation": True,
                "independence_grade": "independent",
            },
            "verdict": "accepted",
            "findings": [],
            "raw_review_path": "validation/INDEPENDENT_REVIEW_RAW.md",
            "reviewed_files": ["problem/official/problem.txt", "code/solve.py"],
        }
    )
    write_json(root, "validation/INDEPENDENT_REVIEW_RESULT.json", independent_result)

    figures = envelope("figure_manifest")
    figures["figures"] = [
        {
            "figure_id": "FIG-Q1-001",
            "kind": "quantitative",
            "purpose": "Show the restricted-class comparison.",
            "path": "figures/policy-cost.png",
            "sha256": digest(figure_bytes),
            "result_ids": ["RES-Q1-001"],
            "run_ids": ["RUN-Q1-001"],
            "caption_claims": ["Restricted-class comparison only."],
            "paper_location": "Results",
            "visual_review": review(),
        }
    ]
    write_json(root, "figures/FIGURE_MANIFEST.json", figures)

    claims = envelope("claim_ledger")
    claims.update(
        {
            "independent_review": review(),
            "conclusion_check": {
                "decision": "accepted",
                "reviewer": "fixture-user",
                "reviewed_at": "2026-08-30T12:00:00Z",
                "reviewer_kind": "human_user",
                "presented_claim_ids": ["CLM-Q1-001"],
                "notes": "Claim text, scope and evidence state were shown before the paper was written.",
            },
            "claims": [
                {
                    "claim_id": "CLM-Q1-001",
                    "text": "The reported policy minimizes cost within the enumerated fixed homogeneous policy class.",
                    "claim_type": "scoped_optimality",
                    "scope": "fixed homogeneous policies only; excludes feedback policies",
                    "paper_location": "Results",
                    "evidence": {
                        "fact_ids": ["FACT-Q1-001"],
                        "model_ids": ["MODEL-Q1-001"],
                        "run_ids": ["RUN-Q1-001"],
                        "result_ids": ["RES-Q1-001"],
                        "figure_ids": ["FIG-Q1-001"],
                    },
                    "evidence_state": "supported_not_reproduced",
                    "certificates": [],
                    "review": review(),
                }
            ],
        }
    )
    write_json(root, "validation/CLAIM_LEDGER.json", claims)

    delivery = envelope("delivery_manifest")
    delivery.update(
        {
            "source_policy": {"mode": "user_supplied_only", "network_lookup_performed": False, "missing_user_materials": []},
            "deliverables": {
                "final_pdf": {"path": "paper/paper.pdf", "entrypoint": "paper/paper.pdf", "editable": False},
                "editable_latex_source": {"path": "paper", "entrypoint": "paper/main.tex", "editable": True},
                "computation_source": {"path": "code", "entrypoint": "code/solve.py", "editable": True},
            },
            "files": [
                {
                    "path": "paper/paper.pdf",
                    "role": "final_pdf",
                    "sha256": digest(paper_bytes),
                    "size": len(paper_bytes),
                }
            ],
            "compile": {
                "command": "xelatex paper.tex",
                "engine": "XeLaTeX",
                "exit_code": 0,
                "log_path": "paper/compile.log",
                "warnings": [],
                "page_count": 1,
            },
            "unresolved_errors": [],
            "accepted_exceptions": [],
            "excluded_files": [],
            "final_check": {
                "decision": "accepted",
                "reviewer": "fixture-user",
                "reviewed_at": "2026-08-30T12:00:00Z",
                "reviewer_kind": "human_user",
                "presented_pages": [1],
                "notes": "Every rendered page was shown before submission.",
            },
        }
    )
    write_json(root, "delivery/DELIVERY_MANIFEST.json", delivery)
    write_accepted_snapshot(root, "model-design", ["model/MODEL_CONTRACT.json"])
    write_accepted_snapshot(root, "validation", ["validation/CLAIM_LEDGER.json"])

