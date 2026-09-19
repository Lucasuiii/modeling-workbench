# Modeling Workbench

English | [简体中文](README.md)

An AI-agent workflow built around the China Undergraduate Mathematical Contest in Modeling. It starts from official materials and connects modelling, computation, review, paper writing and final delivery into one inspectable, traceable evidence chain. The Skill also provides task-driven modeling, open-topic research and Chinese/English writing guidance for other modeling competitions.

**Preserve official materials → analyse the problem → evaluate model candidates → run official computation → review independently → write in LaTeX → QA and deliver the PDF**

It does not supply a ready-made answer or decide whether a model is mathematically correct. It makes sure that **every conclusion entering the paper can be traced to the official problem and a computation that actually ran**, while returning decisions to you at model selection, conclusions before paper writing, and final delivery.

Runs under **Codex** and **Claude Code**. Current version: **v0.6**; older workspaces are not supported.

The repository is named `modeling-workbench`; the Skill invocation remains `$cumcm-workflow`, with the same Skill directory and `.cumcm` workspace format.

## Competition support

**Other competitions can reuse the modeling, computation and review methods and writing guidance, but automatic paper generation and final delivery are not yet compatible with every competition.** Use the support levels below:

| Competition or scenario | Current support | Still requires adaptation |
|---|---|---|
| CUMCM | Existing modeling, computation, review, LaTeX/PDF generation and delivery pipeline | Current official templates and submission requirements still need checking |
| Fixed-problem graduate, MathorCup, electrical-engineering and regional contests | Problem decomposition, model candidates, run recording and result indexing, mechanism validation and paper argument guidance | Competition-specific paper templates and automated final delivery |
| English tasks such as MCM/ICM and APMCM | The shared methods, plus English summaries, terminology and requested audience-specific documents | Automatic English templates and competition-specific automated final delivery |
| Teddy Cup and other data-analysis tasks | Data definitions, cleaning, leakage prevention, baselines and task-matched evaluation guidance; reusable computation evidence tools | Result files, papers and submission packages required by the current rules |
| Statistical modeling and open-topic tasks | Theme constraints, data feasibility, research design, team-defined questions and evidence scope guidance | Full end-to-end validation of open-topic projects and their submission formats |

**Tool boundary:** the paper initializer and template schema remain bound to CUMCM, and automated delivery requires LaTeX/PDF; there is no DOCX export pipeline. Other competitions can proceed with applicable analysis, modeling, computation and review, then prepare a draft after the conclusion checkpoint. This does not establish a passed automated final delivery.

For another competition, give the agent the **competition name, year, official materials, paper language and intended delivery format**. Ask it to read the [competition adaptation guide](.agents/skills/cumcm-workflow/references/competition-adaptation.md) and explain the executable scope before proceeding. Page limits, language, templates and submission requirements come from current official materials.

This table describes guidance coverage and tool reuse, not per-contest end-to-end certification. Passing the existing regression suite does not establish successful real-problem trials for every competition.

## Quick start

### 1. Prepare the materials

Put the current year's official materials in one local directory. During initialization, the workflow copies and identifies these files without modifying the source directory.

| What to prepare | Required? | Notes |
|---|---|---|
| **Codex or Claude Code** | Required | Needs network, local file and terminal execution access |
| **Python 3.10+** | Required | The agent checks dependencies on first use; official computation may use MATLAB or Python |
| **Official problem statement or research theme** | Required | The PDF, Word file or other official edition defines the task, theme and constraints; team-defined questions must not be presented as official questions |
| **Official attachments and result templates** | Required when supplied | Raw data, instructions and files such as `result*.xlsx`; keep them together and do not overwrite the originals |
| **Current format, submission and AI-use rules** | Required when published | Used for paper layout, submission packaging and compliance; do not substitute rules from another year |
| **A new output directory** | Required | Use an absolute path that does not yet exist, separate from both the official materials and workflow tools |

### 2. Check the path format

- **macOS / MacBook**: an example materials path is `/Users/yourname/Documents/official-materials`.
- **Windows (WSL2 recommended)**: run the agent and workflow tools in the WSL2 Linux environment. Windows `C:\Users\yourname\Documents\official-materials` typically maps to `/mnt/c/Users/yourname/Documents/official-materials`; a new project can use `/home/your-wsl-username/cumcm-projects/2026B`.
- **Native Windows PowerShell**: the Bash examples later in this README, especially `$S`, `$PWD` and `ln -s`, cannot be copied verbatim. CI currently runs on Linux and native Windows has not been validated end to end, so WSL2 is the preferred route.

