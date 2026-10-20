# Verified Test-Gap Agent: Integration Guide

Written 2026-10-13 for the three-person team (Section 1, Section 2, Section 3).

## 1. Overview

The agent reads a PR diff, finds the new lines no test covers, asks Nemotron to write a test for each one, and reports a test only after it passed in a sandbox **and** actually executed those exact lines. All three sections now run together end to end. Two small fixes are needed, one in Section 3 and one in Section 1.

| Section | Owns | Status | What is left |
| --- | --- | --- | --- |
| 1 | `find_gaps`, `verify_test`, sandbox clients | Works on real git, pytest and coverage | Fix 2 bugs (section 4 below) |
| 2 | `generate_test` (Nemotron) | Built, 12 unit tests pass | Run against the live Nemotron API |
| 3 | `run_pipeline`, `render`, `cli` | Works with the stub generator | Apply the 3-edit patch, then swap in the real generator |

**What has been proven:** the full loop ran with real git clone, real pytest and real coverage. The model call was a scripted stand-in because no `NVIDIA_API_KEY` was available. In that run all 3 gaps were verified, and one needed a retry: the first test failed with a real `ModuleNotFoundError`, that error reached the next prompt, and the larger model tier passed.

**What has not been proven:** a live Nemotron call, and `NebiusSandboxClient` against the real Nebius service.

---

## 2. How it works

```
PR diff + repo
      |
      v
[Section 3] checkout_repo        git clone + checkout the PR head inside the sandbox
      |
      v
[Section 1] find_gaps            run the existing suite under coverage, compare with the diff
      |                          -> list[Gap]   (file, start_line, end_line, function_context, reason)
      v
 for each Gap:  (Section 3 loop, up to N attempts)
      |
      |   [Section 3] read the gap's file text from the sandbox  -> source
      |
      |   [Section 2] generate_test(gap, example_tests, attempt, prior_failure, source=source)
      |        build prompt -> call Nemotron -> extract code -> lint (one repair if needed)
      |        -> CandidateTest
      |
      |   [Section 1] verify_test(sandbox, repo_path, candidate)
      |        write scratch test, run it under coverage
      |        -> VerificationResult(status, coverage_hit, message)
      |
      +-- verified (status == "pass" AND coverage_hit)?  yes -> done with this gap
      |                                                   no  -> prior_failure = message, retry
      v
[Section 3] render_markdown      PR-comment-style report
```

**Shared types** (`models.py`, owned by Section 1, imported by everyone, never redefined):

- `Gap`: a contiguous range of new lines the PR left untested. `function_context` is only the **function name**, and `reason` is `"uncovered"` (never executed) or `"partial_branch"` (one side of an `if` never taken).
- `CandidateTest`: `code`, `target_gap`, `model_tier_used`, `attempt_number`.
- `VerificationResult`: `status` (`pass`, `fail`, `error`), `coverage_hit`, `message`. Its `.verified` property is `status == "pass" and coverage_hit`. That is the project's core claim: a green test that never touched the gap does not count.

**Key design points**

- Gap-finding and verification are deterministic. Only test writing uses the LLM, and its output is never trusted: it is linted, executed, and checked against coverage of the exact gap lines.
- Retries carry the real pytest failure text into the next prompt, and the model tier escalates (nano, then super, then ultra).
- Everything talks to a `SandboxClient` protocol, so `LocalSandboxClient` (dev) and `NebiusSandboxClient` (real) are swappable.

**Safety note:** `LocalSandboxClient` runs generated code directly on your machine with no isolation. Use it only for development on code you trust. Anything real goes through the Nebius sandbox.

---

## 3. Section 3 actions: `run_pipeline.py`

Three edits let the real generator see the code it is testing. `Gap.function_context` holds only a function name, so without the file text the model has almost nothing to work from. The same edits are in `run_pipeline.patch`, and a fully patched copy is `run_pipeline.py`.

1. Swap the import: replace `from generator_stub import generate_test` with `from generator import generate_test`.
2. Add a helper above `_run_gap`:

```python
def _read_source(sandbox, repo_path, file):
    try:
        return sandbox.read_file(f"{repo_path}/{file}")
    except Exception:
        return None
```

3. In `_run_gap`, read the source once before the retry loop with `source = _read_source(sandbox, repo_path, gap.file)`, then pass `source=source` into the `generate_test(...)` call.

