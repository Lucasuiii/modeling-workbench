# Cross-stage handoffs

Handoffs are the durable interface for fresh-context work. Build them with:

```bash
python3 "$S/build_handoff.py" --project <project> --transition <name> [--task-ref <id>]
```

Transitions are `modeling-computation`, `computation-validation`, `validation-paper`, and `paper-delivery`.

## Two of them must be crossed in a fresh task

`computation-validation` and `validation-paper` are cuts, not just interfaces. The reviewer must not be the task that produced the evidence, and the paper must not be written by the task that reviewed it — a reviewer who then becomes the author defends the verdict it just gave instead of noticing what is wrong with it. Both cuts therefore require `--task-ref`, which lands in the handoff as `producing_task_ref`; the consuming side declares its own (`INDEPENDENT_REVIEW_RESULT.reviewer_context.task_ref`, `PAPER_PLAN.authoring_task_ref`). A missing producing ref is `HANDOFF-E009`; two matching refs are `HANDOFF-E010`. The refs are self-reported, so this is a paste guard rather than proof — the same limitation reviewer independence has always carried. The other two transitions take no ref and need no cut.

Each handoff contains canonical artifact paths and hashes, one upstream digest, a compact downstream payload, and an explicit list of excluded history. It points into the same workspace; it does not duplicate logs or outputs. The independent review package remains the context-separated payload for computation validation and copies only canonical evidence for formally indexed results because a reviewer may work outside the originating workspace. Its digest excludes failed/exploratory runs, stdout/stderr, and debug history, and it declares `context_excluded` explicitly.

The modeling handoff binds the official source manifest and official inputs needed by computation. The computation handoff binds only successful official runs referenced by formal results, their selected source snapshot, formal inputs, and claim-bearing outputs; failed/exploratory runs and full logs stay out. Computation→validation, the review package, and paper→delivery use one resolver for `RESULTS_INDEX → successful official run → source snapshot`, and all fail on a missing, failed, non-official, or stale link. The paper handoff binds the official paper materials it names, so a changed rule or template makes the handoff stale.

The validation-paper payload contains problem/model summaries, verified results, selected claims, real supported-claim/P1/model limitations, proactive `representation_candidates`, and classified official paper materials. For targeted review, it follows structured review lineage newest-first so current P1 concerns survive without copying old review prose. Model `scope` and contradicted/unsupported claim limits are not treated as paper limitations. Candidates flag trends, comparisons, distributions, sensitivity, model performance, and spatial/network/clustering structures without requiring an existing figure or prescribing a minimum count. The paper task starts with `next_task`. Each selected claim links to the supported result IDs it cites. A verified result’s `output_locator` points to its indexed output and value. Follow that pointer for the passage being written; keep exploration history out of the handoff.

The paper-delivery payload names the approved PDF, the compile receipt's editable LaTeX snapshot and entry point, compact referenced-run/source pointers, official-material roles, and current compliance status. It binds these artifacts but does not copy run history or source trees into a second package.

If any canonical artifact changes, the handoff is stale. Rebuild it after the affected stage is revalidated. Do not patch digest fields manually.
