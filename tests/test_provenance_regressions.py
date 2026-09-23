"""Real recorder attacks on synthetic projects; approvals are test fixtures."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import venv

from recorder_fixtures import make_project, run_script
from recorder_fixtures import record_official
from workflow_fixtures import build_valid_project
from canonical_evidence import resolve_official_computation
from record_run import infer_entry_point, runtime_label
from index_result import newest_descendant
from build_handoff import build as build_handoff
from build_independent_review_package import build as build_review
from workflow_checks import check_project


class ProvenanceRegressions(unittest.TestCase):
    def test_unexecuted_source_cannot_be_inferred(self):
        with tempfile.TemporaryDirectory() as d:
            p=make_project(Path(d))
            for argv in ([sys.executable, '-c', 'print(1)'],
                         [sys.executable, '-c', 'print(1)', 'code/solve.py'],
                         ['echo', 'code/solve.py']):
                with self.subTest(argv=argv), self.assertRaises(SystemExit):
                    infer_entry_point(p, argv, ['code/solve.py'])
            self.assertEqual(infer_entry_point(p,[sys.executable,'-u','code/solve.py'],[]),'code/solve.py')

    def test_inline_command_cannot_create_manifest_with_declared_source(self):
        with tempfile.TemporaryDirectory() as d:
            p=make_project(Path(d))
            done=run_script('record_run.py','--project',str(p),'--run-id','INLINE','--source','code/solve.py','--',sys.executable,'-c','from pathlib import Path; Path("ran.txt").write_text("ran")')
            self.assertNotEqual(done.returncode,0)
            self.assertFalse((p/'runs/INLINE/RUN_MANIFEST.json').exists())
            self.assertFalse((p/'ran.txt').exists())

    def test_relative_model_interpreter_recorded_in_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            p=make_project(Path(d))
            env=p/'model-env';venv.EnvBuilder(with_pip=False).create(env)
            rel='model-env/Scripts/python.exe' if os.name=='nt' else 'model-env/bin/python'
            done=run_script('record_run.py','--project',str(p),'--run-id','RUNTIME','--',rel,'code/solve.py')
            self.assertEqual(done.returncode,0,done.stdout+done.stderr)
            manifest=json.loads((p/'runs/RUNTIME/RUN_MANIFEST.json').read_text(encoding="utf-8"))
            self.assertIn(str(p/rel),manifest['implementation']['runtime'])
            self.assertEqual(manifest['argv'][0],rel)

    def test_canonical_rejects_tampered_input_and_output(self):
        for role in ('inputs','outputs'):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as d:
                p=Path(d);build_valid_project(p)
                self.assertTrue(resolve_official_computation(p))
                manifest=json.loads((p/'runs/RUN-Q1-001/RUN_MANIFEST.json').read_text(encoding="utf-8"))
                target=p/manifest[role][0]['path']
                target.write_bytes(target.read_bytes()+b' tampered')
                findings, _ = check_project(p, 'computation')
                self.assertIn('RUN-E007', {f.rule_id for f in findings})
                for consume in (lambda: resolve_official_computation(p),
                                lambda: build_handoff(p, 'computation-validation', task_ref='synthetic-review'),
                                lambda: build_review(p, review_mode='full', refresh=True)):
                    with self.assertRaisesRegex(ValueError,'integrity|hash|SHA'):
                        consume()

    def test_touch_output_and_assertions_rejected_old_bytes_preserved(self):
        for kind in ('output','assertion'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                p=make_project(Path(d));record_official(p)
                target='results/q1_output.json' if kind=='output' else 'results/assertions.json'
                old=(p/target).read_bytes()
                code='from pathlib import Path\nPath('+repr(target)+').touch()\n'
                if kind=='assertion':
                    code+='Path("results/q1_output.json").write_text("{}")\n'
                (p/'code/touch.py').write_text(code, encoding="utf-8")
                args=['--assert-file','results/assertions.json'] if kind=='assertion' else []
                done=run_script('record_run.py','--project',str(p),'--run-id','TOUCH','--output','results/q1_output.json:claim',*args,'--',sys.executable,'code/touch.py')
                self.assertNotEqual(done.returncode,0,done.stdout+done.stderr)
                self.assertFalse((p/'runs/TOUCH/RUN_MANIFEST.json').exists())
                self.assertEqual((p/target).read_bytes(),old)

    def test_timeout_restores_old_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            p=make_project(Path(d));record_official(p)
            old=(p/'results/q1_output.json').read_bytes()
            (p/'code/sleep.py').write_text('import time; time.sleep(3)', encoding="utf-8")
            done=run_script('record_run.py','--project',str(p),'--run-id','TIMEOUT','--timeout','0.1','--output','results/q1_output.json:claim','--',sys.executable,'code/sleep.py')
            self.assertNotEqual(done.returncode,0)
            self.assertEqual((p/'results/q1_output.json').read_bytes(),old)
            self.assertEqual((p/'runs/TIMEOUT/previous_outputs/results/q1_output.json').read_bytes(),old)

    def test_cannot_move_input_as_output(self):
        with tempfile.TemporaryDirectory() as d:
            p=make_project(Path(d))
            before=(p/'code/solve.py').read_bytes()
            done=run_script('record_run.py','--project',str(p),'--output','code/solve.py:claim','--',sys.executable,'code/solve.py')
            self.assertNotEqual(done.returncode,0)
            self.assertIn('source or input',done.stderr)
            self.assertEqual((p/'code/solve.py').read_bytes(),before)

    def test_matlab_entry_requires_explicit_driver(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'driver.m').write_text('disp(1);', encoding="utf-8")
            self.assertEqual(infer_entry_point(p,['matlab','-batch',"run('driver.m')"],[]),'driver.m')
            for expression in ('disp(1)', "disp('driver.m')", "run('driver.m'); disp(2)"):
                with self.assertRaises(SystemExit):
                    infer_entry_point(p,['matlab','-batch',expression],['driver.m'])

    def test_identical_recomputation_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            p=make_project(Path(d));record_official(p)
            old=(p/'results/q1_output.json').read_bytes()
            done=run_script('record_run.py','--project',str(p),'--rerun','RUN-Q1-001','--official','--assert-file','results/assertions.json')
            self.assertEqual(done.returncode,0,done.stdout+done.stderr)
            self.assertEqual((p/'results/q1_output.json').read_bytes(),old)

    def test_runtime_uses_model_interpreter(self):
        with tempfile.TemporaryDirectory() as d:
            env=Path(d)/'model-env';venv.EnvBuilder(with_pip=False).create(env)
            executable=env/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
            label=runtime_label('python',[str(executable),'code/solve.py'])
            self.assertIn(str(executable),label)

    def test_seed_declarations_and_rerun_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            p=make_project(Path(d))
            done=run_script('record_run.py','--project',str(p),'--run-id','META','--seed','42','--toolbox','Optimization Toolbox','--',sys.executable,'code/solve.py')
            self.assertEqual(done.returncode,0,done.stderr)
            done=run_script('record_run.py','--project',str(p),'--rerun','META','--run-id','META2')
            self.assertEqual(done.returncode,0,done.stderr)
            for run in ('META','META2'):
                m=json.loads((p/f'runs/{run}/RUN_MANIFEST.json').read_text(encoding="utf-8"))
                self.assertEqual(m['seeds'],[{'name':'seed','value':'42','source':'declared'}])
                self.assertEqual(m['implementation']['matlab_toolboxes'],['Optimization Toolbox'])

    def test_rerun_explicit_metadata_overrides_declarations(self):
        with tempfile.TemporaryDirectory() as d:
            p=make_project(Path(d))
            first=run_script('record_run.py','--project',str(p),'--run-id','META','--seed','42','--toolbox','old','--',sys.executable,'code/solve.py')
            self.assertEqual(first.returncode,0,first.stderr)
            done=run_script('record_run.py','--project',str(p),'--rerun','META','--run-id','META2','--seed','99','--toolbox','new')
            self.assertEqual(done.returncode,0,done.stderr)
            m=json.loads((p/'runs/META2/RUN_MANIFEST.json').read_text(encoding="utf-8"))
            self.assertEqual(m['seeds'],[{'name':'seed','value':'99','source':'declared'}])
            self.assertEqual(m['implementation']['matlab_toolboxes'],['new'])

    def test_missing_hash_and_escaping_formal_paths_rejected(self):
        for change in ({'sha256':None}, {'path':'../outside'}):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
                p=Path(d);build_valid_project(p)
                path=p/'runs/RUN-Q1-001/RUN_MANIFEST.json'
                manifest=json.loads(path.read_text(encoding="utf-8"))
                manifest['inputs'][0].update(change)
                path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(ValueError,'integrity'):
                    resolve_official_computation(p)

    def test_forked_lineage_is_ambiguous_and_documented(self):
        runs={x:{'run_id':x,'parent_run_id':parent,'official_run':True,'status':'completed','exit_code':0,'finished_at':x}
              for x,parent in [('A',None),('B','A'),('C','A')]}
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            newest_descendant(runs,'A')
        root=Path(__file__).resolve().parents[1]
        for rel in ('.agents/skills/cumcm-workflow/references/04-computation.md','docs/workflow-contract.md'):
            self.assertIn('ambiguous',(root/rel).read_text(encoding="utf-8"))
