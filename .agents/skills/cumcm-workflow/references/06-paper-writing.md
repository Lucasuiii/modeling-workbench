# Paper responsibility

Start in a fresh task when practical. Read `handoffs/validation-paper/HANDOFF.json` first; open upstream files only through its canonical pointers. Do not load failed runs, debug logs, or old review conversations unless a current P0 specifically requires them.

Treat handoff `representation_candidates` as prompts for judgment, not a prescribed chart list. They flag evidence shapes that may benefit from visualization even when no figure exists yet. Select prose, equation, table, or figure according to the claim. Handoff limitations contain claim limits, P1 concerns, and model applicability/assumption/known-limit information; do not reinterpret model scope itself as a limitation.

For English work, audience-specific documents or reference verification, read [competition writing](competition-writing.md). Follow current official requirements while preserving the reviewed claim scope. Set the actual competition and paper language when initializing the scaffold; see [competition adaptation](competition-adaptation.md). Both languages use the same compile, page-review and delivery chain, with official templates taking priority.

## Plan the argument before LaTeX

1. Select the validated claims that answer the official questions.
2. Choose the best representation for each claim from existing evidence.
3. Design `paper_structure` as the semantic argument flow.
4. Generate only the tables/figures justified by the plan and existing results.
5. Adapt a declared official paper template when supplied; otherwise initialize the generic scaffold and keep compliance unverified until rule/instruction documents are checked.
6. Write, compile, render every page, and review the PDF.

`paper_structure` is the source of truth for the body. Each entry supplies a section title, purpose, covered subproblems, and supported claims. One section may serve several subproblems; one complex subproblem may span several mathematically meaningful sections. Background, restatement, assumptions, notation, shared mechanisms, model development, results, validation, evaluation, and conclusions are candidate modules—not mandatory headings. Cover every official subproblem, but do not manufacture sections to imitate a generic modeling paper.

Sections are not independent essays stapled together. Each one states, in its opening sentence or two, why the previous section made it necessary: a quantity the previous model left unknown, an approximation that has to be checked, a decision the previous result did not settle. Questions that are formally independent are still tied together by the shared object, data, or mechanism they act on. A reader should be able to say what breaks if a section is removed. This costs a sentence per section and it is the difference between an argument and a list.

`PAPER_PLAN.json` needs `claim_selection`, `representation_plan`, `paper_structure`, and `authoring_task_ref` — the task writing the paper, which must differ from the `validation-paper` handoff's `producing_task_ref` (see `references/handoffs.md`). Legacy argument layers, reference-paper counts, page budgets, and figure counts may remain optional notes but are not hard gates. A plan with no table/figure creates a warning to reconsider communication, not a failure.

## Abstract and keywords

Write the abstract after the body stabilizes. Use the order problem -> core method -> key result -> meaning/validation. For a quantitative task, include a few decision-bearing numerical anchors with units, comparison, uncertainty, or fit information when supported. Wrap the values that ARE the answer in `\keyresult{}` so a reader skimming the abstract finds them without parsing the sentences around them; use it in the body's result statements too. Bold the answer, not every number on the page — marking everything marks nothing. Avoid empty sequences such as “a model is built for Question 1; Question 2 is solved; results show effectiveness.”

Keywords must come from the actual object, data, model, or method. Do not use workflow filler such as “mathematical modeling,” “reproducible computation,” or “evidence chain.”

## Claim-serving representations

Every representation answers one reading or evidence question:

- observed-versus-fitted plots show where the model follows or misses the data;
- residual/error plots expose structure hidden by a global fit score;
- comparison plots support method, scenario, or policy choice;
- sensitivity/convergence plots support parameter or algorithm stability;
- robustness distributions support noise or perturbation claims;
- mechanism/algorithm diagrams clarify a genuinely complex process. These are drawn, not plotted: an optical path, a four-stage decision flow with a rework loop, a state transition, an algorithm's stages. They need no data, which is exactly why they get skipped — an author reaching for matplotlib finds nothing to plot and moves on. The scaffold loads TikZ so drawing one costs nothing;
- compact tables carry values that readers must compare or retrieve precisely.

