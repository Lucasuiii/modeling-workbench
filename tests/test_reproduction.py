"""Validate claim-specific comparisons through the normal project checker."""
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from workflow_fixtures import build_valid_project, write_json
from build_handoff import build as build_handoff
from recorder_fixtures import run_script
from canonical_evidence import resolve_official_computation
from workflow_checks import check_project
from provenance import sha256_file


class ReproductionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        build_valid_project(self.root)
        self.path = 'validation/CLAIM_LEDGER.json'
        self.ledger = json.loads((self.root / self.path).read_bytes())
        self.claim = self.ledger['claims'][0]
        self.claim['evidence_state'] = 'reproduced'

    def errors(self):
        write_json(self.root, self.path, self.ledger)
        return [f.rule_id for f in check_project(self.root, 'validation')[0] if f.rule_id == 'CLAIM-E013']

    def test_empty_or_same_run_cannot_establish_reproduction(self):
        self.claim['reproduction'] = {}
        self.assertTrue(self.errors())
        self.claim['reproduction'] = {'comparisons': [{'result_id': 'RES-Q1-001',
                                    'comparison_result_id': 'RES-Q1-001', 'absolute_tolerance': 0}]}
        self.assertTrue(self.errors())

    def add_comparison(self, raw_value):
        run = json.loads((self.root / 'runs/RUN-Q1-001/RUN_MANIFEST.json').read_bytes())
        run['run_id'] = 'SECOND'
        output_rel = 'runs/SECOND/outputs/recheck.json'
        output = self.root / output_rel
        output.parent.mkdir(parents=True)
        output.write_text('{"cost":' + raw_value + '}', encoding='utf-8')
        run['outputs'][0].update(path=output_rel, sha256=sha256_file(output), size=output.stat().st_size)
        write_json(self.root, 'runs/SECOND/RUN_MANIFEST.json', run)
        result = run_script('index_result.py', '--project', str(self.root), '--run', 'SECOND',
                            '--locator', output_rel + '#/cost', '--result-id', 'RES-SECOND',
                            '--name', 'Cost', '--unit', 'synthetic_cost', '--scope', 'fixed homogeneous policies only')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.claim['evidence']['result_ids'].append('RES-SECOND')
        self.claim['evidence']['run_ids'].append('SECOND')
        pair = {'result_id': 'RES-Q1-001', 'comparison_result_id': 'RES-SECOND', 'absolute_tolerance': 0}
        self.claim['reproduction'] = {'comparisons': [pair]}
        return pair, output

    def test_current_independent_outputs_and_exact_tolerance(self):
        pair, output = self.add_comparison('12.51')
        pair['absolute_tolerance'] = 0.01
        self.assertFalse(self.errors())
        pair['absolute_tolerance'] = 0.009
        self.assertTrue(self.errors())
        pair['absolute_tolerance'] = 0.01
        output.write_text('{"cost": 12.52}', encoding='utf-8')
        self.assertTrue(self.errors())

    def test_booleans_inside_structures_are_not_numeric_flags(self):
        self.add_comparison('{"flags":[true,false]}')
        path = self.root / 'results/RESULTS_INDEX.json'
        index = json.loads(path.read_bytes())
        index['results'][-1]['value']['flags'] = [1, 0]
        write_json(self.root, 'results/RESULTS_INDEX.json', index)
        with self.assertRaisesRegex(ValueError, 'differs from frozen output'):
            resolve_official_computation(self.root)
        rules = {f.rule_id for f in check_project(self.root, 'computation')[0]}
        self.assertIn('RESULT-E012', rules)
        original = path.read_bytes()
        result = run_script('index_result.py', '--project', str(self.root), '--follow-lineage')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(path.read_bytes(), original)

    def test_exact_decimal_survives_index_refresh_and_tolerance_checks(self):
        pair, _ = self.add_comparison('12.5000000000000001')
        self.assertTrue(self.errors())
        pair['absolute_tolerance'] = 1e-16
        self.assertFalse(self.errors())
        index = self.root / 'results/RESULTS_INDEX.json'
        for operation in ('--refresh', '--follow-lineage'):
            result = run_script('index_result.py', '--project', str(self.root), operation)
            self.assertEqual(result.returncode, 0, result.stderr)
        expected = Decimal('12.5000000000000001')
        self.assertEqual(json.loads(index.read_bytes(), parse_float=Decimal)['results'][-1]['value'], expected)

        # The checkpoint writer must preserve an exact tolerance in the ledger,
        # including when it rewrites the user's confirmation.
        ledger = self.root / self.path
        boundary = '0.0000000000000000999999999999999999'
        ledger.write_text(ledger.read_text().replace('1e-16', boundary))
        self.assertIn('CLAIM-E013', {f.rule_id for f in check_project(self.root, 'validation')[0]})
        passing = '0.0000000000000001000000000000000001'
        ledger.write_text(ledger.read_text().replace(boundary, passing))
        decision = run_script('record_decision.py', '--project', str(self.root), '--stage', 'validation',
                              '--decision', 'accepted', '--confirm-human', '--task-turn-ref', 'fixture-reply',
                              '--summary', 'synthetic regression test')
        self.assertEqual(decision.returncode, 0, decision.stderr)
        recorded = json.loads(ledger.read_bytes(), parse_float=Decimal)['claims'][0]['reproduction']
        self.assertEqual(recorded['comparisons'][0]['absolute_tolerance'], Decimal(passing))
        handoff = build_handoff(self.root, 'validation-paper', 'fixture-review')
        payload = json.loads(handoff.read_bytes(), parse_float=Decimal)['payload']
        self.assertEqual(payload['verified_results'][-1]['value'], expected)
        resolve_official_computation(self.root)
        index.write_text(index.read_text().replace(str(expected), '12.5'))
        self.assertIn('RESULT-E012', {f.rule_id for f in check_project(self.root, 'computation')[0]})
