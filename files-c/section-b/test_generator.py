from pathlib import Path

import openai
import pytest

import generator as g
import models
from conftest import NetworkBlocked
from models import CandidateTest, Gap

SOURCE = '''"""Pricing."""
import math


def other():
    return 1


def apply_discount(price, code):
    if code == 'VIP':
        return price * 0.8
    return price
'''

GAP = Gap(file="src/shop/pricing.py", start_line=10, end_line=11,
          function_context="apply_discount", reason="partial_branch", missing_branches=("10:11",))

GOOD = """```python
from src.shop.pricing import apply_discount

def test_vip_discount():
    assert apply_discount(100, 'VIP') == 80
```"""


@pytest.fixture
def tiers(monkeypatch):
    monkeypatch.setenv("TOKEN_FACTORY_MODEL_NANO", "fake/nemotron-nano")
    monkeypatch.setenv("TOKEN_FACTORY_MODEL_SUPER", "fake/nemotron-super")
    monkeypatch.setenv("TOKEN_FACTORY_MODEL_ULTRA", "fake/nemotron-ultra")


class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, model, messages, temperature):
        self.calls.append((model, messages, temperature))
        return self.replies.pop(0)


def user_prompt(llm):
    return llm.calls[0][1][1]["content"]


def test_uses_section1_types_without_fallback():
    assert g.CandidateTest is models.CandidateTest and g.Gap is models.Gap
    assert "except ImportError" not in Path(g.__file__).read_text()


def test_tier_escalation(tiers):
    assert g.tier_for_attempt(1) == ("nemotron-nano", "fake/nemotron-nano")
    assert g.tier_for_attempt(2) == ("nemotron-super", "fake/nemotron-super")
    assert g.tier_for_attempt(3) == ("nemotron-ultra", "fake/nemotron-ultra")
    assert g.tier_for_attempt(9) == ("nemotron-ultra", "fake/nemotron-ultra")


def test_unset_tier_env_raises(monkeypatch):
    monkeypatch.setenv("TOKEN_FACTORY_MODEL_NANO", "fake/nemotron-nano")
    assert g.tier_for_attempt(1)[1] == "fake/nemotron-nano"
    with pytest.raises(RuntimeError, match="TOKEN_FACTORY_MODEL_SUPER"):
        g.tier_for_attempt(2)
    with pytest.raises(RuntimeError, match="TOKEN_FACTORY_MODEL_ULTRA"):
        g.generate_test(GAP, [], attempt=3, source=SOURCE, llm=FakeLLM(GOOD))


def test_missing_env_lists_only_what_the_attempts_need(monkeypatch):
    assert g.missing_env(1) == ["TOKEN_FACTORY_API_KEY", "TOKEN_FACTORY_BASE_URL", "TOKEN_FACTORY_MODEL_NANO"]
    for v in ("TOKEN_FACTORY_API_KEY", "TOKEN_FACTORY_BASE_URL", "TOKEN_FACTORY_MODEL_NANO"):
        monkeypatch.setenv(v, "x")
    assert g.missing_env(1) == []
    assert g.missing_env(5) == ["TOKEN_FACTORY_MODEL_SUPER", "TOKEN_FACTORY_MODEL_ULTRA"]


def test_happy_path_returns_section1_candidate_type(tiers):
    llm = FakeLLM(GOOD)
    out = g.generate_test(GAP, ["def test_x(): pass"], source=SOURCE, llm=llm)
    assert isinstance(out, CandidateTest)
    assert out.target_gap is GAP
    assert "def test_vip_discount" in out.code
    assert out.model_tier_used == "nemotron-nano"
    assert out.attempt_number == 1
    assert len(llm.calls) == 1
    assert llm.calls[0][0] == "fake/nemotron-nano"


