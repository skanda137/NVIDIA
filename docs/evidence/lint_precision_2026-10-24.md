# Lint precision on human-written tests, 2026-10-24

Command: `python eval/lint_precision.py $HOME/work/lint_repos`  
Rules: `generator._has_oracle` (oracle lint) and `generator._undefined_names`, unchanged. Every file here is from a suite that runs green, so every flag is a false positive (a valid human test the lint would reject).

- Files: 52; test functions: 2204
- Oracle-lint false positives: **27** test function(s)
- Undefined-name false positives: **0** name(s)

| file | test functions | oracle flags | undefined-name flags |
|---|---|---|---|
| seeded/inventory@base/test_inventory.py | 2 | 0 | 0 |
| seeded/inventory@pr/test_inventory.py | 3 | 0 | 0 |
| seeded/textkit@base/test_textkit.py | 1 | 0 | 0 |
| seeded/textkit@pr/test_textkit.py | 4 | 0 | 0 |
| seeded/weather@base/test_weather.py | 1 | 0 | 0 |
| seeded/weather@pr/test_weather.py | 2 | 0 | 0 |
| seeded/schedule@base/test_schedule.py | 1 | 0 | 0 |
| seeded/schedule@pr/test_schedule.py | 5 | 0 | 0 |
| seeded/billing@pr/test_billing.py | 1 | 0 | 0 |
| real/andialbrecht__sqlparse__865@b4835c45/tests/test_cli.py | 20 | 0 | 0 |
| real/andialbrecht__sqlparse__865@b4835c45/tests/test_dos_prevention.py | 7 | 0 | 0 |
| real/andialbrecht__sqlparse__865@b4835c45/tests/test_format.py | 61 | 1 | 0 |
| real/andialbrecht__sqlparse__865@b4835c45/tests/test_grouping.py | 61 | 0 | 0 |
| real/andialbrecht__sqlparse__865@b4835c45/tests/test_keywords.py | 1 | 0 | 0 |
| real/andialbrecht__sqlparse__865@b4835c45/tests/test_parse.py | 52 | 0 | 0 |
| real/andialbrecht__sqlparse__865@b4835c45/tests/test_regressions.py | 43 | 1 | 0 |
| real/andialbrecht__sqlparse__865@b4835c45/tests/test_split.py | 36 | 0 | 0 |
| real/andialbrecht__sqlparse__865@b4835c45/tests/test_tokenize.py | 26 | 0 | 0 |
| real/andialbrecht__sqlparse__865@b4835c45/tests/test_utils.py | 1 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_cacheutils.py | 17 | 1 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_debugutils_trace.py | 6 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_dictutils.py | 29 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_ecoutils.py | 2 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_fileutils.py | 8 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_formatutils.py | 5 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_funcutils.py | 8 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_funcutils_fb.py | 13 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_funcutils_fb_py3.py | 18 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_gcutils.py | 2 | 1 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_ioutils.py | 58 | 2 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_iterutils.py | 50 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_jsonutils.py | 4 | 1 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_listutils.py | 4 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_mathutils.py | 12 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_namedutils.py | 3 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_pathutils.py | 4 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_queueutils.py | 2 | 2 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_setutils.py | 9 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_socketutils.py | 11 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_statsutils.py | 2 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_statsutils_histogram.py | 2 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_strutils.py | 21 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_tableutils.py | 7 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_tbutils.py | 3 | 1 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_tbutils_parsed_exc.py | 5 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_timeutils.py | 10 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_typeutils.py | 3 | 0 | 0 |
| real/mahmoud__boltons__453@8781b91a/tests/test_urlutils.py | 31 | 1 | 0 |
| real/more-itertools__more-itertools__1305@f89d7a33/tests/test_more.py | 615 | 8 | 0 |
| real/more-itertools__more-itertools__1305@f89d7a33/tests/test_recipes.py | 148 | 0 | 0 |
| real/more-itertools__more-itertools__1309@67fcf640/tests/test_more.py | 616 | 8 | 0 |
| real/more-itertools__more-itertools__1309@67fcf640/tests/test_recipes.py | 148 | 0 | 0 |

