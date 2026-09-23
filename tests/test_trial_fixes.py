"""Behavioral regressions from the two local trials; only synthetic workspaces."""
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from recorder_fixtures import make_project, run_script, write_json, SCRIPTS
from workflow_fixtures import build_valid_project, write_accepted_snapshot
from workflow_checks import check_project, check_delivery, check_model_verification, require_human_checkpoint
from delivery_archives import build_archives, check_archives
from build_handoff import build as build_handoff


class HumanStops(unittest.TestCase):
    def test_self_review_blocks_official_execution_but_not_exploration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            path = root / 'model/MODEL_CONTRACT.json'
            model = json.loads(path.read_text(encoding="utf-8"))
            model['selection_check']['reviewer_kind'] = 'same_context_model'
            path.write_text(json.dumps(model), encoding="utf-8")
            for mode in ('working', 'finalizing'):
                state = json.loads((root / '.cumcm/state.json').read_text(encoding="utf-8"))
                state['mode'] = mode
                write_json(root, '.cumcm/state.json', state)
                findings, summary = check_project(root, 'model-design', 'enforce')
                self.assertIn('MODEL-E016', {f.rule_id for f in findings})
                self.assertGreater(summary['blocking_error_count'], 0)
            done = run_script('record_run.py', '--project', str(root), '--official', '--', sys.executable, 'code/solve.py')
            self.assertNotEqual(done.returncode, 0)
            self.assertFalse((root / 'results/q1_output.json').exists())
            done = run_script('record_run.py', '--project', str(root), '--', sys.executable, 'code/solve.py')
            self.assertEqual(done.returncode, 0, done.stderr)

    def test_preflight_reports_pending_review_without_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            path = root / 'model/MODEL_CONTRACT.json'
            data = json.loads(path.read_text(encoding="utf-8")); data['selection_check']['decision'] = 'unreviewed'
            path.write_text(json.dumps(data), encoding="utf-8")
            _, report = check_project(root, 'model-design', 'preflight')
            self.assertEqual(report['gate_status'], 'awaiting_review')
            self.assertEqual(report['blocking_error_count'], 0)

    def test_confirmation_fills_checkpoint_and_advances_without_manual_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            state = json.loads((root / '.cumcm/state.json').read_text(encoding="utf-8"))
            for stage in ('intake', 'problem-analysis'):
                state['stages'][stage] = 'passed'
            write_json(root, '.cumcm/state.json', state)
            model = json.loads((root / 'model/MODEL_CONTRACT.json').read_text(encoding="utf-8"))
            model['selection_check']['decision'] = 'unreviewed'
            model['components'][0]['candidates'] = [{'candidate_id': 'CAND-ENUM', 'status': 'selected'}]
            write_json(root, 'model/MODEL_CONTRACT.json', model)
            done = run_script('record_decision.py', '--project', str(root), '--stage', 'model-design',
                              '--decision', 'accepted', '--confirm-human', '--task-turn-ref', 'user-turn-2',
                              '--summary', 'User accepted both presented candidates and scope')
            self.assertEqual(done.returncode, 0, done.stderr)
            state = json.loads((root / '.cumcm/state.json').read_text(encoding="utf-8"))
            self.assertEqual(state['current_stage'], 'computation')
            self.assertEqual(state['stages']['model-design'], 'passed')
            require_human_checkpoint(root, 'model-design')
            model = json.loads((root / 'model/MODEL_CONTRACT.json').read_text(encoding="utf-8"))
            model['components'][0]['scope'] += ' changed'
            write_json(root, 'model/MODEL_CONTRACT.json', model)
            with self.assertRaisesRegex(ValueError, 'changed after approval'):
                require_human_checkpoint(root, 'model-design')
            with self.assertRaisesRegex(ValueError, 'changed after approval'):
                build_handoff(root, 'modeling-computation')

    def test_stale_acceptance_cannot_be_rebound_and_reopen_requires_new_reply(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            command = ('--project', str(root), '--stage', 'model-design', '--decision', 'accepted',
                       '--task-turn-ref', 'user-turn', '--summary', 'accepted')
            self.assertEqual(run_script('record_decision.py', *command).returncode, 0)
            path = root / 'model/MODEL_CONTRACT.json'
            model = json.loads(path.read_text(encoding="utf-8")); model['components'][0]['scope'] += ' changed'
            model['components'][0]['candidates'] = [{'candidate_id': 'CAND-ENUM', 'status': 'selected'}]
            write_json(root, 'model/MODEL_CONTRACT.json', model)
            self.assertNotEqual(run_script('record_decision.py', *command).returncode, 0)
            reopened = run_script('record_decision.py', '--project', str(root), '--stage', 'model-design',
                                  '--decision', 'revision_requested', '--task-turn-ref', 'turn2', '--summary', 'revise')
            self.assertEqual(reopened.returncode, 0, reopened.stderr)
            with self.assertRaisesRegex(ValueError, 'explicit decision'):
                require_human_checkpoint(root, 'model-design')
            self.assertNotEqual(run_script('record_decision.py', *command).returncode, 0)
            done = run_script('record_decision.py', *command, '--confirm-human')
            self.assertEqual(done.returncode, 0, done.stderr)
            require_human_checkpoint(root, 'model-design')

    def test_approval_detects_changed_files_elsewhere_in_existing_scope(self):
        from workflow_checks import sha256
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            paths = ['model/MODEL_CONTRACT.json', 'code/solve.py']
            write_json(root, '.cumcm/snapshots/model-design.json', {
                'artifacts': [{'path': rel, 'sha256': sha256(root / rel)} for rel in paths]})
            require_human_checkpoint(root, 'model-design')
            (root / 'code/solve.py').write_text('changed', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, 'changed after approval'):
                require_human_checkpoint(root, 'model-design')

    def test_delivery_requires_human_review(self):
        from workflow_checks import check_final_check
        for kind in ('same_context_model', 'fresh_context_model', 'human_user'):
            data = {'final_check': {'decision': 'accepted', 'reviewer_kind': kind,
                    'reviewer': 'reviewer', 'reviewed_at': '2026-09-07', 'presented_pages': [1]}}
            findings = check_final_check(data, 'delivery', {'page_count': 1})
            self.assertEqual(any(f.rule_id == 'DELIVERY-E011' for f in findings), kind != 'human_user')

    def test_failed_confirmation_does_not_change_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            path = root / 'model/MODEL_CONTRACT.json'; before = path.read_bytes()
            done = run_script('record_decision.py', '--project', str(root), '--stage', 'model-design',
                              '--decision', 'accepted', '--confirm-human', '--scope', 'missing.json',
                              '--task-turn-ref', 'user-turn', '--summary', 'accepted')
            self.assertNotEqual(done.returncode, 0)
            self.assertEqual(before, path.read_bytes())
            self.assertFalse((root / '.cumcm/decisions.jsonl').exists())

    def test_self_review_and_open_p0_cannot_build_paper_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); build_valid_project(root)
            path = root / 'validation/CLAIM_LEDGER.json'; claims = json.loads(path.read_text(encoding="utf-8"))
            claims['conclusion_check']['reviewer_kind'] = 'same_context_model'
            path.write_text(json.dumps(claims), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, 'explicit decision'):
                build_handoff(root, 'validation-paper', 'reviewer-task')
            claims['conclusion_check']['reviewer_kind'] = 'human_user'; path.write_text(json.dumps(claims), encoding="utf-8")
            write_accepted_snapshot(root, 'validation', ['validation/CLAIM_LEDGER.json'])
            review = json.loads((root / 'validation/INDEPENDENT_REVIEW_RESULT.json').read_text(encoding="utf-8"))
            review['verdict'] = 'revision_required'
            write_json(root, 'validation/INDEPENDENT_REVIEW_RESULT.json', review)
            with self.assertRaisesRegex(ValueError, 'validation is blocked'):
                build_handoff(root, 'validation-paper', 'reviewer-task')


