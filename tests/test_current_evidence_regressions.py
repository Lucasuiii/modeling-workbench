"""Current evidence must mean the same thing for every formal consumer."""
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from workflow_fixtures import build_valid_project, write_json
from recorder_fixtures import run_script
from canonical_evidence import resolve_official_computation
from delivery_archives import build_archives, check_archives
from build_handoff import build as handoff
from build_independent_review_package import build as review
from workflow_checks import check_project
from plan_redo import build_plan
from compile_sources import runtime_roots, observed_sources
from provenance import sha256_file


class CurrentEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); build_valid_project(self.root)
        self.runpath = 'runs/RUN-Q1-001/RUN_MANIFEST.json'
        self.run = json.loads((self.root / self.runpath).read_text())
        self.index = self.root / 'results/RESULTS_INDEX.json'
        self.delivery = {'deliverables': {'computation_source': {'archive': 'delivery/source.zip', 'entrypoint': 'code/solve.py'}}}

    def team_input(self):
        live = self.root / 'data/cleaned.csv'; live.parent.mkdir(); live.write_text('x\n1\n')
        frozen = self.root / 'runs/RUN-Q1-001/inputs/data/cleaned.csv'; frozen.parent.mkdir(parents=True); shutil.copyfile(live, frozen)
        self.run['inputs'].append({'path': frozen.relative_to(self.root).as_posix(), 'sha256': sha256_file(frozen), 'evidence_role': 'formal_input', 'frozen': True})
        write_json(self.root, self.runpath, self.run)
        return live

    def test_zip_uses_frozen_output_bytes_at_portable_member_path(self):
        rel = self.run['outputs'][0]['path']; live = '/'.join(rel.split('/')[3:])
        target = self.root / live; target.parent.mkdir(parents=True, exist_ok=True); target.write_text('wrong live output')
        build_archives(self.root, self.delivery)
        with zipfile.ZipFile(self.root / 'delivery/source.zip') as z:
            self.assertEqual(z.read(live), (self.root / rel).read_bytes())
        self.assertEqual(check_archives(self.root, self.delivery), [])

    def test_live_source_and_team_input_drift_rejected_by_all_consumers(self):
        live = self.team_input()
        findings, _ = check_project(self.root, 'computation')
        self.assertNotIn('RESULT-E018', {f.rule_id for f in findings})
        for target in (live, self.root / 'code/solve.py'):
            before = target.read_bytes(); target.write_bytes(before + b'changed')
            with self.subTest(path=str(target)):
                findings, _ = check_project(self.root, 'computation')
                self.assertIn('RUN-E020', {f.rule_id for f in findings})
                self.assertIn('RESULT-E018', {f.rule_id for f in findings})
                for consume in (lambda: resolve_official_computation(self.root), lambda: handoff(self.root, 'computation-validation'), lambda: review(self.root), lambda: build_archives(self.root, self.delivery)):
                    with self.assertRaises(ValueError): consume()
            target.write_bytes(before)

    def test_superseded_run_does_not_require_live_input_to_match_history(self):
        from workflow_checks import check_run
        live = self.team_input(); live.write_text('changed current data')
        findings = check_run(self.run, self.root, self.runpath, set(), superseded=True)
        self.assertNotIn('RUN-E020', {f.rule_id for f in findings})
        with self.assertRaisesRegex(ValueError, 'stale'):
            resolve_official_computation(self.root)

    def test_remove_last_result_is_transactional(self):
        data = json.loads(self.index.read_text()); before = self.index.read_bytes()
        done = run_script('index_result.py', '--project', str(self.root), '--remove', data['results'][0]['result_id'])
        self.assertNotEqual(done.returncode, 0); self.assertEqual(self.index.read_bytes(), before)

    def test_refresh_rechecks_current_run_locator_role_and_path(self):
        original = json.loads(self.index.read_text())
        for change in ({'run_id': 'MISSING'}, {'output_locator': '../outside.json#/x'}, {'output_locator': self.run['outputs'][0]['path'] + '#/missing'}):
            data = json.loads(json.dumps(original)); data['results'][0].update(change); write_json(self.root, 'results/RESULTS_INDEX.json', data)
            before = self.index.read_bytes()
            done = run_script('index_result.py', '--project', str(self.root), '--refresh')
            self.assertNotEqual(done.returncode, 0, change); self.assertEqual(self.index.read_bytes(), before)

    def test_new_result_cannot_bind_superseded_run(self):
        child = dict(self.run, run_id='CHILD', parent_run_id='RUN-Q1-001')
        write_json(self.root, 'runs/CHILD/RUN_MANIFEST.json', child)
        before = self.index.read_bytes()
        done = run_script('index_result.py', '--project', str(self.root), '--result-id', 'NEW', '--run', 'RUN-Q1-001', '--locator', self.run['outputs'][0]['path'] + '#', '--name', 'new', '--scope', 'test')
        self.assertNotEqual(done.returncode, 0); self.assertEqual(self.index.read_bytes(), before)

    def test_refresh_rejects_nonclaim_output_and_declared_external_path(self):
        original = json.loads(self.index.read_text())
        self.run['outputs'][0]['evidence_role'] = 'diagnostic_output'
        write_json(self.root, self.runpath, self.run)
        before = self.index.read_bytes()
        done = run_script('index_result.py', '--project', str(self.root), '--refresh')
        self.assertNotEqual(done.returncode, 0); self.assertEqual(self.index.read_bytes(), before)
        self.run['outputs'][0]['evidence_role'] = 'claim_bearing_output'
        self.run['outputs'][0]['path'] = '../outside.json'
        original['results'][0]['output_locator'] = '../outside.json#/x'
        write_json(self.root, self.runpath, self.run)
        write_json(self.root, 'results/RESULTS_INDEX.json', original)
        before = self.index.read_bytes()
        done = run_script('index_result.py', '--project', str(self.root), '--refresh')
        self.assertNotEqual(done.returncode, 0); self.assertEqual(self.index.read_bytes(), before)

    def test_successful_refresh_and_nonfinal_remove(self):
        data = json.loads(self.index.read_text())
        data['results'].append(dict(data['results'][0], result_id='SECOND'))
        write_json(self.root, 'results/RESULTS_INDEX.json', data)
        done = run_script('index_result.py', '--project', str(self.root), '--refresh')
        self.assertEqual(done.returncode, 0, done.stderr)
        done = run_script('index_result.py', '--project', str(self.root), '--remove', 'SECOND')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(json.loads(self.index.read_text())['results']), 1)

    def test_ambiguous_lineage_does_not_modify_index(self):
        for name in ('CHILD1', 'CHILD2'):
            write_json(self.root, f'runs/{name}/RUN_MANIFEST.json', dict(self.run, run_id=name, parent_run_id='RUN-Q1-001'))
        before = self.index.read_bytes()
        done = run_script('index_result.py', '--project', str(self.root), '--follow-lineage')
        self.assertNotEqual(done.returncode, 0); self.assertIn('ambiguous', done.stderr)
        self.assertEqual(self.index.read_bytes(), before)

    def test_conflicting_frozen_outputs_cannot_share_archive_member(self):
        child = json.loads(json.dumps(self.run)); child['run_id'] = 'OTHER'
        frozen = self.root / 'runs/OTHER/outputs/result.json'
        frozen.parent.mkdir(parents=True); frozen.write_text('{"restricted_policy_cost": 99}')
        child['outputs'][0].update(path='runs/OTHER/outputs/result.json', sha256=sha256_file(frozen))
        write_json(self.root, 'runs/OTHER/RUN_MANIFEST.json', child)
        data = json.loads(self.index.read_text())
        data['results'].append(dict(data['results'][0], result_id='OTHER', run_id='OTHER', output_locator='runs/OTHER/outputs/result.json#/restricted_policy_cost'))
        write_json(self.root, 'results/RESULTS_INDEX.json', data)
        with self.assertRaisesRegex(ValueError, 'conflicting frozen evidence'):
            build_archives(self.root, self.delivery)
        self.assertFalse((self.root / 'delivery/source.zip').exists())

    def test_contract_changes_propagate_conservatively(self):
        for path, stage in [('model/MODEL_CONTRACT.json', 'computation'), ('results/RESULTS_INDEX.json', 'validation'), ('validation/CLAIM_LEDGER.json', 'paper'), ('paper/PAPER_PLAN.json', 'paper'), ('paper/LATEX_TEMPLATE_MANIFEST.json', 'paper')]:
            with self.subTest(path=path):
                plan = build_plan(self.root, [path]); self.assertIn(stage, plan['actions']); self.assertIn('delivery', plan['actions'])

    def test_personal_font_roots_do_not_admit_arbitrary_home_files(self):
        with patch('compile_sources.Path.home', return_value=self.root), patch('compile_sources.shutil.which', return_value=None):
            roots = runtime_roots()
        self.assertIn(self.root / 'Library/Fonts', roots)
        self.assertIn(self.root / '.local/share/fonts', roots)
        self.assertNotIn(self.root, roots)
        font = self.root / 'Library/Fonts/test.ttf'; font.parent.mkdir(parents=True); font.write_bytes(b'font')
        project = self.root / 'font-project'; project.mkdir()
        fls = project / 'main.fls'; fls.write_text(f'INPUT {font}\n')
        self.assertEqual(observed_sources(project, project, fls, roots), set())
        outside = self.root / 'other.ttf'; outside.write_bytes(b'font')
        fls.write_text(f'INPUT {outside}\n')
        with self.assertRaisesRegex(ValueError, 'external project dependency'):
            observed_sources(project, project, fls, roots)
