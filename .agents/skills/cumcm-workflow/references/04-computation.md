# Computation responsibility

## Outcome

Produce one reliable official implementation, successful run evidence, and an exact result index. Working mode may keep exploratory and failed runs, but only a successful `official_run: true` run may support a formal result.

For data-intensive work, follow the applicable data preparation, evaluation and budget guidance in [task-driven modeling](task-driven-modeling.md). Preserve consequential preprocessing and result-file transformations as declared dependencies; a clean-looking table or successful training run is not evidence that the population, split or submission fields are correct.

## Choose one backend

Use the project preference (`matlab` preferred, `python` fallback, `auto` selection) as a tie-break, not a mandate. Compare the actual task:

- MATLAB often fits numerical linear algebra, optimization, ODE/PDE, signal processing, and licensed toolbox workflows.
- Python often fits heterogeneous data cleaning, CSV/Excel automation, machine learning, text/web data, or an existing Python codebase.
- Availability, required toolbox/package, implementation complexity, existing code, and runtime stability override preference.

Run `scripts/backend_selection.py` when a recorded deterministic selection is useful. MATLAB detection checks explicit `implementation.matlab_executable`, then `matlab` on PATH, then macOS `/Applications/MATLAB_R*.app/bin/matlab` with newer releases first. A preferred or explicitly selected backend may fall back when unavailable; a task `required_backend` is a hard runtime requirement and must error rather than switch. Once selected, implement and officially execute that language only. Do not build a second backend for parity unless the user explicitly requests cross-implementation validation.

The mathematical formulation, variable meanings, result IDs, and acceptance checks remain language-neutral.

## Recording, not transcribing

`record_run.py` executes the command and writes `RUN_MANIFEST.json` from what it observed. Never hand-write a manifest, a hash, or a `sha256-tree-v1` digest.

```bash
# exploration: no declarations at all
python3 "$S/record_run.py" --project <p> -- python3 code/try.py

# formal: declare only what the tool cannot know
python3 "$S/record_run.py" --project <p> --official --capability CAP-Q1-001 \
  --source code/solve.py --input data/q1.csv:formal \
  --output results/q1.json:claim --assert-file results/assertions.json -- python3 code/solve.py

# a rerun appends a successor (RUN-Q1-002) and leaves the parent untouched
python3 "$S/record_run.py" --project <p> --rerun RUN-Q1-001 --official
python3 "$S/index_result.py" --project <p> --follow-lineage
```

Then index the result; the value is read through the locator, so the index can never disagree with the output:

```bash
python3 "$S/index_result.py" --project <p> --result-id RES-Q1-001 --run RUN-Q1-001 \
  --locator results/q1.json#/minimum_cost --name "Minimum cost" --unit CNY \
  --scope "declared candidates only" --check "feasibility"
```

Exploratory runs are cheap on purpose: they are recorded, never trusted, and never block. A failed assertion or a non-zero exit inside one is a finding about the experiment, not about the formal chain.

Their other job is settling the model comparison. Tag each evaluation with the candidate it is testing:

```bash
python3 "$S/record_run.py" --project <p> --candidate CAND-A -- python3 code/try_a.py
```

That run then counts as evidence for or against `CAND-A` in `MODEL_CONTRACT.components[].candidates`. Only after one candidate is `selected` does that model earn an official run; see [03-model-design.md](03-model-design.md).

## Append-only runs and frozen evidence

A rerun never overwrites. It appends a run whose `parent_run_id` names the one it replaces, and every run copies its declared source and outputs into its own directory:

```text
runs/RUN-Q1-002/
├── RUN_MANIFEST.json
├── stdout.log  stderr.log
├── source/code/solve.py        # the code as executed
└── outputs/results/q1.json     # the output as produced; the locator points here
```

The frozen tree mirrors the original relative paths, so the live counterpart of `runs/<id>/source/code/solve.py` is `code/solve.py`; team inputs land under `runs/<id>/inputs/` the same way. That mapping is what keeps drift detection alive: `RUN-E020` compares the two and reports that the working tree has moved on from this official run. A superseded run is exempt; altering a frozen copy is `RUN-E021`.

Inputs under `problem/official/` are hashed where they live: they are immutable by intake contract and large attachments should not be duplicated per run. Every other formal input — `data/cleaned.csv` and friends, which the team regenerates — is frozen too, up to a size limit, so a preserved run stays reproducible after the data is rebuilt.

A run may only use one backend per capability. That was a selector rule and a sentence in the docs; `RUN-E024` now enforces it, so a capability cannot end up with current official runs in both MATLAB and Python unless the user asked for cross-implementation validation. Warning while `working`, error once frozen.

Seed metadata is declared, not observed: `--seed` does not pass a seed to the model or set its RNG. Pass the seed through the actual model arguments/configuration and inspect the implementation and produced diagnostics. For a program accepting `--seed`:

```bash
python3 "$S/record_run.py" --project <p> --seed 20260907 --seed bootstrap=7 -- python3 code/mc.py --seed 20260907 --bootstrap-seed 7
```

Two things a run may never claim:

- **an output it did not write.** The recorder stats every declared output before and after execution. A program that exits 0 without rewriting its claim-bearing output would otherwise have the previous run's file frozen as its own, with a real hash and false provenance; the recorder refuses to write the manifest at all and says which file was not produced. An untouched intermediate or diagnostic output only warns.
`--assert-file` names a file the run must write during the run. The recorder moves existing assertion files and claim outputs into the new run’s `previous_outputs/` before execution and requires fresh non-empty regular files. Merely touching a path cannot reuse old bytes; recomputation with identical content is valid. Missing/empty generation restores the old file when available and refuses the manifest; backups remain recoverable. Do not use the same path for an input and output, write formal outputs under `runs/`, or run simultaneous writers against the same outputs. A declared `--source` or `--input` must likewise exist before the run starts: something the run creates is an output, and freezing it as the code that ran would record a file the run generated as the file it read.

