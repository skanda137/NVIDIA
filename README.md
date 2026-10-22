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
| Test generation with Nemotron on Nebius Token Factory (`files-c/section-b`) | Unit-tested with a fake LLM; live run on the demo fixture verified 3/3 gaps (2026-10-22) |
| Orchestration, retry loop, report, CLI (`files-c/section-c`) | Works with the stub and with the generator driven by a fake LLM |
| Sandbox (`bwrap`) | Read-only root, private `/tmp`, no network, host home and Windows drives hidden; tested |

## Quick start

Requires Python 3.10+, git and bubblewrap (`sudo apt install bubblewrap`), on Linux or
WSL2. Every repo and generated-test command runs inside `bwrap`.

```bash
python3 -m venv .venv && . .venv/bin/activate
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
git -C /path/to/repo diff main...feature > /tmp/pr.diff
python cli.py --repo-url /path/to/repo --ref feature --diff-file /tmp/pr.diff
```

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

More detail: [files-c/README.md](files-c/README.md).
