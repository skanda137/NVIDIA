# Section 1 — Sandbox verification engine

Implements the two functions locked in the team's interface contract:

```python
def find_gaps(repo_path: str, diff: str) -> list[Gap]
def verify_test(repo_path: str, candidate_test: str, target_gap: Gap) -> VerificationResult
```

(signatures here also take a `sandbox: SandboxClient` first arg — needed so
Section 3 can pass in `LocalSandboxClient` during dev and `NebiusSandboxClient`
for the real thing without this code changing.)

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
- `NebiusSandboxClient` end to end — grounded in documented CLI patterns
  but the file-write-via-heredoc approach has never hit the real API.
  First thing to do once someone has Token Factory credentials: run
  `NebiusSandboxClient().write_file("test.txt", "hi")` then
  `.read_file("test.txt")` and confirm the roundtrip, exactly like the
  LocalSandboxClient check in `demo.py`, before building anything on top.

## Known gaps / next steps for whoever picks this up

1. `compute_gaps()` has no call-graph awareness (see `demo.py`'s closing
   note) — it will report two Gaps for two pieces of code that one good
   test would close together. Not a bug, just know it going in when
   wiring up Section 2's retry budget.
2. `verify_test()` always runs `coverage xml -o _scratch_coverage.xml`
   fresh rather than diffing against a stored "before" snapshot — simpler,
   and sufficient, because we only care whether the target lines show
   `hits > 0` after this one test, not the whole-suite coverage delta.
3. The `--file` upload flag and `contree cp` exact syntax are still
   unconfirmed (see the long comment at the top of `sandbox_client.py`) —
   deliberately avoided rather than guessed at. If you find the real
   syntax in the CLI reference, it's a safe, isolated addition; nothing
   else here depends on it.
