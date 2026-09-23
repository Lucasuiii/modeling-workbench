"""Recorder failures must not leave uncommitted fresh evidence live."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from recorder_fixtures import make_project, run_script
import record_run
from record_run import infer_language


class RecorderTransactions(unittest.TestCase):
    def test_backend_ignores_model_arguments(self):
        self.assertEqual(infer_language([sys.executable, 'code/solve.py', '--note', 'matlab'], None), 'python')
        self.assertEqual(infer_language(['/opt/python-tools/matlab', '-batch', "run('python.m')"], None), 'matlab')
        with self.assertRaises(SystemExit):
            infer_language(['echo', 'python', 'code/solve.py'], None)
        with self.assertRaises(SystemExit):
            infer_language([sys.executable, 'code/solve.py'], 'matlab')

    def test_backend_note_does_not_break_actual_recording(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_project(Path(d))
            done = run_script('record_run.py', '--project', str(p), '--run-id', 'NOTE', '--', sys.executable, 'code/solve.py', '--note', 'matlab')
            self.assertEqual(done.returncode, 0, done.stderr)
            m = json.loads((p/'runs/NOTE/RUN_MANIFEST.json').read_text(encoding="utf-8"))
            self.assertEqual(m['implementation']['selected_language'], 'python')

    def test_rejected_manifest_restores_all_fresh_paths(self):
        for reason in ('source_changed', 'missing_capability', 'invalid_assertions'):
            for preexisting in (True, False):
                with self.subTest(reason=reason, preexisting=preexisting), tempfile.TemporaryDirectory() as d:
                    p = make_project(Path(d))
                    paths = ['results/claim.json', 'results/verdict.json']
                    for rel in paths:
                        if preexisting:
                            (p/rel).write_text('old evidence', encoding="utf-8")
                    code = 'from pathlib import Path\n'
                    code += 'Path("results/claim.json").write_text("new evidence", encoding="utf-8")\n'
                    code += 'Path("results/verdict.json").write_text('+repr('invalid json' if reason == 'invalid_assertions' else '[]')+', encoding="utf-8")\n'
                    if reason == 'source_changed':
                        code += 'Path(__file__).write_text("# changed source", encoding="utf-8")\n'
                    (p/'code/transaction.py').write_text(code, encoding="utf-8")
                    flags = ['--official'] if reason == 'missing_capability' else []
                    done = run_script('record_run.py', '--project', str(p), '--run-id', 'REJECTED', '--output', paths[0]+':claim', '--assert-file', paths[1], *flags, '--', sys.executable, 'code/transaction.py')
                    self.assertNotEqual(done.returncode, 0)
                    expected = {'source_changed': 'source or input changed', 'missing_capability': 'at least one --capability', 'invalid_assertions': 'JSONDecodeError'}[reason]
                    self.assertIn(expected, done.stderr)
                    self.assertFalse((p/'runs/REJECTED/RUN_MANIFEST.json').exists())
                    for rel in paths:
                        if preexisting:
                            self.assertEqual((p/rel).read_text(encoding="utf-8"), 'old evidence')
                        else:
                            self.assertFalse((p/rel).exists())

    def test_manifest_install_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_project(Path(d))
            target = p/'results/q1_output.json'
            target.write_text('original', encoding="utf-8")
            argv = ['record_run.py', '--project', str(p), '--run-id', 'WRITEFAIL', '--output', 'results/q1_output.json:claim', '--', sys.executable, 'code/solve.py']
            replace = record_run.os.replace
            def fail_manifest(source, destination):
                if Path(destination).name == 'RUN_MANIFEST.json':
                    raise OSError('manifest write failure')
                return replace(source, destination)
            with patch.object(sys, 'argv', argv), patch.object(record_run.os, 'replace', side_effect=fail_manifest):
                with self.assertRaisesRegex(OSError, 'manifest write failure'):
                    record_run.main()
            self.assertEqual(target.read_text(encoding="utf-8"), 'original')
            self.assertFalse((p/'runs/WRITEFAIL/RUN_MANIFEST.json').exists())
            self.assertEqual(json.loads((p/'runs/WRITEFAIL/rejected_outputs/results/q1_output.json').read_text(encoding="utf-8"))['minimum_cost'], 1.5)

    def test_committed_manifest_keeps_new_live_output(self):
        with tempfile.TemporaryDirectory() as d:
            p = make_project(Path(d))
            (p/'results/q1_output.json').write_text('old evidence', encoding="utf-8")
            done = run_script('record_run.py', '--project', str(p), '--run-id', 'COMMIT', '--output', 'results/q1_output.json:claim', '--', sys.executable, 'code/solve.py')
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue((p/'runs/COMMIT/RUN_MANIFEST.json').exists())
            self.assertEqual(json.loads((p/'results/q1_output.json').read_text(encoding="utf-8"))['minimum_cost'], 1.5)
