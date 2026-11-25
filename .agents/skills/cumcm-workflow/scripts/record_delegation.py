#!/usr/bin/env python3
"""Record an explicit user delegation for one checkpoint, not an approval."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from record_decision import decision_lock, write_json_atomic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--stage', required=True, choices=('model-design', 'validation', 'delivery'))
    parser.add_argument('--user-turn-ref', required=True, help='reference to the actual user instruction delegating this stage')
    args = parser.parse_args()
    root = args.project.resolve()
    if not (root / '.cumcm/state.json').is_file() or not args.user_turn_ref.strip():
        parser.error('project state and a nonempty actual user turn reference are required')
    directory = root / '.cumcm/delegations'
    directory.mkdir(parents=True, exist_ok=True)
    with decision_lock(root / '.cumcm/decisions.lock'):
        if (root / '.cumcm/pending-decision.json').exists():
            parser.error('interrupted decision pending; recover it before changing delegation')
        path = directory / (args.stage + '.json')
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                existing = {}
            if isinstance(existing, dict) and existing.get('stage') == args.stage and existing.get('user_turn_ref') == args.user_turn_ref:
                print('Delegation already recorded for ' + args.stage)
                return
        write_json_atomic(path, {'stage': args.stage, 'user_turn_ref': args.user_turn_ref, 'recorded_at': datetime.now(timezone.utc).isoformat()})
    print('Recorded explicit user delegation for ' + args.stage)

if __name__ == '__main__':
    main()
