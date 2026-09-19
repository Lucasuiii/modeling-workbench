#!/usr/bin/env python3
"""Create a complete v0.6 modeling contest workspace and run intake preflight."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from inventory_artifacts import sha256
from workflow_checks import check_project


WORKFLOW_VERSION = "0.6.0"
PROJECT_DIRECTORIES = (
    ".cumcm/tmp",
    ".cumcm/snapshots",
    "problem/official",
    "analysis",
    "model",
    "code",
    "data",
    "runs",
    "results",
    "validation",
    "figures",
    "paper",
    "delivery",
    "handoffs",
)
IGNORED_SOURCE_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def envelope(artifact_type: str, project_id: str, created_at: str) -> dict[str, Any]:
    return {
        "schema_version": WORKFLOW_VERSION,
        "artifact_type": artifact_type,
        "project_id": project_id,
        "updated_at": created_at,
        "producer": {"kind": "script", "name": "init_project.py", "version": WORKFLOW_VERSION},
    }


def ensure_safe_relationship(source: Path, target: Path) -> None:
    source_resolved = source.resolve()
    target_resolved = target.resolve(strict=False)
    if source_resolved == target_resolved:
        raise ValueError("official source and project target must be different paths")
    if source_resolved.is_dir():
        try:
            target_resolved.relative_to(source_resolved)
        except ValueError:
            pass
        else:
            raise ValueError("project target must not be created inside the official source directory")
    try:
        source_resolved.relative_to(target_resolved)
    except ValueError:
        pass
    else:
        raise ValueError("official source must not be located inside the project target")


def enumerate_source_files(source: Path) -> tuple[list[tuple[Path, Path]], list[str]]:
    if not source.exists():
        raise ValueError(f"official source does not exist: {source}")
    if source.is_symlink():
        raise ValueError(f"official source may not be a symlink: {source}")
    skipped: list[str] = []
    if source.is_file():
        if source.name in IGNORED_SOURCE_NAMES:
            raise ValueError(f"official source contains no usable files: {source}")
        return [(source, Path(source.name))], skipped
    if not source.is_dir():
        raise ValueError(f"official source must be a regular file or directory: {source}")
    records: list[tuple[Path, Path]] = []
    for path in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
        rel = path.relative_to(source)
        if path.is_symlink():
            raise ValueError(f"official source tree may not contain symlinks: {rel.as_posix()}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"official source tree contains a non-regular file: {rel.as_posix()}")
        if path.name in IGNORED_SOURCE_NAMES:
            skipped.append(rel.as_posix())
            continue
        records.append((path, rel))
    if not records:
        raise ValueError(f"official source contains no usable files: {source}")
    return records, skipped


def copy_official_files(records: list[tuple[Path, Path]], official_dir: Path) -> None:
    for source, rel in records:
        destination = official_dir / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def build_source_records(project: Path) -> list[dict[str, Any]]:
    official_dir = project / "problem" / "official"
    records: list[dict[str, Any]] = []
    for path in sorted(official_dir.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        records.append(
            {
                "source_id": f"SRC-{len(records) + 1:03d}",
                "path": path.relative_to(project).as_posix(),
                "sha256": sha256(path),
                "size": path.stat().st_size,
                "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "origin": "official",
                "acquisition": {"method": "user_local_file", "provided_by_user": True, "source_reference": None},
                "authoritative_for": [],
                "derived_from": None,
                "mutable": False,
            }
        )
    return records


def write_project_brief(project: Path, project_id: str, created_at: str, source_count: int) -> None:
    text = f"""# 数学建模项目工作区

- 项目 ID：`{project_id}`
- 工作流版本：`{WORKFLOW_VERSION}`
- 工作模式：`working`（冻结前切换为 `finalizing`）
- 计算偏好：MATLAB 优先、Python fallback、按任务自动择优
- 初始化时间：`{created_at}`
- 官方输入文件数：{source_count}
- 当前阶段：`intake / working`

## 下一步

1. 查看 `problem/SOURCE_MANIFEST.json` 和 `problem/official/`，确认官方题目、附件及当年规则是否齐全。
2. 不要仅凭文件存在就批准；公式、表格或版式承载含义的 PDF 需要渲染检查。
3. 工作期可继续拆题和试算；进入 `finalizing` 前必须明确批准 intake，并记录 artifact-bound decision/snapshot。
4. 进入 `problem-analysis` 后再创建事实、能力和假设文件；初始化器没有推断任何题意、模型或结果。
5. 计算一律用 `record_run.py` 包装执行，结果一律用 `index_result.py` 索引；不要手写 hash 或 run manifest。