Three smaller changes:

- **Attempts:** set `max_attempts_per_gap=3`. The generator picks the model tier from the attempt number (1 = nano, 2 = super, 3 and up = ultra), so the default of 2 never reaches the largest model. `cli.py` has the same default in `--max-attempts`.
- **Example tests:** `example_tests` is still always empty, so the model gets no style hints from the repo. Pass one or two existing test files from the checkout. Untested sketch:

```python
r = sandbox.run(f"cd {repo_path} && ls test_*.py tests/test_*.py 2>/dev/null | head -2")
example_tests = [sandbox.read_file(f"{repo_path}/{p}") for p in r.stdout.split()]
```

- **Demo:** after the import swap, `demo_pipeline.py` fails because its assertions are written for the stub. Use `demo_real_generator.py` instead, or keep the stub selectable with an environment variable.

---

## 4. Section 1 actions: `verifier.py` and `sandbox_client.py`

Two bugs, one of which will make the demo fail at random.

### 4.1 Stale bytecode rejects correct retries (`verifier.py`)

`verify_test` rewrites `_scratch_verify_test.py` for every attempt. When two candidates have the same length and are written within the same second, Python reuses the cached bytecode of the first one, so the corrected test is judged as the old, failing one. In my runs the correct second attempt was rejected in 3 of 4 runs with default settings, and passed in 6 of 6 with bytecode caching turned off.

Fix: put `PYTHONDONTWRITEBYTECODE=1` in front of the `coverage run` command inside `verify_test`:

```python
f"cd {repo_path} && "
f"PYTHONDONTWRITEBYTECODE=1 coverage run --branch -m pytest -q _scratch_verify_test.py::{test_name} "
f"&& coverage xml -o _scratch_coverage.xml"
```

I verified the environment variable by setting it for the whole run. An alternative I have not tried is a unique scratch filename per attempt.

### 4.2 `LocalSandboxClient` breaks on absolute paths (`sandbox_client.py`)

`read_file` and `write_file` always build `f"{self.cwd}/{path}"`, but `verifier.py` passes absolute paths, which gives a doubled path and a `FileNotFoundError`. Section 3 currently avoids it by using a relative `repo_path`. Suggested fix (untested):

```python
import os

def _full(self, path):
    return path if os.path.isabs(path) else f"{self.cwd}/{path}"
```

Use `self._full(path)` in both `read_file` and `write_file`.

### 4.3 Good to know, no change needed

- `verify_test` runs only the first `def test_...` in a candidate. Section 2 is told to write exactly one test function, so this holds, but nobody should rely on multi-test candidates.
- `find_gaps` reports one `if/else` as two gaps (the `if` line as `partial_branch`, the else body as `uncovered`). That is correct, but one good test can close both.

---

## 5. Section 2 reference: `generate_test`

```python
generate_test(gap, example_tests, attempt=1, prior_failure=None, *, source=None, llm=None) -> CandidateTest
```

- `gap`: Section 1's `Gap` dataclass. Plain dicts with the same fields also work.
- `example_tests`: existing test code from the repo, used for style. At most 3 are used, each cut to 2,500 characters.
- `attempt`: picks the model tier and temperature.
- `prior_failure`: pass `VerificationResult.message` whenever `verified` is False. That includes "passed but NEVER EXECUTED the target gap".
- `source` (new): full text of `gap.file` at PR head. Optional, but strongly recommended.
- `llm` (testing only): a function `(model, messages, temperature) -> text` that replaces the Nemotron call.

**Model tiers** (the model IDs are my best guess; confirm them at build.nvidia.com and override with the environment variables):

| Attempt | Tier | Default model ID | Environment variable | Temperature |
| --- | --- | --- | --- | --- |
| 1 | nemotron-nano | `nvidia/llama-3.1-nemotron-nano-8b-v1` | `NEMOTRON_NANO_MODEL` | 0.2 |
| 2 | nemotron-super | `nvidia/llama-3.3-nemotron-super-49b-v1` | `NEMOTRON_SUPER_MODEL` | 0.4 |
| 3 and up | nemotron-ultra | `nvidia/llama-3.1-nemotron-ultra-253b-v1` | `NEMOTRON_ULTRA_MODEL` | 0.6 and up |

**What happens inside one call**

