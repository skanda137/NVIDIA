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
| Gap finding + verification (`files-c/section-a`) | Works against real pytest + coverage on toy repos |
| Test generation with Nemotron (`files-c/section-b`) | **Not in the repo yet**; a deterministic stub stands in |
| Orchestration, retry loop, report, CLI (`files-c/section-c`) | Works with the stub |
| Nebius sandbox | Client written, never run against Nebius |

## Quick start

Requires Python 3.10+ and git, on Linux, macOS or WSL. The local sandbox needs a POSIX
shell.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install pytest coverage
cd files-c/section-a && python -m pytest -q test_section1.py && python demo.py
cd ../section-c && python demo_pipeline.py
```

`demo_pipeline.py` creates a toy repo with a half-tested PR, finds its 3 gaps, generates
tests (stub), verifies them, including one real retry after a failing attempt, and prints
the report.

Against your own repo:

```bash
cd files-c/section-c
git -C /path/to/repo diff main...feature > /tmp/pr.diff
python cli.py --repo-url /path/to/repo --ref feature --diff-file /tmp/pr.diff \
    --changed-files app/billing.py
```

`--sandbox local` (the default) runs generated code on your machine with **no isolation**.
Use it only on code you trust.

More detail: [files-c/README.md](files-c/README.md).
