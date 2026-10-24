# Eval: repos in /home/skanda/heldout-reqs, 2026-10-24

Command: `python eval/run_eval.py --repos-dir /home/skanda/heldout-reqs --tag heldout --repeats 3`  
Commit: `0e7f46a (clean)`; generator.py sha256 `707adcbb0819`  
Models: nemotron-nano = `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, nemotron-super = `nvidia/nemotron-3-super-120b-a12b`, nemotron-ultra = `nvidia/Nemotron-3-Ultra-550b-a55b`  
Attempts per gap: 3 (nano, super, ultra); one lint-repair call allowed per attempt.  
Token Factory calls: 134 (cap 180); tokens in 107433, out 54079.

## Repo runs

| repo | repeat | result | gaps | seconds |
|---|---|---|---|---|
| ledger | 1 | ok | 7 | 45 |
| logscan | 1 | ok | 8 | 84 |
| ratefeed | 1 | ok | 8 | 93 |
| ledger | 2 | ok | 7 | 40 |
| logscan | 2 | ok | 8 | 101 |
| ratefeed | 2 | ok | 8 | 84 |
| ledger | 3 | ok | 7 | 46 |
| logscan | 3 | ok | 8 | 74 |
| ratefeed | 3 | ok | 8 | 80 |

## Headline

Each gap counted once per repeat. 'Generated' = the LLM was asked for a test for this gap; 'reused' = a test verified for an earlier gap in the same run also closes it (re-verified under coverage, no LLM call). 'Verified' means the test passes, executes the gap (takes its missing branch for partial branches), and lint found a non-constant assert. It does not mean the test would catch a bug in the gap.

| metric | value |
|---|---|
| gap-runs | 69 |
| final closed (generated + reused) | 61/69 (88%) |
| closed by reuse, no LLM call | 0/69 (0%) |
| generated gaps closed on attempt 1 (nano) | 36/69 (52%) |
| generated gaps rescued on attempt 2-3 (escalation) | 25/69 (36%) |
| generated gaps exhausted | 8/69 (12%) |
| closed with first success at nemotron-nano | 36 |
| closed with first success at nemotron-super | 20 |
| closed with first success at nemotron-ultra | 5 |
| mean LLM calls per generated gap | 1.94 |
| mean tokens in / out per generated gap | 1557 / 784 |
| mean seconds per generated gap | 9.0 |

## By category

| category | gap-runs | closed | attempt-1 closed (of generated) | reused | exhausted |
|---|---|---|---|---|---|
| unmarked | 69 | 61/69 (88%) | 36/69 (52%) | 0 | 8 |

## Exhausted gaps (8)

- ledger r1 `ledger.py:34-40 (load_entries)` [unmarked], tiers nemotron-nano/nemotron-super/nemotron-ultra: tly |         assert len(entries) == 2 | >       assert entries[0].dt == date(2023, 1, 1) |                ^^^^^^^^^^^^^ | E       AttributeError: 'Entry' object has no attribute 'dt' |  | _scratch_verify_test.py:25: AttributeError | =========================== short test summary info ============================ | FAILED _scratch_verify_test.py::test_load_entries_target_lines_executed - Att... | 1 failed in 0.02s | 
- ledger r1 `ledger.py:57-62 (add)` [unmarked], tiers nemotron-nano/nemotron-super/nemotron-ultra: cription="bad") |                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ | E       TypeError: Entry.__init__() got an unexpected keyword argument 'description' |  | _scratch_verify_test.py:12: TypeError | =========================== short test summary info ============================ | FAILED _scratch_verify_test.py::test_add_entry_type_and_zero_checks - TypeErr... | 1 failed in 0.02s | 
- ledger r1 `ledger.py:74-78 (monthly_totals)` [unmarked], tiers nemotron-nano/nemotron-super/nemotron-ultra:     Entry(when=date(2023, 2, 5), amount=Decimal("20.00"), type="expense", description="Rent"), |         ] | E       TypeError: Entry.__init__() got an unexpected keyword argument 'type' |  | _scratch_verify_test.py:10: TypeError | =========================== short test summary info ============================ | FAILED _scratch_verify_test.py::test_monthly_totals_returns_correct_aggregates | 1 failed in 0.01s | 
- ledger r2 `ledger.py:34-40 (load_entries)` [unmarked], tiers nemotron-nano/nemotron-super/nemotron-ultra: ========= short test summary info ============================ | FAILED _scratch_verify_test.py::test_load_entries_handles_valid_row - Attribu... | FAILED _scratch_verify_test.py::test_load_entries_skips_blank_line - Attribut... | FAILED _scratch_verify_test.py::test_load_entries_skips_whitespace_only_row | FAILED _scratch_verify_test.py::test_load_entries_missing_memo_defaults_to_empty | 4 failed in 0.04s | 
- ledger r2 `ledger.py:57-62 (add)` [unmarked], tiers nemotron-nano/nemotron-super/nemotron-ultra: rd argument 'when' |  | _scratch_verify_test.py:43: TypeError | =========================== short test summary info ============================ | FAILED _scratch_verify_test.py::test_add_rejects_non_decimal_amount - TypeErr... | FAILED _scratch_verify_test.py::test_add_rejects_zero_amount - TypeError: Led... | FAILED _scratch_verify_test.py::test_add_sorts_entries_by_when - TypeError: L... | 3 failed in 0.02s | 
- ledger r3 `ledger.py:34-40 (load_entries)` [unmarked], tiers nemotron-nano/nemotron-super/nemotron-ultra:         assert len(entries) == 2 | >       assert entries[0].dt == date(2023, 1, 1) |                ^^^^^^^^^^^^^ | E       AttributeError: 'Entry' object has no attribute 'dt' |  | _scratch_verify_test.py:26: AttributeError | =========================== short test summary info ============================ | FAILED _scratch_verify_test.py::test_load_entries_processes_rows_and_creates_entries | 1 failed in 0.02s | 
- logscan r3 `logscan.py:86-93 (read_new)` [unmarked], tiers nemotron-nano/nemotron-super/nemotron-ultra: .py:2: in <module> |     from logscan import LogFileScanner, parse_line | E   ImportError: cannot import name 'LogFileScanner' from 'logscan' (/tmp/vtga_eval_11hsb0cv/logscan-r3/repo/logscan.py) | =========================== short test summary info ============================ | ERROR _scratch_verify_test.py | !!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!! | 1 error in 0.06s | 
- ratefeed r3 `ratefeed.py:68-75 (get)` [unmarked], tiers nemotron-nano/nemotron-super/nemotron-ultra: _scratch_verify_test.py:2: in <module> |     from ratefeed import RateFeed | E   ImportError: cannot import name 'RateFeed' from 'ratefeed' (/tmp/vtga_eval_11hsb0cv/ratefeed-r3/repo/ratefeed.py) | =========================== short test summary info ============================ | ERROR _scratch_verify_test.py | !!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!! | 1 error in 0.09s | 
