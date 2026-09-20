# Modeling Workbench

English | [简体中文](README.md)

**From problem statement to paper, with evidence you can inspect.**

A mathematical modeling competition workflow for **Codex / Claude Code**. Supply the official problem and attachments; the agent works through problem analysis, model comparison, computation, review and Chinese/English LaTeX/PDF delivery. You review and decide whether to proceed at three key checkpoints.

**Read the problem → compare models → compute → review independently → write → check and deliver the PDF**

- **Compare before committing to a model**: evaluate candidates and record why a model was selected before official computation.
- **Trace paper values to their source**: computation records connect code, data and results, with stale-evidence detection after code changes.
- **Deliver inspectable materials**: a Chinese or English paper, source and results, review records, and a compiled PDF checked page by page.

The workflow helps organize and verify the process. Model suitability and the validity of conclusions still require judgment grounded in the problem and evidence.

[Quick start](#quick-start) · [Competition support](#competition-support) · [Architecture](#2-architecture) · [Computation records](#4-recording-computation) · [Development](#11-development)

## Quick start

**Have Codex or Claude Code ready, and put the official problem, attachments and current submission requirements in one folder.** Then copy the two prompts below. You do not need to install the Skill first, fill in contracts or run scripts individually.

### Step 1: prepare the environment (first use)

Open a conversation in a writable local directory and send:

```text
Download or reuse https://github.com/Lucasuiii/modeling-workbench in a separate
tools directory. Inspect existing checkouts first; do not overwrite local changes.
Read the complete .agents/skills/cumcm-workflow/SKILL.md in the repository.
Follow it to check Python 3.10+, Python dependencies, a MATLAB or Python
computation backend, XeLaTeX and PDF rendering tools. First run the Skill’s
scripts/doctor.py and explain which stages are usable and what is missing.
List proposed installations or environment changes and wait for my approval.
Only prepare the environment; do not initialize a contest project yet.
Report the tools directory, versions and any missing requirements when finished.
```

**If the agent cannot download the repository, use the ZIP alternative below for step 1. The original startup method remains available.**

<details>
<summary>Alternative: download a ZIP first and prepare from local files</summary>

Open the [repository homepage](https://github.com/Lucasuiii/modeling-workbench) in your browser, select **Code → Download ZIP**, and extract the entire archive before asking the agent to proceed. An existing complete local copy can be reused without downloading it again.

Keep the extracted workflow in a separate tools directory, such as `modeling/modeling-workbench-main/`. Store official materials separately and choose a new, nonexistent project output directory for step 2. Supply the directory containing `README.md` and `.agents/`, not the ZIP file or its parent directory. Preserve the hidden `.agents` directory when extracting.

In the environment preparation conversation, replace the original step 1 prompt with:

```text
Prepare the environment using this downloaded and fully extracted local Modeling Workbench.
Workflow tools directory: /absolute/path/to/modeling-workbench-main

Do not clone the repository, check for updates or try other download locations.
Read the complete .agents/skills/cumcm-workflow/SKILL.md in the tools directory.
First run scripts/doctor.py and report usable stages and missing dependencies.
If local files are incomplete, report the missing items and stop repository download attempts.
Reuse installed dependencies. List proposed installations or environment changes and wait for my approval.
Only prepare the environment; do not initialize a contest project yet.
Report the actual tools directory, version and missing requirements when finished.
```

Then continue with the original **step 2**, using the actual extraction path as the tools directory. Downloading the ZIP still requires browser access to GitHub. This route avoids repeated repository download attempts by the agent; it does not make dependency installation offline. Missing paper tools such as LaTeX need not block problem analysis and modeling supported by the base environment; install them before the paper stage.

</details>

### Step 2: start modeling (each new problem)

Once the environment is ready, **open a new conversation**, replace the three paths below and send. Use the tools path from step 1; choose a new output directory that does not exist yet, separate from the tools and materials.

```text
Use Modeling Workbench to begin this modeling task.
Workflow tools directory: /absolute/path/to/modeling-workbench
Official materials directory: /absolute/path/to/official-materials
New project output directory: /absolute/path/to/new-project

Read the complete .agents/skills/cumcm-workflow/SKILL.md in the tools directory.
Check the environment and official materials first; do not overwrite existing work.
Report missing dependencies without installing them in this conversation.
Identify the contest, year, paper language and submission requirements from
the materials; ask me if unclear. Follow the Skill to initialize the project
and begin problem analysis. Wait for my explicit confirmation at model selection,
conclusions before paper writing, and final delivery.
```

**Follow the stage prompts to review the work.** Reuse the prepared environment by starting at step 2 for another problem. To resume interrupted work, provide the project output directory and ask to “resume cumcm-workflow”; resume an existing project instead of initializing it again.

You can also ask “check my environment” or “where is this project now?”. The agent uses environment or project diagnostics to report missing dependencies, evidence issues and pending decisions. These tools do not install software, change project state or approve work for you.

<details>
<summary>Advanced: run environment and project diagnostics manually</summary>

Set `S` to the absolute path of `.agents/skills/cumcm-workflow/scripts` in the tools checkout:

```bash
python3 "$S/doctor.py"
python3 "$S/project_status.py" --project /absolute/path/to/existing-project
```

Add `--json` for the full structured report. Environment checks are stage-specific: missing LaTeX does not prevent modeling. Project checks stop at the current stage and report checker results separately from action checkpoints. Exit code 0 can still mean human confirmation is pending. See [diagnostic tools](.agents/skills/cumcm-workflow/references/diagnostics.md).

</details>

<details>
<summary>Paths, Windows and environment troubleshooting</summary>

- **macOS**: an example path is `/Users/yourname/Documents/official-materials`.
- **Windows: WSL2 recommended**. Run the agent and tools inside WSL2. A materials path might be `/mnt/c/Users/yourname/Documents/official-materials`; a new project can go in `/home/your-wsl-username/modeling-projects/2026B`.
- Use paths visible to the **agent's execution environment**. Python, the computation backend and XeLaTeX must also be available in that environment.
- Native PowerShell has not been validated end to end; the Bash examples later in this README cannot be copied verbatim.
- Ask the agent to check and report missing dependencies; you do not need to configure the entire toolchain manually beforehand. Setup time depends on installed dependencies, and first-time LaTeX setup may take a while.
- Initialization copies and identifies the official materials without modifying the source folder. For open-topic tasks, supply the official theme and requirements.

</details>

<details>
<summary>Already installed? Skill name and version notes</summary>

Invoke `$cumcm-workflow` in Codex or `/cumcm-workflow` in Claude Code. Still provide the materials and new-project directories, and confirm the actual Skill path and environment are usable.

The repository is named `modeling-workbench`; the Skill invocation, directory and `.cumcm` workspace format are unchanged. Current version: **v0.6**; workspaces older than v0.6 are unsupported. The multi-competition extension retains CUMCM/Chinese defaults, so existing v0.6 workspaces need no migration.

</details>

## Competition support

Built from the CUMCM workflow, with a shared modeling, computation, review and Chinese/English paper delivery pipeline for other competitions.

| Competition or task | Available support | Adapt to current requirements |
|---|---|---|
| CUMCM | Complete workflow; Chinese paper scaffold by default | Official template and submission rules |
| Graduate, MathorCup, electrical-engineering and regional contests | General modeling/validation guidance, Chinese PDF and source delivery | Specific formatting, attachments and result files |
| English tasks such as MCM/ICM and APMCM | English writing guidance, English PDF and source delivery | Summary sheets, page accounting and supplementary documents |
| Teddy Cup and other data-analysis tasks | Data processing/evaluation guidance and shared paper delivery tools | Result tables, data fields and package contents |
| Statistical modeling and open-topic tasks | Topic selection, data feasibility and research design guidance | Official theme, data sources and scope of conclusions |

**A generic paper scaffold is not an official template.** Current official requirements take priority. DOCX export and automatic conversion of arbitrary official templates are not provided. The agent supplies the competition name and paper language at the paper stage; you do not need to run initialization commands manually. See the [competition adaptation guide](.agents/skills/cumcm-workflow/references/competition-adaptation.md).

<details>
<summary>What has compatibility testing covered?</summary>

Validation covers actual compilation, rendering and packaging of both language scaffolds, plus synthetic non-CUMCM finalizing flows and existing gates. It does not certify every organizer/year or establish full contest-problem trials for every category.

</details>

---

## 1. What v0.6 is about

**Tooling records machine facts; the agent writes judgement.**

Hashes, `sha256-tree-v1` source snapshots, argv, exit codes, PDF page counts, overfull boxes and missing glyphs from the engine log, values resolved through a locator — all observed by scripts. You write the problem facts, the model, the claims and the paper.

The second change follows from the first: **the model is chosen late, and the choice is earned.**

```text
Problem Analysis
      │
      ▼
Model Design ─────► candidate A / candidate B
      │             · why each is worth considering
      │             · what evidence would tell them apart
      ▼
Computation ──────► cheap exploratory evaluation
      │             record_run.py --candidate CAND-A
      ▼
select A ─────────► status: selected, with a rationale
      │             citing the runs that evaluated it
      ▼
A earns the official computation
      ▼
Validation
```

That chain is structural, not advice: exactly one candidate may end up `selected` (`MODEL-E013`), a selection must cite a run that evaluated it (`MODEL-W014`), selecting or rejecting needs a recorded reason (`MODEL-E014`), and a candidate with no discriminating observation is flagged (`MODEL-W012`). Warnings while `working`, errors once frozen. `cumcm_check.py` prints the comparison under `model_candidates`.

| | v0.5 | v0.6 |
|---|---|---|
| JSON Schemas | 22 | 21 |
| Scripts | 15 | 19 |
| Hand-written contracts | 14 | 9 |
| State knobs | mode × profile × gate-mode | mode × gate-mode |
| Stage statuses | 6 | 4 |

## 2. Architecture

```text
orchestrator
  -> modeling
  -> computation (MATLAB or Python; exploratory ⇄ revision -> official run)
  -> independent validation
  -> fresh paper task
  -> delivery
```

These are responsibility boundaries, not a pile of small Skills. The main `cumcm-workflow` Skill routes; the Reviewer Skill shipped inside the review package performs context-separated validation.

| Stage | Job | Canonical artifacts | Written by |
|---|---|---|---|
| `intake` | preserve and inventory official files | `SOURCE_MANIFEST.json` | `init_project.py` |
| `problem-analysis` | subproblems, facts, ambiguities, acceptance targets | `PROBLEM_FACTS.json`, `TASK_CAPABILITIES.json` | agent |
| `model-design` | propose candidates and their discriminators; freeze once one is selected | `MODEL_CONTRACT.json` (draft while working) | agent |
| `computation` | pick one backend, explore, then freeze the official run | `RUN_MANIFEST.json`, `RESULTS_INDEX.json` | `record_run.py`, `index_result.py` |
| `validation` | independent P0 check, record P1/P2 | review package/result, `CLAIM_LEDGER.json` | scripts + agent |
| `paper` | select claims and representations, write, QA the PDF | `PAPER_PLAN.json`, LaTeX, QA sidecars, PDF | agent + `init_latex_paper.py`, `record_compile.py` |
| `delivery` | freeze the submission against official rules | `COMPILE_RECEIPT.json`, `DELIVERY_MANIFEST.json` | `record_compile.py` + agent |

Four cross-stage interfaces only: `modeling-computation`, `computation-validation`, `validation-paper`, `paper-delivery`. A fresh task reads its handoff first.

## 3. Two knobs

v0.6 deleted the `strict`/`sprint` profile. `mode` (in state) decides what must be complete; `--gate-mode` decides whether human gates count toward blocking.

- `working`: official-input protection, real execution before citation, exact locators, non-fabrication. A draft model contract is enough, `CROSS_QUESTION_LEDGER.json` is optional, stage ordering is advisory.
- `finalizing`: frozen model contract, stage decisions and snapshots, fresh handoffs, bounded independent review, paper/PDF QA, delivery binding.

Stage statuses: `not_started`, `in_progress`, `passed`, `needs_revision`.

The three required human stops are model selection, conclusions before paper writing, and final delivery. After showing current material and receiving an explicit reply, use `record_decision.py --decision accepted --confirm-human` with `--stage`, `--task-turn-ref` and `--summary`; it fills existing checkpoint fields and advances state. Technical stages omit `--confirm-human` after passing checks. Model self-review is not human acceptance; records depend on truthful references to user replies. `preflight` reports pending review without blocking exploration; `enforce` requires acceptance in both modes, as do the corresponding official-run and paper entry points.

Findings are graded by consequence: hard invariant / `P0` blocks; `P1` (assumptions, baselines, sensitivity — and **everything about exploratory runs**) stays visible; `P2` never enters the gate.

## 4. Recording computation

```bash
S="$PWD/.agents/skills/cumcm-workflow/scripts"  # set from the repository root

# exploration costs nothing to record
python3 $S/record_run.py --project <p> -- python3 code/try.py

# an exploratory run can also settle the model comparison
python3 $S/record_run.py --project <p> --candidate CAND-A -- python3 code/try_a.py

# freezing costs only the declarations the tool cannot infer
python3 $S/record_run.py --project <p> --official --capability CAP-Q1-001 \
  --source code/solve.py --input data/q1.csv:formal \
  --output results/q1.json:claim --assert-file results/assertions.json -- python3 code/solve.py

# the value is read back through the locator, never transcribed
python3 $S/index_result.py --project <p> --result-id RES-Q1-001 --run RUN-Q1-001 \
  --locator results/q1.json#/minimum_cost --name "Minimum cost" --unit CNY \
  --scope "declared candidates only"

# a rerun appends a successor; the parent and its evidence are untouched
python3 $S/record_run.py --project <p> --rerun RUN-Q1-001 --official
python3 $S/index_result.py --project <p> --follow-lineage
```

Exploratory runs are recorded, never trusted, and never block. Only a successful `official_run: true` run may support a formal result.

**Runs are append-only and their evidence is frozen.** `--rerun` never overwrites: it appends `RUN-Q1-002` with `parent_run_id: RUN-Q1-001`, and every run copies its declared source and outputs into `runs/<id>/source/…` and `runs/<id>/outputs/…`, mirroring the original layout. Frozen copies are immutable, so a preserved run stays verifiable forever — and the most valuable check survives, because staleness is now measured as *frozen copy versus live file*:

```
ERROR RUN-E020  the working tree no longer matches this official run: code/solve.py
```

A run may also only claim what it produced and what it verified: declared outputs are checked for a changed timestamp across the execution, so a program that exits 0 without rewriting its output cannot have the previous run's file frozen as its own evidence, and a rerun never inherits its parent's assertion verdicts. Only a *successful official* rerun supersedes its parent, and every formal consumer resolves the current run through one shared resolver.

Superseded runs are exempt from drift detection (of course they differ); altering a frozen copy is a different failure, `RUN-E021`. Supersession is derived from the parent chain and never written back — stamping the old manifest would change its hash and stale every decision bound to it. A result still citing a superseded run raises `RESULT-E017`, and `index_result.py --follow-lineage` re-points it explicitly, because choosing which run backs a claim is judgement, not a machine fact.

## 5. Iterating and scoped redo

Reopening an upstream stage is one command, not a hand-edit of `state.json`:

```bash
python3 $S/record_decision.py --project <p> --stage model-design \
  --decision revision_requested --decision-id DEC-007 --reviewer <name> \
  --task-turn-ref <ref> --summary "the Q2 model does not fit the observed regime"
```

Reopening invalidates the affected human checkpoints and downstream snapshots, and moves stage state back. Then ask what the change actually costs:

```bash
python3 $S/plan_redo.py --project <p> --changed code/solve_q2.py
```

`plan_redo.py` walks `official source -> fact -> capability` and `source -> official run -> result -> claim -> section -> PDF` and names the runs to re-run, the findings to re-review, the sections to rewrite — and the ones that are **not** affected. The deterministic check stays exhaustive because it is cheap; what gets scoped is re-running, re-reviewing and re-writing.

## 6. Independent validation

Applicable [mechanism guidance](.agents/skills/cumcm-workflow/references/mechanism-validation.md) connects the verification plan, program-written assertions and independent review; the review package freezes the same reference. It adds no universal test checklist.

Review the current task’s risks: task coverage, model and solution validity, discriminating evidence and claim scope. Choose checks appropriate to the problem, not a fixed experiment checklist. The first review is full and context-separated. The package copies only canonical evidence for formally indexed results and declares `context_excluded` — the originating task transcript, debug history, failed runs and prior review prose it physically left out. It does not claim the reviewer holds no conclusions.

The result template ships with every independence field `null`; the reviewer or the user must assert them, and a null fails. Differing originating/reviewer task references are a paste guard, not proof.

Verdicts: `accepted`, `accepted_with_concerns`, `revision_required`, `inconclusive`. Only an open P0 permits `revision_required`; the next package then defaults to a targeted re-review carrying a self-contained `TARGETED_FINDINGS.json`.

## 7. One backend

Default `{"preferred":"matlab","fallback":"python","selection":"auto"}`. MATLAB preference breaks ties only. Detection order: explicit `implementation.matlab_executable`, `matlab` on PATH, macOS `/Applications/MATLAB_R*.app/bin/matlab`. A preferred backend may fall back; a task `required_backend` must fail rather than switch. Implement and officially run one language.

## 8. Paper and LaTeX

```text
verified results -> claim selection -> prose/equation/table/figure planning
  -> representations -> paper structure -> LaTeX -> rendered PDF QA
```

`PAPER_PLAN.paper_structure` is the source of truth for the body; the initializer only turns it into section files and `main.tex` input order.

```bash
python3 $S/record_compile.py --project <p> --update-quality
```

The receipt records project sources and figures actually read by TeX; source ZIPs use the same set. Log verdicts use the final pass. Refreshing machine facts preserves visual findings with their original PDF binding, so old reviews require renewal after the PDF changes. Unavailable rendering never reuses old page records, and a failed recompile retires the current successful receipt.

Compiles, hashes the PDF, reads the page count, rasterises every page into `.cumcm/tmp/pages/`, derives layout checks from the engine log, and refreshes the machine fields of `PAPER_QUALITY_REPORT.layout_report`. Those pages are what the final check has to present — then actually look at them.

For delivery, run `refresh_evidence.py --project <p> --only delivery --package`. ZIPs preserve project-relative paths and are checked for missing or stale declared files; this does not replace execution after extraction. Refresh never rewrites official sources or unchanged manifests.

v0.6 deleted `PAPER_TRACEABILITY.json` (the property it promised is measured directly on the PDF) and the eight-dimension self-attested quality matrix.

## 9. Getting started

1. Give the agent the official local path: *"use cumcm-workflow, initialise a contest project from /absolute/path/to/2026B"*.
2. Work in `working` mode: explore with zero-flag `record_run.py`, then `--official` once the command is the one you mean to cite. Build a handoff before crossing responsibilities.
3. Switch to `finalizing` and complete validation, a fresh paper task, PDF QA and delivery.

```bash
python3 $S/init_project.py --project /path/to/new-project --project-id CUMCM-2026-B --official /path/to/official-files
python3 $S/cumcm_check.py --project /path/to/project --stage validation --gate-mode enforce
python3 $S/set_mode.py --project /path/to/project --mode finalizing
python3 $S/build_handoff.py --project /path/to/project --transition validation-paper
python3 $S/build_independent_review_package.py --project /path/to/project --review-mode auto
python3 $S/plan_redo.py --project /path/to/project --changed code/solve.py
```

## 10. Codex and Claude Code

The single canonical tree is `.agents/skills/cumcm-workflow/`.

- **Codex** picks up `.agents/skills/` inside the repository; `agents/openai.yaml` supplies the display name and default prompt. Trigger with `$cumcm-workflow`.
- **Claude Code**: use `/cumcm-workflow` or explicitly request the workflow inside the checkout. `.claude/skills/cumcm-workflow/SKILL.md` only links to the canonical Skill, relative to the router file rather than the working directory. Root `CLAUDE.md` distinguishes contest work from repository maintenance; engineering rules apply only to maintenance.

For a personal Claude Skill usable from any directory and kept in sync with the checkout, run this from the repository root to link the **complete canonical directory**. If the destination exists, inspect that installation first; do not overwrite it.

```bash
mkdir -p ~/.claude/skills
ln -s "$PWD/.agents/skills/cumcm-workflow" ~/.claude/skills/cumcm-workflow
```

Keep the checkout in place; rebuild the link if it moves. For a standalone installation, copy the complete `.agents/skills/cumcm-workflow/` directory instead. Copies do not update automatically: resync the complete directory when upgrading. Do not copy only the `.claude/` router.

Both agents read the same stage rules. Resolve absolute script paths from the actual Skill directory; scripts locate schemas and assets through `Path(__file__)`. Entry tests verify the router link, script startup from a relocated complete Skill, and matching metadata.

### Computation provenance boundaries

- Entry points must come from a recognized direct Python script or MATLAB `run('path.m')` invocation. `--source` declares snapshot coverage, not execution.
- Previous claim outputs and assertion files are backed up and moved aside before execution. Touching a path cannot reuse old bytes; identical recomputation remains valid.
- Formal handoffs and review packages verify actual input/output SHA256. Multiple successful rerun branches require an explicit choice, never a newest-child guess.
- Python runtime comes from a pre-execution probe of the model interpreter. Seeds, dependencies and toolboxes are declarations, not evidence of use. Reruns retain seed/toolbox declarations but never inherit assertions.

See the [computation guide](.agents/skills/cumcm-workflow/references/04-computation.md) for invocation limits. Historical records are not rewritten or retroactively certified.

## 11. Development

```bash
python3 -m pip install -r requirements-ci.txt
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m compileall -q .agents/skills/cumcm-workflow/scripts tests
```

CI runs the full suite in two environments: Python 3.10, and Python 3.13 with TeX Live/Poppler for real compilation. There is no additional duplicate 3.13 job. Shared fixtures live in `tests/workflow_fixtures.py` and `tests/recorder_fixtures.py`; all regression cases are retained. Tool-dependent tests skip locally when their tools are absent.

## 12. Limits and licence

Fresh context reduces contamination but cannot prove a reviewer is independent or correct. Digests prove artifact identity, not mathematical validity. A frozen model contract can degrade into a description of whatever the code does; the machine can only check that the verification plan maps to recorded assertions, and that the selected candidate cites runs that evaluated it. Log-derived layout checks cannot see that a label inside a figure is too small. See [known limitations](docs/limitations.md).

[MIT License](LICENSE).
