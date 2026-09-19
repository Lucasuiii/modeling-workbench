# Stage 2: Problem analysis

For a team-selected question under an official theme, first use [open-topic research](open-topic-research.md), then express the chosen research questions through the same outputs below. When observations or data preparation determine the answer, consult the data section of [task-driven modeling](task-driven-modeling.md). Keep official requirements, external observations and team assumptions distinguishable.

## Required outputs

- `analysis/PROBLEM_FACTS.json`
- `analysis/TASK_CAPABILITIES.json`
- `analysis/ASSUMPTIONS.md`
- `analysis/SYMBOLS.md`

For each fact, cite an official source file and page, sheet, table, or cell range. Separate stated facts, interpretations, and added assumptions.

Translate each subproblem into observable capabilities: requested output, official facts used, acceptance checks, intended model owners, expected code entry points, and result IDs. Capability coverage is complete only when every requested subproblem output has an owner and a check that could fail.

Write each acceptance check so a program can fail it. The failure this guards is the task quietly shrinking until it fits what the agent can already do: every check after this point verifies faithfulness to the reading that was written down, so none of them can see that the reading itself narrowed.

- `judge: "recorded"` means the solving program decides. Name the assertion in `assertion_name`; the program writes it out through `record_run.py --assert-file`, and `CAP-E012` checks that an official run for this capability actually recorded it passing. Phrase `assertion` as the condition and its negation: "the enumerated count equals the class cardinality; fewer means a policy was skipped". Reserve this for anything a program could settle — a count, a bound, a required field being present and non-empty, an invariant holding on the output.
- `judge: "human"` is for the questions no script settles: whether a reading of the problem is right, whether an interpretation is faithful. These go to the reviewer, and claim nothing.

A capability with only `human` checks is allowed and sometimes correct, but it buys no machine evidence, so prefer a recorded one wherever the delivery has any observable consequence at all.

Use stable fact and capability IDs. Do not treat a method name or keyword as implementation evidence. Identify ambiguous wording and compare plausible interpretations before choosing one.

Record the chosen interpretation and its alternatives. In `working` mode, continue with reversible model exploration when ambiguity does not change the data meaning or requested output. Ask for an explicit user decision only when competing interpretations would materially change the mathematical task, official-data use, or final claims; do not silently freeze a final model before that decision.
