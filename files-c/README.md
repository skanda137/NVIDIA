# Verified Test-Gap Agent — team delivery package

Status at the time of this zip:

| Section | Owns | Status |
|---|---|---|
| A | `find_gaps`, `verify_test`, sandbox execution | **empty — awaiting your files**, see `section-a/README.md` for the contract and one known bug to fix |
| B | `generate_test` (Nemotron) | **empty — awaiting your files**, see `section-b/README.md` for the contract |
| C | orchestration (`run_pipeline`), retry loop, rendering, CLI | **complete**, see `section-c/README_section3.md` |

## How to assemble the full pipeline once A and B land

Drop Section A's files and Section B's files into `section-a/` and
`section-b/` respectively (flat, replacing the placeholder README), then
either put all three folders' `.py` files on one `PYTHONPATH` or flatten
them into one directory — `section-c/run_pipeline.py` imports `models`,
`sandbox_client`, `verifier` (Section A) and `generate_test` from a
`generator_stub`-shaped module (Section B) by plain module name, not by
package path, matching how the three of you have been developing so far.

## Section C, what's already proven

`section-c/demo_pipeline.py` runs the **entire** orchestration end-to-end
against real `git`, real `pytest`, and real `coverage` (not hand-built
fixtures) — using Section A's actual `find_gaps`/`verify_test` code
(included in `section-c/` as the versions Section C last integrated
against, purely so the demo is runnable standalone right now) and a
deterministic stand-in for Section B's `generate_test`. It proves:

- gap-finding agrees with Section A's own demo (same 3 gaps)
- the retry loop actually recovers from a real pytest failure, not a
  scripted one
- a test that passes but never touches the gap's lines is correctly
  rejected, not counted as verified — the project's core claim

Run it yourself: `cd section-c && python3 demo_pipeline.py`

**Note:** the `models.py` / `coverage_diff.py` / `verifier.py` /
`sandbox_client.py` / `demo.py` copies currently sitting in `section-c/`
are Section A's, not Section C's — kept there only so this zip runs
out of the box before `section-a/` is filled in. Once you drop your real
files into `section-a/`, those copies in `section-c/` should be deleted
and `section-c/`'s imports pointed at `section-a/` instead (or the two
folders flattened together), so there's only one source of truth for
Section A's code.
