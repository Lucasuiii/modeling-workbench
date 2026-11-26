#!/usr/bin/env python3
"""Record an explicit user delegation for one checkpoint, not an approval."""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


DELEGATABLE_STAGES = ('model-design', 'validation', 'delivery')


def stage_records(root: Path, stage: str) -> list[Path]:
    """The original single-file grant is the first event in older workspaces."""
    directory = root / '.cumcm/delegations'
    first = directory / f'{stage}.json'
    changes = sorted(p for p in (directory / stage).glob('*.json')
                     if re.fullmatch(r'[0-9]{8}', p.stem))
    return ([first] if first.is_file() else []) + changes


def read_stage_record(path: Path, stage: str) -> dict:
    try:
        record = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return {}
    if (isinstance(record, dict) and record.get('stage') == stage
            and isinstance(record.get('user_turn_ref'), str) and record['user_turn_ref'].strip()):
        return record
    return {}


def active_grant(root: Path, stage: str) -> tuple[str, str] | None:
    paths = stage_records(root, stage)
    if paths:
        record = read_stage_record(paths[-1], stage)
        if record and record.get('action', 'grant') == 'grant':
            return paths[-1].relative_to(root).as_posix(), record['user_turn_ref']
    return None


def record_delegation(root: Path, stage: str, user_turn_ref: str, *, revoke: bool = False) -> bool:
    from record_decision import decision_lock, write_json_atomic
    if stage not in DELEGATABLE_STAGES or not user_turn_ref.strip() or not (root / '.cumcm/state.json').is_file():
        raise ValueError('project state, a valid stage and a nonempty user turn reference are required')
    action = 'revoke' if revoke else 'grant'
    with decision_lock(root / '.cumcm/decisions.lock'):
        if (root / '.cumcm/pending-decision.json').exists():
            raise ValueError('interrupted decision pending; recover it before changing delegation')
        paths = stage_records(root, stage)
        for path in reversed(paths):
            record = read_stage_record(path, stage)
            if record.get('user_turn_ref') == user_turn_ref:
                if path == paths[-1] and record.get('action', 'grant') == action:
                    return False
                raise ValueError('this instruction was already used; a change of authority requires a new user turn')
        directory = root / '.cumcm/delegations'
        if paths:
            number = int(paths[-1].stem) + 1 if paths[-1].parent.name == stage else 1
            destination = directory / stage / f'{number:08d}.json'
        else:
            destination = directory / f'{stage}.json'
        destination.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(destination, {'stage': stage, 'action': action, 'user_turn_ref': user_turn_ref,
                                        'recorded_at': datetime.now(timezone.utc).isoformat()})
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--stage', required=True, choices=DELEGATABLE_STAGES)
    parser.add_argument('--user-turn-ref', required=True, help='reference to the actual user instruction changing this stage authority')
    parser.add_argument('--revoke', action='store_true', help='return future decisions at this stage to the user')
    args = parser.parse_args()
    root = args.project.resolve()
    try:
        changed = record_delegation(root, args.stage, args.user_turn_ref, revoke=args.revoke)
    except ValueError as exc:
        parser.error(str(exc))
    owner = 'user' if args.revoke else 'lead agent'
    print(f'{args.stage}: {owner} decides ({"recorded" if changed else "already recorded"})')

if __name__ == '__main__':
    main()
