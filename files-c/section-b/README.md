# Section B — Test generation (Nemotron on Nebius Token Factory)

```python
def generate_test(gap: Gap, example_tests: list[str], attempt: int = 1,
                  prior_failure: str | None = None, *, source: str | None = None,
                  llm=None) -> CandidateTest
```

`Gap` and `CandidateTest` come from Section A's `models.py` through `_paths.py`
(identical to `section-c/_paths.py`); there is no fallback copy.

- **Provider:** Nebius Token Factory only, via the `openai` SDK. Needs
  `TOKEN_FACTORY_API_KEY` and `TOKEN_FACTORY_BASE_URL`; raises if either is unset.
- **Tiers:** attempt 1 uses `TOKEN_FACTORY_MODEL_NANO`, attempt 2 `_SUPER`, attempt 3+
  `_ULTRA`. No model ID is hardcoded; an unset tier variable raises.
  `scripts/check_token_factory.py` picks the IDs from the live `/models` list with
  `discover_tier_models` (keyword match only).
- **Prompt:** the enclosing function's source (from `source`, which Section C reads from
  the sandbox), up to 3 example tests from the repo, `prior_failure` verbatim on retries,
  and for `partial_branch` gaps each `Gap.missing_branches` entry in words.
- **Thinking:** off on every call via `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`.
  Nemotron 3 on Token Factory ignores system-prompt toggles; checked live on all three tiers.
- **Output:** `<think>` blocks and prose stripped, the fenced code extracted, then linted
  (syntax, a `test_*` function that asserts something (`assert`, `pytest.raises`, `assert*`
  calls), no subprocess/socket/requests/urllib/eval/exec/... ).
  One repair round; if the code still fails lint, `CandidateRejected` (a `ValueError`)
  is raised and Section C records the attempt as failed.
- **Tests:** `python -m pytest -q -p no:cacheprovider files-c/section-b`. `conftest.py`
  clears `TOKEN_FACTORY_*` and makes the OpenAI client constructor raise, so no unit
  test can reach the network.

`section-c/generator_stub.py` keeps the same signature for offline demos
(`demo_pipeline.py`, `cli.py --generator stub`).
