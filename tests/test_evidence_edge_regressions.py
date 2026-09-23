"""Focused regressions for dependency mapping, JSON pointers and runtime scope."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow_fixtures import write_json
from test_latex_template import build_inputs
from init_latex_paper import initialize
from plan_redo import build_plan
from index_result import resolve_pointer
from workflow_checks import resolve_json_pointer
from official_materials import classify_official_material
from compile_sources import runtime_roots, observed_sources


class RequestedRegressions(unittest.TestCase):
    def test_claim_only_section_has_explicit_mapping_and_is_stale(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_inputs(root)
            plan = json.loads((root / 'paper/PAPER_PLAN.json').read_text(encoding="utf-8"))
            plan['paper_structure'].append({'section_id': 'SYNTHESIS', 'title': 'Synthesis',
                'purpose': 'interpret result', 'subproblem_ids': [], 'claim_ids': ['C1']})
            write_json(root, 'paper/PAPER_PLAN.json', plan)
            # Restore the synthetic checkpoint after intentionally changing the fixture plan.
            from workflow_fixtures import write_accepted_snapshot
            write_accepted_snapshot(root, 'validation', ['validation/CLAIM_LEDGER.json'])
            manifest = json.loads(initialize(root, 'Demand model', 2026, 'demand').read_text(encoding="utf-8"))
            write_json(root, 'runs/R1/RUN_MANIFEST.json', {'run_id': 'R1', 'official_run': True,
                'implementation': {'source_snapshot': {'files': ['code/solve.py']}}})
            write_json(root, 'validation/CLAIM_LEDGER.json', {'claims': [{'claim_id': 'C1', 'evidence': {'run_ids': ['R1']}}]})
            result = build_plan(root, ['code/solve.py'])
            self.assertIn('paper/sections/30_synthesis.tex', result['stale_sections'])
            self.assertIn({'section_id': 'SYNTHESIS', 'path': 'paper/sections/30_synthesis.tex'}, manifest['section_paths'])
            # Resolve an explicitly relocated section; do not guess from its ID or order.
            old = 'paper/sections/30_synthesis.tex'
            new = 'paper/sections/custom-discussion.tex'
            manifest['section_files'] = [new if p == old else p for p in manifest['section_files']]
            manifest['section_paths'][-1]['path'] = new
            write_json(root, 'paper/LATEX_TEMPLATE_MANIFEST.json', manifest)
            self.assertEqual(build_plan(root, ['code/solve.py'])['stale_sections'], [new])
            # Incomplete older manifests must not label the claim-only section safe.
            del manifest['section_paths']
            write_json(root, 'paper/LATEX_TEMPLATE_MANIFEST.json', manifest)
            self.assertIn(new, build_plan(root, ['code/solve.py'])['stale_sections'])


    def test_pointer_empty_tokens_and_escapes(self):
        data = {'': {'foo': 7}, 'a/b': {'~key': 9}, '01': 5}
        for pointer, expected in [('', data), ('/', data['']), ('//foo', 7), ('/a~1b/~0key', 9), ('/01', 5)]:
            with self.subTest(pointer=pointer):
                self.assertEqual(resolve_pointer(data, pointer), expected)
                self.assertEqual(resolve_json_pointer(data, pointer), (expected, True))

    def test_invalid_array_indices_and_pointer_syntax(self):
        for pointer in ['/01', '/-1', '/-', '/١', '/²', '0', '/~2', '/~', '/' + '9' * 5000]:
            with self.subTest(pointer=pointer):
                with self.assertRaises(SystemExit):
                    resolve_pointer([1, 2], pointer)
                self.assertEqual(resolve_json_pointer([1, 2], pointer), (None, False))
        self.assertEqual(resolve_json_pointer({'~2': 1}, '/~2'), (None, False))
        self.assertEqual(resolve_pointer({'~1': 3}, '/~01'), 3)
        self.assertEqual(resolve_pointer([1, 2], '/0'), 1)
        self.assertEqual(resolve_json_pointer([1, 2], '/1'), (2, True))

    def test_nonpaper_templates_and_rules_are_not_authority(self):
        for role in ['data_template', '数据模板', 'business_rules', 'data_format', '数据规则']:
            with self.subTest(role=role):
                self.assertIsNone(classify_official_material({'origin': 'official', 'path': 'data.csv', 'authoritative_for': [role]}))
        for role in ['paper_template', 'submission_template', 'format_template', '论文模板']:
            self.assertEqual(classify_official_material({'origin': 'official', 'authoritative_for': [role]}), 'paper_template')
        self.assertEqual(classify_official_material({'origin': 'official', 'authoritative_for': ['submission_rules']}), 'format_or_submission_rule')

    def test_texmfhome_is_runtime_but_other_external_files_still_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp).resolve()
            root = base / 'project'; root.mkdir()
            home = base / 'Library/texmf'; home.mkdir(parents=True)
            (home / 'personal.sty').write_text('style', encoding="utf-8")
            (root / 'main.tex').write_text('source', encoding="utf-8")
            fls = root / 'main.fls'
            fls.write_text(f'INPUT {root / "main.tex"}\nINPUT {home / "personal.sty"}\n', encoding="utf-8")
            def query(argv, **kwargs):
                return subprocess.CompletedProcess(argv, 0, stdout=str(home) if argv[-1] == '-var-value=TEXMFHOME' else '')
            with patch('compile_sources.shutil.which', return_value='/bin/kpsewhich'), patch('compile_sources.subprocess.run', side_effect=query):
                roots = runtime_roots()
            self.assertEqual(observed_sources(root, root, fls, roots), {'main.tex'})
            outside = base / 'outside.sty'; outside.write_text('external', encoding="utf-8")
            fls.write_text(f'INPUT {outside}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, 'external project dependency'):
                observed_sources(root, root, fls, roots)
