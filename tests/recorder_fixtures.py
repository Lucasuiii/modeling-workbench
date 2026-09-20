"""Shared real-recorder setup; model approvals remain synthetic test fixtures."""
from __future__ import annotations
import json
import shutil
import subprocess
import sys
from pathlib import Path
from workflow_fixtures import write_accepted_snapshot
from init_project import initialize

ROOT = Path(__file__).resolve().parents[1]


SCRIPTS = ROOT / ".agents" / "skills" / "cumcm-workflow" / "scripts"


PROJECT_ID = "RECORDER-2026-A"


def envelope(kind: str) -> dict:
    return {
        "schema_version": "0.6.0",
        "artifact_type": kind,
        "project_id": PROJECT_ID,
        "updated_at": "2026-09-04T00:00:00Z",
        "producer": {"kind": "script", "name": "test-fixture", "version": "0.6.0"},
    }


def write_json(root: Path, rel: str, payload: dict) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_script(name: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPTS / name), *args], check=False, capture_output=True, text=True)


SOLVER = """import json, pathlib
values = [3.0, 1.5, 4.25]
out = pathlib.Path("results/q1_output.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"minimum_cost": min(values), "count": len(values)}) + "\\n", encoding="utf-8")
checks = {"assertions": [{"name": "enumeration coverage", "passed": len(values) == 3}]}
pathlib.Path("results/assertions.json").write_text(json.dumps(checks) + "\\n", encoding="utf-8")
print("solved")
"""


def make_project(temp: Path) -> Path:
    official_dir = temp / "official"
    official_dir.mkdir()
    (official_dir / "problem.txt").write_text("Minimise the cost over the declared candidate set.\n", encoding="utf-8")
    project = temp / "workspace"
    initialize(project, PROJECT_ID, official_dir)

    facts = envelope("problem_facts")
    facts.update({
        "subproblems": [{"subproblem_id": "Q1", "request": "Minimise cost over the candidate set.", "expected_output": "Minimum cost"}],
        "facts": [{
            "fact_id": "FACT-Q1-001", "statement": "The candidate set is finite and stated.",
            "source_id": "SRC-001", "location": "line 1", "raw_value": "finite", "normalized_value": "finite",
            "unit": None, "extraction_method": "native_text", "render_verified": True,
        }],
        "definitions": [], "ambiguities": [], "assumptions": [],
    })
    write_json(project, "analysis/PROBLEM_FACTS.json", facts)

    capabilities = envelope("task_capabilities")
    capabilities["capabilities"] = [{
        "capability_id": "CAP-Q1-001", "subproblem_id": "Q1",
        "objective": "Enumerate the candidate set.", "required_output": "Minimum cost",
        "fact_ids": ["FACT-Q1-001"],
        "acceptance_checks": [{
            "check_id": "ACC-Q1-001", "judge": "recorded", "assertion_name": "minimum_matches_expected",
            "assertion": "the reported minimum equals the enumerated minimum; a mismatch means a candidate was skipped",
        }],
        "model_ids": ["MODEL-Q1-001"], "code_entry_points": ["code/solve.py:main"],
        "result_ids": [], "lifecycle_state": "implemented", "blocking_issues": [],
    }]
    write_json(project, "analysis/TASK_CAPABILITIES.json", capabilities)

    # A draft model contract: method and scope only. This is what Deferred Model
    # Selection means -- variables, inputs, outputs and the verification plan are
    # written once computation has told us what the model actually is.
    model = envelope("model_contract")
    model["selection_check"] = {
        "decision": "accepted",
        "reviewer": "fixture-user",
        "reviewed_at": "2026-08-30T12:00:00Z",
        "reviewer_kind": "human_user",
        "presented_candidate_ids": ["CAND-ENUM", "CAND-GREEDY"],
        "notes": "Both candidates were shown before the choice.",
    }
    model["components"] = [{
        "model_id": "MODEL-Q1-001", "capability_ids": ["CAP-Q1-001"],
        "method": "complete enumeration over the declared candidate set",
        "scope": "declared candidates only; no continuous relaxation",
    }]
    model["components"][0]["candidates"] = [{
        "candidate_id": "CAND-ENUM", "status": "selected", "method": "complete enumeration",
        "why_considered": "finite search", "discriminating_evidence": ["exact small case"],
        "decision_rationale": "exact within the finite scope",
    }]
    write_json(project, "model/MODEL_CONTRACT.json", model)
    write_accepted_snapshot(project, "model-design", ["model/MODEL_CONTRACT.json"])

    (project / "code").mkdir(exist_ok=True)
    (project / "code" / "solve.py").write_text(SOLVER, encoding="utf-8")
    return project


def ctex_available() -> bool:
    if shutil.which("kpsewhich") is None:
        return False
    found = subprocess.run(["kpsewhich", "ctexart.cls"], check=False, capture_output=True, text=True)
    return found.returncode == 0 and bool(found.stdout.strip())


MINIMAL_TEX = """\\documentclass[a4paper]{article}
\\begin{document}
\\section{Enumeration}
The minimum enumerated cost is 1.5 cost units.
\\end{document}
"""


GREEDY = """import json, pathlib
cands = {"a": 3.0, "b": 1.5, "c": 4.25}
best = sorted(cands)[0]
p = pathlib.Path("results/greedy.json"); p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps({"minimum_cost": cands[best], "visited": 1}) + "\\n", encoding="utf-8")
print("greedy done")
"""


NO_OP = """print("did nothing")
"""


SELF_EDITING = """import json, pathlib
pathlib.Path("results/q1_output.json").parent.mkdir(parents=True, exist_ok=True)
pathlib.Path("results/q1_output.json").write_text(json.dumps({"minimum_cost": 1.0}) + "\\n", encoding="utf-8")
pathlib.Path("code/self_editing.py").write_text("# rewritten while running\\n", encoding="utf-8")
print("moved under myself")
"""


def record_official(project: Path) -> None:
    completed = run_script(
        "record_run.py", "--project", str(project), "--run-id", "RUN-Q1-001", "--official",
        "--capability", "CAP-Q1-001", "--source", "code/solve.py",
        "--input", "problem/official/problem.txt:formal",
        "--output", "results/q1_output.json:claim",
        "--assert-file", "results/assertions.json",
        "--", sys.executable, "code/solve.py",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    indexed = run_script(
        "index_result.py", "--project", str(project), "--result-id", "RES-Q1-001",
        "--run", "RUN-Q1-001", "--locator", "results/q1_output.json#/minimum_cost",
        "--name", "Minimum enumerated cost", "--unit", "cost", "--scope", "declared candidates only",
        "--check", "enumeration coverage",
    )
    assert indexed.returncode == 0, indexed.stdout + indexed.stderr