## Oracle-lint false positives

By heuristic kind: check in a helper: 15; manual raise: 5; no check: smoke test that passes if nothing raises: 7. The smoke tests are arguably correct flags (they check nothing beyond not raising).

- `real/andialbrecht__sqlparse__865@b4835c45/tests/test_format.py` :: `test_format_right_margin` (no check: smoke test that passes if nothing raises)
- `real/andialbrecht__sqlparse__865@b4835c45/tests/test_regressions.py` :: `test_issue359_index_error_assignments` (no check: smoke test that passes if nothing raises)
- `real/mahmoud__boltons__453@8781b91a/tests/test_cacheutils.py` :: `test_lri_cache_eviction` (no check: smoke test that passes if nothing raises)
- `real/mahmoud__boltons__453@8781b91a/tests/test_gcutils.py` :: `test_toggle_gc_postcollect` (no check: smoke test that passes if nothing raises)
- `real/mahmoud__boltons__453@8781b91a/tests/test_ioutils.py` :: `test_truthy` (manual raise)
- `real/mahmoud__boltons__453@8781b91a/tests/test_ioutils.py` :: `test_instance_check` (manual raise)
- `real/mahmoud__boltons__453@8781b91a/tests/test_jsonutils.py` :: `test_reverse_iter_lines` (check in a helper)
- `real/mahmoud__boltons__453@8781b91a/tests/test_queueutils.py` :: `test_heap_queue` (check in a helper)
- `real/mahmoud__boltons__453@8781b91a/tests/test_queueutils.py` :: `test_sorted_queue` (check in a helper)
- `real/mahmoud__boltons__453@8781b91a/tests/test_tbutils.py` :: `test` (manual raise)
- `real/mahmoud__boltons__453@8781b91a/tests/test_urlutils.py` :: `test_url` (no check: smoke test that passes if nothing raises)
- `real/more-itertools__more-itertools__1305@f89d7a33/tests/test_more.py` :: `test_consumer` (no check: smoke test that passes if nothing raises)
- `real/more-itertools__more-itertools__1305@f89d7a33/tests/test_more.py` :: `test_0` (check in a helper)
- `real/more-itertools__more-itertools__1305@f89d7a33/tests/test_more.py` :: `test_1` (check in a helper)
- `real/more-itertools__more-itertools__1305@f89d7a33/tests/test_more.py` :: `test_4` (check in a helper)
- `real/more-itertools__more-itertools__1305@f89d7a33/tests/test_more.py` :: `test_5` (check in a helper)
- `real/more-itertools__more-itertools__1305@f89d7a33/tests/test_more.py` :: `test_6` (check in a helper)
- `real/more-itertools__more-itertools__1305@f89d7a33/tests/test_more.py` :: `test_7` (check in a helper)
- `real/more-itertools__more-itertools__1305@f89d7a33/tests/test_more.py` :: `test_serialize_generator_methods_locking` (manual raise)
- `real/more-itertools__more-itertools__1309@67fcf640/tests/test_more.py` :: `test_consumer` (no check: smoke test that passes if nothing raises)
- `real/more-itertools__more-itertools__1309@67fcf640/tests/test_more.py` :: `test_0` (check in a helper)
- `real/more-itertools__more-itertools__1309@67fcf640/tests/test_more.py` :: `test_1` (check in a helper)
- `real/more-itertools__more-itertools__1309@67fcf640/tests/test_more.py` :: `test_4` (check in a helper)
- `real/more-itertools__more-itertools__1309@67fcf640/tests/test_more.py` :: `test_5` (check in a helper)
- `real/more-itertools__more-itertools__1309@67fcf640/tests/test_more.py` :: `test_6` (check in a helper)
- `real/more-itertools__more-itertools__1309@67fcf640/tests/test_more.py` :: `test_7` (check in a helper)
- `real/more-itertools__more-itertools__1309@67fcf640/tests/test_more.py` :: `test_serialize_generator_methods_locking` (manual raise)

## Undefined-name false positives

None.
