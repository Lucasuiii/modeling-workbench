# CLAUDE.md

Choose the entry point from the user's task:

- **Solve or resume a contest problem:** read [.agents/skills/cumcm-workflow/SKILL.md](.agents/skills/cumcm-workflow/SKILL.md) and follow it. The engineering instructions below do not apply to solving the contest problem. Resolve this link from the directory containing this file, not the contest workspace.
- **Edit this workflow repository:** follow the engineering instructions below. Do not start a contest run unless requested.

The Claude Code Skill at `.claude/skills/cumcm-workflow/SKILL.md` routes to the same canonical workflow.

## Layout

`.agents/skills/cumcm-workflow/` is the single canonical tree: `SKILL.md`, `references/`, `schemas/`, `scripts/`, `assets/`. `.claude/skills/cumcm-workflow/SKILL.md` is a thin router into it and deliberately restates no rules — if you add a rule, it goes in the canonical tree only.

## Invariants to preserve when editing

- **Machine facts are recorded, never hand-written.** If a change would make an agent type a SHA-256, an exit code, a page count or a result value into a contract, the change is wrong; extend a recorder instead.
- **Two knobs only.** `mode` (`working` / `finalizing`) and `--gate-mode` (`preflight` / `enforce`). Do not reintroduce a profile axis.
- **Four stage statuses.** `not_started`, `in_progress`, `passed`, `needs_revision`.
- **Schemas describe shape, the checker decides strictness.** Mode-dependent requirements (for example the frozen model contract) live in `workflow_checks.py`, not in a JSON Schema `required` list — a schema cannot see the mode.
- **A schema is also a prompt.** An optional field that nothing consumes will still get filled in by an agent. Delete it rather than leaving it optional.
- **Exploratory runs never block.** Anything about an `official_run: false` run is at most a warning.
- **Runs are append-only and their evidence is frozen.** A rerun appends a successor with `parent_run_id`; it must never overwrite a run directory. Declared source and outputs are copied into `runs/<id>/{source,outputs}/` mirroring the original paths, and hashed as copies. Supersession is derived from the parent chain -- never write it back into the old manifest, because that changes its hash and stales every decision bound to it.
- **Declared is not recorded.** Anything the caller types (`--assert name=pass`) is a note; only what the run wrote itself (`--assert-file`) is machine-derived evidence. Tag provenance on the record and let the checks that mean "this was verified" read only the recorded kind. The same test applies to any future field: who produced this, the tool or the caller?
- **A run may only claim what it produced and verified.** Claim outputs and assertion files must be freshly generated at paths cleared with recoverable backups before execution -- a leftover file must never be frozen as this run's evidence -- and assertions are never inherited by a rerun. Both are evidence-fabrication paths, not conveniences.
- **Only a successful official rerun supersedes.** A failed or exploratory child replaces nothing. Whenever you add a consumer of "the current official run", route it through `canonical_evidence.resolve_official_computation` so the definition stays single.
- **Freezing must not cost drift detection.** Because the frozen copy cannot change, staleness is measured as frozen-versus-live (`RUN-E020`), and tampering with the frozen copy is a separate failure (`RUN-E021`). If you add another frozen artifact, add its drift check at the same time.
- Do not add a check whose only evidence is that someone asserted it. If it cannot be measured, it belongs in `REVIEW_REQUEST.md` as a named failure class for a human or a fresh-context reviewer.
- **A free-text field is not a check.** `alternatives_considered` was a string array whose only rule was "non-empty", so "I compared alternatives" was unfalsifiable. Structured `candidates` replaced it because a candidate can be tied to the runs that evaluated it. Apply the same test to anything new: what would make this claim wrong, and can a script see it?
- **No backward compatibility.** v0.6 rejects any contract whose `schema_version` is not `0.6.0`, and the repository keeps no migration scripts or historical design documents. An older workspace is re-initialised from its official files.

## Development

```bash
python3 -m pip install -r requirements-ci.txt
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m compileall -q .agents/skills/cumcm-workflow/scripts tests
```

`tests/workflow_fixtures.py` holds synthetic contracts/approvals; `tests/recorder_fixtures.py` holds shared real-recorder setup. Import these helpers rather than another test class. Test files retain their regression cases; recorder, compile, and cross-competition tests may execute real subprocesses and LaTeX. Tool-dependent cases skip when tools are absent. CI runs the full suite on Python 3.10 and once on Python 3.13 with XeLaTeX/CTeX/Poppler installed; there is no duplicate Python 3.13 job.

When you add a rule ID, test its failing and passing cases. Completeness checks warn in `working`; human checkpoints still block dependent actions and `enforce` in both modes. Test that `preflight` reports pending review without blocking exploration.

Two habits, both learned from bugs the tests did not catch:

- **Count the entry points before you stop.** A new invariant almost never has one. Claim-bearing outputs got an mtime check against leftovers; the assertion file that the whole declared/recorded split rests on did not, and a five-year-old file satisfied a verification plan. Declared outputs were compared across the execution; declared sources were only checked afterwards, so a file the run generated could be frozen as the code that produced the result. The checker rejected declared verdicts while four documents still showed `--assert "x=pass"` in the official-run example. Each time the rule was right and one of its doors was open. When you add one, list every place the same thing can enter, and fix them together.
- **Re-run the known failure modes against new code.** The catalogue is short and it repeats: a leftover file standing in for this run's evidence, a superseded run still vouching for its replacement, a caller-typed value satisfying a check that means "measured", a free-text field whose only rule is non-empty. Take each one to anything you just wrote and ask whether it has that hole. This has found more real defects here than the test suite has, because the suite is written by the same person with the same blind spots.

Verify a fix by reverting it and confirming the new test goes red. A test that passes with its fix removed asserts an outcome without asserting its precondition.

## Version bumps

`WORKFLOW_VERSION` in `workflow_checks.py` and the recorders, the `const` in every schema, and `pyproject.toml`. The checker rejects any contract whose `schema_version` differs; that is intentional, and existing workspaces are re-initialised rather than migrated. Say so in the README when you bump.
