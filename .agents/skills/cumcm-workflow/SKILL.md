---
name: cumcm-workflow
description: Build or resume mathematical-modeling competition work, including CUMCM, MCM/ICM, graduate and regional contests, data challenges, and open-topic statistical modeling. Guide problem framing, modeling, computation, validation, Chinese or English LaTeX writing, and reviewed PDF/source delivery using current official requirements. Not for ordinary paper polishing.
---

# Modeling Workbench

Spend reasoning on the problem, mathematics, experiments and explanation. Tools maintain execution records, hashes, snapshots and stage state. Do not create extra checklists or repeatedly edit contracts to silence warnings.

## Competition and task routing

For a new competition, read [competition adaptation](references/competition-adaptation.md) to identify the current official requirements and the supported automation boundary. Competition names do not determine methods, page limits or evidence standards. Keep the existing stages, two knobs and three checkpoints.

Read additional guidance only when the active work needs it:

| Current need | Read |
|---|---|
| Choose a research question under an official theme; find suitable data | [Open-topic research](references/open-topic-research.md) during problem analysis |
| Choose a model, audit data, design a useful comparison within the available budget | [Task-driven modeling](references/task-driven-modeling.md) during analysis/model design/computation |
| English summary, audience-specific memo, references or format adaptation | [Competition writing](references/competition-writing.md) during paper planning |

For paper initialization, pass the actual `--competition` and `--language zh|en` to `init_latex_paper.py`; omitted options retain CUMCM/Chinese behavior. The shared LaTeX/PDF compile, review and source-package chain works across competition names. Generic scaffolds are not official templates: current-rule compliance, page QA and the three checkpoints still apply. DOCX export is not implemented.

## Start or resume

1. Read the project's `.cumcm/state.json` and the incoming handoff, if present. Resume exact `0.6.0` projects; older schemas are unsupported.
2. For a new project, use [intake](references/01-intake.md) and `init_project.py` with the supplied official files.
3. Read **only the active stage guide** below. Consult a schema only when the guide and command help leave a specific field unresolved; do not load the checker to learn the workflow.
4. Define `S` as the **absolute path** to this Skill's `scripts` directory. All examples use `python3 "$S/<command>.py"`; the contest workspace does not contain these scripts.
5. After interruption, check pending human decisions before continuing. Existing downstream files do not establish approval. Never infer approval from a quota reset, a new task, or “continue”.

## Setup and progress diagnostics

On first setup or an environment change, run `python3 "$S/doctor.py"`; on resumption or a progress question, run `python3 "$S/project_status.py" --project <p>`. Both print reports without changing project state. Summarize what is usable, what blocks the next action, and the next step; continue authorized work instead of adding a confirmation point. Missing paper tools do not block modeling. A ready preflight is not approval: read the separately reported checkpoint availability. Use [diagnostics](references/diagnostics.md) for probe depth, JSON output, optional model dependencies and exit codes. Do not run diagnostics on every reply or reinstall an already prepared environment.

## Three checkpoints (human by default)

| Before | Show the user | Record after their explicit reply |
|---|---|---|
| Official computation | Objective, constraints, all candidates and their discriminating evidence, chosen scope, any unanswered requirement | `model-design` |
| Paper writing | Every claim's text, scope, evidence state, and open P0/P1 | `validation` |
| Final delivery | Current PDF pages, answers, remaining findings and actual delivery files | `delivery` |

By default, stop the dependent work after presenting the material. Model self-review is useful judgement, **never human acceptance**. A reply before the material was shown does not approve it. If a reviewed claim or model changes, show the revision and obtain a new decision; do not relabel the old acceptance.

After the user accepts **all the presented current material**, one command fills the existing checkpoint, records its snapshot and advances state:

```bash
python3 "$S/record_decision.py" --project <p> --stage <stage> \
  --decision accepted --confirm-human --task-turn-ref <user-reply-ref> \
  --summary <what-the-user-accepted>
```

### Explicit stage-scoped delegation

**At conversational initialization**, briefly explain delegation in the user's language before offering the choice. Keep the explanation and the question in one message. For example:

> 托管就是把你指定的决定交给主代理。它会根据试算和独立复核结果作判断，并记录理由。最终本地验收包括逐页检查论文和核对交付包，对外提交仍需你另行同意。
>
> 这个项目你想怎么安排？
> 1. 人工确认：选模型、定结论和最终验收都由你确认。
> 2. 托管建模：主代理选模型、定结论，你验收成品。
> 3. 全程托管：这三项都交给主代理。

Accept a custom subset. If the opening request already specifies the decision owners, use it directly. An unqualified yes to an ambiguous question cannot grant final delivery. Leave the choice pending until the user replies; read-only intake may proceed. An explicit skip uses human review. A resume uses the existing project and its stage grants; do not show the startup question again.

Pass the selected checkpoints as repeated `--delegate-stage` arguments to `init_project.py`, together with `--user-turn-ref` pointing to the reply. Omit both for human review. Tell the user who owns each checkpoint after initialization. Direct, noninteractive calls without flags retain human review.

The user may explicitly delegate judgment to the lead agent for a named checkpoint. Never infer delegation from a general request to continue, and never self-grant it. The user may delegate some stages while retaining the others; final delivery remains human-controlled unless separately delegated. Record the actual user-turn reference and only the stages the user explicitly delegated. For each such stage the lead agent must review all current material and record its own identity and decision honestly:

```bash
python3 "$S/record_delegation.py" --project <p> --stage <stage> --user-turn-ref <actual-user-delegation-turn>
python3 "$S/record_decision.py" --project <p> --stage <stage> --decision accepted --delegated \
  --reviewer <actual-lead-agent-identity> --task-turn-ref <same-user-delegation-turn> --summary <review-and-decision>
```

On resume, or when asked who decides, run `project_status.py --project <p>`. Report `decision_owners` for the next decisions, even at intake. When the user takes a stage back, run `record_delegation.py --project <p> --stage <stage> --revoke --user-turn-ref <actual-revocation-turn>` for that stage. Future delegation requires a fresh explicit instruction. Historical signatures stay bound to the grant used at the time.

This records an agent decision, never a human approval. Delegated validation requires a current independent review and package; delegated delivery additionally requires a valid delivery package, final quality and compile records, and every rendered page. `--scope` can add files but cannot remove the default material from a delegated decision. The authorization and reviewed material are snapshot-bound; changed material requires a new review and decision. Delegation does not replace independent review, allow external submission, or authorize a push. Before delivery the lead agent must actually inspect all rendered pages if delivery was delegated. User-turn references are honest conversation records, not authentication.

If a decision write was interrupted, run `record_decision.py --project <p> --recover` before dependent work. Recovery checks the original material and reply. If a binding changed, reopen the named stage and present the revision.

No manual timestamps, presented-ID lists, hashes or state edits. Other stages are technical completions: use the same command **without** `--confirm-human`, after their checks pass, referencing the current task. They do not require another user confirmation. Reopen with `--decision revision_requested`; downstream approvals become unusable. Decisions are honest conversation records, not cryptographic proof that a person answered.

## Working and finalizing

- `working` permits incomplete model drafts and cheap exploratory runs. Failed exploration never blocks. Use `preflight` while drafting: pending review is visible but does not fail the command.
- `enforce` requires the three checkpoints in **both modes**, using human confirmation or explicit stage-scoped delegation. Official recording and paper entry also check the corresponding stop, so skipping a checker does not silently replace approval with self-review.
- `finalizing` requires complete current evidence, decisions, independent review and delivery binding. Switch with `set_mode.py`. Do not run full finalizing checks before exploratory model selection: formal assertions do not exist yet.

```bash
python3 "$S/cumcm_check.py" --project <p> --stage <stage> --gate-mode preflight
```

Warnings remain visible; they are not a request to rewrite upstream evidence. An error requires repair; `awaiting_review` means present the material and wait. Passing does not prove mathematical correctness.

## Stage guides

| Work | Read | Outgoing handoff |
|---|---|---|
| Problem analysis | [02-problem-analysis.md](references/02-problem-analysis.md) | — |
| Model candidates and cheap comparisons | [03-model-design.md](references/03-model-design.md) | `modeling-computation` |
| One backend, official runs and result indexing | [04-computation.md](references/04-computation.md) | `computation-validation` |
| Independent review and conclusions | [05-validation.md](references/05-validation.md) | `validation-paper` |
| Reader-facing paper and visual QA | [06-paper-writing.md](references/06-paper-writing.md) | `paper-delivery` |
| Actual delivery packages | [07-compile-delivery.md](references/07-compile-delivery.md) | final package |

Build handoffs with `build_handoff.py`; read [handoffs](references/handoffs.md) only at a crossing. `computation-validation` and `validation-paper` must cross into fresh tasks. Task refs are a paste guard, not proof of independence; same-model new-context review remains correlated. After a full review finds P0, the package builder defaults to targeted re-review of those findings.

## Evidence without paperwork

- Preserve official files. `record_run.py` records real execution and freezes declared evidence; `index_result.py` reads values from outputs. Never type machine facts into contracts.
- Choose a model after cheap candidate evaluation; officially implement one backend. MATLAB preference breaks ties, not task suitability. No parity implementation unless requested.
- Runs are append-only. A rerun uses `--rerun`, never overwrites its parent. Only successful official descendants supersede. `plan_redo.py` scopes affected work; it does not waive checks.
- P0: wrong computation/data, task mismatch, scope beyond evidence, stale evidence, fabricated approval/review, or unusable delivery. P1: weaknesses **within a supported and task-relevant scope**. P2: optional improvements. Narrowing a claim cannot erase an unanswered requirement.
- Derive review priorities from the current task, not previous failure examples. Check task coverage, model assumptions, solution validity and claim scope using a few tests or independent arguments that could expose a plausible wrong answer. Choose applicable mathematical properties; do not require every problem to run the same tests. A repair must address the failure mechanism and affected conclusions, not only the failing example.
- Claims use `supported_not_reproduced` unless an isolated rerun and comparison establish `reproduced`. Label simulations and synthetic scenarios explicitly.
- Keep workflow IDs and evidence bookkeeping out of reader-facing prose. Compilation logs do not establish visual quality; inspect rendered pages.
- `refresh_evidence.py --only delivery --package` builds declared ZIPs with project-relative directories and refreshes their existing metadata. The paper ZIP uses compilation dependencies. The support ZIP omits organizer originals by default. Add `--internal-reproduction` only for a local copy with frozen inputs. See the delivery guide for per-file exceptions and submission archive inspection. It never refreshes official sources. No-change refreshes do not rewrite files.

Use [artifact contracts](references/artifact-contracts.md) only for an unfamiliar artifact and [evidence rules](references/evidence-rules.md) for unresolved evidence semantics. Do not read every reference at startup.
