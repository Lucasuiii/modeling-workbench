---
name: cumcm-independent-review
description: Independently review a CUMCM computation package before its claims enter validation or paper writing. Use only inside a generated independent-review package.
---

# CUMCM Independent Review

Review this freshness-bound package without consulting the originating conversation. Treat conclusions as untrusted and reconstruct only what is needed from official inputs, contracts, selected source, official runs, and outputs.

## Boundaries

- Work read-only inside the package.
- Do not search for missing official materials. Report them as missing.
- Do not edit, rerun, or replace the preserved execution unless the user separately authorizes a reproduction run.
- File existence and successful execution do not prove that the model answers the official question.
- Verify the package/upstream bindings before substantive review; a stale package is inconclusive.
- Give exact file, formula, code, or numerical locations for every P0/P1 finding.
- Preserve negative and inconclusive findings verbatim.

## Review order

1. Read `REVIEW_REQUEST.md` and `materials/problem/SOURCE_MANIFEST.json`. In targeted mode, also read package-root `TARGETED_FINDINGS.json`; it is the self-contained prior-P0 brief, so do not request the complete prior review.
2. Reconstruct each subproblem from the supplied official files and `PROBLEM_FACTS.json`.
3. Compare the official request with the model objective, variables, constraints, assumptions, and cross-question dependencies.
4. Inspect computation entry points, run manifests, executed outputs, and result locators. For a claim-bearing output, `preexisting` reports whether the path existed before the recorder moved the old file into `previous_outputs/`. The generation check refers to the path after that move and before the solver starts.
5. Challenge relevant failure classes:
   - task or target misunderstood;
   - upper/lower bound or optimization direction reversed;
   - a quantity counted twice;
   - unsupported extrapolation;
   - an observed variable omitted without justification;
   - cross-question contradiction;
   - code and mathematical formulation disagree;
   - numerical output violates units, bounds, conservation, or official constraints.
6. For targeted mode, resolve every entry in `TARGETED_FINDINGS.json` first. Do not repeat a full review unless the target change has global impact or current evidence reveals a new, well-supported P0.
7. Write the raw review and structured result using the supplied template.

## Verdict

- `accepted`: no open P0 and no material unresolved concern in scope.
- `accepted_with_concerns`: no open P0; one or more P1 concerns remain.
- `revision_required`: at least one open P0 requires returning to the earliest affected stage.
- `inconclusive`: required material is missing or the available evidence cannot support a decision.

Classify findings as P0/P1/P2 and open/resolved/accepted_concern. State the reviewer, model if applicable, originating/reviewer task references, and independence grade. Never describe same-context review as independent; a same-model fresh task remains correlated.
