"""Read-only diagnostics, with synthetic project approvals only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from workflow_fixtures import SCRIPTS, build_valid_project, write_json
from workflow_checks import check_project
import doctor
from project_status import inspect_project


def snapshot(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob('*') if p.is_file()}


def cli(name, *args, cwd=None):
    return subprocess.run([sys.executable, '-B', str(SCRIPTS / name), *args],
                          cwd=cwd, capture_output=True, text=True)


class DoctorTests(unittest.TestCase):
    def test_missing_paper_tools_do_not_block_base_and_matlab_is_optional(self):
        with patch.object(doctor.shutil, 'which', return_value=None), \
             patch.object(doctor, 'detect_matlab_executable', return_value=None):
            report = doctor.diagnose()
        self.assertTrue(report['base_ready'])
        self.assertFalse(report['paper_tools_detected'])
        self.assertEqual(next(c['status'] for c in report['checks'] if c['name'] == 'matlab'), 'missing')

    def test_found_matlab_not_misrepresented_as_executed(self):
        with patch.object(doctor, 'detect_matlab_executable', return_value={'path': '/fake/matlab'}), \
             patch.object(doctor, 'probe', return_value=('available', 'version')) as probe:
            report = doctor.diagnose()
        self.assertEqual(next(c['status'] for c in report['checks'] if c['name'] == 'matlab'), 'unverified')
        self.assertFalse(any(call.args[0][0] == '/fake/matlab' for call in probe.call_args_list))

    def test_broken_dependencies_block_base(self):
        with patch.object(doctor, 'probe', return_value=('failed', 'import failure')):
            report = doctor.diagnose()
        self.assertFalse(report['base_ready'])

    def test_timeout_and_failed_process_are_not_success(self):
        status, _ = doctor.probe([sys.executable, '-c', 'import time; time.sleep(2)'], .05)
        self.assertEqual(status, 'failed')
        status, _ = doctor.probe([sys.executable, '-c', 'raise SystemExit(3)'], 5)
        self.assertEqual(status, 'failed')

    def test_real_json_and_no_project_writes_with_unicode_space_path(self):
        with tempfile.TemporaryDirectory(prefix='诊断 项目 ') as directory:
            root = Path(directory)
            (root / 'keep.txt').write_text('unchanged', encoding="utf-8")
            before = snapshot(root)
            done = cli('doctor.py', '--json', cwd=root)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertTrue(json.loads(done.stdout)['base_ready'])
            self.assertEqual(snapshot(root), before)

    def test_doctor_runs_without_third_party_dependencies(self):
        done = subprocess.run([sys.executable, '-S', '-B', str(SCRIPTS / 'doctor.py'), '--json'], capture_output=True, text=True)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertFalse(json.loads(done.stdout)['base_ready'])

    def test_unsupported_dependency_rejected_even_with_python_optimization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'jsonschema.py').write_text('# synthetic importable incompatible version', encoding="utf-8")
            dist = root / 'jsonschema-99.0.dist-info'
            dist.mkdir()
            (dist / 'METADATA').write_text('Metadata-Version: 2.1\nName: jsonschema\nVersion: 99.0\n', encoding="utf-8")
            env = dict(os.environ, PYTHONPATH=str(root), PYTHONOPTIMIZE='1')
            done = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'doctor.py'), '--json'], env=env, capture_output=True, text=True)
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            check = next(c for c in json.loads(done.stdout)['checks'] if c['name'] == 'jsonschema')
            self.assertEqual(check['status'], 'failed')
            self.assertIn('unsupported version', check['detail'])

    def test_model_dependency_failure_and_invalid_timeout(self):
        done = cli('doctor.py', '--json', '--module', '_modeling_nonexistent_fixture_dependency_')
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertTrue(json.loads(done.stdout)['base_ready'])
        self.assertFalse(json.loads(done.stdout)['python_imports_ready'])
        for timeout in ('0', '-1', 'nan', 'inf'):
            self.assertEqual(cli('doctor.py', '--timeout', timeout).returncode, 2)


class ProjectStatusTests(unittest.TestCase):
    def test_real_checker_parity_readonly_and_no_auto_advance(self):
        with tempfile.TemporaryDirectory(prefix='状态 项目 ') as directory:
            root = Path(directory)
            build_valid_project(root)
            before = snapshot(root)
            done = cli('project_status.py', '--project', str(root), '--json')
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            report = json.loads(done.stdout)
            findings, summary = check_project(root, 'validation', 'preflight')
            self.assertEqual(report['summary'], summary)
            self.assertEqual(report['findings'], [f.to_dict() for f in findings])
            self.assertEqual(snapshot(root), before)
            self.assertTrue(all(c['status'] == 'accepted_current' for c in report['checkpoints']))

    def test_changed_code_reported_even_if_stage_declares_passed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_valid_project(root)
            state = json.loads((root / '.cumcm/state.json').read_text(encoding="utf-8"))
            state['stages']['validation'] = 'passed'
            write_json(root, '.cumcm/state.json', state)
            (root / 'code/solve.py').write_text('print("changed")\n', encoding="utf-8")
            done = cli('project_status.py', '--project', str(root), '--json')
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            report = json.loads(done.stdout)
            self.assertIn('RUN-E020', {f['rule_id'] for f in report['technical_errors']})
            self.assertEqual(report['summary']['gate_status'], 'blocked')

    def test_pending_review_separate_from_execution_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_valid_project(root)
            claims = json.loads((root / 'validation/CLAIM_LEDGER.json').read_text(encoding="utf-8"))
            claims['conclusion_check']['decision'] = 'unreviewed'
            write_json(root, 'validation/CLAIM_LEDGER.json', claims)
            done = cli('project_status.py', '--project', str(root), '--json')
            report = json.loads(done.stdout)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertTrue(report['pending_review'])
            self.assertFalse(report['technical_errors'])
            self.assertEqual(report['summary']['gate_status'], 'awaiting_review')

    def test_missing_approval_snapshot_blocks_action_even_when_preflight_is_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_valid_project(root)
            (root / '.cumcm/snapshots/validation.json').unlink()
            report = inspect_project(root)
            checkpoint = next(c for c in report['checkpoints'] if c['stage'] == 'validation')
            self.assertEqual(checkpoint['status'], 'not_ready')
            self.assertIn('snapshot', checkpoint['reason'])
            self.assertIn('不能开始', report['next_action'])

    def test_changed_approved_material_invalidates_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_valid_project(root)
            path = root / 'validation/CLAIM_LEDGER.json'
            claims = json.loads(path.read_text(encoding="utf-8"))
            claims['claims'][0]['text'] = 'Revised synthetic claim'
            write_json(root, 'validation/CLAIM_LEDGER.json', claims)
            report = inspect_project(root)
            checkpoint = next(c for c in report['checkpoints'] if c['stage'] == 'validation')
            self.assertEqual(checkpoint['status'], 'not_ready')
            self.assertIn('changed', checkpoint['reason'])

    def test_early_stage_does_not_require_paper_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_valid_project(root)
            state = json.loads((root / '.cumcm/state.json').read_text(encoding="utf-8"))
            state['current_stage'] = 'intake'
            write_json(root, '.cumcm/state.json', state)
            report = inspect_project(root)
            self.assertNotIn('paper_plan', report['summary']['contracts_loaded'])
            self.assertFalse(any(f['path'].startswith(('paper/', 'delivery/')) for f in report['findings']))

    def test_corrupt_missing_or_old_state_never_reported_ready(self):
        for contents in (None, '{', '[]', '{"schema_version":"0.5.0"}'):
            with self.subTest(contents=contents), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                if contents is not None:
                    (root / '.cumcm').mkdir()
                    (root / '.cumcm/state.json').write_text(contents, encoding="utf-8")
                before = snapshot(root)
                done = cli('project_status.py', '--project', str(root), '--json')
                self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
                self.assertEqual(json.loads(done.stdout)['status'], 'unavailable')
                self.assertEqual(snapshot(root), before)


if __name__ == '__main__':
    unittest.main()
