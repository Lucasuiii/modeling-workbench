# Choose models and evidence from the task

Read only the parts needed for the current question. This guide complements `MODEL_CONTRACT` and [mechanism validation](mechanism-validation.md); it adds no artifact, model quota or universal experiment suite. Map a requested output to a mathematical quantity before choosing an algorithm. Different subquestions may need different model families while sharing quantities consistently.

## Data before model complexity

Inspect what one row, record, image or trajectory represents. Establish keys, units, denominators, sampling times, aggregation level and target definition. Track joins that change row counts, duplicate observations, missing values and unit conversions. Zero, missing and censored are different observations; an extreme value may be the event the question asks about.

Preserve raw inputs. Record consequential transformations as reproducible code with declared input/output dependencies through the existing recorder. A cleaning report is useful only if it names the rule, affected observations and impact; do not generate one as paperwork. Put decisions affecting scientific meaning in the existing facts/assumptions/model scope so reviewers can inspect them.

Fit learned preprocessing inside training folds. Split by the deployment unit and time, not by a convenient random row split. Audit feature availability, label construction and overlap across train/test; a future-derived feature remains leakage even when the target column itself is excluded. Changes to cleaning require reconsidering dependent results using the existing redo procedure.

## Candidate choice and credible comparisons

| Task | Formulation to make explicit | Comparison or evidence worth considering |
|---|---|---|
| Allocation, scheduling, routing, control | Decision domains, objective priority, feasible actions, information available at each decision and resource/terminal conditions | Simple feasible policy or small exact instance; replay the exported solution; bound/gap only when valid |
| Forecasting, regression, classification | Deployment target/horizon, loss aligned with use, available predictors and train/validation/test design | Persistence/seasonal/linear or majority/class-prior baseline as appropriate; held-out error, calibration or cost-sensitive evaluation |
| Statistical estimation or intervention analysis | Estimand, sample/design, dependence, estimator and identification assumptions | Uncertainty appropriate to the sampling unit; design diagnostics, alternative assumptions and claim-specific sensitivity |
| Mechanistic dynamics, geometry or inverse problems | States/coordinates, physical relations, units, initial/boundary conditions, observation model and parameter sources | Hand-solvable limits, balances, observation reconstruction and accuracy of the answer quantity under refinement |
| Evaluation and ranking | Indicator purpose/direction, scale transformation, preference/weight source and aggregation rule | Dominance checks and rank changes under defensible weights/normalization; explain which conclusions survive |
| Graphs and networks | Node/edge meaning, direction, cost/capacity/time and whether the graph is observed or constructed | Disconnected/degenerate cases, conservation and small exact examples; test whether network construction drives the conclusion |
| Simulation, queues or stochastic systems | Event ordering, input process, initial state, warm-up/horizon and target statistic | Analytic or limiting case where available, replication uncertainty and a validation design distinct from tuning |
| Clustering or dimension reduction | Similarity, scaling, retained information and how the representation answers the question | Stability and external interpretation when available; reconstruction alone does not prove useful groups |

A baseline must answer the same question under comparable information, data and resources. Use the same evaluation population and report variability where it could reverse the choice. Do not rank models by training fit or compare a constrained policy with an unlabelled omniscient benchmark. Prefer a simpler supported model when extra complexity buys no task-relevant improvement.

Method-specific cautions:

- A percentage error with zero or near-zero targets can be undefined or misleading; choose a metric from the loss and scale, not a habitual list. Accuracy alone may conceal rare-event failure.
- A time series needs splits consistent with its intended horizon; preserve temporal ordering in feature construction and tuning. A spatial deployment may require spatial separation as well as distinct rows.
- Entropy weights describe variation, not stakeholder importance; AHP judgments express preferences, not measured truth. Correlated indicators can double-count a construct. Do not automatically combine weighting methods to claim objectivity.
- A regression coefficient is not automatically an intervention effect. Identify the assumptions supporting the intended interpretation before selecting DID, IV, discontinuity or another design.
- Solver status and neural-network fit measure different aspects of a computation; neither substitutes for checking the actual requested output and its scope.

## Plan a small set of decisive experiments

Use candidate `discriminating_evidence` and the existing `verification_plan` to state the claim, test quantity, data/split, comparison, failure condition and tolerance basis. Working notes in `VALIDATION_PLAN.md` can explain rationale and approximate cost; do not add a second experiment contract. Reviewers judge whether the proposed evidence is sufficient, while scripts record only what really ran.

Prioritize a cheap feasibility or sanity check, a task-relevant baseline, and the most consequential unresolved validation risk. Additional ablations, seeds or perturbations are justified when they can change the choice or support an intended claim; they are not compulsory decorations. Fix a useful stopping condition from the deadline, cost, decision precision or lack of expected improvement. If a required check remains unresolved, report the gap rather than converting a budget limit into a pass.

Reuse existing evidence only while its inputs, method, definitions and scope remain applicable. Keep explorations separate from official evidence. Paper-stage requests for a new experiment return to computation and the affected review; they do not authorize new numbers in the manuscript. Preserve all three existing human stops and the existing P0/P1 meanings.

## Explain the mathematical commitment

For each substantive model, make the route from task to answer visible: why the relation applies, how real objects map to variables, which assumptions close the system, what transformations produce the computable formulation, what was solved, and what the evidence establishes. Use only the steps the problem needs.

Show an optimization objective with its constraints and domains; a dynamic model with its evolution and boundary conditions; a statistical model with its target, estimator/loss and design; a ranking with its transformations and aggregation. Refer to unchanged shared equations instead of duplicating them. Algorithm descriptions and flowcharts cannot replace the model, while long textbook derivations cannot replace an explanation of why it fits this problem.
