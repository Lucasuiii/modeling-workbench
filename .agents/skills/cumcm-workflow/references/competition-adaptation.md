# Adapt to the competition, preserve the workflow

For Huawei Cup / 中国研究生数学建模竞赛, also read [Huawei delivery adaptation](huawei-delivery.md): current official cover, abstract/anonymity checks, submission filenames, attachments and measured MD5 binding.

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

## Shared LaTeX/PDF delivery

- `init_project.py --official` accepts a supplied official theme/rule document as an input; it does not require a pre-existing numbered problem. Supply a truthful project ID, keep team data separate from the official input set and classify provenance honestly.
- After the existing conclusion checkpoint, `init_latex_paper.py --competition <actual-name> --language zh|en` generates a Chinese CTeX or English article scaffold. The competition name is stored in the template manifest; it does not select a rule preset. Omitting the options preserves CUMCM/Chinese defaults. The template manifest keeps the chosen scaffold ID/mode, so downstream tools use the actual files rather than guessing language from the contest name.
- Use the same `record_compile.py`, `paper-delivery` handoff, package builder and final checks for every competition. They bind the real PDF and editable sources. The competition is part of the existing paper-stage snapshot and handoff; changing it after review requires renewed review through the existing process.
- A declared official paper template still takes priority: generic initialization stops so the agent can adopt/adapt the supplied template and maintain the existing `official_package_adapter` manifest. That adapter may now identify the actual competition. Automated conversion of arbitrary official templates is not provided.
- Generic scaffolds start with `official_compliance: unverified`. Apply current rules for title/summary sheets, page size/counting, identifiers, appendices and required supporting files before the existing final compliance review. A successful compile does not establish compliance.
- Delivery expects a reviewed PDF, editable LaTeX sources and computation sources. Word/Markdown-only delivery has no export-receipt path. Do not rename a DOCX ZIP as a LaTeX package or mark an ordinary converter run as a TeX compile.

For example, after `PAPER_PLAN` and current human conclusion acceptance are ready:

```bash
python3 "$S/init_latex_paper.py" --project <p> --competition 'MCM/ICM' \
  --language en --competition-year <year> --title '<actual title>' --keywords '<actual keywords>'
```

Use `--language zh` with the actual competition name for a Chinese paper. Read [LaTeX template guidance](latex-template.md) for the shared compile/render process. Synthetic pipeline tests and real scaffold compilation exercise the infrastructure; they do not certify every organizer/year or replace real-problem validation.

## Preserve the current decisions

Present the selected research scope, objective, candidates and evidence at the existing model-design checkpoint. Present reviewed conclusions before writing. Retain the final-artifact checkpoint for any actual delivery. There is no extra mandatory “competition approval” or “topic approval” stage.

If a rule clarification changes the task, model or accepted conclusions, use the existing revision and re-review procedure for the affected work. Do not treat a prose edit in the brief as automatically invalidating machine snapshots; put consequential changes into the relevant existing contracts and explicitly reopen affected decisions. Do not claim new automatic rule checking: semantic completeness and current-rule compliance still require review.
