# Verified Test-Gap Agent

Given a pull request, this finds the new or changed lines that no test executes, has an
LLM write a test for each one, and keeps a test only if it **passes and provably executes
the gap**. Each test is run in a sandbox under branch coverage. For a half-tested `if`,
the test must take the branch the existing suite never took. A green test that touches
nothing is rejected.

Built for the Nebius x NVIDIA Global AI Hackathon (Coding & Agentic Engineering track).

## Status

| Part | State |
|---|---|
| Gap finding + verification (`files-c/section-a`) | Real pytest + coverage; seeded repos and 4 real public repos (see [Results](#results)) |
| Test generation with Nemotron on Nebius Token Factory (`files-c/section-b`) | Live eval: 3 runs over 87 gap-runs each, plus real repos (see [Results](#results)) |
| Orchestration, retry loop, report, CLI (`files-c/section-c`) | `--pr-url`, `--base-ref` and `--diff-file` run live from a fresh clone |
| Sandbox (`bwrap`) | Read-only root, private `/tmp`, no network, host home and Windows drives hidden; tested |

## Quick start

Platform requirements:

- Linux or WSL2 (the sandbox uses Linux user namespaces). Tested on WSL2 Ubuntu with
  Python 3.14.4, git 2.53, bubblewrap 0.11.1.
- Python 3.10+ with `venv`, git and bubblewrap. On Debian/Ubuntu:
  `sudo apt install python3-venv git bubblewrap`. Without `python3-venv`,
  `python3 -m venv` fails with "ensurepip is not available".
- Create the venv under your home directory, as below. The sandbox hides `/tmp` and the
  Windows drives (`/mnt/c`, ...) and re-exposes only a venv under `$HOME`. A `.venv`
  inside a clone under `/tmp` or `/mnt/c` makes every test run fail with
  `.venv/bin/python: not found`.

Every repo and generated-test command runs inside `bwrap`.

```bash
python3 -m venv ~/.venvs/vtga && . ~/.venvs/vtga/bin/activate
pip install -r requirements.txt
python -m pytest -q -p no:cacheprovider files-c
cd files-c/section-a && python demo.py
cd ../section-c && python demo_pipeline.py
```

The tests make no network calls. `demo_pipeline.py` is offline too: it creates a toy repo
with a half-tested PR, finds its 3 gaps, generates tests with the deterministic stub,
verifies them, including one real retry after a failing attempt, and prints the report.

Against your own repo, with Nemotron on Nebius Token Factory (the default `--generator llm`):

```bash
cp .env.example .env                    # then fill in the key; .env is gitignored
python scripts/check_token_factory.py   # lists Nemotron IDs and the tier picks
cd files-c/section-c
python cli.py --pr-url https://github.com/<owner>/<repo>/pull/<n>        # public GitHub PR
python cli.py --repo-url /path/to/repo --ref feature --base-ref main      # any git repo
```

`--pr-url` takes the head SHA, clone URL and diff from the GitHub REST API (public repos,
no auth). `--base-ref` diffs `main...feature` inside the sandbox's clone. `--diff-file`
still accepts a saved unified diff.

`cli.py` and `check_token_factory.py` read the `TOKEN_FACTORY_*` lines of the repo-root
`.env`; variables already exported win. Thinking is switched off on every call
(`chat_template_kwargs.enable_thinking=False`): Nemotron 3 ignores system-prompt toggles,
and its reasoning would otherwise eat the token budget. The analysed files default to the
non-test `.py` files in the diff (`--changed-files` overrides), and at most `--max-gaps`
(10) gaps may call the LLM. A test verified for one gap is re-run against later gaps
before any new test is generated.

Offline, without credentials, add `--generator stub` (canned tests that only fit the demo
fixture). Generated tests run with `TOKEN_FACTORY_*`, `NEBIUS*` and any `*KEY*`, `*TOKEN*`
or `*SECRET*` variables removed from their environment.

Inside the sandbox the root filesystem is read-only, `/tmp` is private, `$HOME` and the
Windows drives (`/mnt/c`, where `.env` lives) are empty, and there is no network. Only the
`--sandbox-cwd` workdir is writable and persists. Network is on for exactly two steps:
cloning the repo and `--install-deps`, which pip-installs into the workdir, not your venv.

## Results

Every number below comes from a report in [docs/evidence](docs/evidence). Nemotron 3
on Nebius Token Factory, 3 attempts per gap (Nano, then Super, then Ultra), one
lint-repair call allowed per attempt. "Generated" counts gaps the LLM wrote a test for;
gaps closed by reusing a test written for an earlier gap are counted apart. Reuse
mostly reflects coverage reporting an `if` and its body as two gaps.

### Seeded repos: 4 repos, 29 gaps, 3 repeats (87 gap-runs per run)

| | Run A, pre-fix | Run B, pre-fix | Run C, post-fix (in-sample) |
|---|---|---|---|
| Generated gaps closed | 46/59 (78%) | 47/56 (84%) | 54/54 (100%) |
| Closed on attempt 1 (Nano) | 18/59 (31%) | 14/56 (25%) | 37/54 (69%) |
| Closed after escalation (Super / Ultra) | 28 (26 / 2) | 33 (28 / 5) | 17 (15 / 2) |
| Exhausted | 13 (22%) | 9 (16%) | 0 |
| Closed by reuse, no LLM call | 28 | 31 | 33 |
| Token Factory calls | 117 | 114 | 90 |

Runs A and B found two defects in our generator. The model often used `pytest.raises`
without `import pytest`, and the prompt asked for "target lines 22-22" without showing
line numbers. Both are fixed: an undefined-name lint now feeds the repair round, and the
context lines are numbered. Run C reruns the same repos the fixes were found on, so its
numbers are in-sample, not the rate on unseen code. A held-out run has not been done.
Reports: [run A](docs/evidence/eval_2026-10-23_runA.md),
[run B](docs/evidence/eval_2026-10-24_runB.md), [run C](docs/evidence/eval_2026-10-24_runC.md).

### Real public repos

On 4 merged PRs (sqlparse #865, boltons #453, more-itertools #1309 and #1305), every
repo checked out, installed and ran its suite green in the sandbox. #1305 comes from a
deleted fork and checks out via `pull/1305/head`. All four had **0 gaps**: merged PRs
arrive with tests. In a constructed scenario, we removed each PR's own test changes. 3
PRs still had 0 gaps, because older tests already run the changed lines. boltons #453
had 1 gap, which Nano closed on attempt 1. That is a single real gap, n=1.
Reports: [as merged](docs/evidence/real_repos_2026-10-24.md),
[PR tests dropped](docs/evidence/real_repos_2026-10-24_droptests.md).

### How strong are the verified tests?

- **Mutation check, run C:** 99/147 mutants of the gap lines were killed (67%). Loop
  gaps scored 90% and exception paths 50%; exception tests tend to check the exception
  type, not the resulting state or return value. Survivors include equivalent mutants.
  [Report](docs/evidence/mutation_2026-10-24_runC.md).
- **Manual sample:** of 10 random verified tests per run, 9/10 (run B) and 10/10
  (run C) check a value (a comparison, `pytest.raises` or a mock assertion).
  [B](docs/evidence/verified_sample_2026-10-24_runB.md),
  [C](docs/evidence/verified_sample_2026-10-24_runC.md).
- **Lint precision on 2204 human-written passing tests:** the undefined-name rule
  flagged 0. The oracle rule flagged 27 (1.2%): 15 delegate their check to a helper, 5
  raise `AssertionError` by hand, 7 are smoke tests that check nothing.
  [Report](docs/evidence/lint_precision_2026-10-24.md).

## Limitations

- Linux or WSL2 with bubblewrap only. The venv must live under `$HOME`.
- Public GitHub repos only for `--pr-url`; the GitHub API is called without auth (60
  requests per hour). Diffs for the demo PRs are cached in `docs/evidence/pr_cache/`.
- Dependencies from `requirements.txt` are tested (requests, python-dateutil in the
  seeded repos). Dependencies declared only in `pyproject.toml` are untested; the real
  repos above have no runtime dependencies.
- "Verified" means the test passes, executes the gap (takes the missing branch, for a
  partial branch) and has a non-constant assert. It does not mean the test catches every
  bug: a third of mutants survive (see the mutation check).
- The post-fix eval is in-sample and no held-out eval has been run. Real-repo evidence
  for test generation is one gap.
- The oracle lint would reject human tests that check through a helper function or a
  hand-written `raise AssertionError` (20 of 2204 in the lint-precision run).

More detail: [files-c/README.md](files-c/README.md).
