# Held-out probe: dependency declared only in pyproject.toml (cfgload), 2026-10-24

Commit `0e7f46a` (tag `eval-heldout`). The repo `cfgload` declares PyYAML only in
`pyproject.toml`, not in `requirements.txt`. Command:

    python eval/run_eval.py --repos-dir ~/heldout-repos --dry-run

Result: the base suite fails at collection, so the run stops before any gap is found and
no LLM is called. The pipeline installs only `requirements.txt`, so `yaml` is missing in
the sandbox. This is the expected outcome and a known limitation; the pipeline was not
changed. The other three held-out repos were run from a directory that links only to
them (`~/heldout-reqs`), see `eval_2026-10-24_heldout.md`.

Output (last lines):

```
RuntimeError: test suite failed to run cleanly:
_______________________ ERROR collecting test_cfgload.py _______________________
ImportError while importing test module '.../cfgload-dry/repo/test_cfgload.py'.
test_cfgload.py:1: in <module>
    from cfgload import merge
cfgload.py:5: in <module>
    import yaml
E   ModuleNotFoundError: No module named 'yaml'
ERROR test_cfgload.py
1 error in 0.05s
```
