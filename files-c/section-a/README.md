# Section A — Sandbox verification engine (EMPTY — awaiting submission)

This folder is a placeholder. Drop your files in here directly (flat, no
subfolder) before the group tries to run the full pipeline.

## Contract to implement

```python
def find_gaps(sandbox: SandboxClient, repo_path: str, diff: str,
              changed_py_files: list[str]) -> list[Gap]

def verify_test(sandbox: SandboxClient, repo_path: str,
                 candidate: CandidateTest) -> VerificationResult
```

## Expected files

- `models.py` — the shared `Gap` / `CandidateTest` / `VerificationResult`
  dataclasses. This is the interface boundary all three sections build
  against — Section C already imports from this module name, so keep the
  class/field names exactly as agreed.
- `sandbox_client.py` — the `SandboxClient` protocol plus at least a local
  implementation (`LocalSandboxClient`) Section C can run the demo against
  without credentials.
- `coverage_diff.py` / `verifier.py` (or however you split it) — the actual
  `find_gaps`/`verify_test` logic.
- A short README noting what's actually been run/verified vs. what's only
  asserted — Section C's README follows this convention, worth matching.

## Known gap for whoever picks this up

Section C integrated against an earlier draft of this contract and found
one real bug worth fixing on arrival: `LocalSandboxClient.read_file()` /
`write_file()` string-concatenated `cwd + path` unconditionally, which
breaks if `repo_path` is passed in as an absolute path (`run()` tolerates
absolute paths fine, since it just does `cd <path>`; `read_file`/
`write_file` didn't). Section C's demo currently works around this by using
a sandbox-relative `repo_path`. Worth fixing at the source so either
calling convention works. Full writeup in Section C's README under "A real
bug found during integration."
