# Adapt to the competition, preserve the workflow

Use this guide when starting a competition other than a familiar CUMCM problem, or when the requested language, deliverables or research format differ. It is a routing guide, not a source of current competition rules. The same competition can contain several task families.

## Identify the actual assignment

Read the user-supplied current official problem/theme, attachments and submission instructions using [intake](01-intake.md). Distinguish a paper template, a results spreadsheet and a document describing submission rules; their file extensions do not determine their roles.

Summarize the competition/year, requested language, fixed problem versus open topic, required outputs and material uncertainties in the existing `PROJECT_BRIEF.md`. Keep substantive task requirements in `PROBLEM_FACTS` and `TASK_CAPABILITIES`, with source locations, so they reach modeling and review. These are facts and writing requirements, not new runtime options. A note in the brief does not reconfigure a script.

For submission constraints, retain the source location and precise scope: which pages count, which attachments are separate, where identifiers are required or forbidden, accepted formats, and any restrictions on data or tools. Unknown is not permission and not a guessed default. Ask only about material missing information; continue reversible analysis where it is unaffected. Never fetch neighboring official files without user authorization or replace current rules with a competition-name lookup.

## Route by the work, not by a template count

The examples below identify useful entry points, not verified support for each organizer/year.

| Assignment encountered | Examples of competition labels | Guidance to load |
|---|---|---|
| Fixed problem, Chinese modeling paper | CUMCM, 华为杯, MathorCup, 电工杯, 华东杯, 华中杯, 五一杯, 深圳杯 and other regional contests | Existing stages; select sections of [task-driven modeling](task-driven-modeling.md) from the actual mathematical task |
| Fixed problem, English paper and possibly an audience-specific document | MCM/ICM, APMCM, international 数维杯 or 认证杯 tracks | Same modeling/validation stages; [competition writing](competition-writing.md) for English and supplementary documents |
| Data-centered prediction, classification or decision task | 泰迪杯 and data-oriented tasks in other contests | Data audit and predictive evaluation in [task-driven modeling](task-driven-modeling.md); preserve required result-file layouts |
| Official theme with a team-selected research question | Statistical-modeling and open-topic tracks | [Open-topic research](open-topic-research.md), then the common model/computation/validation stages |
| Engineering, physical or simulation-heavy task | Any of the above | Mechanism, units, numerical accuracy and parameter identification; do not pick a solver merely from the competition label |

No fixed model count, chart quota, page target or diagram tool follows from this table. A topic named “prediction” may actually require an actionable decision; an English-language problem may require no memo at all.

## What v0.6 tools can actually do

- The problem/model/result contracts and run recorders can organize fixed questions or explicitly identified team-defined research questions. Keep MATLAB/Python selection and the existing evidence semantics.
- `init_project.py --official` accepts a supplied official theme/rule document as an input; it does not require a pre-existing numbered problem. Supply a truthful project ID. Its generated CUMCM brief heading is a default, not a competition determination; correct the descriptive brief when adapting it. Keep team data separate from that official input set and classify its provenance honestly.
- `init_latex_paper.py` generates a Chinese CTeX scaffold and writes `competition: CUMCM`; its schema also requires that competition. It has no English/competition-selection switch. Even `official_package_adapter` does not remove the CUMCM restriction.
- Delivery expects a reviewed PDF, editable LaTeX sources and computation sources. Word/Markdown-only delivery has no export-receipt path in this version. Do not rename a DOCX ZIP as a LaTeX package or mark an ordinary converter run as a TeX compile.

For a non-CUMCM project, use the applicable analysis, modeling, computation and review guidance, and prepare a clearly labeled paper draft after the existing conclusion checkpoint. Report the unsupported automated paper/delivery boundary before using it; do not invoke the CUMCM LaTeX initializer as if it supported the new competition. If an authorized separate export is needed, deliver it honestly as a separately reviewed artifact, not as a passed v0.6 finalizing pipeline. Ask for a targeted adapter change only if that automated completion is requested.

## Preserve the current decisions

Present the selected research scope, objective, candidates and evidence at the existing model-design checkpoint. Present reviewed conclusions before writing. Retain the final-artifact checkpoint for any actual delivery. There is no extra mandatory “competition approval” or “topic approval” stage.

If a rule clarification changes the task, model or accepted conclusions, use the existing revision and re-review procedure for the affected work. Do not treat a prose edit in the brief as automatically invalidating machine snapshots; put consequential changes into the relevant existing contracts and explicitly reopen affected decisions. Do not claim new automatic rule checking: semantic completeness and current-rule compliance still require review.
