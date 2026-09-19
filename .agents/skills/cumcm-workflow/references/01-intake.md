# Stage 1: Intake

## Goal

Create a read-only inventory of the official problem, attachments, and current competition rules before interpretation.

For another competition or a different language/deliverable, use [competition adaptation](competition-adaptation.md) to establish requirements and the current tool boundary. For open-topic work, the official theme and instructions are the initial official inputs; team-selected questions and external datasets must not be presented as organizer-provided facts.

## Procedure

1. The user-facing initializer is conversational. When the user supplies an official file or directory path and asks to initialize, inspect that path read-only, infer the project ID from the available context, choose a safe sibling workspace when no target is specified, and run `scripts/init_project.py` for them. Do not ask the user to type the Python command. Ask only when the source is missing, the year/problem identifier cannot be inferred, or the proposed target is non-empty.

   The script copies official inputs into `problem/official/`, creates the v0.6 working workspace with MATLAB-preferred/Python-fallback configuration, writes a stable-ID source manifest, and runs intake preflight. It refuses to overwrite a non-empty project, rejects symlinked source trees, and never deletes or edits the official source. A supplied file means that file only; a supplied directory means its usable regular-file tree. Do not silently widen the source set.
2. Review `PROJECT_BRIEF.md`, `problem/SOURCE_MANIFEST.json`, and the copied files. The initializer labels copied inputs `official`; reclassify organizer attachments, external references, or team-created files before approval when needed. For paper materials, use `authoritative_for` to distinguish an adaptable official template (for example `paper_template`) from format/submission/competition instructions (for example `format_rules`, `submission_rules`, or `competition_rules`). Filenames and extensions are routing hints, not authoritative roles. Record derived files separately with their parent source ID.
   Every source records how it was acquired. Official and organizer material must be a user-supplied local file or an explicit user-supplied URL. Never search for neighboring rules, attachments, or templates. If the expected set is incomplete, list the missing items and wait for the user.
3. Render PDFs when formulas, tables, or layout carry meaning. Use extracted text only for navigation.
4. Working mode may continue to problem decomposition while the source set is being confirmed. Before `finalizing`, set `intake: passed` only after every expected official attachment and current competition rule file is accounted for and the artifact-bound decision/snapshot is recorded.

Run `cumcm_check.py --stage intake --gate-mode preflight`, resolve errors, and record the technical completion. Passing proves source identity and the declared inventory, not that the expected-source list is complete. Ask the user only if the supplied files leave a material ambiguity; intake is not an additional mandatory approval stop.

Let the inventory and validator record and compare SHA-256 automatically for official statements and organizer attachments. The reviewer confirms the source list and origin, not the digest characters. An official-source hash mismatch blocks intake; external references and team-created materials may omit hashes, and stale optional hashes are warnings. A byte-size mismatch is only stale metadata and should be refreshed.

Do not run code or macros embedded in unfamiliar inputs during intake.

`refresh_evidence.py` re-computes size/hash metadata for files already declared here; it never re-roles a source and never rewrites an official run's preserved hashes.

`inventory_artifacts.py` remains available for refreshing a source manifest after an explicitly reviewed source-set change; it is not required for ordinary initialization.