1. Build the prompt: file, import hint, target lines, why it is a gap (the `partial_branch` wording asks for input that forces the *other* side of the condition), the real function source (or a +/-15 line window for module-level gaps), example tests, and on retries the previous failure text.
2. Call the model through NVIDIA NIM (OpenAI-compatible endpoint, 3 retries with backoff).
3. Extract the code: strips `<think>` blocks, prose, and code fences.
4. Lint: it must parse, contain a `test_*` function, and avoid `subprocess`, `socket`, `requests`, `urllib`, `http`, `httpx`, `shutil`, `ctypes`, `eval`, `exec`, `__import__`, `os.system` and similar. If lint fails, one automatic repair request is sent.
5. Return a `CandidateTest`.

**Setup:** `pip install openai pytest coverage`, then set ONE key: `TOKEN_FACTORY_API_KEY` (Nebius Token Factory, base URL `https://api.tokenfactory.nebius.com/v1/`) or `NVIDIA_API_KEY` (build.nvidia.com). If `TOKEN_FACTORY_API_KEY` is set it wins, and the three tier models are discovered from the provider's model list (Nemotron ids matched by 'nano' / 'super' / 'ultra', else by parameter count). Run `python list_models.py` to see the assignment, override with the `NEMOTRON_*_MODEL` variables, then `python live_pipeline.py` for the full pipeline with the real model. Never paste or commit the key.

**What Section 2 needs from the others**

- Section 3 passes `source=` and `prior_failure=` as described above.
- The runner must start from the repo root, which `verify_test` already does with `cd {repo_path}` and `python -m`. The generator derives the import from the file path (`app/billing.py` becomes `from app.billing import ...`).
- **Known limitation:** for `src/` layouts where the package is `pkg` rather than `src.pkg`, the derived import will be wrong. The retry loop may fix it from the `ModuleNotFoundError`, but it is not handled directly yet.

---

## 6. How to run and verify

Install first: `pip install pytest coverage openai`. You need `git` too.

| What | Command | Expected result |
| --- | --- | --- |
| Section 2 unit tests | `python -m pytest -q test_generator.py` | `12 passed` |
| Section 1 demo (no network, hand-built coverage) | `python demo.py` | ends with the three-gap explanation |
| Section 3 demo with the stub generator (before the patch) | `python demo_pipeline.py` | `gaps_found=3 ... verified_pass=3` and the retry proof |
| Full pipeline with the real generator (after the patch) | `python demo_real_generator.py` | `FULL PIPELINE WITH REAL generate_test: OK` |
| A real PR | `python cli.py --repo-url <git-url> --ref <sha> --diff-file diff.txt --changed-files a.py,b.py --max-attempts 3` | Markdown report on stdout |

`demo_real_generator.py` replaces only the Nemotron HTTP call with a scripted model. Everything else is real: git, pytest, coverage, prompt building, extraction, lint, tier escalation and failure feedback. To try the real model, delete the line `generator.nvidia_llm = scripted_llm` and set `NVIDIA_API_KEY`. The scripted answers are tied to the toy repo, so on a real model you would only look at the report.

---

## 7. Risks and next steps

**Risks**

- **Model quality:** the small Nemotron may fail often. Measure it before the demo; the tier escalation is the mitigation.
- **Untested sandbox:** `NebiusSandboxClient` has never run against the real service. First check: write a file, read it back, confirm the round trip, before building on it.
- **Hangs:** there is no timeout on `sandbox.run()`, so a hung command hangs the whole pipeline.
- **Import paths:** `src/` layouts, as described above.
- **No isolation locally:** see the safety note in section 2.

**Next steps, in order**

1. Get an `NVIDIA_API_KEY`, confirm the three model IDs, and run `generate_test` against the real model on the toy repo. Fix whatever breaks first. (Section 2)
2. Apply the Section 3 patch and the two Section 1 fixes above. (Sections 3 and 1)
3. Run the pipeline on one or two small real open-source PRs.
4. Build a benchmark of 10 to 20 realistic gaps and measure pass rate by attempt and by tier. A chart of "attempt 1 vs attempt 3" is the strongest demo slide. (Section 2 with Section 3)
5. Wire `example_tests` from the repo, add timeouts around `sandbox.run()`, and skip gaps already covered by a verified test.
6. Switch to `NebiusSandboxClient` once credentials exist.
7. Prepare a recorded fallback demo in case the API or sandbox is flaky on stage.
