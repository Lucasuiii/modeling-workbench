"""Action-boundary regressions, using synthetic projects and real recorder commands."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from recorder_fixtures import make_project, run_script, write_json
from workflow_fixtures import write_accepted_snapshot
from workflow_checks import require_human_checkpoint
from workflow_checks import sha256
from build_handoff import build
from record_decision import main as record_decision_main


def model_with_candidates(root, statuses):
    path = root / 'model/MODEL_CONTRACT.json'
    model = json.loads(path.read_text(encoding="utf-8"))
    model['components'][0]['candidates'] = [
        {'candidate_id': f'CAND-{i}', 'status': status, 'method': 'enumeration',
         'why_considered': 'finite search', 'discriminating_evidence': ['exact small instance'],
         'decision_rationale': 'compared against exact solution'}
        for i, status in enumerate(statuses)]
    model['selection_check']['presented_candidate_ids'] = [f'CAND-{i}' for i in range(len(statuses))]
    write_json(root, 'model/MODEL_CONTRACT.json', model)


def confirm(root, *extra):
    return run_script('record_decision.py', '--project', str(root), '--stage', 'model-design',
                      '--decision', 'accepted', '--confirm-human', '--task-turn-ref', 'user-reply',
                      '--summary', 'User approved the presented model choice', *extra)


class CheckpointAudit(unittest.TestCase):
    def test_confirmation_binds_exact_checkpoint_bytes_under_windows_newlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp)); model_with_candidates(root, ['selected'])
            original = tempfile.NamedTemporaryFile

            def windows_newlines(*args, **kwargs):
                if args and args[0] == 'w':
                    kwargs['newline'] = '\r\n'
                return original(*args, **kwargs)

            argv = ['record_decision.py', '--project', str(root), '--stage', 'model-design',
                    '--decision', 'accepted', '--confirm-human', '--task-turn-ref', 'fixture-turn',
                    '--summary', 'Synthetic approval of the presented model']
            with patch('record_decision.tempfile.NamedTemporaryFile', side_effect=windows_newlines), \
                    patch.object(sys, 'argv', argv):
                self.assertEqual(record_decision_main(), 0)
            require_human_checkpoint(root, 'model-design')
            snapshot = json.loads((root / '.cumcm/snapshots/model-design.json').read_text(encoding='utf-8'))
            record = next(item for item in snapshot['artifacts'] if item['path'] == 'model/MODEL_CONTRACT.json')
            self.assertEqual(record['sha256'], sha256(root / 'model/MODEL_CONTRACT.json'))

    def test_missing_snapshot_blocks_handwritten_approval_at_action_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp)); model_with_candidates(root, ['selected'])
            (root / '.cumcm/snapshots/model-design.json').unlink(missing_ok=True)
            for action in (lambda: require_human_checkpoint(root, 'model-design'),
                           lambda: build(root, 'modeling-computation')):
                with self.assertRaisesRegex(ValueError, 'snapshot'):
                    action()
            done = run_script('record_run.py', '--project', str(root), '--official', '--', sys.executable, 'code/solve.py')
            self.assertNotEqual(done.returncode, 0)
            self.assertFalse((root / 'results/q1_output.json').exists())
            self.assertEqual(confirm(root).returncode, 0)
            require_human_checkpoint(root, 'model-design')
            (root / '.cumcm/snapshots/model-design.json').unlink()
            with self.assertRaisesRegex(ValueError, 'snapshot'):
                require_human_checkpoint(root, 'model-design')

    def test_unresolved_comparison_cannot_advance_and_exploration_remains_available(self):
        for statuses in ([], ['under_evaluation'], ['selected', 'selected'], ['selected', 'under_evaluation']):
            with self.subTest(statuses=statuses), tempfile.TemporaryDirectory() as tmp:
                root = make_project(Path(tmp)); model_with_candidates(root, statuses)
                state = (root / '.cumcm/state.json').read_bytes()
                contract = (root / 'model/MODEL_CONTRACT.json').read_bytes()
                done = confirm(root)
                self.assertNotEqual(done.returncode, 0, 'unresolved model was accepted')
                self.assertEqual(state, (root / '.cumcm/state.json').read_bytes())
                self.assertEqual(contract, (root / 'model/MODEL_CONTRACT.json').read_bytes())
                # A matching snapshot alone cannot make an unresolved comparison valid.
                write_accepted_snapshot(root, 'model-design', ['model/MODEL_CONTRACT.json'])
                with self.assertRaisesRegex(ValueError, 'unresolved'):
                    require_human_checkpoint(root, 'model-design')
                with self.assertRaisesRegex(ValueError, 'unresolved'):
                    build(root, 'modeling-computation')
                official = run_script('record_run.py', '--project', str(root), '--official', '--', sys.executable, 'code/solve.py')
                self.assertNotEqual(official.returncode, 0)
                self.assertFalse((root / 'results/q1_output.json').exists())
                exploratory = run_script('record_run.py', '--project', str(root), '--', sys.executable, 'code/solve.py')
                self.assertEqual(exploratory.returncode, 0, exploratory.stderr)
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp)); model_with_candidates(root, ['selected', 'rejected'])
            done = confirm(root)
            self.assertEqual(done.returncode, 0, done.stderr)
            require_human_checkpoint(root, 'model-design')
            self.assertEqual(json.loads((root / '.cumcm/state.json').read_text(encoding="utf-8"))['stages']['model-design'], 'passed')

    def test_human_reviewer_matches_in_contract_and_event(self):
        for reviewer in (None, 'Alice'):
            with self.subTest(reviewer=reviewer), tempfile.TemporaryDirectory() as tmp:
                root = make_project(Path(tmp)); model_with_candidates(root, ['selected'])
                done = confirm(root, *(['--reviewer', reviewer] if reviewer else []))
                self.assertEqual(done.returncode, 0, done.stderr)
                check = json.loads((root / 'model/MODEL_CONTRACT.json').read_text(encoding="utf-8"))['selection_check']
                event = json.loads((root / '.cumcm/decisions.jsonl').read_text(encoding="utf-8").splitlines()[-1])
                self.assertEqual(check['reviewer'], reviewer or 'user')
                self.assertEqual(event['reviewer'], check['reviewer'])
