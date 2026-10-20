import generator as g
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
          function_context="apply_discount", reason="partial_branch")

GOOD = """```python
from src.shop.pricing import apply_discount

def test_vip_discount():
    assert apply_discount(100, 'VIP') == 80
```"""


class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, model, messages, temperature):
        self.calls.append((model, messages, temperature))
        return self.replies.pop(0)


def user_prompt(llm):
    return llm.calls[0][1][1]["content"]


def test_tier_escalation():
    assert g.tier_for_attempt(1)[0] == "nemotron-nano"
    assert g.tier_for_attempt(2)[0] == "nemotron-super"
    assert g.tier_for_attempt(3)[0] == "nemotron-ultra"
    assert g.tier_for_attempt(9)[0] == "nemotron-ultra"


def test_happy_path_returns_section1_candidate_type():
    llm = FakeLLM(GOOD)
    out = g.generate_test(GAP, ["def test_x(): pass"], source=SOURCE, llm=llm)
    assert isinstance(out, CandidateTest)
    assert out.target_gap is GAP
    assert "def test_vip_discount" in out.code
    assert out.model_tier_used == "nemotron-nano"
    assert out.attempt_number == 1
    assert len(llm.calls) == 1


def test_prompt_contains_real_function_source_not_just_name():
    llm = FakeLLM(GOOD)
    g.generate_test(GAP, [], source=SOURCE, llm=llm)
    p = user_prompt(llm)
    assert "src.shop.pricing" in p
    assert "10-11" in p
    assert "OTHER side" in p
    assert "return price * 0.8" in p       # real body shown
    assert "def other" not in p            # not the neighbouring function


def test_module_level_gap_uses_line_window():
    gap = Gap("m.py", 2, 2, "", "uncovered")
    llm = FakeLLM(GOOD)
    g.generate_test(gap, [], source=SOURCE, llm=llm)
    assert "import math" in user_prompt(llm)


def test_without_source_degrades_gracefully():
    llm = FakeLLM(GOOD)
    g.generate_test(GAP, [], llm=llm)
    assert "apply_discount" in user_prompt(llm)


def test_dict_gap_still_supported():
    d = dict(file="a.py", start_line=1, end_line=1, function_context="f", reason="uncovered")
    llm = FakeLLM(GOOD)
    g.generate_test(d, [], llm=llm)
    assert "a.py" in user_prompt(llm)


def test_prior_failure_is_fed_back_and_tier_escalates():
    llm = FakeLLM(GOOD)
    out = g.generate_test(GAP, [], attempt=2, prior_failure="AssertionError: 80.0 != 81",
                          source=SOURCE, llm=llm)
    p = user_prompt(llm)
    assert "AssertionError: 80.0 != 81" in p
    assert "attempt 2" in p
    assert out.model_tier_used == "nemotron-super"
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


def test_repair_round_runs_once_on_bad_output():
    llm = FakeLLM("```python\nx = 1\n```", GOOD)
    out = g.generate_test(GAP, [], source=SOURCE, llm=llm)
    assert len(llm.calls) == 2
    assert "def test_vip_discount" in out.code
    assert "problems" in llm.calls[1][1][-1]["content"]


def test_examples_are_capped():
    exs = ["def test_%d(): pass" % i for i in range(10)]
    msgs = g.build_messages(GAP, exs, source=SOURCE)
    assert msgs[1]["content"].count("--- example test") == g.MAX_EXAMPLES


def test_discover_by_keyword_and_size():
    ids = ["meta-llama/Llama-3.3-70B", "nvidia/Llama-3_1-Nemotron-Ultra-253B-v1",
           "nvidia/Llama-3_3-Nemotron-Super-49B-v1", "nvidia/Nemotron-Nano-9B-v2", "nvidia/Nemotron-Nano-12B-v2"]
    d = g.discover_tier_models(ids)
    assert d["nemotron-ultra"].endswith("Ultra-253B-v1")
    assert d["nemotron-super"].endswith("Super-49B-v1")
    assert d["nemotron-nano"].endswith("Nano-12B-v2")  # biggest of the nanos


def test_discover_fills_missing_tiers_by_size():
    d = g.discover_tier_models(["x/nemotron-4b", "x/nemotron-30b", "x/nemotron-340b", "x/other"])
    assert d == {"nemotron-nano": "x/nemotron-4b", "nemotron-super": "x/nemotron-30b", "nemotron-ultra": "x/nemotron-340b"}


def test_provider_prefers_token_factory(monkeypatch):
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "k")
    assert g._provider()[0] == "tokenfactory" and "nebius" in g._provider()[2]
    monkeypatch.delenv("TOKEN_FACTORY_API_KEY")
    monkeypatch.setenv("NVIDIA_API_KEY", "k2")
    assert g._provider()[0] == "nim"
