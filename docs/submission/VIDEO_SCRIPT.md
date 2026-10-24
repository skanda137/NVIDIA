# Video script (target 2:45; the limit is 3:00)

Record in a terminal with a large font. Every number on screen must come from
`docs/evidence/`. Times are cumulative.

## 0:00-0:20 The problem
**Screen:** a generated test that passes and asserts nothing (e.g. `assert True`).
**Say:** "AI can write tests that pass without testing anything. Green doesn't mean
covered. We built an agent that keeps a generated test only when it can prove the test
runs the code the PR changed."

## 0:20-0:50 How it works
**Screen:** a four-box diagram: find gaps, then Nemotron writes a test, then verify in a
sandbox, then report.
**Say:** "Given a pull request, we run the repo's own tests under branch coverage and
intersect the result with the diff. That gives the changed lines no test executes. That
part is deterministic, with no LLM. For each gap, Nemotron 3 on Nebius Token Factory
writes a test, starting with Nano and escalating to Super, then Ultra, only on failure.
Every test runs in a bubblewrap sandbox: no network, read-only filesystem, API keys
scrubbed. We keep it only if it passes and coverage shows it ran the gap. For a
half-tested `if`, it has to take the branch the suite missed."

## 0:50-1:40 Live run
**Screen:** `python cli.py --pr-url <a demo PR> --install-deps`. Cut the waiting; show the
gap list, one retry, and the final report.
**Say:** point at one gap closed on attempt 1 by Nano, and one that failed verification
and was rescued by Super. Read the reason the first attempt was rejected.
**Fallback if the live run is slow:** the offline `demo_pipeline.py`, which shows 3 gaps
and one real retry.

## 1:40-2:25 Does it work?
**Screen:** the Results table from the README.
**Say:**
- "On new repos written after our fixes, it closed 88% of gaps, and Nano alone closed
  52% on the first try. Almost every miss was the model guessing a field or class name
  it couldn't see. Those repos were written by the same agent that made the fixes, so they
  are new code, but not an independent test."
- "Our first two runs exposed bugs in our own prompt: missing imports and no line
  numbers. Fixing them took Nano's first-try rate from about 30% to 69%."
- "Verified doesn't mean perfect. The tests kill 67% of mutants; exception paths are
  weakest."

## 2:25-2:45 Close
**Say:** "Nebius serves all three Nemotron tiers behind one API, which is what makes the
cost ladder work. The code, the eval harness and every report are in the repo."
**Screen:** the repo URL.

## Do not say
- "Independent held-out test", "Nebius sandboxes" (we use bubblewrap), or "100%"
  without "in-sample".
