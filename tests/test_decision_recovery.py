"""Kill the real recorder at publication boundaries and resume the same reply."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from recorder_fixtures import SCRIPTS, make_project, run_script
from workflow_checks import check_project, require_human_checkpoint


CRASH_AFTER_WRITE = """
import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv.pop(1))
import record_decision as recorder
target, root = sys.argv[1], Path(sys.argv[2]).resolve()
write = recorder.write_atomic
def crash_after(path, content):
    write(path, content)
    if path == root / target:
        os._exit(77)
recorder.write_atomic = crash_after
sys.argv = ['record_decision.py', '--project', str(root), '--stage', 'model-design',
            '--decision', 'accepted', '--confirm-human', '--task-turn-ref', 'test-reply',
            '--summary', 'reviewed the model']
recorder.main()
"""


class RecoveryTests(unittest.TestCase):
    def interrupt(self, root, target):
        child = subprocess.run([sys.executable, '-c', CRASH_AFTER_WRITE, str(SCRIPTS), target, str(root)],
                               timeout=30, capture_output=True)
        self.assertEqual(child.returncode, 77, child.stderr)

    def test_each_write_can_be_resumed_once(self):
        for boundary in ('.cumcm/pending-decision.json', 'model/MODEL_CONTRACT.json', '.cumcm/decisions.jsonl',
                         '.cumcm/snapshots/model-design.json', '.cumcm/state.json'):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory() as tmp:
                root = make_project(Path(tmp))
                self.interrupt(root, boundary)
                with self.assertRaisesRegex(ValueError, 'recover'):
                    require_human_checkpoint(root, 'model-design')
                self.assertIn('STATE-E014', {f.rule_id for f in check_project(root, 'model-design')[0]})
                for _ in range(2):
                    done = run_script('record_decision.py', '--project', str(root), '--recover')
                    self.assertEqual(done.returncode, 0, done.stderr)
                retry = run_script('record_decision.py', '--project', str(root), '--stage', 'model-design',
                                   '--decision', 'accepted', '--confirm-human', '--task-turn-ref', 'test-reply',
                                   '--summary', 'reviewed the model')
                self.assertEqual(retry.returncode, 0, retry.stderr)
                require_human_checkpoint(root, 'model-design')
                self.assertNotIn('STATE-E014', {f.rule_id for f in check_project(root, 'model-design')[0]})
                events = (root / '.cumcm/decisions.jsonl').read_text(encoding='utf-8').splitlines()
                self.assertEqual(len(events), 1)
                self.assertEqual(json.loads(events[0])['task_turn_ref'], 'test-reply')
                state = json.loads((root / '.cumcm/state.json').read_bytes())
                self.assertEqual(state['stages']['model-design'], 'passed')

    def test_recovery_preserves_edited_material_and_allows_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            self.interrupt(root, '.cumcm/decisions.jsonl')
            model = root / 'model/MODEL_CONTRACT.json'
            changed = model.read_bytes() + b'\n'
            model.write_bytes(changed)
            done = run_script('record_decision.py', '--project', str(root), '--recover')
            self.assertNotEqual(done.returncode, 0)
            self.assertIn('model/MODEL_CONTRACT.json', done.stderr)
            self.assertEqual(model.read_bytes(), changed)
            done = run_script('record_decision.py', '--project', str(root), '--stage', 'model-design',
                              '--decision', 'revision_requested', '--task-turn-ref', 'revision',
                              '--summary', 'revisit the changed model')
            self.assertEqual(done.returncode, 0, done.stderr)
            with self.assertRaises(ValueError):
                require_human_checkpoint(root, 'model-design')
            events = (root / '.cumcm/decisions.jsonl').read_text(encoding='utf-8').splitlines()
            self.assertEqual([json.loads(line)['decision'] for line in events], ['accepted', 'revision_requested'])
