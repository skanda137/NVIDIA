# Verified Test-Gap Agent — code layout

| Section | Folder | Owns | Status (2026-10-14) |
|---|---|---|---|
| 1 | `section-a/` | `models.py`, `find_gaps`, `verify_test`, sandbox clients | Audit fixes in; passes against real pytest + coverage locally. Nebius client never run. |
| 2 | `section-b/` | `generate_test` (Nemotron on Nebius Token Factory) | `generator.py` in place; unit tests use a fake LLM and block the network (`conftest.py`). Live run pending. |
| 3 | `section-c/` | `run_pipeline`, retry loop, report, CLI | Calls Section 2 by default; `--generator stub` for offline demos. |

`section-a/` is the single source of truth for Section 1 and `section-b/` for Section 2.
`section-b/_paths.py` and `section-c/_paths.py` (identical) put both on `sys.path`. Do not
copy files between folders.

## Run

Linux, macOS or WSL (the local sandbox needs a POSIX shell):

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install pytest coverage openai
python -m pytest -q -p no:cacheprovider files-c
cd files-c/section-a && python demo.py
cd ../section-c && python demo_pipeline.py
```

`demo_pipeline.py` builds a toy git repo and runs the whole loop: real `git clone`, real
pytest and coverage, gap finding, the retry loop, and the markdown report. It passes the
stub generator, so it needs no credentials.

To point it at a real repo, use `section-c/cli.py --help`. The default `--generator llm`
needs the `TOKEN_FACTORY_*` variables in `.env.example`; `--generator stub` is for offline
demos only. `--sandbox local` runs generated code on your machine with no isolation.
