# Held-out repos

`build_heldout.py` builds the four repos used for the held-out eval
(`docs/evidence/eval_2026-10-24_heldout.md`) under `~/heldout-repos/`. Commit authors and
dates are fixed, so the commit SHAs are the same on every build. The script refuses to
overwrite an existing repo.

| repo | new code in head | dependency |
|---|---|---|
| ledger | CSV load/save, a `Ledger` class, `next_due` | python-dateutil, in requirements.txt |
| ratefeed | HTTP fetch (injectable), parsing, a TTL cache, JSON save/load | requests, in requirements.txt |
| logscan | log reading, filtering, regex search, a tail reader | humanize, in requirements.txt |
| cfgload | YAML load/dump, env overrides, dotted lookup | PyYAML, **only in pyproject.toml** (probe) |

Each repo has two commits. The base commit has library code and a passing suite; the head
commit adds 6-8 functions or methods and no tests. The eval treats base..head as the PR.

**Not independent.** The same agent that diagnosed and fixed the generator after runs A
and B wrote these repos. It is new code the generator was never tuned on, but its author
knew the failure classes.

To reproduce the run (`cfgload` stops the harness, so the other three are linked into a
separate directory):

    python3 eval/heldout/build_heldout.py
    mkdir ~/heldout-reqs && for r in ledger logscan ratefeed; do ln -s ~/heldout-repos/$r ~/heldout-reqs/$r; done
    ~/.venvs/vtga/bin/python eval/run_eval.py --repos-dir ~/heldout-reqs --tag heldout --repeats 3
