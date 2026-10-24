# Mutation check, 2026-10-24

Command: `python eval/mutation_check.py docs/evidence/eval_2026-10-24_runC.jsonl $HOME/work/mutation`  
Source: 87 verified gap-runs (each with its saved test; reused gaps use the earlier gap's test). No LLM calls. 54 s.

Killed = the verified test fails on the mutant. Survivors include **equivalent mutants** (e.g. `<` -> `<=` where the boundary value cannot occur), so the kill rate is a lower bound. This is a report only; nothing is gated on it.

- Baseline (test passes on unmutated code): 87/87
- Gap-runs with at least one mutation site: 60
- **Overall kill rate: 99/147 (67%)**

| category | gap-runs | mutants killed |
|---|---|---|
| branch | 12 | 18/24 (75%) |
| exception | 21 | 9/18 (50%) |
| exception+stateful | 3 | 3/12 (25%) |
| exit_arc | 3 | 3/6 (50%) |
| loop | 18 | 27/30 (90%) |
| stateful | 18 | 20/24 (83%) |
| third_party | 12 | 19/33 (58%) |

## Surviving mutants (48 total; first 5 distinct shown)

- inventory r1 inventory.py:22-22 [exception]: line 22: `qty > have` -> `qty >= have`
- inventory r1 inventory.py:31-36 [exception+stateful]: line 32: `if missing:` -> `if not missing:`
- inventory r1 inventory.py:31-36 [exception+stateful]: line 36: `return sum(order.values())` -> `return None`
- inventory r1 inventory.py:31-36 [exception+stateful]: line 36: `return sum(order.values())` -> `return 0`
- inventory r1 inventory.py:31-36 [exception+stateful]: line 31: `self.count(sku) < qty` -> `self.count(sku) <= qty`

## Baseline failures

None.
