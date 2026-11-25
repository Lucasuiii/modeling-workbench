# Validation responsibility

## First review: full and context-separated

Build the current computation handoff, then run:

```bash
python3 "$S/build_independent_review_package.py" --project <project>
```

The package binds only canonical evidence for formal results: official inputs, problem/model contracts, `RESULTS_INDEX.json`, cited successful `official_run: true` manifests, matching source snapshots, formal inputs, claim-bearing outputs, and review instructions. It records `context_excluded` — the prior reasoning it physically left out — rather than asserting that the reviewer holds no conclusions. Failed/exploratory runs, stdout/stderr, full logs, and debug history are excluded; package/upstream freshness digests cover this same canonical set. Stop and route it to a separate task. The builder records the reviewer selection rather than asking the user to confirm it: separation now comes from the block cut itself, since the `computation-validation` handoff carries the task that produced it and `HANDOFF-E010` rejects a review whose `task_ref` matches. The result template ships with every remaining independence field `null`, so the reviewer has to assert them; a null fails `IREVIEW-E027`. Differing task references are a paste guard, not proof of independence. Same-model fresh-context review remains correlated. Task references improve context-separation evidence but cannot cryptographically prove reviewer independence.

The package includes a frozen copy of [mechanism-validation.md](mechanism-validation.md). Read only applicable sections and independently assess the selected checks’ mathematical meaning, tolerance basis and evidence strength, including whether a plausible incorrect implementation could pass. Packaged instructions are bound by the package digest; changing the installed guide alone does not alter historical evidence. Rebuild the package to use revised guidance: the changed digest invalidates the old review result.

## Findings and verdicts

Use the general review criteria in `assets/independent-review/REVIEW_REQUEST.md`: derive risks from the current problem, then check task coverage, model validity, implementation, discriminating evidence and claim scope. Classify by the consequence for the answer: P0 invalidates the answer or delivery; P1 is a material limitation within a supported, task-relevant answer; P2 is an optional improvement. Give concrete evidence for blockers, not a preference for a different model.

A valid proof can support a general claim; finite experiments support only their justified coverage. Scope reduction cannot erase an unanswered requirement. Review a repair's effect on other conclusions, not just the original failing case. Select a few high-value checks appropriate to the problem; no universal experiment checklist is required.

Verdicts are `accepted`, `accepted_with_concerns`, `revision_required`, and `inconclusive`. Only an open P0 permits `revision_required`. Open P1/P2 items remain visible as warnings or suggestions and do not block paper work.

After a full review returns open P0 findings, rerunning the package builder in auto mode defaults to a targeted re-review. It archives the prior review/package and targets every prior open P0. The new package embeds `TARGETED_FINDINGS.json` with only `finding_id`, `category`, `location`, `evidence`, and `recommendation`, so a fresh reviewer can work from the package alone without receiving the full old review. Do not turn unrelated newly noticed P1/P2 items into new blockers. A genuinely new P0 may still require revision.

## The one checkpoint in this block

Before building `validation-paper`, put the conclusions in front of the person and record the answer in `CLAIM_LEDGER.conclusion_check`. This is the cheap place to hear no: a rejection here costs a recomputation, the same rejection at delivery costs a rewritten paper.

Show the claim text, its `scope`, its evidence state, and every open P0/P1 from the review. Do not show run ids, hashes or evidence chains — nobody can audit those by eye, and putting them on the page only dilutes the few things a person can actually judge. `scope` is the one worth reading aloud: it is where a rule that only holds at the point it was derived from becomes visible.

`presented_claim_ids` records what was actually shown. `CLAIM-E023` rejects an acceptance that did not cover every declared claim, so the record cannot say a person approved a conclusion they never saw.

Create `CLAIM_LEDGER.json` from the reviewed evidence. Each paper-bearing claim records its exact text, scope, evidence IDs, evidence state, and limitations. Strong claims—global optimality, equivalence, causality, robustness, significance, or reproducibility—still need claim-specific support. `reproduced` requires an isolated rerun and comparison; an original successful run is only `supported_not_reproduced` unless stronger evidence exists.

Before paper writing, build `validation-paper`. For a targeted result, the builder follows only the structured `previous_review_path` lineage and applies the latest status per finding ID: open/accepted P1 concerns remain, while resolved findings drop out. Its limitations come from supported paper-eligible claim limitations, those current P1 concerns, and explicit model applicability, assumptions, and known limitations—not contradicted/unsupported claims or model `scope`. Its `representation_candidates` proactively identify trend, multi-group comparison, distribution, sensitivity, model-performance, and spatial/network/clustering evidence. A fresh paper task reads this compact handoff first, chooses prose/equation/table/figure, and does not scan full run/debug history.

After the explicit reply, use `record_decision.py --stage validation --decision accepted --confirm-human` with the reply reference and summary (see SKILL.md). It records the existing fields and advances state; paper handoff and initialization reject missing or stale human acceptance.


## Reproduced claims

For a scalar result, first declare the comparison quantity, unit, scope and absolute tolerance. Record an independent execution under a new run ID; reserve `--rerun` for replacing an obsolete run. Index each value from its own frozen output. Cite both result IDs and run IDs in the claim. For example:

```json
{"reproduction": {"comparisons": [
  {"result_id": "RES-Q1-001", "comparison_result_id": "RES-Q1-002", "absolute_tolerance": 0.00001}
]}}
```

The checker reads both values, checks that both runs are current, and compares the absolute difference. Each result cited by a reproduced claim must participate. The reviewer still assesses execution isolation, comparable inputs, the mathematical meaning of the quantity, and whether the chosen tolerance is appropriate. The default tolerance is zero. Categorical and structured outputs use exact JSON comparison. For approximate vector outputs, index the scalar quantities the conclusion actually asserts. Use `supported_not_reproduced` for conclusions supported by a proof or review alone.
