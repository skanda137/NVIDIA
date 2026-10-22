# Section 1 — Sandbox verification engine

Implements the two functions locked in the team's interface contract:

```python
def find_gaps(repo_path: str, diff: str) -> list[Gap]
def verify_test(repo_path: str, candidate_test: str, target_gap: Gap) -> VerificationResult
```

(signatures here also take a `sandbox: SandboxClient` first arg; Section 3
passes in `LocalSandboxClient`, which runs every command inside `bwrap`.)

## What's actually verified vs. what's asserted

This container has no network access, so nothing here could pip-install
pytest/coverage or call the real Nebius API. Be clear-eyed about what that
does and doesn't mean for how much you can trust this code:

**Verified by actually running it (see `demo.py`, run it yourself —
`python3 demo.py`):**
- `changed_lines_by_file()` — diff parsing, correct new-file line numbers
- `enclosing_function()` — AST-based function-context lookup, including
  telling two different functions in the same file apart correctly
- `compute_gaps()` — the core mechanic: cross-referencing a diff against a
  coverage report, including the branch-vs-fully-uncovered distinction and
  correctly bucketing contiguous lines into one Gap vs. keeping separate
  Gaps for lines that aren't contiguous
- `LocalSandboxClient` — file write/read roundtrip
- `verify_test()`'s malformed-input rejection path

This is the hard, novel part of the project, and it's genuinely tested, not
just written.

**NOT verified — needs testing the moment anyone has 10 minutes with
network + pytest installed, before you trust it on a real PR:**
- `find_gaps()` / `verify_test()`'s actual `sandbox.run(...)` calls against
  a real pytest+coverage run (the plumbing is straightforward but
  untested; do a run against a real toy repo in `LocalSandboxClient` mode
  first, that alone will need neither Nebius credentials nor a review)

## Known gaps / next steps for whoever picks this up

1. `compute_gaps()` has no call-graph awareness (see `demo.py`'s closing
   note) — it will report two Gaps for two pieces of code that one good
   test would close together. Not a bug, just know it going in when
   wiring up Section 2's retry budget.
2. `verify_test()` always runs `coverage xml -o _scratch_coverage.xml`
   fresh rather than diffing against a stored "before" snapshot — simpler,
   and sufficient, because we only care whether the target lines show
   `hits > 0` after this one test, not the whole-suite coverage delta.

## Changes after the Oct 14 audit

Fixes for audit findings B1, B2, B3, B5, B7, B8, B11, B12, B14 (see the audit report for
the evidence behind each). Tests: `python -m pytest -q test_section1.py` (30 tests, fake
sandbox; 3 are POSIX-only and skip on Windows).

Re-run against real pytest 9.1.1 + coverage 7.16.2 (WSL Ubuntu, Python 3.14), all pass:
E1 (re-running the covered branch is now rejected), E3 (all three path layouts find gaps),
E4b (an unimported new module is now reported), E4c (one gap, not two), E5 (absolute
paths), E6 (the ModuleNotFoundError is in the message), E8 (0/6 wrong rejections), the
real `exit` branch token, and a `while True` candidate (times out as `fail`).
`LocalSandboxClient` needs Linux and `bwrap`. On Windows it raises; run the pipeline in WSL2.
`test_sandbox_env.py` proves the isolation: writes outside the workdir fail with
`Read-only file system`, the repo `.env`, `~/.config` and `~/.ssh` are not there, and a
socket connect fails with `Network is unreachable`.

- `Gap.missing_branches` (defaulted): partial_branch gaps now carry coverage.py's missing
  branches, and `verify_test` accepts a candidate only if it takes one of them.
- `compute_gaps` / `parse_coverage_xml` take the XML *text*, not a path. No /tmp files.
- Report paths are matched to diff paths by exact name, then longest path-suffix. A `.py`
  file in `changed_py_files` that is absent from the coverage report raises.
- Coverage runs with `--source=.`; the candidate run sets PYTHONDONTWRITEBYTECODE=1.
- All sandbox calls take `timeout` (default 120 s); timeout returns code 124.
- `prepare_env()` installs pytest, coverage and requirements.txt. Section 3 calls it when
  `run_pipeline(..., install_deps=True)` / `cli.py --install-deps`.
- Deliberately unchanged: a red existing suite still aborts `find_gaps` (fail fast), now
  with the real pytest output in the message.
