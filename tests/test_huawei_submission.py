"""Synthetic contest rules test mechanics, not organizer-format certification."""
from __future__ import annotations
import copy
import json
import locale
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from workflow_fixtures import write_json
from recorder_fixtures import run_script
from test_latex_template import build_inputs
from init_latex_paper import initialize
from submission_check import inspect_submission, check_submission, is_huawei, measure, main, run_tool
from workflow_checks import check_delivery


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'paper').mkdir()
        (self.root / 'paper/A999.pdf').write_bytes(b'%PDF-synthetic-file')
        (self.root / 'rules.txt').write_text('synthetic current rules', encoding="utf-8")
        write_json(self.root, 'problem/SOURCE_MANIFEST.json', {'sources': [
            {'path': 'rules.txt', 'origin': 'official', 'authoritative_for': ['submission_rules']}]})
        write_json(self.root, 'paper/LATEX_TEMPLATE_MANIFEST.json', {'competition': '华为杯'})
        self.data = {'deliverables': {'final_pdf': {'path': 'paper/A999.pdf'}}, 'submission': {'rules': {
            'sources': ['rules.txt'], 'pdf_name': 'A999.pdf', 'cover_pages': 1,
            'identity_tokens': ['University XYZ', 'Team 999'],
            'abstract': {'start_marker': 'Abstract', 'body_marker': '1 Introduction', 'max_pages': 2},
            'attachments': []}}}
        self.data['compile_receipt_path'] = 'delivery/COMPILE_RECEIPT.json'
        self.update_compile()
        self.pages = ['University XYZ Team 999', 'Abstract\nResult', '1 Introduction\nBody']
        self.meta = ''
        self.tool = patch('submission_check.run_tool', side_effect=self.pdf_tool)
        self.tool.start()
        self.addCleanup(self.tool.stop)

    def update_compile(self):
        write_json(self.root, 'delivery/COMPILE_RECEIPT.json', {'selected_attempt_id': 'TEST', 'attempts': [
            {'attempt_id': 'TEST', 'exit_code': 0, 'pdf_path': 'paper/A999.pdf',
             'pdf_sha256': measure(self.root, 'paper/A999.pdf')['sha256']}]})

    def pdf_tool(self, argv):
        if argv[0] == 'pdftotext':
            return '\f'.join(self.pages) + '\f'
        if '-meta' in argv:
            return self.meta
        return f'Pages: {len(self.pages)}\nTitle: Anonymous paper\n'

    def record(self):
        observed, errors = inspect_submission(self.root, self.data)
        self.assertEqual(errors, [])
        self.data['submission']['recorded'] = observed
        return observed

    def test_cover_identity_allowed_but_body_and_xmp_identity_rejected(self):
        self.record()
        self.assertEqual(check_submission(self.root, self.data), [])
        self.pages[-1] += '\nUniversity XYZ'
        self.assertTrue(any('outside the cover' in e for e in check_submission(self.root, self.data)))
        self.pages[-1] = '1 Introduction\nBody'
        self.meta = '<author>Team 999</author>'
        self.assertTrue(any('metadata' in e for e in check_submission(self.root, self.data)))

    def test_identity_casefold_in_body_and_metadata(self):
        self.data['submission']['rules']['identity_tokens'].append('Straße')
        for token in ('UNIVERSITY XYZ', 'university xyz', 'STRASSE', 'Ｕｎｉｖｅｒｓｉｔｙ ＸＹＺ'):
            with self.subTest(token=token):
                self.pages[-1] = '1 Introduction\n' + token
                self.assertTrue(any('outside the cover' in e for e in check_submission(self.root, self.data)))
                self.pages[-1] = '1 Introduction\nBody'
                self.meta = '<author>' + token + '</author>'
                self.assertTrue(any('metadata' in e for e in check_submission(self.root, self.data)))
                self.meta = ''

    def test_md5_is_measured_and_pdf_rules_or_config_changes_invalidate(self):
        import hashlib
        observed = self.record()
        self.assertEqual(observed['pdf']['md5'], hashlib.md5(b'%PDF-synthetic-file', usedforsecurity=False).hexdigest())
        for path in ('paper/A999.pdf', 'rules.txt'):
            before = (self.root / path).read_bytes()
            (self.root / path).write_bytes(before + b'changed')
            self.assertTrue(any('stale' in e for e in check_submission(self.root, self.data)))
            (self.root / path).write_bytes(before)
        self.data['submission']['rules']['abstract']['max_pages'] = 3
        self.assertTrue(any('stale' in e for e in check_submission(self.root, self.data)))

    def test_name_abstract_limit_and_ambiguous_boundaries(self):
        self.data['submission']['rules']['pdf_name'] = 'B999.pdf'
        self.pages = ['Team 999', 'Abstract text', 'more abstract', 'more abstract', '1 Introduction\nBody']
        _, errors = inspect_submission(self.root, self.data)
        self.assertTrue(any('filename' in e for e in errors))
        self.assertTrue(any('3 pages' in e for e in errors))
        self.pages[-1] += ' Abstract'
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            inspect_submission(self.root, self.data)

    def test_two_page_abstract_and_shared_body_page(self):
        self.pages = ['Team 999', 'Abstract text', 'more abstract', '1 Introduction\nBody']
        observed, errors = inspect_submission(self.root, self.data)
        self.assertEqual((observed['abstract_pages'], errors), (2, []))
        self.pages = ['Team 999', 'Abstract text 1 Introduction\nBody']
        observed, errors = inspect_submission(self.root, self.data)
        self.assertEqual((observed['abstract_pages'], errors), (1, []))

    def test_missing_pdf_tool_and_image_only_page_fail_closed(self):
        self.pages[1] = ''
        self.assertTrue(any('unextractable' in e for e in check_submission(self.root, self.data)))
        with patch('submission_check.run_tool', side_effect=ValueError('PDF inspection failed')):
            self.assertTrue(check_submission(self.root, self.data))

    def test_attachment_size_container_and_byte_drift(self):
        path = self.root / 'A999.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('solve.py', 'print(1)')
        item = {'path': 'A999.zip', 'name': 'A999.zip', 'max_bytes': 10000, 'formats': ['zip']}
        self.data['submission']['rules']['attachments'] = [item]
        self.record()
        item['max_bytes'] = 1
        self.assertTrue(any('byte limit' in e for e in check_submission(self.root, self.data)))
        item['max_bytes'] = 10000
        path.write_bytes(b'not really a zip')
        errors = check_submission(self.root, self.data)
        self.assertTrue(any('container' in e for e in errors))
        self.assertTrue(any('stale' in e for e in errors))

    def test_paths_and_unclassified_rules_are_rejected(self):
        with self.assertRaises(ValueError):
            measure(self.root, '../outside.pdf')
        write_json(self.root, 'problem/SOURCE_MANIFEST.json', {'sources': []})
        self.assertTrue(any('official' in e for e in check_submission(self.root, self.data)))

    def test_named_copy_must_match_compiled_bytes(self):
        original = self.root / 'paper/A999.pdf'
        copied = self.root / 'A999.pdf'
        shutil.copyfile(original, copied)
        self.data['deliverables']['final_pdf']['path'] = 'A999.pdf'
        self.record()
        self.assertEqual(check_submission(self.root, self.data), [])
        copied.write_bytes(b'%PDF-other-paper')
        self.assertTrue(any('compiled PDF' in e for e in check_submission(self.root, self.data)))

    def test_huawei_requires_check_and_other_competitions_unchanged(self):
        data = copy.deepcopy(self.data)
        del data['submission']
        self.assertTrue(check_submission(self.root, data))
        for mode, severity in [('working', 'warning'), ('finalizing', 'error')]:
            write_json(self.root, '.cumcm/state.json', {'mode': mode})
            findings = check_delivery(data, self.root, 'delivery/DELIVERY_MANIFEST.json')
            self.assertEqual([f.severity for f in findings if f.rule_id == 'DELIVERY-E022'], [severity])
        write_json(self.root, 'paper/LATEX_TEMPLATE_MANIFEST.json', {'competition': 'MCM/ICM'})
        self.assertEqual(check_submission(self.root, data), [])

    def test_record_failure_does_not_write_and_stale_receipt_is_not_refreshed(self):
        path = self.root / 'delivery/DELIVERY_MANIFEST.json'
        self.record()
        write_json(self.root, str(path.relative_to(self.root)), self.data)
        before = path.read_bytes()
        (self.root / 'paper/A999.pdf').write_bytes(b'%PDF-new-file')
        with patch.object(sys, 'argv', ['submission_check.py', '--project', str(self.root), '--record']), patch('builtins.print'):
            self.assertEqual(main(), 1)
        self.assertEqual(path.read_bytes(), before)
        del self.data['submission']['recorded']
        self.update_compile()
        write_json(self.root, str(path.relative_to(self.root)), self.data)
        with patch.object(sys, 'argv', ['submission_check.py', '--project', str(self.root), '--record']), patch('builtins.print'):
            self.assertEqual(main(), 0)
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(check_submission(self.root, saved), [])

    def test_chinese_paths_and_json_are_read_with_utf8_locale_independently(self):
        chinese_pdf = self.root / 'paper/中文队伍.pdf'
        (self.root / 'paper/A999.pdf').rename(chinese_pdf)
        (self.root / 'rules.txt').rename(self.root / '中文规则.txt')
        self.data['deliverables']['final_pdf']['path'] = 'paper/中文队伍.pdf'
        self.data['submission']['rules']['pdf_name'] = '中文队伍.pdf'
        self.data['submission']['rules']['sources'] = ['中文规则.txt']
        self.data['submission']['rules']['identity_tokens'] = ['上海大学']
        write_json(self.root, 'problem/SOURCE_MANIFEST.json', {'sources': [
            {'path': '中文规则.txt', 'origin': 'official', 'authoritative_for': ['submission_rules']}]})
        receipt_path = self.root / 'delivery/COMPILE_RECEIPT.json'
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        receipt['attempts'][0]['pdf_path'] = 'paper/中文队伍.pdf'
        receipt['attempts'][0]['pdf_sha256'] = measure(self.root, 'paper/中文队伍.pdf')['sha256']
        write_json(self.root, 'delivery/COMPILE_RECEIPT.json', receipt)
        write_json(self.root, 'delivery/DELIVERY_MANIFEST.json', self.data)
        with patch.object(locale, 'getencoding', return_value='ascii'):
            self.assertTrue(is_huawei(self.root))
            observed, errors = inspect_submission(self.root, self.data)
            self.assertEqual(errors, [])
            self.assertEqual(observed['pdf']['path'], 'paper/中文队伍.pdf')
            with patch.object(sys, 'argv', ['submission_check.py', '--project', str(self.root)]), patch('builtins.print'):
                self.assertEqual(main(), 0)
        code = """import json, sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
import submission_check as s
root = Path(sys.argv[2])
s.run_tool = lambda argv: ('Team 999\\fAbstract\\nResult\\f1 Introduction\\nBody\\f' if argv[0] == 'pdftotext' else '' if '-meta' in argv else 'Pages: 3\\n')
data = json.loads((root / 'delivery/DELIVERY_MANIFEST.json').read_text(encoding='utf-8'))
assert s.is_huawei(root)
assert s.inspect_submission(root, data)[1] == []
with patch.object(sys, 'argv', ['submission_check.py', '--project', str(root)]), patch('builtins.print'):
    assert s.main() == 0
print(sys.flags.utf8_mode)
"""
        env = dict(os.environ, PYTHONUTF8='0', PYTHONCOERCECLOCALE='0', LC_ALL='C', LANG='C')
        done = subprocess.run([sys.executable, '-c', code, str(Path(__file__).resolve().parents[1] / '.agents/skills/cumcm-workflow/scripts'), str(self.root)],
                              env=env, capture_output=True, text=True, encoding='utf-8', timeout=10)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), '0')

    def test_poppler_output_encoding_is_explicit_and_strict(self):
        argv_seen = []
        def observe(argv):
            argv_seen.append(argv)
            return self.pdf_tool(argv)
        with patch('submission_check.run_tool', side_effect=observe):
            inspect_submission(self.root, self.data)
        self.assertTrue(all(argv[1:3] == ['-enc', 'UTF-8'] for argv in argv_seen))
        with patch('submission_check.subprocess.run', return_value=subprocess.CompletedProcess([], 0, stdout='中文')) as invoked:
            self.assertEqual(run_tool(['pdftotext', '-enc', 'UTF-8', 'paper.pdf', '-']), '中文')
        self.assertEqual(invoked.call_args.kwargs['encoding'], 'utf-8')
        self.assertEqual(invoked.call_args.kwargs['errors'], 'strict')
        with patch('submission_check.subprocess.run', side_effect=UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'invalid')):
            with self.assertRaisesRegex(ValueError, 'PDF inspection failed'):
                run_tool(['pdftotext', '-enc', 'UTF-8', 'paper.pdf', '-'])