def test_prompt_contains_real_function_source_not_just_name(tiers):
    llm = FakeLLM(GOOD)
    g.generate_test(GAP, [], source=SOURCE, llm=llm)
    p = user_prompt(llm)
    assert "from shop.pricing import <name>" in p  # src/ layout: package is `shop`
    assert "10-11" in p
    assert "OTHER side" in p
    assert "return price * 0.8" in p       # real body shown
    assert "def other" not in p            # not the neighbouring function


def test_partial_branch_prompt_has_missing_branch_hints_in_words(tiers):
    gap = Gap("src/shop/pricing.py", 10, 10, "apply_discount", "partial_branch",
              missing_branches=("5:8", "10:exit"))
    llm = FakeLLM(GOOD)
    g.generate_test(gap, [], source=SOURCE, llm=llm)
    p = user_prompt(llm)
    assert "the branch from line 5 to line 8 is never taken; choose inputs that take it" in p
    assert "the branch from line 10 to the function exit is never taken" in p
    assert "finish without entering the block" in p


def test_uncovered_prompt_has_no_branch_hint(tiers):
    llm = FakeLLM(GOOD)
    g.generate_test(Gap("m.py", 2, 2, "", "uncovered"), [], source=SOURCE, llm=llm)
    assert "is never taken" not in user_prompt(llm)


def test_system_prompt_asks_for_exactly_one_test_function():
    assert "Write exactly one test function" in g.SYSTEM_PROMPT
    assert "only the first test_*" not in g.SYSTEM_PROMPT


def test_module_level_gap_uses_line_window(tiers):
    gap = Gap("m.py", 2, 2, "", "uncovered")
    llm = FakeLLM(GOOD)
    g.generate_test(gap, [], source=SOURCE, llm=llm)
    assert "import math" in user_prompt(llm)


def test_without_source_degrades_gracefully(tiers):
    llm = FakeLLM(GOOD)
    g.generate_test(GAP, [], llm=llm)
    assert "apply_discount" in user_prompt(llm)


def test_dict_gap_still_supported(tiers):
    d = dict(file="a.py", start_line=1, end_line=1, function_context="f", reason="uncovered")
    llm = FakeLLM(GOOD)
    g.generate_test(d, [], llm=llm)
    assert "a.py" in user_prompt(llm)


def test_prior_failure_is_fed_back_and_tier_escalates(tiers):
    llm = FakeLLM(GOOD)
    out = g.generate_test(GAP, [], attempt=2, prior_failure="AssertionError: 80.0 != 81",
                          source=SOURCE, llm=llm)
    p = user_prompt(llm)
    assert "AssertionError: 80.0 != 81" in p
    assert "attempt 2" in p
    assert out.model_tier_used == "nemotron-super"
    assert llm.calls[0][0] == "fake/nemotron-super"
    assert llm.calls[0][2] > 0.2


def test_think_blocks_and_prose_stripped():
    raw = "<think>hmm</think>Sure!\n" + GOOD + "\nHope it helps"
    assert g.extract_code(raw).startswith("from src.shop")


def test_unterminated_fence():
    assert "def test_a" in g.extract_code("```python\ndef test_a():\n    assert 1")


def test_lint_flags_problems():
    assert g.lint_candidate("def test_a(:\n")[0].startswith("SyntaxError")
    assert "no function" in g.lint_candidate("x = 1")[0]
    assert any("subprocess" in p for p in g.lint_candidate("import subprocess\ndef test_a(): pass"))
    assert g.lint_candidate("def test_a():\n    assert True") == []


@pytest.mark.parametrize("body", [
    "    assert f() == 1",
    "    with pytest.raises(ValueError):\n        f()",
    "    self.assertEqual(f(), 1)",
    "    m.assert_called_once_with(1)",
])
def test_lint_accepts_any_oracle(body):
    assert g.lint_candidate(f"def test_a():\n{body}") == []


def test_lint_rejects_test_without_oracle():
    problems = g.lint_candidate("def test_a():\n    f(1)\n\ndef test_b():\n    assert f(2)")
    assert problems == ["test_a has no assert or pytest.raises: it checks nothing"]


