"""Portable recorder and checker regressions using real child processes."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from workflow_fixtures import build_valid_project
from workflow_checks import check_run


SCRIPTS = Path(__file__).resolve().parents[1] / ".agents/skills/cumcm-workflow/scripts"


class DecisionLockTests(unittest.TestCase):
    def test_help_does_not_require_posix_fcntl(self):
        # Simulate the missing module locally; native Windows CI tests it too.
        code = """import runpy, sys
sys.modules['fcntl'] = None
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]).parent))
sys.argv = [sys.argv[1], '--help']
runpy.run_path(sys.argv[0], run_name='__main__')
"""
        done = subprocess.run([sys.executable, "-c", code, str(SCRIPTS / "record_decision.py")],
                              capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_lock_blocks_other_process_and_is_released_on_exit(self):
        child = """import os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from record_decision import decision_lock
with decision_lock(Path(sys.argv[2])):
    Path(sys.argv[4]).write_text('locked', encoding='utf-8')
    sys.stdin.readline()
    if sys.argv[3] == 'crash':
        os._exit(0)
"""
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "decisions.lock"
            for exit_mode in ("normal", "crash"):
                with self.subTest(exit_mode=exit_mode):
                    holder_marker = Path(tmp) / f"{exit_mode}-holder"
                    waiter_marker = Path(tmp) / f"{exit_mode}-waiter"
                    holder = subprocess.Popen([sys.executable, "-u", "-c", child, str(SCRIPTS), str(lock), exit_mode, str(holder_marker)],
                                              stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                              text=True, encoding="utf-8")
                    waiter = None
                    try:
                        deadline = time.monotonic() + 5
                        while not holder_marker.exists() and holder.poll() is None and time.monotonic() < deadline:
                            time.sleep(0.02)
                        self.assertTrue(holder_marker.exists(), holder.stderr.read() if holder.poll() is not None else "holder timed out")
                        waiter = subprocess.Popen([sys.executable, "-u", "-c", child, str(SCRIPTS), str(lock), "normal", str(waiter_marker)],
                                                  stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                                  text=True, encoding="utf-8")
                        time.sleep(0.25)
                        self.assertFalse(waiter_marker.exists(), "second process acquired a held lock")
                        self.assertIsNone(waiter.poll(), waiter.stderr.read() if waiter.poll() is not None else "")
                        holder.stdin.write("release\n")
                        holder.stdin.flush()
                        self.assertEqual(holder.wait(timeout=5), 0)
                        deadline = time.monotonic() + 5
                        while not waiter_marker.exists() and waiter.poll() is None and time.monotonic() < deadline:
                            time.sleep(0.02)
                        self.assertTrue(waiter_marker.exists(), waiter.stderr.read() if waiter.poll() is not None else "waiter timed out")
                        waiter.stdin.write("release\n")
                        waiter.stdin.flush()
                        self.assertEqual(waiter.wait(timeout=5), 0)
                    finally:
                        for process in (holder, waiter):
                            if process is not None:
                                if process.poll() is None:
                                    process.kill()
                                    process.wait(timeout=5)
                                for pipe in (process.stdin, process.stderr):
                                    if pipe is not None:
                                        pipe.close()


class AssertionFindingTests(unittest.TestCase):
    def test_failed_assertions_identify_names_and_positions_without_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build_valid_project(root)
            rel = "runs/RUN-Q1-001/RUN_MANIFEST.json"
            run = json.loads((root / rel).read_text(encoding="utf-8"))
            run["assertions"] = [
                {"name": "first check", "passed": False, "details": "private diagnostic"},
                {"name": "passing check", "passed": True},
                {"passed": False},
                {"name": "last check", "passed": False},
            ]
            for official, severity in ((True, "error"), (False, "warning")):
                with self.subTest(official=official):
                    run["official_run"] = official
                    result = [f for f in check_run(run, root, rel, set()) if f.rule_id == "RUN-E008"]
                    self.assertEqual(len(result), 1)
                    self.assertEqual(result[0].severity, severity)
                    for token in ("first check", "last check", "#1", "#3", "#4", "unnamed"):
                        self.assertIn(token, result[0].message)
                    self.assertNotIn("private diagnostic", result[0].message)


if __name__ == "__main__":
    unittest.main()