class RecorderAndRefresh(unittest.TestCase):
    def test_parallel_decisions_allocate_unique_ids_and_leave_consistent_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            commands = [
                [sys.executable, str(SCRIPTS / 'record_decision.py'), '--project', str(root),
                 '--stage', 'model-design', '--decision', 'accepted', '--confirm-human',
                 '--task-turn-ref', f'user-turn-{index}', '--summary', f'accepted {index}']
                for index in (1, 2)
            ]
            children = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for command in commands]
            for child in children:
                out, err = child.communicate(timeout=30)
                self.assertEqual(child.returncode, 0, out.decode() + err.decode())
            events = [json.loads(line) for line in (root / '.cumcm/decisions.jsonl').read_text(encoding="utf-8").splitlines()]
            ids = [event['decision_id'] for event in events]
            self.assertEqual(len(ids), 2)
            self.assertEqual(len(set(ids)), 2)
            snapshot = json.loads((root / '.cumcm/snapshots/model-design.json').read_text(encoding="utf-8"))
            state = json.loads((root / '.cumcm/state.json').read_text(encoding="utf-8"))
            checkpoint = json.loads((root / 'model/MODEL_CONTRACT.json').read_text(encoding="utf-8"))
            self.assertIn(snapshot['decision_id'], ids)
            self.assertEqual(state['stages']['model-design'], 'passed')
            self.assertEqual(checkpoint['selection_check']['decision'], 'accepted')

    def test_parallel_runs_reserve_distinct_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp))
            (root / 'code/a.py').write_text("import time; time.sleep(.2); print('A')", encoding="utf-8")
            (root / 'code/b.py').write_text("import time; time.sleep(.2); print('B')", encoding="utf-8")
            children = [subprocess.Popen([sys.executable, str(SCRIPTS / 'record_run.py'), '--project', str(root),
                         '--', sys.executable, f'code/{name}.py'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        for name in ('a', 'b')]
            for child in children:
                out, err = child.communicate(timeout=30)
                self.assertEqual(child.returncode, 0, err.decode())
            manifests = list((root / 'runs').glob('*/RUN_MANIFEST.json'))
            self.assertEqual(len(manifests), 2)
            self.assertEqual({(p.parent / 'stdout.log').read_text(encoding="utf-8").strip() for p in manifests}, {'A', 'B'})

    def test_existing_unfinished_run_is_never_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp)); reserved = root / 'runs/RUN-001'; reserved.mkdir(parents=True)
            (reserved / 'stdout.log').write_text('preserve', encoding="utf-8")
            done = run_script('record_run.py', '--project', str(root), '--', sys.executable, 'code/solve.py')
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertTrue((root / 'runs/RUN-002/RUN_MANIFEST.json').exists())
            self.assertEqual((reserved / 'stdout.log').read_text(encoding="utf-8"), 'preserve')

    def test_refresh_is_idempotent_and_never_rebaselines_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_project(Path(tmp)); source = root / 'problem/SOURCE_MANIFEST.json'
            before = source.read_bytes()
            write_json(root, 'delivery/DELIVERY_MANIFEST.json', {'files': []})
            delivery = root / 'delivery/DELIVERY_MANIFEST.json'; initial = delivery.read_bytes()
            (root / 'problem/official/problem.txt').write_text('modified official bytes', encoding="utf-8")
            done = run_script('refresh_evidence.py', '--project', str(root))
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(delivery.read_bytes(), initial)

    def test_refresh_rejects_traversal_and_absolute_paths_outside_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = make_project(base)
            outside = base / 'outside.txt'
            outside.write_text('private', encoding="utf-8")
            for declared in ('../outside.txt', str(outside.resolve())):
                with self.subTest(path=declared):
                    write_json(root, 'delivery/DELIVERY_MANIFEST.json', {
                        'files': [{'path': declared, 'sha256': 'stale', 'size': 0}]
                    })
                    before = (root / 'delivery/DELIVERY_MANIFEST.json').read_bytes()
                    done = run_script('refresh_evidence.py', '--project', str(root), '--only', 'delivery')
                    self.assertNotEqual(done.returncode, 0)
                    self.assertIn('outside project', done.stderr)
                    self.assertEqual((root / 'delivery/DELIVERY_MANIFEST.json').read_bytes(), before)

    def test_structured_verification_plan_matches_assertion_name(self):
        model = {'components': [{'model_id': 'M', 'capability_ids': ['C'],
                 'verification_plan': [{'assertion_name': 'nonzero_failure_case', 'method': 'hand calculation'}]}]}
        self.assertEqual(check_model_verification(model, {'C': {'nonzero_failure_case'}}, 'model'), [])
        self.assertIn('MODEL-W010', {x.rule_id for x in check_model_verification(model, {'C': {'other_check'}}, 'model')})