def test_module_path_hint():
    assert g.module_path_from_file("app/billing.py") == "app.billing"
    assert g.module_path_from_file("src/pkg/mod.py") == "pkg.mod"
    assert g.module_path_from_file("./pkg/__init__.py") == "pkg"
    assert g.module_path_from_file("billing.py") == "billing"


def test_thinking_disabled_on_every_call(monkeypatch):
    sent = {}

    class Completions:
        def create(self, **kw):
            sent.update(kw)
            msg = type("M", (), {"content": "ok"})
            return type("R", (), {"choices": [type("C", (), {"message": msg})]})

    client = type("Client", (), {"chat": type("Chat", (), {"completions": Completions()})})
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "k")
    monkeypatch.setenv("TOKEN_FACTORY_BASE_URL", "https://example.invalid/v1/")
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: client)
    assert g.token_factory_llm("m", [], 0.2) == "ok"
    assert sent["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert "detailed thinking" not in g.SYSTEM_PROMPT


def test_repair_round_runs_once_on_bad_output(tiers):
    llm = FakeLLM("```python\nx = 1\n```", GOOD)
    out = g.generate_test(GAP, [], source=SOURCE, llm=llm)
    assert len(llm.calls) == 2
    assert "def test_vip_discount" in out.code
    assert "problems" in llm.calls[1][1][-1]["content"]


def test_still_bad_after_repair_raises_value_error(tiers):
    bad = "```python\nimport subprocess\ndef test_a():\n    subprocess.run('ls')\n```"
    llm = FakeLLM(bad, bad)
    with pytest.raises(ValueError) as exc:
        g.generate_test(GAP, [], source=SOURCE, llm=llm)
    assert len(llm.calls) == 2
    assert any("subprocess" in p for p in exc.value.args[0])
    assert isinstance(exc.value, g.CandidateRejected)
    assert exc.value.tier == "nemotron-nano" and "import subprocess" in exc.value.code


def test_examples_are_capped():
    exs = ["def test_%d(): pass" % i for i in range(10)]
    msgs = g.build_messages(GAP, exs, source=SOURCE)
    assert msgs[1]["content"].count("--- example test") == g.MAX_EXAMPLES


def test_discover_by_keyword_takes_largest():
    ids = ["meta-llama/Llama-3.3-70B", "nvidia/Llama-3_1-Nemotron-Ultra-253B-v1",
           "nvidia/Llama-3_3-Nemotron-Super-49B-v1", "nvidia/Nemotron-Nano-9B-v2", "nvidia/Nemotron-Nano-12B-v2"]
    d = g.discover_tier_models(ids)
    assert d["nemotron-ultra"].endswith("Ultra-253B-v1")
    assert d["nemotron-super"].endswith("Super-49B-v1")
    assert d["nemotron-nano"].endswith("Nano-12B-v2")  # biggest of the nanos


def test_discover_leaves_tier_without_keyword_out():
    d = g.discover_tier_models(["x/nemotron-4b", "x/nemotron-nano-30b", "x/nemotron-340b", "x/other"])
    assert d == {"nemotron-nano": "x/nemotron-nano-30b"}


def test_provider_is_token_factory_only(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "k2")
    with pytest.raises(RuntimeError, match="TOKEN_FACTORY_API_KEY"):
        g._provider()
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "k")
    with pytest.raises(RuntimeError, match="TOKEN_FACTORY_BASE_URL"):
        g._provider()
    monkeypatch.setenv("TOKEN_FACTORY_BASE_URL", "https://example.invalid/v1/")
    assert g._provider() == ("k", "https://example.invalid/v1/")


def test_conftest_blocks_client_construction(monkeypatch):
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "k")
    monkeypatch.setenv("TOKEN_FACTORY_BASE_URL", "https://example.invalid/v1/")
    with pytest.raises(NetworkBlocked):
        g._client()