@unittest.skipUnless(all(shutil.which(t) for t in ('xelatex', 'pdfinfo', 'pdftotext', 'pdftoppm')), 'XeLaTeX/Poppler required')
class OfficialCoverTests(unittest.TestCase):
    def test_official_cover_compiles_and_remains_unverified(self):
        self.check_cover_template("generic", "cumcm-contest-ctex")

    def test_huawei_cover_compiles_and_remains_unverified(self):
        self.check_cover_template("auto", "huawei-ctex")

    def check_cover_template(self, template, template_id):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_inputs(root)
            cover_source = r'\documentclass{article}\begin{document}\thispagestyle{empty}University XYZ Team 999\end{document}'
            (root / 'cover.tex').write_text(cover_source, encoding="utf-8")
            done = subprocess.run(['xelatex', '-interaction=nonstopmode', '-halt-on-error', 'cover.tex'], cwd=root, capture_output=True)
            self.assertEqual(done.returncode, 0, done.stdout.decode(errors='replace'))
            (root / 'official.txt').write_text('synthetic official template; not contest certification', encoding="utf-8")
            write_json(root, 'problem/SOURCE_MANIFEST.json', {'sources': [
                {'path': 'official.txt', 'origin': 'official', 'authoritative_for': ['paper_template']}]})
            manifest_path = initialize(root, 'Demand model', 2030, 'demand; regression', competition='华为杯', cover_pdf='cover.pdf', template=template)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest['mode'], 'official_package_adapter')
            self.assertEqual(manifest['template_id'], template_id)
            self.assertEqual(manifest['official_compliance'], 'unverified')
            self.assertEqual(manifest['competition_year'], 2030)
            (root / 'paper/sections/00_abstract.tex').write_text('Abstract\nSynthetic result.\\par\n', encoding="utf-8")
            first = root / manifest['subproblem_sections'][0]['path']
            first.write_text('\\section{Introduction}\nSynthetic body.\n', encoding="utf-8")
            done = run_script('record_compile.py', '--project', str(root))
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            receipt = json.loads((root / 'delivery/COMPILE_RECEIPT.json').read_text(encoding="utf-8"))
            # Independently inspect the generated PDF: actual cover first, no identity in body.
            pdf = root / 'paper/main.pdf'
            if not pdf.exists():
                pdf = next(root.rglob('main.pdf'))
            pages = subprocess.run(['pdftotext', str(pdf), '-'], check=True, capture_output=True, text=True).stdout.split('\f')
            self.assertIn('University XYZ', pages[0])
            self.assertNotIn('University XYZ', ''.join(pages[1:]))
            self.assertIn('official-cover.pdf', json.dumps(receipt))
            data = {'compile_receipt_path': 'delivery/COMPILE_RECEIPT.json',
                    'deliverables': {'final_pdf': {'path': pdf.relative_to(root).as_posix()}},
                    'submission': {'rules': {'sources': ['official.txt'], 'pdf_name': pdf.name,
                        'cover_pages': 1, 'identity_tokens': ['University XYZ', 'Team 999'],
                        'abstract': {'start_marker': 'Abstract', 'body_marker': '1 Introduction', 'max_pages': 2},
                        'attachments': []}}}
            observed, errors = inspect_submission(root, data)
            self.assertEqual(errors, [])
            self.assertEqual(observed['abstract_pages'], 1)
            data['submission']['recorded'] = observed
            self.assertEqual(check_submission(root, data), [])
            with self.assertRaisesRegex(ValueError, 'refusing to overwrite'):
                initialize(root, 'Demand model', 2030, 'demand', competition='华为杯', cover_pdf='cover.pdf')

    def test_cover_requires_official_source_and_single_page(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            build_inputs(root)
            (root / 'cover.pdf').write_bytes(b'%PDF-test')
            with self.assertRaisesRegex(ValueError, 'declared official'):
                initialize(root, 'Demand model', 2030, 'demand', competition='华为杯', cover_pdf='cover.pdf')
            (root / 'official.txt').write_text('template', encoding="utf-8")
            write_json(root, 'problem/SOURCE_MANIFEST.json', {'sources': [
                {'path': 'official.txt', 'origin': 'official', 'authoritative_for': ['paper_template']}]})
            with patch('init_latex_paper.subprocess.run', return_value=subprocess.CompletedProcess([], 0, stdout='Pages: 2\n')):
                with self.assertRaisesRegex(ValueError, 'exactly one page'):
                    initialize(root, 'Demand model', 2030, 'demand', competition='华为杯', cover_pdf='cover.pdf')
            self.assertFalse((root / 'paper/main.tex').exists())