class ActualArchives(unittest.TestCase):
    def test_declared_archives_are_not_recursively_packaged_and_editable_files_are_included(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'paper').mkdir(); (root / 'delivery').mkdir()
            (root / 'paper/main.tex').write_text('main', encoding="utf-8")
            (root / 'paper/figure.pdf').write_bytes(b'figure')
            manifest = {'deliverables': {
                'computation_source': {'archive': 'delivery/all.zip'},
                'editable_latex_source': {'archive': 'delivery/all.zip', 'entrypoint': 'paper/main.tex'}},
                'files': [{'path': 'delivery/all.zip', 'role': 'computation_source'},
                          {'path': 'paper/figure.pdf', 'role': 'editable_latex_source'}]}
            build_archives(root, manifest)
            build_archives(root, manifest)
            self.assertEqual(check_archives(root, manifest), [])
            with zipfile.ZipFile(root / 'delivery/all.zip') as archive:
                self.assertEqual(set(archive.namelist()), {'paper/main.tex', 'paper/figure.pdf'})

    def test_flattened_missing_and_stale_members_fail_then_packaged_program_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for directory in ('code', 'data', 'results', 'paper/figures', 'delivery'):
                (root / directory).mkdir(parents=True)
            (root / 'code/solve.py').write_text("from pathlib import Path\np=Path(__file__).resolve().parents[1]\nprint((p/'data/input.txt').read_text(encoding='utf-8'))\n", encoding="utf-8")
            (root / 'data/input.txt').write_text('42', encoding="utf-8")
            (root / 'paper/figures/plot.py').write_text('# plotting source', encoding="utf-8")
            manifest = {'deliverables': {'computation_source': {'entrypoint': 'code/solve.py', 'archive': 'delivery/support.zip'}},
                        'files': [{'path': 'code/solve.py', 'role': 'computation_source'},
                                  {'path': 'data/input.txt', 'role': 'supporting_evidence'}]}
            with zipfile.ZipFile(root / 'delivery/support.zip', 'w') as z:
                z.write(root / 'code/solve.py', 'solve.py')
                z.write(root / 'data/input.txt', 'input.txt')
            problems = check_archives(root, manifest)
            self.assertTrue(any('code/solve.py' in x for x in problems))
            self.assertTrue(any('plot.py' in x for x in problems))
            self.assertIn('DELIVERY-E021', {f.rule_id for f in check_delivery(manifest, root, 'delivery')})
            write_json(root, '.cumcm/state.json', {'mode': 'working'})
            self.assertEqual({f.severity for f in check_delivery(manifest, root, 'delivery') if f.rule_id == 'DELIVERY-E021'}, {'warning'})
            write_json(root, '.cumcm/state.json', {'mode': 'finalizing'})
            self.assertEqual({f.severity for f in check_delivery(manifest, root, 'delivery') if f.rule_id == 'DELIVERY-E021'}, {'error'})
            write_json(root, 'delivery/DELIVERY_MANIFEST.json', manifest)
            done = run_script('refresh_evidence.py', '--project', str(root), '--only', 'delivery', '--package')
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(check_archives(root, manifest), [])
            refreshed = json.loads((root / 'delivery/DELIVERY_MANIFEST.json').read_text(encoding="utf-8"))
            self.assertTrue(all(f.get('sha256') for f in refreshed['files']))
            with zipfile.ZipFile(root / 'delivery/support.zip') as z:
                z.extractall(root / 'clean')
            done = subprocess.run([sys.executable, str(root / 'clean/code/solve.py')], capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stdout.strip(), '42')
            (root / 'data/input.txt').write_text('43', encoding="utf-8")
            self.assertTrue(any('stale member data/input.txt' in x for x in check_archives(root, manifest)))
