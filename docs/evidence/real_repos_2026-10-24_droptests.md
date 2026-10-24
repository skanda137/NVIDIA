# Real public repos, PR test changes dropped (constructed scenario), 2026-10-24

Command: `python eval/run_real.py --drop-pr-tests --max-calls 70 https://github.com/andialbrecht/sqlparse/pull/865 https://github.com/mahmoud/boltons/pull/453 https://github.com/more-itertools/more-itertools/pull/1309 https://github.com/more-itertools/more-itertools/pull/1305`  
Commit: `a2a57a0 (clean)`; generator.py sha256 `707adcbb0819`  
Models: nemotron-nano = `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, nemotron-super = `nvidia/nemotron-3-super-120b-a12b`, nemotron-ultra = `nvidia/Nemotron-3-Ultra-550b-a55b`  
Token Factory calls: 1 (cap 70); tokens in 2620, out 210.  
PR metadata and diffs are cached in `docs/evidence/pr_cache/`.

| pr | checkout | deps | suite | gaps | closed | generated | reused | exhausted | failure | seconds |
|---|---|---|---|---|---|---|---|---|---|---|
| https://github.com/andialbrecht/sqlparse/pull/865 | ok | ok (no requirements.txt: pytest+coverage only) | green | 0 | 0 | 0 | 0 | 0 |  | 5.6 |
| https://github.com/mahmoud/boltons/pull/453 | ok | ok (no requirements.txt: pytest+coverage only) | green | 1 | 1 | 1 | 0 | 0 |  | 10.5 |
| https://github.com/more-itertools/more-itertools/pull/1309 | ok | ok (no requirements.txt: pytest+coverage only) | green | 0 | 0 | 0 | 0 | 0 |  | 13.4 |
| https://github.com/more-itertools/more-itertools/pull/1305 | ok | ok (no requirements.txt: pytest+coverage only) | green | 0 | 0 | 0 | 0 | 0 |  | 16.2 |

## Details

- https://github.com/andialbrecht/sqlparse/pull/865: head b4835c45; non-test .py files in diff: sqlparse/sql.py; PR test changes dropped (1 file(s)), commit fbcde48b; full report: docs/evidence/real_andialbrecht_sqlparse_pull_865_droptests.md
- https://github.com/mahmoud/boltons/pull/453: head 8781b91a; non-test .py files in diff: boltons/statsutils.py; PR test changes dropped (1 file(s)), commit f1c877db; full report: docs/evidence/real_mahmoud_boltons_pull_453_droptests.md
- https://github.com/more-itertools/more-itertools/pull/1309: head 67fcf640; non-test .py files in diff: more_itertools/more.py; PR test changes dropped (1 file(s)), commit 21bee8aa; full report: docs/evidence/real_more_itertools_more_itertools_pull_1309_droptests.md
- https://github.com/more-itertools/more-itertools/pull/1305: head f89d7a33; non-test .py files in diff: more_itertools/more.py; PR test changes dropped (1 file(s)), commit 199f858b; full report: docs/evidence/real_more_itertools_more_itertools_pull_1305_droptests.md

## Token Factory calls by model

| model | calls | mean seconds | max seconds | mean tokens in / out |
|---|---|---|---|---|
| `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | 1 | 3.0 | 3.0 | 2620 / 210 |
