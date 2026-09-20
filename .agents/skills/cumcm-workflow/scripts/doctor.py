#!/usr/bin/env python3
"""Read-only environment diagnostics; standard library only, no installation."""
from __future__ import annotations

import argparse
import ast
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
from backend_selection import detect_matlab_executable

SKILL = Path(__file__).resolve().parents[1]


def probe(command: list[str], timeout: float) -> tuple[str, str]:
    """Run a bounded probe outside the project; never use a shell."""
    try:
        with tempfile.TemporaryDirectory(prefix="modeling-doctor-") as directory:
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
            result = subprocess.run(command, cwd=directory, env=env, stdin=subprocess.DEVNULL,
                                    capture_output=True, text=True, errors="replace", timeout=timeout)
        detail = (result.stdout + result.stderr).strip()[:1500]
        return ("available" if result.returncode == 0 else "failed", detail or f"exit={result.returncode}")
    except subprocess.TimeoutExpired:
        return "failed", f"probe timed out after {timeout:g}s"
    except OSError as exc:
        return "failed", str(exc)


def python_command(code: str) -> list[str]:
    # Keep site/environment visibility consistent with the interpreter being diagnosed.
    flags = []
    if sys.flags.no_site:
        flags.append("-S")
    if sys.flags.no_user_site:
        flags.append("-s")
    if sys.flags.ignore_environment:
        flags.append("-E")
    return [sys.executable, *flags, "-B", "-c", code]


def diagnose(timeout: float = 10, modules: tuple[str, ...] = (), probe_matlab: bool = False) -> dict:
    checks = []

    def add(name, status, detail, stage):
        checks.append(dict(name=name, status=status, detail=detail, needed_for=stage))

    required = ["SKILL.md", "scripts/init_project.py", "scripts/workflow_checks.py",
                "scripts/record_run.py", "scripts/project_status.py", "schemas/workflow-state.schema.json"]
    missing = [p for p in required if not (SKILL / p).is_file()]
    version = None
    try:
        tree = ast.parse((SKILL / "scripts/workflow_checks.py").read_text(encoding="utf-8"))
        version = next(ast.literal_eval(node.value) for node in tree.body
                       if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "WORKFLOW_VERSION" for t in node.targets))
    except (OSError, SyntaxError, ValueError, StopIteration):
        missing.append("readable WORKFLOW_VERSION")
    add("workflow", "missing" if missing else "available", ", ".join(missing) if missing else f"{SKILL} (v{version}; core files only)", "all")
    add("python", "available" if sys.version_info >= (3, 10) else "failed", f"{sys.version.split()[0]} ({sys.executable})", "all")
    # Import AND check supported distribution versions, without importing workflow code.
    for module, lower, upper in (("jsonschema", (4, 18), (5,)), ("referencing", (0, 35), (1,))):
        code = ("import importlib, importlib.metadata, re; "
                f"importlib.import_module({module!r}); v=importlib.metadata.version({module!r}); "
                "n=tuple(int(x) for x in re.match(r'(\\d+(?:\\.\\d+)*)', v).group().split('.')); "
                f"print(v); raise SystemExit(0 if {lower!r} <= n < {upper!r} else 'unsupported version')")
        status, detail = probe(python_command(code), timeout)
        add(module, status, detail, "all")
    for module in modules:
        if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", module):
            raise ValueError(f"invalid import module name: {module}")
        status, detail = probe(python_command(f"import importlib; importlib.import_module({module!r}); print('import succeeded')"), timeout)
        add(f"module:{module}", status, detail, "computation")
    detected = detect_matlab_executable()
    matlab = detected["path"] if detected else None
    if not matlab:
        add("matlab", "missing", "MATLAB not found by the existing backend detector; Python remains an option", "optional MATLAB backend")
    elif probe_matlab:
        status, detail = probe([matlab, "-batch", "disp(version); assert(license('test','MATLAB'));"], timeout)
        add("matlab", status, detail, "optional MATLAB backend")
    else:
        add("matlab", "unverified", f"{matlab}; not launched; license/toolboxes untested", "optional MATLAB backend")
    for name, args in (("xelatex", ["--version"]), ("pdftoppm", ["-v"]), ("pdfinfo", ["-v"])):
        executable = shutil.which(name)
        status, detail = probe([executable, *args], timeout) if executable else ("missing", f"{name} not found on PATH")
        add(name, status, detail.splitlines()[0] if detail else detail, "paper/delivery")
    kpsewhich = shutil.which("kpsewhich")
    status, detail = probe([kpsewhich, "ctexart.cls"], timeout) if kpsewhich else ("missing", "kpsewhich not found on PATH")
    if status == "available" and not Path(detail).is_file():
        status, detail = "unverified", "no existing class file returned"
    add("ctex", status, detail, "Chinese paper")
    base = all(c["status"] == "available" for c in checks if c["needed_for"] == "all")
    return {
        "workflow_version": version, "checks": checks,
        "base_ready": base,
        "python_imports_ready": base and all(c["status"] == "available" for c in checks if c["needed_for"] == "computation"),
        "paper_tools_detected": all(c["status"] == "available" for c in checks if c["needed_for"] == "paper/delivery"),
        "notes": ["Only explicitly requested model modules are checked; solver execution and task suitability are not established.",
                  "Paper probes check tools/class discovery, not actual compilation, fonts or PDF quality.",
                  "Missing paper tools do not block intake/modeling. No installation or project writes performed."],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit structured report to stdout")
    parser.add_argument("--timeout", type=float, default=10, help="seconds per probe")
    parser.add_argument("--module", action="append", default=[], help="trusted installed Python module to import; repeat for model dependencies")
    parser.add_argument("--probe-matlab", action="store_true", help="launch MATLAB in a temporary directory; may use a license")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be finite and positive")
    try:
        report = diagnose(args.timeout, tuple(args.module), args.probe_matlab)
    except ValueError as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("基础工作流环境：" + ("可用" if report["base_ready"] else "存在缺失或失败"))
        for c in report["checks"]:
            print(f"[{c['status']}] {c['name']} ({c['needed_for']}): {c['detail']}")
        print("下一步：" + ("可以开始读题与建模；按当前任务补齐计算依赖。" if report["base_ready"] else "先修复基础环境检查中的缺失或失败项，再重新诊断。"))
        print("论文工具缺失可稍后补齐；安装或系统配置变更前先取得用户同意。")
        for note in report["notes"]:
            print(note)
    return 0 if report["base_ready"] and report["python_imports_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
