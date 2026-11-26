#!/usr/bin/env python3
"""Record an explicit user delegation for one checkpoint, not an approval."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from record_decision import decision_lock, write_json_atomic


DELEGATABLE_STAGES = ('model-design', 'validation', 'delivery')


def record_delegation(root: Path, stage: str, user_turn_ref: str) -> bool:
    if stage not in DELEGATABLE_STAGES or not user_turn_ref.strip() or not (root / '.cumcm/state.json').is_file():
        raise ValueError('project state, a valid stage and a nonempty user turn reference are required')
    directory = root / '.cumcm/delegations'
    directory.mkdir(parents=True, exist_ok=True)
    with decision_lock(root / '.cumcm/decisions.lock'):
        if (root / '.cumcm/pending-decision.json').exists():
            raise ValueError('interrupted decision pending; recover it before changing delegation')
        path = directory / (stage + '.json')
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                existing = {}
            if isinstance(existing, dict) and existing.get('stage') == stage and existing.get('user_turn_ref') == user_turn_ref:
                return False
        write_json_atomic(path, {'stage': stage, 'user_turn_ref': user_turn_ref, 'recorded_at': datetime.now(timezone.utc).isoformat()})
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--stage', required=True, choices=DELEGATABLE_STAGES)
    parser.add_argument('--user-turn-ref', required=True, help='reference to the actual user instruction delegating this stage')
    args = parser.parse_args()
    root = args.project.resolve()
    try:
        changed = record_delegation(root, args.stage, args.user_turn_ref)
    except ValueError as exc:
        parser.error(str(exc))
    print(('Recorded explicit user delegation for ' if changed else 'Delegation already recorded for ') + args.stage)

if __name__ == '__main__':
    main()
