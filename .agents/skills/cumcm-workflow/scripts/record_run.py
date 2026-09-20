#!/usr/bin/env python3
"""Execute a computation and record every machine fact about it.

The agent declares meaning on the command line (purpose, capabilities, which files
are formal inputs or claim-bearing outputs). Everything else -- argv, timings, exit
status, logs, hashes, and the source-tree snapshot -- is observed, never typed.

A rerun never overwrites: it appends a new run whose `parent_run_id` points at
the one it replaces, and the declared source and outputs are frozen into the run
directory so a preserved run stays verifiable no matter what the workspace does
next.

Exploratory runs are deliberately cheap:

    record_run.py --project P -- python3 code/try.py

Freezing a run for formal results costs a few declarations:

    record_run.py --project P --official --capability CAP-Q1-001 \
        --source code/solve.py --input data/q1.csv:formal \
        --output results/q1.json:claim -- python3 code/solve.py
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from provenance import sha256_file, tree_snapshot

WORKFLOW_VERSION = "0.6.0"
INPUT_ROLES = {"formal": "formal_input", "auxiliary": "auxiliary_input"}
FROZEN_KINDS = {"source", "outputs", "inputs"}
MAX_FROZEN_INPUT_BYTES = 64 * 1024 * 1024
OUTPUT_ROLES = {"claim": "claim_bearing_output", "intermediate": "intermediate_output", "diagnostic": "diagnostic_output"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def relative(root: Path, value: str) -> str:
    candidate = (root / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
    try:
        return candidate.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise SystemExit(f"path escapes the project: {value}") from exc


def split_role(spec: str, table: dict[str, str], default: str) -> tuple[str, str]:
    path, _, role = spec.partition(":")
    if not role:
        return path, default
    if role not in table:
        raise SystemExit(f"unknown role '{role}'; expected one of {', '.join(sorted(table))}")
    return path, table[role]


def file_record(root: Path, rel: str, role: str) -> dict[str, Any]:
    target = root / rel
    if not target.is_file():
        raise SystemExit(f"declared file does not exist after the run: {rel}")
    return {
        "path": rel,
        "sha256": sha256_file(target),
        "size": target.stat().st_size,
        "media_type": mimetypes.guess_type(target.name)[0] or "application/octet-stream",
        "evidence_role": role,
    }


def infer_language(argv: list[str], explicit: str | None) -> str:
    if python_script_index(argv) is not None:
        detected = "python"
    elif (len(argv) == 3 and Path(argv[0]).name.lower() in {"matlab", "matlab.exe"}
          and argv[1] == "-batch" and re.fullmatch(r"\s*run\('([^']+\.m)'\)\s*;?\s*", argv[2])):
        detected = "matlab"
    else:
        raise SystemExit("cannot infer backend from a supported executable/invocation structure")
    if explicit and explicit != detected:
        raise SystemExit("declared backend differs from the executed invocation")
    return detected


def python_script_index(argv: list[str]) -> int | None:
    """Only direct Python script invocation is attributable without a wrapper."""
    if not argv or not re.fullmatch(r"python(?:\d+(?:\.\d+)*)?(?:\.exe)?", Path(argv[0]).name, re.I):
        return None
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == "--":
            index += 1
            break
        if token in {"-W", "-X"}:
            index += 2
        elif token in {"-B", "-E", "-I", "-s", "-S", "-u", "-O", "-OO", "-q", "-v"} or token.startswith(("-W", "-X")):
            index += 1
        elif token.startswith("-"):
            return None
        else:
            break
    return index if index < len(argv) and argv[index].endswith(".py") else None


def infer_entry_point(root: Path, argv: list[str], sources: list[str]) -> str:
    index = python_script_index(argv)
    candidate = argv[index] if index is not None else None
    # Keep MATLAB support explicit: one run('path.m') expression, no arbitrary batch code.
    if candidate is None and argv and Path(argv[0]).name.lower() in {"matlab", "matlab.exe"}:
        if len(argv) == 3 and argv[1] == "-batch":
            match = re.fullmatch(r"\s*run\('([^']+\.m)'\)\s*;?\s*", argv[2])
            if match:
                candidate = match.group(1)
    if candidate is not None and (root / candidate).is_file():
        return relative(root, candidate)
    raise SystemExit("cannot establish executed entry point; use python path.py or matlab -batch \"run('path.m')\"; --source only declares snapshot coverage")


def runtime_label(language: str, argv: list[str], root: Path | None = None) -> str:
    if language == "python":
        index = python_script_index(argv)
        if index is None:
            raise SystemExit("cannot probe runtime for an unsupported Python invocation")
        probe = [*argv[:index], "-c", "import sys,json; print(json.dumps([sys.version,sys.executable]))"]
        # A CLI separator belongs before the script, not before our -c probe.
        if "--" in probe:
            probe.remove("--")
        try:
            result = subprocess.run(probe, cwd=root, capture_output=True, text=True, timeout=15, check=True)
            version, executable = json.loads(result.stdout)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise SystemExit(f"cannot observe model Python runtime: {exc}") from exc
        return f"Python {version} ({executable}); observed interpreter probe before execution"
    return f"MATLAB via {argv[0]} (version unverified)"


def parse_assertions(
    entries: list[str],
    assertion_file: str | None,
    root: Path,
) -> list[dict[str, Any]]:
    assertions: list[dict[str, Any]] = []
    for entry in entries:
        name, _, verdict = entry.partition("=")
        name = name.strip()
        if not name:
            raise SystemExit(f"malformed --assert entry: {entry}")
        passed = verdict.strip().casefold() not in {"fail", "false", "0", "no"}
        # A verdict typed on the command line is a human note, not executed evidence.
        assertions.append({"name": name, "passed": passed, "source": "declared"})
    if assertion_file:
        target = root / assertion_file
        if not target.is_file():
            raise SystemExit(f"the run did not write its assertion file: {assertion_file}")
        # Fresh generation is enforced before this parser is called.
        payload = json.loads(target.read_text(encoding="utf-8"))
        items = payload.get("assertions") if isinstance(payload, dict) else payload
        for item in items or []:
            if isinstance(item, dict) and item.get("name"):
                extra = {k: v for k, v in item.items() if k not in {"name", "passed", "source"}}
                # The run wrote this file itself, so the verdict is machine-derived.
                assertions.append({"name": str(item["name"]), "passed": item.get("passed") is True, **extra, "source": "recorded"})
    return assertions


def freeze(root: Path, run_dir: Path, rel: str, kind: str) -> str:
    """Copy an artifact into the run directory and return its frozen path.

    The frozen tree mirrors the original layout (runs/<id>/source/code/solve.py),
    so the live counterpart of any frozen file is just the path with the
    runs/<id>/<kind>/ prefix removed. That keeps drift detection possible without
    storing a second mapping.
    """
    origin = root / rel
    if not origin.is_file():
        raise SystemExit(f"declared file does not exist after the run: {rel}")
    destination = run_dir / kind / rel
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(origin, destination)
    return destination.relative_to(root).as_posix()


def live_path_of(frozen: str) -> str | None:
    """Inverse of freeze(): runs/<id>/source/code/solve.py -> code/solve.py."""
    parts = frozen.split("/")
    if len(parts) > 3 and parts[0] == "runs" and parts[2] in FROZEN_KINDS:
        return "/".join(parts[3:])
    return None


def mtime_of(root: Path, rel: str) -> int | None:
    target = root / rel
    return target.stat().st_mtime_ns if target.is_file() else None


def freeze_input(root: Path, run_dir: Path, rel: str) -> tuple[str, bool]:
    """Freeze a team-produced input; leave official material and huge files in place.

    Official sources are immutable by intake contract and hash-guarded, and copying
    a large attachment into every run is waste. Everything else is a file the team
    can regenerate, so a preserved run needs its own copy to stay reproducible.
    """
    if rel.startswith("problem/official/"):
        return rel, False
    target = root / rel
    if target.is_file() and target.stat().st_size > MAX_FROZEN_INPUT_BYTES:
        print(f"input left in place (over {MAX_FROZEN_INPUT_BYTES // (1024 * 1024)} MiB): {rel}", file=sys.stderr)
        return rel, False
    return freeze(root, run_dir, rel, "inputs"), True


def child_run_id(root: Path, parent: str) -> str:
    """RUN-Q1-001 -> RUN-Q1-002, keeping whatever prefix the parent used."""
    existing = {path.name for path in (root / "runs").iterdir()}
    match = re.match(r"^(.*?)(\d+)$", parent)
    if match:
        head, number = match.group(1), int(match.group(2))
        width = len(match.group(2))
        while True:
            number += 1
            candidate = f"{head}{number:0{width}d}"
            if candidate not in existing:
                return candidate
    index = 2
    while f"{parent}-R{index}" in existing:
        index += 1
    return f"{parent}-R{index}"


def parse_seeds(entries: list[str]) -> list[dict[str, Any]]:
    """Caller declarations only; they do not establish delivery to or use by code."""
    seeds: list[dict[str, Any]] = []
    for entry in entries:
        name, sep, value = entry.partition("=")
        seeds.append({"name": name.strip() if sep else "seed", "value": (value if sep else name).strip(), "source": "declared"})
    return seeds


def load_previous(root: Path, run_id: str) -> dict[str, Any]:
    path = root / "runs" / run_id / "RUN_MANIFEST.json"
    if not path.is_file():
        raise SystemExit(f"cannot rerun unknown run: {run_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def next_run_id(root: Path) -> str:
    existing = {path.name for path in (root / "runs").iterdir()} if (root / "runs").is_dir() else set()
    index = 1
    while f"RUN-{index:03d}" in existing:
        index += 1
    return f"RUN-{index:03d}"


@contextmanager
def fresh_output_transaction(root: Path, run_dir: Path, paths: set[str]):
    """Commit live fresh evidence only when the manifest write succeeds.

    Keep old backups and rejected new files for recovery. This does not roll back
    arbitrary model side effects or protect against concurrent/malicious writers.
    """
    backups = {}
    prepared = []
    committed = False
    try:
        for rel in sorted(paths):
            target = root / rel
            if target.is_file():
                backup = run_dir / "previous_outputs" / rel
                backup.parent.mkdir(parents=True, exist_ok=True)
                target.replace(backup)
                backups[rel] = backup
            prepared.append(rel)
        yield
        committed = True
    finally:
        if not committed:
            for rel in prepared:
                target = root / rel
                try:
                    # A replaced parent directory must not redirect rollback outside
                    # the workspace. Preserve backups and report rather than guess.
                    if target.parent.resolve() != target.parent:
                        raise OSError("output parent was replaced by a symlink")
                    if target.exists() or target.is_symlink():
                        rejected = run_dir / "rejected_outputs" / rel
                        rejected.parent.mkdir(parents=True, exist_ok=True)
                        target.replace(rejected)
                    if rel in backups:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(backups[rel], target)
                except OSError as exc:
                    print(f"cannot roll back {rel}: {exc}; recover from {run_dir}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a command and record its evidence; the agent never types a hash")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--rerun", help="re-execute an existing run's exact argv as a new, appended run")
    parser.add_argument("--purpose")
    parser.add_argument("--capability", action="append", default=[])
    parser.add_argument("--candidate", action="append", default=[], help="model candidate this run evaluates; repeat as needed")
    parser.add_argument("--source", action="append", default=[], help="project-relative source file that the snapshot must cover")
    parser.add_argument("--input", action="append", default=[], help="path[:formal|auxiliary]")
    parser.add_argument("--output", action="append", default=[], help="path[:claim|intermediate|diagnostic]")
    parser.add_argument("--assert", dest="assertions", action="append", default=[], help="NAME=pass|fail")
    parser.add_argument("--assert-file", help="project-relative JSON file the run wrote with its own assertions")
    parser.add_argument("--seed", action="append", default=None, help="declared seed metadata only; does not set RNG state or pass arguments to the model")
    parser.add_argument("--dependency", action="append", default=[])
    parser.add_argument("--toolbox", action="append", default=None, help="declared toolbox metadata; not proof of loading or use")
    parser.add_argument("--language", choices=("matlab", "python"))
    parser.add_argument("--rationale")
    parser.add_argument("--official", action="store_true")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- followed by the command to execute")
    args = parser.parse_args()

    root = args.project.resolve()
    if not root.is_dir():
        parser.error(f"project is not a directory: {root}")

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    previous: dict[str, Any] = {}
    run_id = args.run_id
    if args.rerun:
        previous = load_previous(root, args.rerun)
        if command:
            parser.error("cannot provide a command with --rerun; a rerun executes the parent's exact argv")
        # A rerun appends. Overwriting the parent would destroy the only record of
        # what the superseded run executed and produced.
        run_id = run_id or child_run_id(root, args.rerun)
        if run_id == args.rerun:
            parser.error("a rerun must use a new run id; it never overwrites its parent")
        command = [str(token) for token in previous.get("argv", [])]
    if not command:
        parser.error("provide the command to execute after --")
    run_id = run_id or next_run_id(root)

    capabilities = args.capability or [str(value) for value in previous.get("capability_ids", [])]
    candidates = args.candidate or [str(value) for value in previous.get("candidate_ids", [])]
    sources = [relative(root, value) for value in args.source]
    if not sources and previous:
        snapshot = previous.get("implementation", {}).get("source_snapshot", {})
        sources = [live_path_of(str(value)) or str(value) for value in snapshot.get("files", [])]
    declared_inputs = args.input or [
        f"{live_path_of(str(item['path'])) or item['path']}:"
        f"{'formal' if item.get('evidence_role') == 'formal_input' else 'auxiliary'}"
        for item in previous.get("inputs", []) if isinstance(item, dict)
    ]
    declared_outputs = args.output or [
        f"{live_path_of(str(item['path'])) or item['path']}:"
        f"{ {'claim_bearing_output': 'claim', 'intermediate_output': 'intermediate'}.get(item.get('evidence_role'), 'diagnostic') }"
        for item in previous.get("outputs", []) if isinstance(item, dict)
    ]

    language = infer_language(command, args.language or previous.get("implementation", {}).get("selected_language"))
    entry_point = infer_entry_point(root, command, sources)
    expected_suffix = ".py" if language == "python" else ".m"
    if not entry_point.endswith(expected_suffix):
        parser.error("declared backend differs from the executed entry point")
    executable_path = Path(command[0])
    if executable_path.is_absolute():
        executable = command[0]
    elif executable_path.parent != Path(".") or command[0].startswith("./"):
        executable = str(root / executable_path)
    else:
        executable = shutil.which(command[0])
    if not executable:
        parser.error("cannot locate execution runtime")
    executed_command = [str(Path(executable).absolute()), *command[1:]]
    observed_runtime = runtime_label(language, executed_command, root)
    if entry_point not in sources:
        sources.append(entry_point)

    if args.official:
        from workflow_checks import require_human_checkpoint
        try:
            require_human_checkpoint(root, "model-design")
        except ValueError as exc:
            parser.error(str(exc))
    # Reserve the directory before launching a process, including unfinished runs.
    # mkdir is atomic; simultaneous automatic allocations retry rather than overwrite.
    (root / "runs").mkdir(exist_ok=True)
    while True:
        if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
            parser.error("run id must be a single directory name")
        run_dir = root / "runs" / run_id
        try:
            run_dir.mkdir()
            break
        except FileExistsError:
            if args.run_id:
                parser.error(f"run {run_id} already exists or is in progress; runs are append-only")
            run_id = child_run_id(root, args.rerun) if args.rerun else next_run_id(root)
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"

    # P0: a program that exits 0 without rewriting its output would otherwise have
    # the previous run's file frozen as its own, with a real hash and false provenance.
    declared_output_paths = [relative(root, spec.split(":", 1)[0]) for spec in declared_outputs]
    mtimes_before = {rel: mtime_of(root, rel) for rel in declared_output_paths}
    # Freezing happens after execution, so the copy is only honest if the file did
    # not move under the run. Hash what the run is about to read, and check after.
    declared_input_paths = [relative(root, spec.split(":", 1)[0]) for spec in declared_inputs]
    # Something the run creates is an output. Accepting it as a source would let a file
    # the run generated be frozen and hashed as the code that produced the result.
    absent = sorted(
        rel for rel in dict.fromkeys(sources + declared_input_paths)
        if not (root / rel).is_file()
    )
    if absent:
        parser.error(
            "declared source or input does not exist before the run: " + ", ".join(absent)
        )
    assert_file_rel = relative(root, args.assert_file) if args.assert_file else None
    read_before = {
        rel: sha256_file(root / rel)
        for rel in dict.fromkeys(sources + declared_input_paths)
        if (root / rel).is_file()
    }

    fresh_paths = {
        relative(root, spec.split(":", 1)[0]) for spec in declared_outputs
        if split_role(spec, OUTPUT_ROLES, "diagnostic_output")[1] == "claim_bearing_output"
    }
    if assert_file_rel:
        fresh_paths.add(assert_file_rel)
    if fresh_paths & set(read_before):
        parser.error("claim/assertion outputs cannot also be source or input files; use separate paths")
    for rel in fresh_paths:
        if rel.startswith(("runs/", ".cumcm/", "problem/official/")):
            parser.error(f"fresh evidence output cannot overwrite protected workspace material: {rel}")
        target = root / rel
        if target.exists() and (not target.is_file() or target.stat().st_nlink != 1):
            parser.error(f"fresh evidence output must be a regular unlinked file: {rel}")
    with fresh_output_transaction(root, run_dir, fresh_paths):
        started_at = utc_now()
        try:
            with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
                completed = subprocess.run(executed_command, cwd=root, stdout=out, stderr=err, timeout=args.timeout, check=False)
            exit_code = completed.returncode
            status = "completed" if exit_code == 0 else "failed"
        except subprocess.TimeoutExpired:
            exit_code = 124
            status = "interrupted"
        except FileNotFoundError as exc:
            parser.error(f"cannot execute the command: {exc}")
        missing_fresh = [rel for rel in fresh_paths if not (root / rel).is_file() or (root / rel).is_symlink() or (root / rel).stat().st_nlink != 1 or (root / rel).stat().st_size == 0]
        if missing_fresh:
            parser.error("the command did not write fresh non-empty evidence; assertion file not rewritten by this run: " + ", ".join(sorted(missing_fresh)))
        finished_at = utc_now()

        changed_under_run = sorted(
            rel for rel, digest in read_before.items()
            if not (root / rel).is_file() or sha256_file(root / rel) != digest
        )
        if changed_under_run:
            parser.error(
                "source or input changed while the run was executing: " + ", ".join(changed_under_run)
                + " -- the frozen copy would not be what the run actually read; re-run with a settled workspace"
            )

        official = args.official
        if official and status != "completed":
            print(f"run {run_id} exited {exit_code}; recording it as exploratory instead of official", file=sys.stderr)
            official = False
        if official and not capabilities:
            parser.error("an official run must name at least one --capability")

        # Inputs are hashed where they live: official material is immutable by intake
        # contract, and a changed team input is drift worth seeing.
        inputs = []
        for spec in declared_inputs:
            role = split_role(spec, INPUT_ROLES, "auxiliary_input")[1]
            rel = relative(root, spec.split(":", 1)[0])
            stored, frozen_here = freeze_input(root, run_dir, rel)
            record = file_record(root, stored, role)
            record["frozen"] = frozen_here
            inputs.append(record)
        untouched = [
            rel for rel, before in mtimes_before.items()
            if rel not in fresh_paths and before is not None and mtime_of(root, rel) == before
        ]
        if untouched:
            print("declared output was not rewritten by this run: " + ", ".join(sorted(untouched)), file=sys.stderr)

        # Source and outputs are frozen: a rerun would otherwise overwrite exactly the
        # files this run's evidence points at.
        frozen_sources = [freeze(root, run_dir, rel, "source") for rel in sources]
        frozen_entry_point = freeze(root, run_dir, entry_point, "source")
        outputs = []
        for spec in declared_outputs:
            role = split_role(spec, OUTPUT_ROLES, "diagnostic_output")[1]
            rel = relative(root, spec.split(":", 1)[0])
            record = file_record(root, freeze(root, run_dir, rel, "outputs"), role)
            # Recorded so a reviewer can see what the produced-by-this-run decision rested on.
            record["preexisting"] = mtimes_before.get(rel) is not None
            if rel in fresh_paths:
                record["generation_check"] = "absent_before_execution_nonempty_after"
            outputs.append(record)
        if not outputs:
            # Every run produces at least its own log; recording it keeps a zero-flag
            # exploratory run schema-valid without inventing a claim-bearing artifact.
            outputs = [file_record(root, stdout_path.relative_to(root).as_posix(), "diagnostic_output")]
        if official and not any(item["evidence_role"] == "claim_bearing_output" for item in outputs):
            parser.error("an official run must declare at least one --output <path>:claim")

        manifest = {
            "schema_version": WORKFLOW_VERSION,
            "artifact_type": "run_manifest",
            "project_id": json.loads((root / ".cumcm" / "state.json").read_text(encoding="utf-8"))["project_id"],
            "updated_at": finished_at,
            "producer": {"kind": "script", "name": "record_run.py", "version": WORKFLOW_VERSION},
            "run_id": run_id,
            "purpose": args.purpose or previous.get("purpose") or ("official computation" if official else "exploratory run"),
            "capability_ids": capabilities,
            "candidate_ids": candidates,
            "argv": command,
            "working_directory": ".",
            "started_at": started_at,
            "finished_at": finished_at,
            "exit_code": exit_code,
            "status": status,
            "official_run": official,
            "implementation": {
                "selected_language": language,
                "selection_rationale": args.rationale or previous.get("implementation", {}).get("selection_rationale") or f"recorded by record_run.py from the executed {language} command",
                "entry_point": frozen_entry_point,
                "runtime": observed_runtime,
                "dependencies": args.dependency or [str(value) for value in previous.get("implementation", {}).get("dependencies", [])],
                "matlab_toolboxes": args.toolbox if args.toolbox is not None else previous.get("implementation", {}).get("matlab_toolboxes", []),
                "metadata_provenance": {"dependencies": "declared", "matlab_toolboxes": "declared"},
                "fallback_from": None,
                "source_snapshot": tree_snapshot(root, frozen_sources, entrypoint=frozen_entry_point),
            },
            "inputs": inputs,
            "outputs": outputs,
            "environment": {"platform": platform.platform(), "python": platform.python_version()},
            "seeds": parse_seeds(args.seed) if args.seed is not None else [dict(seed, source="declared") for seed in previous.get("seeds", [])],
            "stdout_path": stdout_path.relative_to(root).as_posix(),
            "stderr_path": stderr_path.relative_to(root).as_posix(),
            # Assertions are verdicts about THIS execution. Inheriting a parent's `pass`
            # would hand formal verification evidence that was never produced.
            "assertions": parse_assertions(args.assertions, assert_file_rel, root),
            "parent_run_id": args.rerun or None,
        }
        destination = run_dir / "RUN_MANIFEST.json"
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=run_dir, delete=False) as stream:
            json.dump(manifest, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            temp_name = stream.name
        os.replace(temp_name, destination)

    grade = "official" if official else "exploratory"
    print(f"recorded {grade} run {run_id} (exit {exit_code}) -> {destination.relative_to(root)}")
    if args.rerun:
        print(f"appended after {args.rerun}; that run and its evidence are untouched")
        if previous.get("assertions") and not manifest["assertions"]:
            print(
                f"{args.rerun} recorded {len(previous['assertions'])} assertion(s); they were NOT inherited -- "
                "re-declare with --assert or --assert-file so the new code is actually verified",
                file=sys.stderr,
            )
    for entry in outputs:
        if entry["evidence_role"] == "claim_bearing_output":
            print(f"claim-bearing output frozen at {entry['path']}")
    if candidates:
        print(f"evaluated candidate(s): {', '.join(candidates)} -- cite this run in the candidate's evaluation_run_ids")
    if not official:
        print("exploratory runs never support formal results; add --official once the command is the one you mean to cite")
    return 0 if status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
