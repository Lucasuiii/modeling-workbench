# Environment and project diagnostics

Use diagnostics at setup, after an environment change, on project resumption, or when the user asks about progress. Do not repeat them on every reply. They report observations without installing software, rewriting contracts, recording approvals, or advancing stages. Probes use temporary directories; they are not a sandbox for untrusted software.

## Environment: `doctor.py`

```bash
python3 "$S/doctor.py"
python3 "$S/doctor.py" --json
```

The doctor uses the Python interpreter that launches it. It checks core workflow files and reads the workflow version, imports supported `jsonschema` and `referencing` versions in child processes, locates MATLAB with the existing backend detector, runs version probes for XeLaTeX/Poppler, and looks for `ctexart.cls`. It does not certify all repository files, solve a model, test fonts or compile a paper. A missing Python interpreter prevents launching the doctor; report that prerequisite directly.

Statuses are `available`, `missing`, `failed`, and `unverified`. Found MATLAB is **unverified** by default: discovery does not prove license or toolbox availability. If the chosen task needs MATLAB execution testing, `--probe-matlab --timeout 60` starts it in a temporary directory and tests base runtime/license access; task-specific toolboxes remain untested. This may consume a license and use ordinary application preferences. No parallel backend implementation is requested.

For known, trusted installed Python dependencies needed by the actual model, use repeatable `--module numpy --module scipy`. This imports code in a child process, not from the contest directory. Do not import arbitrary modules supplied with unfamiliar input materials. Successful imports do not establish solver correctness, task suitability or GPU availability. Without these options, the doctor makes no claim about scientific libraries.

Exit status: `0` means base checks and requested Python imports passed; `1` means one of these failed; `2` means invalid command arguments. Paper tools and optional MATLAB checks are stage-specific and do not change that exit code: inspect individual results. `paper_tools_detected` excludes Chinese class discovery; read the separate `ctex` result for Chinese papers. Tool detection never establishes compile/visual QA success.

Tell the user what is usable now, what is missing, and which stage needs it. Missing LaTeX must not prevent intake or model exploration. Recommend only the relevant dependency/environment repair, matching the detected execution environment; ask before installing or changing system configuration. Honor an already prepared environment instead of reinstalling it.

## Project: `project_status.py`

```bash
python3 "$S/project_status.py" --project <p>
python3 "$S/project_status.py" --project <p> --json
```

Reads and validates the current state, then invokes the existing checker through that stage using `preflight`. It also calls the existing human-checkpoint action boundaries through that stage: a lightweight preflight can be ready while a missing/stale approval snapshot still prevents dependent work. Those two observations are reported separately; the tool introduces no new rule or approval mechanism.

The text groups technical errors, review-related findings and warnings, shows up to five findings per group, lists checkpoint availability, and links the active stage guide. JSON retains every original finding, rule ID, path, remediation and checker summary. A checkpoint failure can reflect incomplete candidate selection or missing/stale confirmation evidence; do not interpret every failure as simply asking the user to approve immediately. Repair or prepare the material first, and never invent an earlier approval.

Exit status: `0` means no automated checker errors (human review may still be pending); `1` means automated checker errors; `2` means status could not be evaluated, such as invalid/unsupported state, missing dependencies or unreadable contracts. Never treat `0`, declared `passed`, or existing downstream files as authority to cross a human checkpoint. The usual action tools enforce their own boundaries.

The scope ends at the recorded current stage. This does not certify later files or declare a project finished. For affected-work planning after a concrete change, use the existing `plan_redo.py`; status does not guess which unexamined work is unaffected. If state is corrupt, report it without reinitializing or overwriting the project. Summarize findings in the user's language and continue already-authorized work when possible.
