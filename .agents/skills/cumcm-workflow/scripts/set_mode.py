#!/usr/bin/env python3
"""Atomically switch a v0.6 workspace between working and finalizing."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from record_decision import decision_lock
from workflow_checks import WORKFLOW_VERSION, check_project


def set_mode(project: Path, mode: str) -> dict:
    project = project.resolve()
    with decision_lock(project / ".cumcm/decisions.lock"):
        if (project / ".cumcm/pending-decision.json").exists():
            raise ValueError("interrupted decision pending; run record_decision.py --project <p> --recover")
        return _set_mode(project, mode)


def _set_mode(project: Path, mode: str) -> dict:
    path = project / ".cumcm" / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or state.get("workflow_version") != WORKFLOW_VERSION:
        raise ValueError(f"mode switch requires workflow {WORKFLOW_VERSION}")
    candidate = dict(state)
    candidate["mode"] = mode
    _, summary = check_project(
        project,
        str(candidate.get("current_stage")),
        "preflight",
        state_override=candidate,
    )
    if mode == "finalizing" and summary["blocking_error_count"]:
        raise ValueError(
            "finalizing preflight is blocking; state was not changed "
            f"({summary['blocking_error_count']} blocking error(s))"
        )
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        json.dump(candidate, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        temp_name = stream.name
    os.replace(temp_name, path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Switch a v0.6 project between working and finalizing")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("working", "finalizing"))
    args = parser.parse_args()
    try:
        summary = set_mode(args.project, args.mode)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(f"mode: {args.mode}")
    print(f"preflight: {summary['gate_status']}; blocking={summary['blocking_error_count']}; pending_review={summary['pending_review_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
