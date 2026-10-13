# Section B — Test generation (Nemotron) (EMPTY — awaiting submission)

This folder is a placeholder. Drop your files in here directly (flat, no
subfolder) before the group tries to run the full pipeline.

## Contract to implement

```python
def generate_test(gap: Gap, example_tests: list[str], attempt: int = 1,
                   prior_failure: str | None = None) -> CandidateTest
```

`Gap` and `CandidateTest` come from Section A's `models.py` — import them,
don't redefine them.

- `gap` — where to write a test (file, line range, enclosing function,
  why it's a gap: fully uncovered vs. a half-tested branch).
- `example_tests` — existing test snippets from the repo, for style/pattern
  matching. Section C's orchestrator currently always passes `[]` here —
  nobody has wired up "pull a few real tests from the repo" yet, so that's
  an open gap on the orchestration side too, not just something to consume.
- `attempt` / `prior_failure` — on a retry, `prior_failure` carries the
  previous attempt's real pytest failure message (stdout/stderr tail), so
  the generator can actually react to *why* the last candidate didn't
  verify, not just blindly retry the same thing.

## What Section C's stand-in does today

`section-c/generator_stub.py` is a deterministic placeholder matching this
exact signature, used so the orchestration loop is demoable before a real
generator exists. It hand-writes correct tests for two known gap shapes
(proving the happy path) and, for one gap, deliberately returns a broken
candidate on attempt 1 and a fixed one on attempt 2 using `prior_failure`
(proving the retry path against a real pytest failure, not a canned one).

Swapping in your real implementation should be a one-line import change in
`section-c/run_pipeline.py` — see the comment next to the import there.
