"""Execution-backed regressions for compile evidence and declared redo scope."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from recorder_fixtures import make_project, write_json, envelope, run_script, MINIMAL_TEX
from test_paper_pipeline import build_paper_ready_project
from plan_redo import build_plan
from provenance import sha256_file
from workflow_checks import check_paper_quality
from delivery_archives import build_archives
import record_compile as rc
from compile_sources import observed_sources


class RedoRegressionTests(unittest.TestCase):
    def test_split_and_shared_sections_are_all_affected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_paper_ready_project(root)
            plan = json.loads((root / 'paper/PAPER_PLAN.json').read_text())
            plan['paper_structure'] = [{'subproblem_ids': ['Q1'], 'claim_ids': ['CLM-Q1-001']}]
            write_json(root, 'paper/PAPER_PLAN.json', plan)
            write_json(root, 'paper/LATEX_TEMPLATE_MANIFEST.json', {'subproblem_sections': [
                {'subproblem_id': 'Q1', 'path': 'paper/a.tex'},
                {'subproblem_id': 'Q1', 'path': 'paper/shared.tex'},
                {'subproblem_id': 'Q2', 'path': 'paper/shared.tex'},
                {'subproblem_id': 'Q2', 'path': 'paper/b.tex'}]})
            result = build_plan(root, ['code/solve.py'])
            self.assertEqual(result['stale_sections'], ['paper/a.tex', 'paper/shared.tex'])
            self.assertEqual(result['unaffected']['paper'], ['paper/b.tex'])

    def test_transitive_run_inputs_and_unrelated_branch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for rid, inputs in [('A', []), ('B', ['runs/A/outputs/results/A.json']),
                                ('C', ['results/B.json']), ('D', [])]:
                write_json(root, f'runs/{rid}/RUN_MANIFEST.json', {
                    'run_id': rid, 'official_run': True, 'status': 'completed', 'exit_code': 0,
                    'implementation': {'source_snapshot': {'files': [f'runs/{rid}/source/code/{rid}.py']}},
                    'inputs': [{'path': p, 'evidence_role': 'formal_input'} for p in inputs],
                    'outputs': [{'path': f'runs/{rid}/outputs/results/{rid}.json', 'evidence_role': 'claim_bearing_output'}]})
            result = build_plan(root, ['code/A.py'])
            self.assertEqual(result['stale_official_runs'], ['A', 'B', 'C'])
            self.assertEqual(result['unaffected']['computation'], ['D'])
            self.assertIn('refresh input bindings for B', '\n'.join(result['actions']['computation']))
            self.assertEqual(build_plan(root, ['scratch.txt'])['stale_official_runs'], [])


@unittest.skipIf(shutil.which('xelatex') is None, 'xelatex is not installed')
class CompileRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = make_project(Path(self.temp.name))
        (self.root / 'paper/main.tex').write_text(MINIMAL_TEX)
        write_json(self.root, 'paper/LATEX_TEMPLATE_MANIFEST.json', {
            'engine': 'xelatex', 'main_path': 'paper/main.tex', 'required_files': ['paper/main.tex']})

    def compile(self, *args):
        result = run_script('record_compile.py', '--project', str(self.root), *args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads((self.root / 'delivery/COMPILE_RECEIPT.json').read_text())

    def quality(self, digest):
        artifact = {'path': 'paper/main.pdf', 'sha256': digest}
        data = envelope('paper_quality_report')
        data.update({'paper_status': 'final', 'paper_artifact': artifact, 'open_issues': [],
                     'content_report': {'artifact': artifact, 'summary': 'fixture', 'questions': []},
                     'layout_report': {'artifact': artifact, 'page_count': 1, 'rendered_pages': [1], 'checks': [
                         {'check_id': 'FIG-OVERLAP', 'category': 'figure', 'status': 'fail', 'notes': 'unresolved'},
                         {'check_id': 'VISUAL', 'category': 'other', 'status': 'pass', 'notes': 'previous inspection'}]}})
        write_json(self.root, 'paper/PAPER_QUALITY_REPORT.json', data)

    def test_final_log_resolves_first_pass_reference_but_keeps_real_failure(self):
        (self.root / 'paper/main.tex').write_text(r'\documentclass{article}\begin{document}See \ref{x}.\section{X}\label{x}\end{document}')
        receipt = self.compile()
        self.assertNotIn('undefined', ' '.join(receipt['attempts'][0]['warnings']))
        self.assertIn('undefined', (self.root / 'delivery/compile.log').read_text())
        (self.root / 'paper/main.tex').write_text(r'\documentclass{article}\begin{document}See \ref{missing} and \cite{absent}.\end{document}')
        receipt = self.compile()
        self.assertIn('undefined', ' '.join(receipt['attempts'][0]['warnings']))

    def test_no_render_clears_pages_and_preserves_failed_and_stale_visual_checks(self):
        self.compile()
        self.quality(sha256_file(self.root / 'paper/main.pdf'))
        (self.root / 'paper/main.tex').write_text(MINIMAL_TEX.replace('\\end{document}', 'Changed.\\end{document}'))
        self.compile('--no-render', '--update-quality')
        quality = json.loads((self.root / 'paper/PAPER_QUALITY_REPORT.json').read_text())
        self.assertEqual(quality['layout_report']['rendered_pages'], [])
        self.assertFalse((self.root / '.cumcm/tmp/pages').exists())
        checks = {c['check_id']: c for c in quality['layout_report']['checks']}
        self.assertEqual(checks['FIG-OVERLAP']['status'], 'fail')
        # Even if content is reviewed and pages subsequently rendered, the old
        # visual pass still cannot vouch for this new PDF.
        quality['content_report']['artifact'] = quality['paper_artifact']
        quality['layout_report']['rendered_pages'] = [1]
        findings = check_paper_quality(quality, self.root, 'paper/PAPER_QUALITY_REPORT.json', set())
        self.assertTrue(any(f.rule_id == 'PQUALITY-E004' for f in findings))
        for check in quality['layout_report']['checks']:
            if 'artifact' in check:
                check['artifact'] = quality['paper_artifact']
        findings = check_paper_quality(quality, self.root, 'paper/PAPER_QUALITY_REPORT.json', set())
        self.assertFalse(any(f.rule_id == 'PQUALITY-E004' for f in findings))

    def test_preserved_visual_pass_requires_its_own_current_binding(self):
        self.compile('--no-render')
        self.quality(sha256_file(self.root / 'paper/main.pdf'))
        quality = json.loads((self.root / 'paper/PAPER_QUALITY_REPORT.json').read_text())
        check = quality['layout_report']['checks'][1]
        check['artifact'] = {'path': 'paper/main.pdf', 'sha256': '0' * 64}
        findings = check_paper_quality(quality, self.root, 'paper/PAPER_QUALITY_REPORT.json', set())
        self.assertTrue(any(f.rule_id == 'PQUALITY-E004' for f in findings))
        check['artifact'] = quality['paper_artifact']
        findings = check_paper_quality(quality, self.root, 'paper/PAPER_QUALITY_REPORT.json', set())
        self.assertFalse(any(f.rule_id == 'PQUALITY-E004' for f in findings))

    def test_render_failure_does_not_reuse_previous_pages(self):
        self.compile()
        self.quality(sha256_file(self.root / 'paper/main.pdf'))
        with patch.object(sys, 'argv', ['record_compile.py', '--project', str(self.root), '--update-quality']), patch.object(rc, 'render_pages', return_value=[]):
            self.assertEqual(rc.main(), 0)
        quality = json.loads((self.root / 'paper/PAPER_QUALITY_REPORT.json').read_text())
        self.assertEqual(quality['layout_report']['rendered_pages'], [])
        self.assertTrue(any(c['check_id'] == 'FIG-OVERLAP' for c in quality['layout_report']['checks']))

    def test_actual_inputs_are_bound_packaged_and_compile_after_extraction(self):
        self.compile('--no-render')
        (self.root / 'figures').mkdir(exist_ok=True)
        shutil.copy2(self.root / 'paper/main.pdf', self.root / 'figures/plot.pdf')
        paper = self.root / 'paper'
        (paper / 'nested').mkdir()
        (paper / 'nested/included.tex').write_text('Actual included chapter.\n')
        (paper / 'unused.tex').write_text('Unused file.\n')
        (paper / 'main.tex').write_text(r'\documentclass{article}\usepackage{graphicx}\begin{document}\input{nested/included}\includegraphics[width=1cm]{../figures/plot.pdf}\end{document}')
        receipt = self.compile('--no-render')
        self.assertIn('paper/nested/included.tex', receipt['source_snapshot']['files'])
        self.assertNotIn('paper/unused.tex', receipt['source_snapshot']['files'])
        self.assertIn('figures/plot.pdf', receipt['source_snapshot']['files'])
        self.assertIn('delivery', build_plan(self.root, ['figures/plot.pdf'])['actions'])
        # This test has no formal result chain; only a real editable paper.
        (self.root / 'results/RESULTS_INDEX.json').unlink(missing_ok=True)
        manifest = {'files': [], 'deliverables': {'editable_latex_source': {'archive': 'delivery/source.zip', 'entrypoint': 'paper/main.tex'}}}
        build_archives(self.root, manifest)
        import zipfile, subprocess
        with tempfile.TemporaryDirectory() as extracted:
            with zipfile.ZipFile(self.root / 'delivery/source.zip') as archive:
                archive.extractall(extracted)
            result = subprocess.run(['xelatex', '-halt-on-error', '-interaction=nonstopmode', 'main.tex'], cwd=Path(extracted) / 'paper', capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout.decode(errors='replace'))
        (paper / 'nested/included.tex').write_text('Changed dependency.\n')
        with self.assertRaisesRegex(ValueError, 'stale'):
            build_archives(self.root, manifest)
        self.assertIn('delivery', build_plan(self.root, ['paper/nested/included.tex'])['actions'])

    def test_failed_new_compile_retires_successful_receipt(self):
        self.compile()
        (self.root / 'paper/main.tex').write_text(r'\documentclass{article}\begin{document}\undefinedcommand\end{document}')
        result = run_script('record_compile.py', '--project', str(self.root))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'delivery/COMPILE_RECEIPT.json').exists())
        self.assertTrue(list((self.root / 'delivery').glob('compile-*/COMPILE_RECEIPT.json')))

    def test_source_mutation_between_discovery_and_final_pass_is_rejected(self):
        original = observed_sources
        calls = 0
        def mutate(*args):
            nonlocal calls
            found = original(*args)
            calls += 1
            if calls == 2:
                with (self.root / 'paper/main.tex').open('a') as stream:
                    stream.write('% drift\n')
            return found
        with patch.object(sys, 'argv', ['record_compile.py', '--project', str(self.root)]), patch.object(rc, 'observed_sources', side_effect=mutate, create=True):
            self.assertEqual(rc.main(), 1)
        self.assertFalse((self.root / 'delivery/COMPILE_RECEIPT.json').exists())


class MissingEvidenceTests(unittest.TestCase):
    def test_page_count_cannot_be_invented_without_parser(self):
        with tempfile.TemporaryDirectory() as temp:
            pdf = Path(temp) / 'fake.pdf'
            pdf.write_bytes(b'/Type /Page')
            with patch.object(rc.shutil, 'which', return_value=None):
                with self.assertRaisesRegex(ValueError, 'page count'):
                    rc.page_count(pdf)

    def test_external_custom_input_is_not_misclassified_as_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fls = root / 'main.fls'
            fls.write_text('INPUT /some/external/custom.tex\n')
            with self.assertRaisesRegex(ValueError, 'external project dependency'):
                observed_sources(root, root, fls, [])
