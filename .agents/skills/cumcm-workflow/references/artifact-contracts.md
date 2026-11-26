# Artifact contracts

Read this reference when creating or checking v0.8 files. JSON Schemas define core machine-readable shapes, but a schema mismatch is important only when it prevents reliable interpretation of evidence.

## Canonical artifacts

| Responsibility | Canonical files |
|---|---|
| Workflow | `.cumcm/state.json`, `.cumcm/decisions.jsonl`, `.cumcm/snapshots/<stage>.json` |
| Intake/modeling | `SOURCE_MANIFEST.json`, `PROBLEM_FACTS.json`, `TASK_CAPABILITIES.json`, `MODEL_CONTRACT.json`, `CROSS_QUESTION_LEDGER.json` |
| Computation | `runs/<id>/RUN_MANIFEST.json`, `RESULTS_INDEX.json` (both written by `record_run.py` / `index_result.py`) |
| Validation | independent review package/result, `CLAIM_LEDGER.json` |
| Paper | `PAPER_PLAN.json`, `LATEX_TEMPLATE_MANIFEST.json`, `PAPER_QUALITY_REPORT.json`, `PAPER_VISIBLE_TEXT_REPORT.json` |
| Delivery | `COMPILE_RECEIPT.json` (written by `record_compile.py`), `DELIVERY_MANIFEST.json` |
| Cross-stage | `handoffs/<transition>/HANDOFF.json` |

v0.6 removed the per-artifact `review` envelope: formal stage approval lives only in the append-only decision log. Three checkpoints remain human by default; explicitly delegated stages record the lead agent as reviewer. Each records the material reviewed: `model.selection_check` (`presented_candidate_ids`), `claim_ledger.conclusion_check` (`presented_claim_ids`) and `delivery.final_check` (`presented_pages`). `paper_quality.content_report` and `layout_report` are reports, not approvals — they carry no decision. `claim_ledger.independent_review` and the optional `figure.visual_review` are unchanged.

`PAPER_TRACEABILITY.json` was deleted. The property it promised — no internal IDs in visible content — is measured directly on the rendered PDF by `paper_visible_text_check.py`. Recording an accepted decision automatically writes a derived stage snapshot. Snapshot files require no human fields and can be regenerated from the accepted scope.

## Evidence-critical bindings

- Official sources, formal inputs, and claim-bearing outputs use file hashes.
- Official computation uses one canonical resolution in handoffs and review packaging: `RESULTS_INDEX.json` → referenced successful official run → current selected source-tree snapshot. Broken links fail rather than being omitted.
- Review packages bind packaged files and the live upstream sources.
- Handoffs bind only canonical downstream inputs.
- Paper compilation binds the exact final PDF and the exact editable source tree.

Stable IDs and exact result locators remain important. Paper plans and quality reports are intentionally lighter: they record claims, representations, structure, P0/P1/P2, and version bindings rather than fixed counts or exhaustive quality dimensions.

## Modes

Working mode permits a draft model contract and incomplete downstream contracts. Finalizing requires the frozen model contract with a resolved candidate comparison, current decisions, snapshots, handoffs, review, PDF QA, and delivery.

v0.8 rejects any contract whose `schema_version` is not `0.8.0` and ships no migration path. An older workspace is re-initialised from its official files.
