"""Validate claim-specific comparisons through the normal project checker."""
import json
import tempfile
import unittest
from pathlib import Path

from workflow_fixtures import build_valid_project, write_json
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

    def test_current_independent_outputs_and_exact_tolerance(self):
        run = json.loads((self.root / 'runs/RUN-Q1-001/RUN_MANIFEST.json').read_bytes())
        run['run_id'] = 'SECOND'
        output_rel = 'runs/SECOND/outputs/recheck.json'
        write_json(self.root, output_rel, {'cost': 12.51})
        run['outputs'][0].update(path=output_rel, sha256=sha256_file(self.root / output_rel))
        write_json(self.root, 'runs/SECOND/RUN_MANIFEST.json', run)
        index = json.loads((self.root / 'results/RESULTS_INDEX.json').read_bytes())
        second = dict(index['results'][0], result_id='RES-SECOND', run_id='SECOND',
                      value=12.51, output_locator=output_rel + '#/cost')
        index['results'].append(second)
        write_json(self.root, 'results/RESULTS_INDEX.json', index)
        self.claim['evidence']['result_ids'].append('RES-SECOND')
        self.claim['evidence']['run_ids'].append('SECOND')
        pair = {'result_id': 'RES-Q1-001', 'comparison_result_id': 'RES-SECOND', 'absolute_tolerance': 0.01}
        self.claim['reproduction'] = {'comparisons': [pair]}
        self.assertFalse(self.errors())
        pair['absolute_tolerance'] = 0.009
        self.assertTrue(self.errors())
        pair['absolute_tolerance'] = 0.01
        write_json(self.root, output_rel, {'cost': 12.52})
        self.assertTrue(self.errors())
