# Stage 3: Model design

## Required output

- `model/MODEL_CONTRACT.json`

`MODEL_CANDIDATES.md`, `OPTIMALITY_SCOPE.md`, `VALIDATION_PLAN.md` and `CROSS_QUESTION_LEDGER.json` are working notes, not contracts. Write them when they help; the review package picks them up if they exist.

## The shape of this stage

```text
problem analysis
      |
model design            candidate A / candidate B
      |                 + why each is worth considering
      |                 + what evidence would tell them apart
      v
computation             cheap exploratory runs, one per candidate
      |                 record_run.py --candidate <id>
      v
selection               exactly one candidate becomes `selected`,
      |                 with a rationale that cites those runs
      |                 --- the person confirms the choice here ---
      v
official computation    only the selected model earns record_run.py --official
      |
      v
validation
```

Model design does not choose the model. It sets up the comparison so that computation can settle it.

## When a subproblem repeatedly misses its target

Before selection, look at a representative failure on development data. Identify the assumption or decision that could explain the miss. If a plausible alternative would behave differently on that case, use the existing candidate trial to test that prediction. In delegated model design, the lead can assign this comparison to the owner of the affected subproblem and keep the current solution as the baseline.

Run both versions on the same development cases, including cases the baseline solved. Compare the target metric, any newly failing cases, and the outcome under the task’s actual acceptance rule. For example, a routing policy can reduce average cost yet lose a batch because it fails to finish one route. Check other subproblems that consume a changed result or share the changed code.

Use the paired results in the existing `decision_rationale`. Continue exploring while there is a feasible comparison whose outcome could change the choice. When the alternatives tried offer no useful gain, keep the stronger supported candidate and identify any requirement it still misses. Cases used to diagnose or select a repair count as development evidence; use fresh cases for a new held-out claim.

## The checkpoint at selection

Before a candidate becomes `selected`, present the choice to the checkpoint reviewer and record the decision in `MODEL_CONTRACT.selection_check`. This is the earliest of the three checkpoints and the cheapest: only exploratory comparisons have been run, so a rejection precedes official computation. It is also the one with the most leverage, because everything downstream inherits the judgement criterion settled here.

Show three things:

1. **What is being optimized, and under what constraints.** State the criterion in one line. A criterion that controls only one kind of error, or optimizes only one side of a tradeoff, is visible here and nowhere else — by validation it has already shaped every result.
2. **Each candidate's `discriminating_evidence`, and whether it can actually discriminate.** If both candidates would produce the same value of the named evidence, the comparison is decorative.
3. **The `scope` the selected model will claim.** Whatever is written here is what validation must later cover; a scope wider than the evidence is a P0 finding at that point, so it is worth narrowing now.

`presented_candidate_ids` records what was shown. `MODEL-E018` rejects an acceptance that did not present every declared candidate — showing only the winner is not a comparison — and `MODEL-E016` keeps the choice unconfirmed until the reviewer decides. Use `preflight` for drafts. In both modes the user normally reviews the candidates. An explicit delegation for model design lets the lead agent make and record that choice. Use the matching human or delegated command in [SKILL.md](../SKILL.md).

## Candidates

Each entry in `components[].candidates` records:

| field | meaning |
|---|---|
| `candidate_id` | stable ID that runs can point at |
| `method` | what this candidate actually is |
| `why_considered` | why it is on the table at all |
| `discriminating_evidence` | the observation that would separate it from the others |
| `status` | `under_evaluation` / `selected` / `rejected` |
| `evaluation_run_ids` | the runs that actually evaluated it |
| `decision_rationale` | why it won or lost, in terms of what those runs showed |

Before exploring competing candidates, use `discriminating_evidence` to say which observation would change the choice. Specify the task outcome, comparable cases, and what would favor each candidate. Use a numerical tolerance when the task or measurement precision supports it. If the trial cannot resolve the difference, keep the simpler adequate method or leave the choice open for a more informative trial.

When proposing extra complexity, use `why_considered` to name the baseline behavior it could improve and explain how the change could help. An untested weakness is a hypothesis for exploration. Use `decision_rationale` after the trial to identify the observed shortcoming, whether the added complexity addressed it, and the scope of that result. A structural counterexample can establish a shortcoming directly. If the baseline meets the task and the trial shows no relevant advantage, retain it.

