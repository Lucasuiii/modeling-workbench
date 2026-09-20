#!/usr/bin/env python3
"""Summarize current-stage evidence read-only; never advance or approve a stage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Importing the checker must not create __pycache__ in the tools checkout.
sys.dont_write_bytecode = True


def inspect_project(root: Path) -> dict:
    from workflow_checks import CONTRACT_PATHS, STAGES, check_project, check_schema, require_human_checkpoint

    root = root.resolve()
    state = json.loads((root / CONTRACT_PATHS["state"]).read_text(encoding="utf-8"))
    invalid = check_schema(state, "state", "intake", CONTRACT_PATHS["state"])
    if invalid:
        raise ValueError("invalid/unsupported state: " + "; ".join(f.message for f in invalid))
    stage = state["current_stage"]
    # preflight retains gate-only findings without pretending they prohibit exploration.
    findings, summary = check_project(root, stage, "preflight")
    technical = [f.to_dict() for f in findings if f.severity == "error" and not f.gate_only]
    review = [f.to_dict() for f in findings if f.severity == "error" and f.gate_only]
    warnings = [f.to_dict() for f in findings if f.severity == "warning"]
    checkpoints = []
    for checkpoint, dependent in (("model-design", "official computation"), ("validation", "paper writing"), ("delivery", "final delivery")):
        if STAGES.index(checkpoint) > STAGES.index(stage):
            continue
        try:
            require_human_checkpoint(root, checkpoint)
            checkpoints.append({"stage": checkpoint, "dependent_action": dependent, "status": "accepted_current", "reason": "existing action boundary passed"})
        except ValueError as exc:
            checkpoints.append({"stage": checkpoint, "dependent_action": dependent, "status": "not_ready", "reason": str(exc)})
    blocked_checkpoints = [c for c in checkpoints if c["status"] == "not_ready"]
    if technical:
        action = "先修复列出的证据或结构错误，再重新检查；根据规则位置定位受影响材料。"
    elif blocked_checkpoints:
        action = "先按关卡原因核对候选方案、待审材料及确认记录；没有当前有效确认时，展示材料并等待用户明确答复，依赖该确认的工作不能开始。"
    elif review:
        action = "准备并展示当前待审材料，取得明确确认后记录决定；依赖该确认的工作必须等待，其他探索按阶段指南继续。"
    elif warnings:
        action = "按当前阶段指南继续工作并处理相关警告；preflight 可用不代表阶段已完成。"
    else:
        action = "按当前阶段指南核对剩余工作；确实完成后使用现有记录命令推进，不由状态工具自动推进。"
    return {
        "project": str(root), "current_stage": stage,
        "declared_stage_status": state["stages"][stage],
        "summary": summary, "checkpoints": checkpoints, "technical_errors": technical, "pending_review": review,
        "warnings": warnings, "findings": [f.to_dict() for f in findings],
        "next_action": action,
        "guide": str(Path(__file__).resolve().parents[1] / "references" / {
            "intake": "01-intake.md", "problem-analysis": "02-problem-analysis.md",
            "model-design": "03-model-design.md", "computation": "04-computation.md",
            "validation": "05-validation.md", "paper": "06-paper-writing.md",
            "delivery": "07-compile-delivery.md",
        }[stage]),
        "scope": "Checks through the recorded current stage only; downstream artifacts are not certified. No completion or approval is inferred from file presence.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = inspect_project(args.project)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ImportError) as exc:
        error = {"status": "unavailable", "error": str(exc),
                 "next_action": "检查项目路径、状态/契约文件和工作流依赖；不要重新初始化或推断已完成。"}
        print(json.dumps(error, ensure_ascii=False, indent=2) if args.json else f"无法读取项目状态：{exc}\n{error['next_action']}")
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"当前阶段：{report['current_stage']}（记录状态：{report['declared_stage_status']}）")
        print(f"实时检查：{report['summary']['gate_status']}；检查范围截至当前阶段")
        for key, label in (("technical_errors", "需修复"), ("pending_review", "待确认"), ("warnings", "警告")):
            print(f"{label}：{len(report[key])} 项")
            for f in report[key][:5]:
                print(f"  {f['rule_id']} {f['path']}{f['pointer']}: {f['message']}")
                if f["remediation"]:
                    print(f"    {f['remediation']}")
            if len(report[key]) > 5:
                print("  更多详情见 --json 输出。")
        for checkpoint in report["checkpoints"]:
            print(f"行动关卡 {checkpoint['stage']}: {checkpoint['status']} — {checkpoint['reason']}")
        print(f"下一步：{report['next_action']}\n阶段指南：{report['guide']}")
        print(report["summary"]["evidence_boundary"])
    # Pending human review is not an execution failure. Dependent actions keep their own gates.
    return 1 if report["technical_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