机器可读初始化记录位于 `.cumcm/init-report.json`，当前 preflight 位于 `.cumcm/validation-report.json`。
"""
    (project / "PROJECT_BRIEF.md").write_text(text, encoding="utf-8")


def create_staged_project(
    staging: Path,
    final_project: Path,
    project_id: str,
    source_records: list[tuple[Path, Path]],
    skipped_sources: list[str],
) -> dict[str, Any]:
    for rel in PROJECT_DIRECTORIES:
        (staging / rel).mkdir(parents=True, exist_ok=True)
    copy_official_files(source_records, staging / "problem" / "official")
    created_at = utc_now()

    state = envelope("workflow_state", project_id, created_at)
    state.update(
        {
            "workflow_version": WORKFLOW_VERSION,
            "mode": "working",
            "implementation": {"preferred": "matlab", "fallback": "python", "selection": "auto"},
            "current_stage": "intake",
            "stages": {
                "intake": "in_progress",
                "problem-analysis": "not_started",
                "model-design": "not_started",
                "computation": "not_started",
                "validation": "not_started",
                "paper": "not_started",
                "delivery": "not_started",
            },
        }
    )
    write_json(staging / ".cumcm" / "state.json", state)

    sources = envelope("source_manifest", project_id, created_at)
    sources["sources"] = build_source_records(staging)
    write_json(staging / "problem" / "SOURCE_MANIFEST.json", sources)
    write_project_brief(staging, project_id, created_at, len(sources["sources"]))

    findings, summary = check_project(staging, "intake", "preflight")
    if summary["blocking_error_count"]:
        messages = "; ".join(
            f"{item.rule_id}: {item.message}"
            for item in findings
            if item.severity == "error" and not item.gate_only
        )
        raise ValueError(f"generated project failed intake preflight: {messages}")
    validation_report = {
        "report_version": WORKFLOW_VERSION,
        "generated_at": utc_now(),
        "project_root": str(final_project),
        "summary": summary,
        "findings": [item.to_dict() for item in findings],
    }
    write_json(staging / ".cumcm" / "validation-report.json", validation_report)
    init_report = {
        "report_version": WORKFLOW_VERSION,
        "created_at": created_at,
        "project_id": project_id,
        "source_count": len(sources["sources"]),
        "skipped_source_metadata": skipped_sources,
        "current_stage": "intake",
        "gate_status": summary["gate_status"],
        "generated_paths": [
            ".cumcm/state.json",
            ".cumcm/init-report.json",
            ".cumcm/validation-report.json",
            "problem/SOURCE_MANIFEST.json",
            "PROJECT_BRIEF.md",
        ],
        "next_action": "review official input completeness; working mode may continue, finalizing requires an accepted intake snapshot",
    }
    write_json(staging / ".cumcm" / "init-report.json", init_report)
    return {"created_at": created_at, "summary": summary, "source_count": len(sources["sources"])}


def initialize(project: Path, project_id: str, official: Path) -> dict[str, Any]:
    project = project.resolve(strict=False)
    official = official.resolve()
    if project.exists():
        if project.is_symlink() or not project.is_dir():
            raise ValueError(f"project target must be a new or empty directory: {project}")
        if any(project.iterdir()):
            raise ValueError(f"refusing to overwrite non-empty project target: {project}")
    ensure_safe_relationship(official, project)
    source_records, skipped_sources = enumerate_source_files(official)
    project.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f".{project.name}.init-", dir=project.parent) as temp:
        staging = Path(temp) / "workspace"
        staging.mkdir()
        result = create_staged_project(staging, project, project_id, source_records, skipped_sources)
        if project.exists():
            project.rmdir()
        os.replace(staging, project)

    result.update({"project": str(project), "skipped_sources": skipped_sources})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a complete v0.6 modeling contest workspace from official inputs and run intake preflight"
    )
    parser.add_argument("--project", required=True, type=Path, help="new or empty project directory")
    parser.add_argument("--project-id", required=True, help="stable project identifier, for example CUMCM-2026-B")
    parser.add_argument("--official", required=True, type=Path, help="official input file or directory")
    args = parser.parse_args()
    if not args.project_id.strip():
        parser.error("project-id must not be empty")
    try:
        result = initialize(args.project, args.project_id.strip(), args.official)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(f"initialized: {result['project']}")
    print(f"official sources: {result['source_count']}")
    if result["skipped_sources"]:
        print(f"ignored operating-system metadata: {', '.join(result['skipped_sources'])}")
    print(f"intake preflight: {result['summary']['gate_status']}")
    print("next: review PROJECT_BRIEF.md and problem/SOURCE_MANIFEST.json, then approve the intake gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