These are options, not a checklist. Do not require every kind, impose a minimum count, or invent residual, Monte Carlo, sensitivity, convergence, or robustness analyses that computation/validation did not execute. The initializer never decides what to plot.

## Result -> validation -> boundary

After a result, explain what makes it credible, where it weakens, and what changes the conclusion. Prefer already available residual/error analysis, feasibility or constraint checks, sensitivity, convergence, stability/robustness, baseline/model comparison, or out-of-sample evidence. If an important check is missing, state a concern or limitation; the paper stage must not create a new numerical experiment merely to complete the narrative.

Distinguish the two kinds of cross-check and say which one you have. Computing the same quantity twice through the same model — a closed form against a truncated series, a vectorized implementation against a loop — agrees to machine precision and shows only that the code matches the derivation. Computing it through a second, independent route — a different physical principle, a different estimator, a different data channel — produces a real discrepancy that has to be explained, and that explanation is what convinces a reader the model is right. Implementation agreement is the floor. Do not present it as model validation.

When model evaluation is useful, distinguish strengths, limitations, and possible improvements. Tie each point to the actual mechanism, assumption, data region, parameter identifiability issue, sensitive perturbation, or missing data. Prefer claim limitations and accepted/open P1 concerns over generic claims that a model is simple, accurate, general, or practically meaningful.

## Quality-reference boundary

The user-supplied 2025 B first-prize paper, *基于联合物理色散模型与先进信号处理方法测定碳化硅外延层厚度*, is a quality reference, not a template.

Transferable lessons:

- a high-information abstract names the physical/modeling route and reports numerical anchors;
- derivation, algorithm, computed result, interpretation, and reliability analysis form a continuous argument;
- fitted curves, residuals, method comparisons, sensitivity/convergence views, and robustness distributions have distinct claim functions;
- limitations identify concrete systematic residuals, material assumptions, parameter coupling, and dependence on external constants;
- long supporting code and file lists remain in the appendix instead of interrupting the main narrative.

Non-transferable traits:

- its section count/order, 38-page length, and number of figures/tables;
- its optics models, algorithms, parameter values, and physics-specific organization;
- its AI-tool citation practice and any 2025 competition-specific formatting;
- any claim that another paper should look similar or reproduce analyses absent from current evidence.

Use this priority whenever sources conflict: a current official paper template and official rules > the generic scaffold > reference-paper style. Rule PDFs/DOCs are compliance inputs, not automatically adaptable templates.

## Reader-facing quality

- Explain why equations and algorithms are used and what results mean.
- Prefer a representative result plus interpretation over number dumping.
- Use tables for exact comparisons, figures for patterns/relationships, equations for mechanisms, and prose for conclusions or assumptions.
- Give captions enough context to understand the claim, scope, axes/units, and comparison without repeating the body.
- Keep internal IDs, evidence states, local paths, workflow terms, and run coverage in sidecars only.
- Do not create new numerical results while writing.
- Do not impose a minimum page or chart count.
- Keep figures near the argument they support; use booktabs-style tables, concise captions, and subfigures only when joint comparison improves reading.
- Use `tabularx` or `longtable` for genuinely wide/long material before shrinking text. Move supporting bulk to the appendix when rules allow.

`PAPER_QUALITY_REPORT.json` binds content, rendered layout and final QA to the exact PDF. v0.6 dropped the per-question eight-dimension matrix: a reviewed subproblem records `status` and `notes`, and the layout block's page count, rendered pages and checks come from `record_compile.py` rather than from an attestation. Open P0 issues block final status. P1 concerns and P2 suggestions remain visible but do not block. Failed layout checks that make equations, tables, figures, glyphs or pages unreadable remain hard submission-reliability failures.

Run `paper_visible_text_check.py`. Internal metadata and local paths block; excessive decimal precision and number-dense sentences are warnings for reader review. It matches workflow IDs by their actual shape (`PREFIX-[Qn-]NNN`), so ordinary prose such as "Model-A" is not a false positive. A revision log is optional: use it when it helps track a real P0/P1 correction, not to force rounds.

Build `paper-delivery` after the exact PDF and editable source are approved.
