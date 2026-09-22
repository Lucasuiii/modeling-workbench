"""Regression cases for canonical values and exact review/delivery contents."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from workflow_fixtures import build_valid_project, write_json
from recorder_fixtures import run_script
from canonical_evidence import resolve_official_computation
from build_handoff import build as handoff
from build_independent_review_package import build as review
from delivery_archives import build_archives, check_archives
from plan_redo import build_plan
from provenance import sha256_file
from workflow_checks import check_independent_review_package, check_schema


class RemainingBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve(); build_valid_project(self.root)

    def test_value_mismatch_rejected_by_consumers_but_refresh_repairs(self):
        path = self.root / 'results/RESULTS_INDEX.json'
        data = json.loads(path.read_text()); original = data['results'][0]['value']
        data['results'][0]['value'] = 'wrong value'
        write_json(self.root, 'results/RESULTS_INDEX.json', data)
        for consumer in (lambda: resolve_official_computation(self.root), lambda: handoff(self.root, 'computation-validation'), lambda: review(self.root, refresh=True)):
            with self.assertRaisesRegex(ValueError, 'value'):
                consumer()
        done = run_script('index_result.py', '--project', str(self.root), '--refresh')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(path.read_text())['results'][0]['value'], original)
        self.assertTrue(resolve_official_computation(self.root))

    def test_zip_rejects_safe_undeclared_extra(self):
        manifest = {'deliverables': {'computation_source': {'archive': 'delivery/source.zip', 'entrypoint': 'code/solve.py'}}}
        build_archives(self.root, manifest)
        self.assertEqual(check_archives(self.root, manifest), [])
        with zipfile.ZipFile(self.root / 'delivery/source.zip', 'a') as archive:
            archive.writestr('private-notes.txt', 'not declared')
        self.assertTrue(any('unexpected' in problem for problem in check_archives(self.root, manifest)))

    def test_contract_only_change_does_not_recommend_follow_lineage(self):
        result = build_plan(self.root, ['results/RESULTS_INDEX.json'])
        actions = ' '.join(result['actions'].get('computation', []))
        self.assertNotIn('--follow-lineage', actions)
        self.assertIn('revalidate', actions)
        changed_run = build_plan(self.root, ['code/solve.py'])
        self.assertIn('--follow-lineage', ' '.join(changed_run['actions']['computation']))

    def test_team_formal_input_role_schema_checker_and_digest(self):
        live = self.root / 'data/team.csv'; live.parent.mkdir(); live.write_text('x\n1\n')
        frozen = self.root / 'runs/RUN-Q1-001/inputs/data/team.csv'; frozen.parent.mkdir(parents=True); frozen.write_bytes(live.read_bytes())
        manifest_path = self.root / 'runs/RUN-Q1-001/RUN_MANIFEST.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['inputs'].append({'path': frozen.relative_to(self.root).as_posix(), 'sha256': sha256_file(frozen), 'evidence_role': 'formal_input', 'frozen': True})
        write_json(self.root, manifest_path.relative_to(self.root).as_posix(), manifest)
        path = review(self.root, refresh=True)
        package = json.loads(path.read_text())
        record = next(item for item in package['files'] if item.get('source_path') == frozen.relative_to(self.root).as_posix())
        self.assertEqual(record['role'], 'formal_input')
        self.assertEqual(check_schema(package, 'independent_review_package', 'validation', str(path)), [])
        self.assertFalse([f for f in check_independent_review_package(package, self.root, str(path)) if f.severity == 'error' and not f.gate_only])
        record['role'] = 'run_record'
        self.assertTrue(any(f.rule_id == 'IREVIEW-E003' for f in check_independent_review_package(package, self.root, str(path))))
