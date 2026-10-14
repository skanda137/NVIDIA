# Verified Test-Gap Agent — code layout

| Section | Folder | Owns | Status (2026-10-14) |
|---|---|---|---|
| 1 | `section-a/` | `models.py`, `find_gaps`, `verify_test`, sandbox clients | Audit fixes in; passes against real pytest + coverage locally. Nebius client never run. |
| 2 | `section-b/` | `generate_test` (Nemotron) | **The `.py` files are 0 bytes.** The only `generate_test` is `section-c/generator_stub.py`. |
| 3 | `section-c/` | `run_pipeline`, retry loop, report, CLI | Works with the stub generator. |

`section-a/` is the single source of truth for Section 1. Section 3 imports it through
`section-c/_paths.py`, which puts `section-a/` on `sys.path`. Do not copy Section 1 files
into other folders.

## Run

Linux, macOS or WSL (the local sandbox needs a POSIX shell):

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install pytest coverage
cd files-c/section-a && python -m pytest -q test_section1.py && python demo.py
cd ../section-c && python demo_pipeline.py
```

`demo_pipeline.py` builds a toy git repo and runs the whole loop: real `git clone`, real
pytest and coverage, gap finding, the retry loop, and the markdown report. Only
`generate_test` is a stub.

To point it at a real repo, use `section-c/cli.py --help`. `--sandbox local` runs
generated code on your machine with no isolation.
