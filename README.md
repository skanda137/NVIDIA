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
| Test generation with Nemotron on Nebius Token Factory (`files-c/section-b`) | In the repo; unit-tested with a fake LLM; live run pending |
| Orchestration, retry loop, report, CLI (`files-c/section-c`) | Works with the stub and with the generator driven by a fake LLM |
| Nebius sandbox | Client written, never run against Nebius |

## Quick start

Requires Python 3.10+ and git, on Linux, macOS or WSL. The local sandbox needs a POSIX
shell.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install pytest coverage openai
python -m pytest -q -p no:cacheprovider files-c
cd files-c/section-a && python demo.py
cd ../section-c && python demo_pipeline.py
```

The tests make no network calls. `demo_pipeline.py` is offline too: it creates a toy repo
with a half-tested PR, finds its 3 gaps, generates tests with the deterministic stub,
verifies them, including one real retry after a failing attempt, and prints the report.

Against your own repo, with Nemotron on Nebius Token Factory (the default `--generator llm`):

```bash
export TOKEN_FACTORY_API_KEY=...   # never commit it; see .env.example for all names
export TOKEN_FACTORY_BASE_URL=https://api.tokenfactory.nebius.com/v1/
export TOKEN_FACTORY_MODEL_NANO=... TOKEN_FACTORY_MODEL_SUPER=... TOKEN_FACTORY_MODEL_ULTRA=...
python scripts/check_token_factory.py   # lists Nemotron IDs and the tier picks
cd files-c/section-c
git -C /path/to/repo diff main...feature > /tmp/pr.diff
python cli.py --repo-url /path/to/repo --ref feature --diff-file /tmp/pr.diff \
    --changed-files app/billing.py
```

Offline, without credentials, add `--generator stub` (canned tests that only fit the demo
fixture). Generated tests run with `TOKEN_FACTORY_*`, `NEBIUS*` and any `*KEY*`, `*TOKEN*`
or `*SECRET*` variables removed from their environment.

`--sandbox local` (the default) runs generated code on your machine with **no isolation**.
Use it only on code you trust.

More detail: [files-c/README.md](files-c/README.md).
