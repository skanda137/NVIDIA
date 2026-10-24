# Verified Test-Gap Agent: written description

Nebius x NVIDIA Global AI Hackathon, Coding & Agentic Engineering track.

## The problem

AI coding tools can write tests that pass without testing anything. A test that imports
a module and asserts `True` is green, and a test that calls the wrong function is green
too. Reviewers then have to read every generated test to find out whether it covers the
code the pull request changed.

## What it does

Given a pull request, the agent:

1. **Finds the gaps.** It checks out the PR in a sandbox and runs the repo's own suite
   under branch coverage. It intersects the result with the diff, giving the new or
   changed lines that no test executes, plus half-tested `if` statements whose other
   branch is never taken. This step is deterministic and uses no LLM.
2. **Writes a test for each gap** with NVIDIA Nemotron 3 on Nebius Token Factory. The
   prompt shows the function with numbered lines, marks the target lines, and includes
   the repo's existing test style. It starts with Nano and escalates to Super, then Ultra,
   only when a cheaper model's test fails verification.
3. **Keeps a test only if it is verified.** The test must pass and must provably execute
   the gap under coverage. For a partial branch it must take the branch the suite never
   took. A green test that touches nothing is rejected. A static lint also rejects tests
   with no real assertion or with undefined names, and asks the model once for a repair.
4. **Reports** every gap: closed (with the test, the model tier and the attempt number),
   or exhausted (with the reason each attempt failed).

Every repo command and every generated test runs inside a `bubblewrap` sandbox. The root
filesystem is read-only, `/tmp` is private, the host home directory and the Windows drives
are hidden, and API keys are scrubbed from the environment. Network is off except while
cloning and installing dependencies.

## How we use Nebius and NVIDIA

- **NVIDIA Nemotron 3 (Nano 30B, Super 120B, Ultra 550B)** writes the tests. The tiers
  form a cost ladder: in our post-fix eval, Nano closed 69% of generated gaps on the first
  attempt, and Super and Ultra handled the rest.
- **Nebius Token Factory** serves all three tiers through its OpenAI-compatible API. Every
  test-generation call at runtime goes there: about 460 calls in our evaluations, with no
  API errors. We disable Nemotron's reasoning mode with
  `chat_template_kwargs.enable_thinking=False`, so the token budget goes to the test.
- **What we did not use:** Nebius Sandboxes. We could not install its CLI (see our
  feedback), so isolation is local `bubblewrap`. Nebius is our inference provider only.

## Results

All numbers come from reports committed in `docs/evidence/`.

**Held-out repos.** These are 3 new repos with 23 gaps, run 3 times after the generator
fixes, for 69 gap-runs. Each repo uses a third-party package (python-dateutil, requests
or humanize), which the agent installs in the sandbox.

| | Result |
|---|---|
| Generated gaps closed | 88% (61/69) |
| Closed by Nano on attempt 1 | 52% |
| Rescued by Super or Ultra | 25 gaps |
| Exhausted | 8 gaps |

7 of the 8 exhausted gaps failed the same way: the test used a dataclass field,
constructor keyword or class name that the code does not define. The prompt shows only the function
under test, and those names are defined elsewhere in the file, so the model guessed.
Showing the definitions a function refers to is the next fix.

The same agent that fixed the generator also wrote these repos, so they are new code but
not an independent test.

**Seeded repos.** 4 repos, 29 gaps, 3 repeats, so 87 gap-runs per run.

| | Before our generator fixes | After (in-sample) |
|---|---|---|
| Generated gaps closed | 78% and 84% (runs A, B) | 100% (54/54, run C) |
| Closed by Nano on attempt 1 | 31% and 25% | 69% |

Runs A and B exposed two bugs in our own generator, not in the model:

- The model often used `pytest.raises` without importing `pytest`. We added an
  undefined-name lint that triggers a repair round.
- We asked for "lines 22-22" without showing line numbers. The context is now numbered.

Run C re-ran the same repos, so it is in-sample.

**Real public PRs.** We ran 4 merged PRs from sqlparse, boltons and more-itertools. All
four checked out, installed and ran green in the sandbox. All four had 0 gaps, because
merged PRs ship with tests. We then removed each PR's own tests: boltons #453 had 1 gap,
which Nano closed on its first attempt. The evidence from real repos is that one gap.

**How good are the verified tests?**

- **Mutation check:** the verified tests killed 67% of the mutants of the gap lines (99 of
  147). Loop gaps scored 90% and exception paths 50%.
- **Manual check:** in a random sample of 10 verified tests from the post-fix run, all 10
  assert a real value.
- **Lint precision:** we ran the lint on 2,204 passing human-written tests from real
  projects. It flagged 27 (1.2%). Of those, 7 really check nothing. The other 20 check
  through a helper function or a hand-written `raise AssertionError`; the lint misses
  both patterns.

## Limitations

- Runs on Linux or WSL2 only, with bubblewrap installed.
- Installs dependencies from `requirements.txt` only. Dependencies declared only in
  `pyproject.toml` are not installed; our held-out probe confirms this.
- "Verified" means the test passes, executes the gap and asserts something. It does not
  mean the test catches every bug: a third of the mutants survived.
- The held-out repos were written by the same agent that diagnosed and fixed the
  generator. They are new code, but not an independent test.

## Try it

See the README's Quick start. The offline demo needs no credentials: run
`cd files-c/section-c && python demo_pipeline.py`. To run against a public PR, from the
same directory:
`python cli.py --pr-url https://github.com/<owner>/<repo>/pull/<n> --install-deps`.
