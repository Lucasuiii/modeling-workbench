#!/usr/bin/env python3
"""Run v0.8 CUMCM evidence checks and write a machine-readable report."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from workflow_checks import GATE_MODES, STAGES, WORKFLOW_VERSION, check_project


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate v0.8 workflow evidence. A passing result establishes "
            "traceability and recorded evidence, not mathematical correctness."
        )
    )
    parser.add_argument("--project", type=Path, required=True)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--stage", choices=STAGES)
    selection.add_argument("--all", action="store_true", help="validate through delivery")
    parser.add_argument(
        "--gate-mode",
        choices=sorted(GATE_MODES),
        default="enforce",
        help="preflight reports human-gated findings without failing; enforce requires them accepted",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="report path; defaults to <project>/.cumcm/validation-report.json",
    )
    parser.add_argument("--no-write-report", action="store_true")
    args = parser.parse_args()

    project = args.project.resolve()
    if not project.is_dir():
        parser.error(f"project is not a directory: {project}")
    stage = "delivery" if args.all else args.stage
    try:
        findings, summary = check_project(project, stage, args.gate_mode)
    except (OSError, ValueError) as exc:
        print(f"validator failure: {exc}", file=sys.stderr)
        return 2

    payload = {
        "report_version": WORKFLOW_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "project_root": str(project),
        "summary": summary,
        "findings": [item.to_dict() for item in findings],
    }
    if not args.no_write_report:
        report_path = args.report or (project / ".cumcm" / "validation-report.json")
        if not report_path.is_absolute():
            report_path = project / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"report: {report_path}")

    for item in findings:
        pointer = f"{item.path}{item.pointer}" if item.pointer else item.path
        print(f"{item.severity.upper()} {item.rule_id} [{item.evidence_type}] {pointer}: {item.message}")
    counts = summary["finding_counts"]
    print(
        f"checked through {stage} ({summary['workflow_mode']}): "
        f"{counts['error']} error(s), {counts['warning']} warning(s), {counts['info']} info"
    )
    print(f"gate status: {summary['gate_status']} ({args.gate_mode})")
    print(summary["evidence_boundary"])
    return 1 if summary["blocking_error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