Use path formats visible to the **agent's execution environment**; do not mix Windows and WSL paths. Python, the selected computation backend and XeLaTeX must also be installed in that execution environment.

### 3. Conversation one: download the workflow and prepare the environment

For first use, open a dedicated conversation that handles only the workflow download and environment setup. **Do not provide the contest-materials path or initialize a project yet.** From a writable local working directory, send:

```text
Prepare the runtime environment for the latest main workflow from
https://github.com/Lucasuiii/modeling-workbench.
This conversation is only for downloading the workflow, reading its instructions,
and checking and configuring the environment. Do not read a contest problem,
initialize a contest project, or begin modelling.

First inspect the current working directory without changing it. Use git clone to download the repository
into a separate tools directory. If a checkout from the same repository already exists,
inspect its remote, version and local changes; do not overwrite existing work.
Create a separate clean checkout if needed.
Read the complete .agents/skills/cumcm-workflow/SKILL.md inside the tools directory.
Using the Skill's absolute path, check Python 3.10+, required Python dependencies,
an available MATLAB or Python computation backend, XeLaTeX, and PDF rendering support.

Before installing dependencies or changing the system environment, list the proposed
changes and wait for my explicit approval. Once the environment is ready, stop and report
the workflow directory, absolute Skill path, detected versions, available backend,
and any remaining limitations for use in the next conversation.
```

Even if the Skill is already installed, use this conversation to confirm the checkout version, actual Skill path and runtime environment. A discoverable Skill alone does not prove that the environment is ready.

### 4. Conversation two: initialize the contest project and begin

After conversation one confirms that the environment is ready, **start a new conversation**. Insert the workflow directory it reported, your official-materials directory, and a new project output directory into this prompt:

```text
Use the prepared Modeling Workbench to begin this contest problem.

Workflow tools directory: /absolute/path/to/modeling-workbench
Official materials directory: /absolute/path/to/official-materials
New project output directory: /absolute/path/to/a-directory-that-does-not-exist

First inspect the workflow and official-materials directories without changing them.
Confirm the workflow version and working-tree state, and do not overwrite existing work.
Read the complete .agents/skills/cumcm-workflow/SKILL.md and invoke scripts using
the Skill's absolute path. Confirm that the Python dependencies, computation backend,
and XeLaTeX environment prepared in conversation one are still available.
If the environment is incomplete, stop and report what is missing; do not install
dependencies or change the system environment in this conversation.

Identify the problem statement, attachments, result templates, and current format,
submission and AI-use rules. Initialize a new project from the official materials,
then follow the Skill into problem reading and decomposition.
Stop for my explicit confirmation at model selection, conclusions before paper
writing, and final delivery.
```

If the Skill is already installed, conversation two may invoke `$cumcm-workflow` in Codex or `/cumcm-workflow` in Claude Code, but it should still provide the workflow, official-materials and new-project directories.

### 5. What you do after launch

The first conversation leaves behind reusable workflow tools and an environment report. The second copies the official materials, initializes the project, and begins with problem reading and decomposition. You do not need to prefill contracts or run every script yourself. Review the current material and decide whether to continue at the three explicit human checkpoints. After an interruption, return to the second conversation, provide the output directory, and ask to “resume cumcm-workflow”.

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

## 11. Development

```bash
python3 -m pip install -r requirements-ci.txt
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m compileall -q .agents/skills/cumcm-workflow/scripts tests
```

CI runs the contract tests on Python 3.10 and 3.13. `tests/test_recorders.py` exercises the recorder chain with real execution and a real `xelatex` compile, skipping when the engine or the ctex class is absent.

## 12. Limits and licence

Fresh context reduces contamination but cannot prove a reviewer is independent or correct. Digests prove artifact identity, not mathematical validity. A frozen model contract can degrade into a description of whatever the code does; the machine can only check that the verification plan maps to recorded assertions, and that the selected candidate cites runs that evaluated it. Log-derived layout checks cannot see that a label inside a figure is too small. See [known limitations](docs/limitations.md).

[MIT License](LICENSE).
