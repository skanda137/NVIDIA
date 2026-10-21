# Section 3 — Orchestration

Implements `run_pipeline()`: checks out a PR's head inside the sandbox,
calls Section 1's `find_gaps()`, loops `generate_test() -> verify_test()`
with retries per gap, aggregates results, and renders a report.

```python
def run_pipeline(sandbox, repo_url, ref, diff, changed_py_files,
                  example_tests=None, config=None, repo_path=...) -> PipelineResult
```

Files:
- `pipeline_models.py` — `GapRecord` / `PipelineResult` / `PipelineConfig`,
  the shapes Section 3 owns. `Gap` / `CandidateTest` / `VerificationResult`
  are imported from Section 1's `models.py`, never redefined.
- `generator_stub.py` — offline stand-in for Section 2's `generate_test()`,
  same signature. `run_pipeline()` uses Section 2's real generator by default;
  the demo and `cli.py --generator stub` pass the stub as `generate=`.
- `run_pipeline.py` — the orchestration loop itself, plus `checkout_repo()`
  (cloning the PR head into the sandbox, which `verifier.find_gaps()`'s
  own docstring says is this section's job, not Section 1's).
- `render.py` — `PipelineResult` → PR-comment-shaped markdown.
- `demo_pipeline.py` — proof this actually runs, see below.
- `cli.py` — entry point for pointing this at a real PR.

## What's actually verified vs. what's asserted

**Verified by actually running it (`python3 demo_pipeline.py`) — and unlike
Section 1's `demo.py`, this container had network access, so this isn't
hand-built fixtures standing in for a real run:**

- A real local git repo is built with two real commits (base + "PR").
- `checkout_repo()` does a real `git clone` + `git checkout` of the PR
  head into the sandbox via `LocalSandboxClient`.
- `find_gaps()` runs **real** `pytest` + `coverage` (installed via pip in
  this environment) against that checkout — not a hand-written
  coverage.xml. It finds the same 3 gaps Section 1's own `demo.py` found
  by construction, confirming both ends of the pipeline agree.
- The retry loop is proven both ways, not just the happy path:
  - Two gaps get a correct candidate test on attempt 1 and verify immediately.
  - One gap's attempt 1 is a deliberately broken candidate (bad import).
    Real pytest produces a real `ModuleNotFoundError`. That failure text
    flows into `generate_test()`'s `prior_failure` argument. Attempt 2
    uses it, passes, and hits the target lines.
- The project's core claim — a test that passes but never executes the
  gap must be rejected, not just "ran green" — is proven against a real
  pytest run: `verify_test()` correctly returns `status="pass",
  coverage_hit=False` for a vacuous test and the orchestrator correctly
  does **not** count that as `verified_pass`.
- `render_markdown()` producing the full report shown in `demo_pipeline.py`'s output.

**NOT verified:**
- `NebiusSandboxClient` end to end — same caveat Section 1's README gives;
  nothing here changes it since `run_pipeline()` only talks to the
  `SandboxClient` protocol, not to either implementation directly.
- `run_gaps_in_parallel=True` — deliberately raises `NotImplementedError`
  rather than silently racing; see the comment in `run_pipeline.py` for why
  (concurrent gaps could step on each other's shared `_scratch_verify_test.py`
  inside one evolving sandbox session).
- A live run of Section 2's generator through this loop. The wiring is tested
  offline (`test_pipeline_integration.py`, fake LLM, real git/pytest/coverage).

## Fixed since the Oct 14 audit

- Absolute `repo_path` with `LocalSandboxClient`: fixed in Section 1 (`os.path.join`).
- Rerunning into the same sandbox dir: `checkout_repo` now does `rm -rf` before cloning.
- Timeouts: every sandbox call has one (Section 1); a looping candidate becomes `fail`.
- `cli.py --sandbox {local,nebius}` and `--install-deps` (calls `verifier.prepare_env`).
- Section 1 files are imported from `../section-a` via `_paths.py`; no copies here.

## Known gaps / next steps

1. `example_tests`: when not passed, `collect_example_tests()` reads up to 3
   `test_*.py` files from the checked-out repo (sorted; `_scratch_*` and hidden
   dirs skipped). It takes the first 3 by path, not the most relevant ones.
2. `run_gaps_in_parallel` needs per-gap sandbox session isolation (a
   separate scratch filename, or a session-per-gap sandbox) before it's
   safe to implement — see the `NotImplementedError` in `run_pipeline.py`.
