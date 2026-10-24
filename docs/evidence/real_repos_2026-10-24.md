# Real public repos, 2026-10-24

Command: `python eval/run_real.py --max-calls 70 https://github.com/andialbrecht/sqlparse/pull/865 https://github.com/mahmoud/boltons/pull/453 https://github.com/more-itertools/more-itertools/pull/1309 https://github.com/more-itertools/more-itertools/pull/1305`  
Commit: `a3a2b5b (clean)`; generator.py sha256 `707adcbb0819`  
Models: nemotron-nano = `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, nemotron-super = `nvidia/nemotron-3-super-120b-a12b`, nemotron-ultra = `nvidia/Nemotron-3-Ultra-550b-a55b`  
Token Factory calls: 0 (cap 70); tokens in 0, out 0.  
PR metadata and diffs are cached in `docs/evidence/pr_cache/`.

| pr | checkout | deps | suite | gaps | closed | generated | reused | exhausted | failure | seconds |
|---|---|---|---|---|---|---|---|---|---|---|
| https://github.com/andialbrecht/sqlparse/pull/865 | ok | ok (no requirements.txt: pytest+coverage only) | green | 0 | 0 | 0 | 0 | 0 |  | 8.5 |
| https://github.com/mahmoud/boltons/pull/453 | ok | ok (no requirements.txt: pytest+coverage only) | green | 0 | 0 | 0 | 0 | 0 |  | 9.7 |
| https://github.com/more-itertools/more-itertools/pull/1309 | ok | ok (no requirements.txt: pytest+coverage only) | green | 0 | 0 | 0 | 0 | 0 |  | 26.2 |
| https://github.com/more-itertools/more-itertools/pull/1305 | ok | ok (no requirements.txt: pytest+coverage only) | green | 0 | 0 | 0 | 0 | 0 |  | 16.3 |

## Details

- https://github.com/andialbrecht/sqlparse/pull/865: head b4835c45; non-test .py files in diff: sqlparse/sql.py; full report: docs/evidence/real_andialbrecht_sqlparse_pull_865.md
- https://github.com/mahmoud/boltons/pull/453: head 8781b91a; non-test .py files in diff: boltons/statsutils.py; full report: docs/evidence/real_mahmoud_boltons_pull_453.md
- https://github.com/more-itertools/more-itertools/pull/1309: head 67fcf640; non-test .py files in diff: more_itertools/more.py; full report: docs/evidence/real_more_itertools_more_itertools_pull_1309.md
- https://github.com/more-itertools/more-itertools/pull/1305: head f89d7a33; non-test .py files in diff: more_itertools/more.py; full report: docs/evidence/real_more_itertools_more_itertools_pull_1305.md

## Token Factory calls by model

| model | calls | mean seconds | max seconds | mean tokens in / out |
|---|---|---|---|---|
