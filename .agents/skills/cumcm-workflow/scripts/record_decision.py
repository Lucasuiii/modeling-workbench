#!/usr/bin/env python3
"""Append a file-version-bound human decision to .cumcm/decisions.jsonl.

An `accepted` decision derives the stage snapshot and advances state. A `revision_requested` decision
is the reopen primitive: it invalidates this stage and every downstream stage so
that iteration never requires hand-editing .cumcm/state.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from file_lock import file_lock as decision_lock
import evidence_json
from record_delegation import active_grant
from workflow_checks import STAGES, WORKFLOW_VERSION, safe_project_path, sha256, stage_scope_paths
from provenance import digest_records


def load_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events: list[dict] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise ValueError(f"line {line_number} is not an object")
        decision_id = event.get("decision_id")
        if not isinstance(decision_id, str) or not decision_id or decision_id in seen:
            raise ValueError(f"line {line_number} has a missing or duplicate decision_id")
        seen.add(decision_id)
        events.append(event)
    return events


def json_bytes(payload: dict) -> bytes:
    return (evidence_json.dumps(payload) + "\n").encode("utf-8")


def write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False)
    temporary = Path(stream.name)
    try:
        with stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json_atomic(path: Path, payload: dict) -> None:
    write_atomic(path, json_bytes(payload))


CHECKPOINT_PATHS = {"model-design": ("model/MODEL_CONTRACT.json", "selection_check"),
                    "validation": ("validation/CLAIM_LEDGER.json", "conclusion_check"),
                    "delivery": ("delivery/DELIVERY_MANIFEST.json", "final_check")}


def reopen(root: Path, stage: str) -> None:
    """Invalidate this stage and everything downstream of it."""
    index = STAGES.index(stage)
    for later in STAGES[index:]:
        (root / ".cumcm" / "snapshots" / f"{later}.json").unlink(missing_ok=True)
        if later in CHECKPOINT_PATHS:
            rel, key = CHECKPOINT_PATHS[later]
            path = root / rel
            if path.is_file():
                data = evidence_json.read(path)
                if isinstance(data.get(key), dict):
                    data[key]["decision"] = "unreviewed"
                    write_json_atomic(path, data)
    state_path = root / ".cumcm" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    stages = state.get("stages")
    if not isinstance(stages, dict):
        raise ValueError("cannot reopen stage: invalid workflow state")
    stages[stage] = "needs_revision"
    for later in STAGES[index + 1 :]:
        if stages.get(later) == "passed":
            stages[later] = "needs_revision"
    state["current_stage"] = stage
    write_json_atomic(state_path, state)


def finish_pending(root: Path, pending: dict) -> None:
    """Replay under the decision lock. Keep the intent until every write completes."""
    event = pending["event"]
    stage = event["stage"]
    log_path = root / ".cumcm/decisions.jsonl"
    events = load_events(log_path)
    previous = next((e for e in events if e["decision_id"] == event["decision_id"]), None)
    if previous is not None and previous != event:
        raise ValueError(f"decision ID conflict: {event['decision_id']}")
    if event["decision"] == "accepted":
        checkpoint = pending.get("checkpoint")
        checkpoint_rel = CHECKPOINT_PATHS[stage][0] if checkpoint is not None else None
        if pending.get("delegated"):
            from workflow_checks import require_delegated_prerequisites
            required = set(stage_scope_paths(root, stage) + require_delegated_prerequisites(root, stage))
            grant = active_grant(root, stage)
            if not grant or grant[1] != event["task_turn_ref"]:
                raise ValueError(f"{stage} decision requires the active user delegation")
            required.add(grant[0])
            if not required.issubset({entry["path"] for entry in event["scope"]}):
                raise ValueError(f"{stage} required material changed; record revision_requested for {stage}")
        elif pending.get("default_scope"):
            actual = set(stage_scope_paths(root, stage))
            if actual != {entry["path"] for entry in event["scope"]}:
                changed = sorted(actual.symmetric_difference(entry["path"] for entry in event["scope"]))
                raise ValueError(f"{stage} material list changed: {', '.join(changed)}; record revision_requested for {stage}")
        # A previous attempt may have already written the prepared checkpoint.
        # Validate every binding before touching anything, including an edited checkpoint.
        for entry in event["scope"]:
            target = safe_project_path(root, entry["path"])
            allowed = {entry["sha256"]}
            if entry["path"] == checkpoint_rel:
                allowed.add(pending["checkpoint_before"])
            if target is None or not target.is_file() or sha256(target) not in allowed:
                raise ValueError(f"{stage} approval material changed: {entry['path']}; "
                                 f"record revision_requested for {stage}, then present the new material")
        if checkpoint_rel is not None:
            write_json_atomic(root / checkpoint_rel, checkpoint)
    if previous is None:
        # Preserve historical bytes (including Windows newlines). Replacing the
        # small log atomically prevents a truncated final JSON line on interruption.
        history = log_path.read_bytes() if log_path.exists() else b""
        if history and not history.endswith(b"\n"):
            history += b"\n"
        line = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        write_atomic(log_path, history + line.encode("utf-8") + b"\n")
    if event["decision"] == "accepted":
        state_path = root / ".cumcm/state.json"
        state = json.loads(state_path.read_bytes())
        snapshot = {
            "snapshot_version": WORKFLOW_VERSION, "project_id": state["project_id"], "stage": stage,
            "decision_id": event["decision_id"], "decision": "accepted", "created_at": event["decided_at"],
            "artifacts": event["scope"], "snapshot_digest": digest_records(event["scope"]),
        }
        write_json_atomic(root / ".cumcm/snapshots" / f"{stage}.json", snapshot)
        state["stages"][stage] = "passed"
        next_stage = next((s for s in STAGES if state["stages"].get(s) != "passed"), STAGES[-1])
        if state["stages"].get(next_stage) == "not_started":
            state["stages"][next_stage] = "in_progress"
        state["current_stage"] = next_stage
        write_json_atomic(state_path, state)
    else:
        reopen(root, stage)
    (root / ".cumcm/pending-decision.json").unlink()
    print(f"recorded {event['decision_id']} for {stage}: {event['decision']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Record an append-only, artifact-bound workflow decision")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--recover", action="store_true", help="finish an interrupted decision using its original scope and reply")
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--decision", choices=("accepted", "revision_requested"))
    parser.add_argument("--decision-id", help="optional; otherwise allocated from the existing decision log")
    parser.add_argument("--reviewer", default="agent")
    parser.add_argument("--task-turn-ref")
    parser.add_argument("--summary", dest="user_visible_summary")
    parser.add_argument("--delegated", action="store_true", help="lead agent decision only after explicit stage-scoped user delegation")
    parser.add_argument("--confirm-human", action="store_true", help="only after the user explicitly accepted ALL currently presented material; fills the existing checkpoint fields")
    parser.add_argument("--scope", action="append", default=[], help="project-relative file; repeat to override stage defaults, or add to them with --delegated")
    args = parser.parse_args()

    if args.recover:
        if any((args.stage, args.decision, args.task_turn_ref, args.user_visible_summary, args.confirm_human, args.delegated,
                args.scope, args.decision_id, args.reviewer != "agent")):
            parser.error("--recover takes only --project")
    elif not all((args.stage, args.decision, args.task_turn_ref, args.user_visible_summary)):
        parser.error("supply --stage, --decision, --task-turn-ref and --summary, or --recover")

    root = args.project.resolve()
    if not root.is_dir():
        parser.error(f"project is not a directory: {root}")
    log_path = root / ".cumcm" / "decisions.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # Include allocation and checkpoint validation in the same transaction as
    # the append-only log, snapshot, and state writes.
    with decision_lock(root / ".cumcm" / "decisions.lock"):
        pending_path = root / ".cumcm/pending-decision.json"
        try:
            if pending_path.is_file():
                pending = evidence_json.loads(pending_path.read_bytes())
                event = pending["event"]
                if args.recover:
                    finish_pending(root, pending)
                    return 0
                # An explicit revision can retire an interrupted approval after material changed.
                if not (args.decision == "revision_requested" and args.stage == event["stage"]
                        and event["decision"] == "accepted"):
                    parser.error("interrupted decision pending; rerun with --recover")
            elif args.recover:
                print("no interrupted decision")
                return 0
            return _record_decision(args, root, parser, log_path)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.error(str(exc))


def _record_decision(args, root: Path, parser: argparse.ArgumentParser, log_path: Path) -> int:
    if args.scope:
        scope = []
        for rel in args.scope:
            target = safe_project_path(root, rel)
            if target is None or not target.is_file():
                parser.error(f"scope file is missing or unsafe: {rel}")
            scope.append(target.relative_to(root).as_posix())
        args.scope = list(dict.fromkeys(scope))
    if args.delegated:
        if args.confirm_human or args.decision != "accepted" or args.stage not in CHECKPOINT_PATHS:
            parser.error("--delegated applies only to a delegated checkpoint acceptance")
        if not args.reviewer.strip() or args.reviewer in {"agent", "user", "human"}:
            parser.error("--delegated requires the actual lead agent identity in --reviewer")
        grant = active_grant(root, args.stage)
        if not grant or grant[1] != args.task_turn_ref:
            parser.error("missing active delegation for this stage and user turn")
        authority_rel = grant[0]

        from workflow_checks import require_delegated_prerequisites
        try:
            extra_scope = require_delegated_prerequisites(root, args.stage)
        except (OSError, ValueError, TypeError) as exc:
            parser.error(str(exc))
    else:
        extra_scope = []

    events = load_events(log_path)
    last = events[-1] if events else {}
    reviewer = "user" if args.confirm_human and args.reviewer == "agent" else args.reviewer
    if (last and args.decision_id in (None, last["decision_id"])
            and bool(last.get("delegated")) == args.delegated
            and (last.get("stage"), last.get("decision"), last.get("reviewer"), last.get("task_turn_ref"),
                 last.get("user_visible_summary")) ==
                (args.stage, args.decision, reviewer, args.task_turn_ref, args.user_visible_summary)
            and not (root / ".cumcm/pending-decision.json").exists()):
        if args.decision == "accepted":
            expected = set(stage_scope_paths(root, args.stage) + args.scope + extra_scope if args.delegated
                           else (args.scope or stage_scope_paths(root, args.stage)))
            if args.stage in CHECKPOINT_PATHS:
                expected.add(CHECKPOINT_PATHS[args.stage][0])
            if args.delegated:
                expected.add(authority_rel)
            recorded = last["scope"]
            if expected != {r["path"] for r in recorded} or any(
                (target := safe_project_path(root, r["path"])) is None or not target.is_file()
                or sha256(target) != r["sha256"] for r in recorded
            ):
                parser.error("approval material or scope changed; present it and record a new reply")
            snapshot = root / ".cumcm/snapshots" / f"{args.stage}.json"
            if not snapshot.is_file() or json.loads(snapshot.read_bytes()).get("decision_id") != last["decision_id"]:
                parser.error("approval snapshot changed; review the current material")
        print(f"already recorded {last['decision_id']} for {args.stage}")
        return 0
    if not args.decision_id:
        used = {event["decision_id"] for event in events}
        number = len(events) + 1
        while f"DEC-{number:03d}" in used:
            number += 1
        args.decision_id = f"DEC-{number:03d}"
    if args.decision_id in {event["decision_id"] for event in events}:
        parser.error(f"decision_id already exists: {args.decision_id}")

    # Fill the existing checkpoint once; the agent need not copy ids or timestamps.
    checkpoint_paths = CHECKPOINT_PATHS
    checkpoint_data = None
    checkpoint_path = None
    checkpoint_before = None
    if args.confirm_human or args.delegated:
        if args.decision != "accepted" or args.stage not in checkpoint_paths:
            parser.error("--confirm-human applies only to acceptance at the three human checkpoints")
        rel, key = checkpoint_paths[args.stage]
        checkpoint_path = root / rel
        original = checkpoint_path.read_bytes()
        checkpoint_before = hashlib.sha256(original).hexdigest()
        data = evidence_json.loads(original)
        if args.stage == "model-design":
            presented_key = "presented_candidate_ids"
            presented = [c["candidate_id"] for component in data.get("components", [])
                         for c in component.get("candidates", [])]
        elif args.stage == "validation":
            presented_key = "presented_claim_ids"
            presented = [c["claim_id"] for c in data.get("claims", [])]
        else:
            presented_key = "presented_pages"
            presented = list(range(1, data.get("compile", {}).get("page_count", 0) + 1))
        if not presented:
            parser.error("no material to confirm; prepare and show it first")
        if args.reviewer == "agent":
            args.reviewer = "user"
        data[key] = {"decision": "accepted", "reviewer": args.reviewer,
                     "reviewer_kind": "lead_agent" if args.delegated else "human_user", "reviewed_at": datetime.now(timezone.utc).isoformat(),
                     presented_key: presented, "notes": args.user_visible_summary}
        checkpoint_data = data
    if args.decision == "accepted" and args.stage in checkpoint_paths:
        from workflow_checks import check_selection_check, check_conclusion_check, check_final_check, require_human_checkpoint
        if not (args.confirm_human or args.delegated):
            try:
                require_human_checkpoint(root, args.stage)
            except ValueError as exc:
                parser.error(str(exc))
        rel, key = checkpoint_paths[args.stage]
        data = checkpoint_data or json.loads((root / rel).read_text(encoding="utf-8"))
        checks = {"model-design": lambda: check_selection_check(data, rel),
                  "validation": lambda: check_conclusion_check(data, rel),
                  "delivery": lambda: check_final_check(data, rel, data.get("compile"))}
        if args.stage == "model-design":
            from workflow_checks import require_resolved_model
            try:
                require_resolved_model(data)
            except ValueError as exc:
                parser.error(str(exc))
        errors = checks[args.stage]()
        if errors:
            parser.error(errors[0].message + "; show the material, then use --confirm-human after the user's reply")

    scope_paths = list(dict.fromkeys(stage_scope_paths(root, args.stage) + args.scope + extra_scope)) if args.delegated else (args.scope or stage_scope_paths(root, args.stage))
    if args.decision == "accepted" and args.stage in checkpoint_paths:
        rel, _ = checkpoint_paths[args.stage]
        scope_paths = list(dict.fromkeys([*scope_paths, rel]))
    if args.delegated:
        scope_paths = list(dict.fromkeys([*scope_paths, authority_rel]))
    if ".cumcm/state.json" in scope_paths:
        parser.error("workflow state is mutable and must not be included in a decision scope")
    scope = []
    checkpoint_scope = None
    for rel in scope_paths:
        artifact = safe_project_path(root, rel)
        if artifact is None or not artifact.is_file():
            parser.error(f"scope file is missing or unsafe: {rel}")
        is_checkpoint = checkpoint_data is not None and artifact == checkpoint_path
        item = {"path": rel, "sha256": None if is_checkpoint else sha256(artifact)}
        if is_checkpoint:
            checkpoint_scope = item
        scope.append(item)

    event = {
        "decision_id": args.decision_id,
        "stage": args.stage,
        "decision": args.decision,
        "delegated": args.delegated,
        "scope": scope,
        "reviewer": args.reviewer,
        "task_turn_ref": args.task_turn_ref,
        "user_visible_summary": args.user_visible_summary,
        "decided_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if checkpoint_scope is not None:
        checkpoint_scope["sha256"] = hashlib.sha256(json_bytes(checkpoint_data)).hexdigest()
    pending = {"event": event, "default_scope": not args.scope, "delegated": args.delegated,
               "checkpoint": checkpoint_data, "checkpoint_before": checkpoint_before}
    write_json_atomic(root / ".cumcm/pending-decision.json", pending)
    finish_pending(root, pending)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
