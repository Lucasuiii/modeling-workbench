# Delivery responsibility

For Huawei Cup / 中国研究生数学建模竞赛, also read [Huawei delivery adaptation](huawei-delivery.md): current official cover, abstract/anonymity checks, submission filenames, attachments and measured MD5 binding.

Delivery is a `finalizing` responsibility. It uses only current user-supplied official rules/templates and the fresh `paper-delivery` handoff. That handoff must identify the reviewed PDF, the compile-bound editable LaTeX snapshot/entry point, every official computation source selected through `RESULTS_INDEX → successful official run → source snapshot`, and the official paper materials still requiring compliance review.

The LaTeX/PDF chain supports the actual competition name recorded in the template manifest and both Chinese and English scaffolds. Apply [competition adaptation](competition-adaptation.md) and [competition writing](competition-writing.md) to current official rules, references and supplementary documents. Word-only submission still has no export-receipt path. Do not infer rule compliance from the selected language or a successful compile.

Produce the receipt with the recorder, not by hand:

```bash
python3 "$S/record_compile.py" --project <p> --update-quality
```

## Hard checks

- the selected compile attempt exited successfully with the declared engine;
- font and missing-glyph checks pass (derived from the engine log, not asserted);
- the reviewed PDF path/hash, page count, layout report, compile receipt, and delivery manifest agree;
- the compile receipt contains a current `sha256-tree-v1` snapshot of every required editable LaTeX source file and its entry point;
- fonts/glyphs, overflow, clipping, unreadable figures/tables, and unresolved references are checked;
- current official-format compliance is verified from user-supplied material;
- final PDF, editable LaTeX source, and computation source are separately addressable and present.

The exact PDF hash and source-tree snapshot bind the final approved artifact to its editable source without requiring per-file hashes to be typed or reviewed manually. Ordinary logs, caches, temporary files, documentation, and debugging material stay outside the delivery package.

Missing current rules or a required template yields `blocked_missing_user_material`; it does not authorize web search. Submission remains user-controlled.

## The last checkpoint

`DELIVERY_MANIFEST.final_check` is the single approval before submission; the paper report carries none of its own. It replaced four separate ones, which in practice collapsed into a single typed sentence approving things nobody had looked at.

This one asks a narrower question than the conclusion check did. The model is settled by now: what is being judged is the finished object — whether the answers are stated correctly in the paper, whether the pages hold together, whether the deliverables are complete. Present the rendered pages `record_compile.py` wrote to `.cumcm/tmp/pages/`, the answer to each subproblem, the open findings, and anything still in `unresolved_errors`.

`presented_pages` records what was actually put in front of the reviewer. `DELIVERY-E020` rejects a check that skipped rendered pages, and `DELIVERY-E019` rejects `reviewer_kind: human_user` with nothing presented at all — if the pages were never shown, the record must not claim a person read them. A model that cannot see images has not done layout QA; say so in `notes` and record the kind honestly rather than upgrading a text transcription into a human reading.

## Package the files actually delivered

Run `python3 "$S/refresh_evidence.py" --project <project> --only delivery --package` before final QA and acceptance. It uses the existing delivery, LaTeX and result declarations, preserves project-relative directories, includes figure-generation scripts, and updates existing delivery metadata. `DELIVERY-E021` inspects ZIP members and bytes: missing, flattened, unsafe or stale members warn in working and block finalizing. Archive member names remain portable (`code/`, `data/`, `results/`), but canonical computation bytes come from the selected official run’s frozen files. Live source or team-input drift blocks packaging until rerun; overwritten live outputs never replace frozen output bytes. If two current runs need different bytes at the same member name, packaging refuses the collision instead of choosing a version. No new manifest or hash chain is needed.

This checks declared dependencies, not arbitrary imports or runtime success. Check that appendix commands refer to shipped files; use an isolated extracted copy for an authorized execution check. Inspect figure labels for overlap and remove redundant figures/tables that add no explanation. After showing all current pages and files, use the single human confirmation command in SKILL.md. Repack or edit after approval only with renewed review of the changed material.

## Compile evidence refresh

`record_compile.py` uses the first TeX pass to discover actual inputs through
`-recorder`; at least one further pass must consume the same stable source set.
`--passes` therefore runs at least two passes. Project-local chapters, figures
and custom resources join declared `required_files` in the source snapshot and
editable ZIP. Installed TeX trees and system fonts remain runtime dependencies;
copy other external resources into the project. Keep bibliography source files
in `required_files`: a TeX-only pass reads the generated `.bbl`, not its `.bib`.
Run bibliography generation before recording the final stable compilation.

The full multi-pass log remains diagnostic history; only the last engine log
supplies final warning verdicts. `pdfinfo` must provide a real page count.
Rendering failures and `--no-render` clear the current rendered-page list.
A failed new attempt archives the previous receipt/log and leaves no current
successful receipt; repair and recompile before delivery.

Refreshing quality replaces only recorder-owned checks. Existing visual findings
retain the PDF `artifact` they examined. After a PDF change, re-review them and
update their bindings only from that actual review; a recorder never closes a
visual failure or renews a visual pass. Content review keeps its own binding too.