For example, to decide whether to add an intercept when predicting remaining time, compare errors in remaining minutes at the same simulated cutoffs. An improvement in fit on the visible segment alone leaves that choice unresolved.

Evaluate candidates with cheap exploratory runs — they cost no declarations and never block:

```bash
python3 "$S/record_run.py" --project <p> --candidate CAND-A -- python3 code/try_a.py
python3 "$S/record_run.py" --project <p> --candidate CAND-B -- python3 code/try_b.py
```

Then set exactly one candidate to `selected`, write a `decision_rationale` that refers to what those runs showed, and list them in `evaluation_run_ids`. `cumcm_check.py` reports the comparison under `model_candidates`, and flags a selection with no evaluation run (`MODEL-W014`), a decision with no reason (`MODEL-E014`), a candidate with no discriminator (`MODEL-W012`), and a comparison that never resolved to one winner (`MODEL-E013`). Warnings in `working`; errors once frozen. A component may explain its method in its own words. `MODEL-W017` reports a concrete mismatch when the whole method label names another candidate. Review the derivation and implementation to assess free-text descriptions.

One candidate is allowed when one model is clearly right — that only raises `MODEL-W007`. What is not allowed is claiming a comparison you did not make.

## Deferred model selection

In `working` mode a component needs only `model_id`, `capability_ids`, `method` and `scope`. That is deliberate: real modeling runs `sketch -> exploratory computation -> compare -> revise -> freeze`, and a contract frozen before the first run is a guess.

What does **not** defer is capability ownership. Every official subproblem needs a capability with an acceptance check that could fail (`CAP-E008`, `CAP-E009`), because "answered the wrong question" is the failure this workflow exists to prevent, and that invariant does not change when the model does.

Entering `finalizing` requires the complete contract: `variables`, `inputs`, `outputs`, `verification_plan`, and a resolved candidate comparison. Each `verification_plan` entry should match an assertion name that an official run actually recorded — a plan with no executed assertion behind it fails (`MODEL-E009`), and entries with no matching assertion warn (`MODEL-W010`).

A frozen contract must read as a design commitment, not as a transcript of whatever the code ended up doing. That distinction is not machine-checkable; it is a named failure class for the independent reviewer.

Compare candidates using fit to the task contract, identifiability, data requirements, computation cost, interpretability, and validation opportunities. Do not force multiple models when one is clearly sufficient.

Use the applicable family in [task-driven modeling](task-driven-modeling.md) when selecting the formulation, baseline and evidence. It also covers data audit and experiment priorities under a time budget. Reuse the fields and optional working notes above; no extra experiment contract or model quota is required.

For the selected model, define state, decisions, parameters, objective, constraints, observation mechanism, stochastic assumptions, and numerical method. Declare whether an optimum is exact, local, heuristic, relaxed, sampled, or restricted to a stated policy class.

Map every capability to a model component; `CAP-E013` reports any that no component takes on (a warning while working, an error once frozen), because a capability nobody claims is how a task quietly loses a requirement. Record each shared quantity's producer, consumers, definition, unit, time basis, transformation, uncertainty propagation, and authoritative artifact in the cross-question ledger. Resolve incompatible reuse before computation.

Plan meaningful checks appropriate to the actual claims: hand-solvable instance, extreme case, conservation law, out-of-sample test, residual analysis, or perturbation analysis. An independent second implementation is optional and must not be created merely for MATLAB/Python parity.

When choosing discriminating evidence and the `verification_plan`, consult the applicable sections of [mechanism-validation.md](mechanism-validation.md). Select checks that could expose a plausible wrong answer, including their scope and tolerance basis; reuse existing coverage and preserve the current question’s simplifications.

Before freezing, obtain approval of the selected model and scope, then build the `modeling-computation` handoff. A computation task reads that handoff rather than the full modeling conversation.

To revisit a frozen model, record a `revision_requested` decision for `model-design`; it reopens the stage and everything downstream in one step.