Acceptance checks judged `recorded` are the reason `--assert-file` exists. The capability names an assertion; the solving program computes it and writes the verdict out; `CAP-E012` checks that an official run for that capability recorded it passing. Have the program raise or write `passed: false` when the condition fails rather than reporting success and letting a later reader notice -- the point is that "we did the task" becomes something the run either shows or does not.

- **a verdict it did not reach.** Assertions carry their provenance. `--assert name=pass` is a note typed by the caller and is recorded as `source: "declared"`; `--assert-file` reads verdicts the program wrote itself and is recorded as `source: "recorded"`. Only recorded verdicts satisfy a frozen `verification_plan` (`MODEL-E009`/`MODEL-W010`), and an official run carrying only declared ones raises `RUN-W003`. Assertions are also never inherited by a rerun -- new code has not been verified by the old run's `pass` -- and a rerun that drops its parent's assertions says so on stderr.
- **evidence that moved under it.** Declared source and formal inputs are hashed before execution and re-checked after. Freezing happens once the command exits, so a file edited mid-run would be frozen as something the run never read; the recorder refuses to write the manifest and names the file.

Only a **successful official** rerun supersedes its parent. A failed or exploratory child replaces nothing — retiring the parent on its account would invalidate the only usable evidence — and `--follow-lineage` skips it. Multiple successful official children are **ambiguous**: choose the intended branch explicitly with `--run-id`; no newest-child guess is made.

Every formal consumer resolves "the run behind this result" through the same code, so the checker, the computation handoff, the review package and paper→delivery all refuse a superseded run rather than one of them quietly packaging it. Claims and figures still citing a retired run raise `CLAIM-W020` / `FIGURE-W013`.

Never edit a run directory by hand, and never re-point a result at a different run silently: `index_result.py --follow-lineage` exists so that choosing the run behind a claim stays a deliberate act.

Translate applicable checks from [mechanism-validation.md](mechanism-validation.md) into the selected implementation’s result-based assertions. Inspect final exported/rounded values when they are the answer, retain diagnostic quantities and tolerance rationale with the existing outputs, and record verdicts through `--assert-file`. A recorded pass establishes that the code evaluated its condition; the reviewer still checks whether that condition means what the claim needs.

## Official run evidence

Each `RUN_MANIFEST.json` records:

- selected language, rationale, entry point, runtime, dependencies, and MATLAB toolboxes when applicable;
- a `sha256-tree-v1` source snapshot covering the executed code;
- argument array, working directory, timestamps, exit status, stdout/stderr, environment, any `--seed` values, and assertions;
- `formal_input` and `claim_bearing_output` hashes;
- `official_run: true` only for the run selected to support formal results.

Failed or exploratory runs may remain for local debugging with `official_run: false`; they do not block merely because they failed, and they do not enter handoffs or support claims.

Every result uses an exact `path#JSON-pointer` into a declared claim-bearing JSON output. Keep unrounded values authoritative and display rounding separate. A successful exit code proves execution, not model correctness, so include problem-specific feasibility, residual, conservation, baseline, or stability checks when they matter.

Before validation, build `modeling-computation` and `computation-validation` handoffs. The latter points to canonical official runs/results. Computation→validation, the independent package, and paper→delivery all resolve the same chain: `RESULTS_INDEX.json` → referenced successful `official_run: true` manifest → current source snapshot. A missing, failed, non-official, or stale link fails every consumer rather than being silently skipped. The context-separated reviewer package copies only the official inputs, problem/model contracts, results index, that resolved evidence, formal inputs, claim-bearing outputs, and review instructions. It excludes failed/exploratory runs and stdout/stderr/debug history.

## Invocation and provenance boundaries

Use a direct `python [supported interpreter options] code/solve.py [model arguments]` invocation, or `matlab -batch "run('code/solve.m')"`. Inline `-c`, `-m`, shell wrappers and arbitrary MATLAB batch expressions are refused because a declared `--source` does not prove that file was executed. Put such logic in a real driver file and declare its helper sources. Interpreter flags not recognized by the recorder are also refused rather than guessed.

Python runtime is probed using the resolved model executable and its interpreter options before execution; the manifest labels this observation. `environment.python` describes the recorder environment, not the model. MATLAB version remains explicitly unverified. This is not protection against a malicious executable impersonating Python or changing between probe and execution.

Seeds carry `source: declared`. Reruns inherit seed and toolbox declarations unless overridden; dependencies/toolboxes are declared metadata, not observed use. Assertions are never inherited. Old seed records without a source tag are likewise declarations. This update does not retroactively certify older manifests.

The canonical resolver verifies actual SHA256 for every formal input and claim-bearing output, in addition to source snapshots. Handoffs and independent review packages therefore reject missing or modified formal artifacts before accepting that evidence.

Backend detection follows the executable and supported invocation structure, never model arguments or directory-name substrings. An explicit backend must agree with that structure.

Fresh claim outputs and assertion files form a transaction ending at the atomic manifest write. If the recorder exits exceptionally before that commit (including provenance rejection, missing capability, assertion parsing or manifest-write failure), it restores old live files; files that were absent before the run become absent again. New rejected files are retained in `runs/<id>/rejected_outputs/`, and backups remain in `previous_outputs/`. A committed failed/exploratory run is still a recorded run, so a nonzero exit status alone does not trigger rollback. This does not roll back arbitrary source/input edits or diagnostic outputs. Hard kills, filesystem failures and concurrent writers can still require manual recovery; rollback failures name the recoverable run directory.
