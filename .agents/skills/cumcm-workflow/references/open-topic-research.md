# Open-topic research under an official theme

Use when the organizer supplies a theme or research remit rather than fully specified subquestions. Keep the normal stages: topic work belongs to problem analysis and candidate model design, not a new workflow mode.

## Choose a question that can be answered

Start from the official theme, audience and available data. State the population/system, place and time, the quantity to estimate or decision to make, and what observation could contradict the proposed answer. “Use machine learning for urban development” is a method plus a domain, not a research question.

Consider alternatives only where uncertainty about scope or feasibility makes a comparison useful. Compare them on theme fit, data access, unit of analysis, estimability, validation opportunity, time and computational cost. Do not require three topics or three models. An accessible sample and a simple baseline can reveal infeasibility sooner than a long novelty narrative.

Distinguish three different choices:

- **Question:** what the team wants to learn or decide under the official remit.
- **Design:** which observations/comparisons could answer it and under what assumptions.
- **Estimator or algorithm:** how that design becomes a computed result.

Do not choose the algorithm first and invent a question around its output. Novelty may lie in the question, data linkage, constraints or interpretation; do not claim novelty from a renamed combination of familiar methods.

## Establish data feasibility before expensive work

A suggested dataset is not an acquired dataset. Inspect a real accessible sample or documentation: population, dates, observation unit, variables, units, access restrictions and usable size. Record whether the data are acquired, documented but unavailable, or merely proposed in existing working notes. Do not invent a column list, survey response count, access permission or downloaded file.

Use supplied data first. Acquire external data only within the user's authorized scope and the contest's rules. A source requiring payment, credentials, participant recruitment or external contact needs the corresponding authorization. Preserve acquisition/version information; public data do not become organizer-provided data. Raw data remain distinct from reproducible cleaning outputs.

If the necessary outcome, comparison group, temporal coverage or independent sample is absent, revise the question or design before selecting the model. Synthetic data may test an implementation; they do not establish an empirical finding about the population.

## Match the design to the intended conclusion

| Intended answer | Design issue that must be settled |
|---|---|
| Describe a population or trend | Sampling frame, denominator, weights, missingness and representativeness |
| Predict future or unseen cases | Deployment horizon/unit, information available then, separated validation and a credible baseline |
| Estimate an intervention effect | Estimand, assignment mechanism, identification assumptions and plausible confounding; a fitted regression alone does not identify causality |
| Rank or evaluate objects | Meaning/direction of indicators, preference or weight source, aggregation assumptions and ranking sensitivity |
| Discover groups | Feature scaling, distance, stability and interpretation; clusters are not automatically real classes or causal mechanisms |

Consult [task-driven modeling](task-driven-modeling.md) for the applicable comparison and validation choices. State a failure interpretation before running a decisive experiment: would a negative result reject a hypothesis, expose insufficient data, or only reject an estimator? Do not silently redefine success after seeing the result.

## Join the existing evidence chain

Use `PROJECT_BRIEF.md` and `ASSUMPTIONS.md` for the selected research design and its rationale. In `PROBLEM_FACTS`, cite official material for theme constraints; explicitly mark team-defined questions as such in their descriptions and distinguish external observations from official facts. Represent the chosen research questions as subproblems and observable capabilities in the existing contracts. Do not attribute a team hypothesis to an organizer or manufacture numbered official questions.

The model-design checkpoint presents this scope along with candidate evidence and unresolved data limitations. Cheap feasibility exploration may precede it; formal computation still follows human acceptance. Rejected topic alternatives need no new permanent contract. Any premise essential to a conclusion must appear in the model scope/assumptions or claims carried to independent review, not only in a notebook the review package omits.

When the data cannot distinguish the hypotheses, report that limitation or propose a feasible redesign. Statistical insignificance does not establish equivalence, and a narrow honest answer must still satisfy the official theme and selected research objectives.
