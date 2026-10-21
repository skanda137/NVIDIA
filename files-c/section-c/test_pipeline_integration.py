"""run_pipeline on the billing fixture with real git, pytest and coverage, and a
fake LLM (no network). Needs a POSIX shell with git and coverage on PATH."""
import functools
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _paths  # noqa: E402,F401
import generator  # noqa: E402
import generator_stub  # noqa: E402
from demo_pipeline import build_fixture_repo  # noqa: E402
from pipeline_models import PipelineConfig  # noqa: E402
from run_pipeline import collect_example_tests, run_pipeline  # noqa: E402
from sandbox_client import LocalSandboxClient  # noqa: E402

# The stub's known-good tests, keyed by the gap's first line in billing.py.
KNOWN_GOOD = {
    5: generator_stub.generate_test(
        generator.Gap("billing.py", 5, 5, "calculate_discount", "partial_branch"), [], attempt=1).code,
    8: generator_stub.generate_test(
        generator.Gap("billing.py", 8, 9, "calculate_discount", "uncovered"), [], attempt=2).code,
    14: generator_stub.generate_test(
        generator.Gap("billing.py", 14, 14, "log_non_member_purchase", "uncovered"), [], attempt=1).code,
}


class FakeLLM:
    """Answers with the stub's known-good test for the gap named in the prompt."""

    def __init__(self):
        self.calls = []

    def __call__(self, model, messages, temperature):
        self.calls.append(model)
        start = int(re.search(r"Target lines \(in the file, 1-indexed\): (\d+)-", messages[1]["content"]).group(1))
        return f"<think>plan</think>\n```python\n{KNOWN_GOOD[start]}```"


@pytest.fixture(scope="module")
def fixture_repo(tmp_path_factory):
    return build_fixture_repo(tmp_path_factory.mktemp("billing"))


@pytest.fixture
def tiers(monkeypatch):
    monkeypatch.setenv("TOKEN_FACTORY_MODEL_NANO", "fake/nemotron-nano")
    monkeypatch.setenv("TOKEN_FACTORY_MODEL_SUPER", "fake/nemotron-super")
    monkeypatch.setenv("TOKEN_FACTORY_MODEL_ULTRA", "fake/nemotron-ultra")


def _run(fixture_repo, tmp_path, generate, attempts=3):
    url, diff, sha = fixture_repo
    tmp_path.mkdir(parents=True, exist_ok=True)
    return run_pipeline(LocalSandboxClient(cwd=str(tmp_path)), url, sha, diff, ["billing.py"],
                        config=PipelineConfig(max_attempts_per_gap=attempts),
                        repo_path="checked_out_repo", generate=generate)


def test_fake_llm_generator_matches_stub_verified_count(fixture_repo, tmp_path, tiers):
    stub = _run(fixture_repo, tmp_path / "stub", generator_stub.generate_test)
    llm = FakeLLM()
    real = _run(fixture_repo, tmp_path / "llm", functools.partial(generator.generate_test, llm=llm))
    assert stub.gaps_found == real.gaps_found == 3
    assert real.tests_verified_pass == stub.tests_verified_pass == 3
    assert llm.calls == ["fake/nemotron-nano"] * 3
    assert all(r.attempts[0].model_tier_used == "nemotron-nano" for r in real.records)


def test_rejected_candidate_becomes_failed_attempt_and_prior_failure(fixture_repo, tmp_path, tiers):
    seen = []

    def generate(gap, example_tests, attempt=1, prior_failure=None, *, source=None):
        seen.append((attempt, prior_failure, source))
        if attempt == 1:
            raise generator.CandidateRejected(["imports banned module 'subprocess'"],
                                              code="import subprocess", tier="nemotron-nano")
        return generator.generate_test(gap, example_tests, attempt, prior_failure, source=source, llm=FakeLLM())

    result = _run(fixture_repo, tmp_path, generate)
    assert result.tests_verified_pass == 3
    for rec in result.records:
        assert len(rec.attempts) == 2
        assert rec.attempts[0].model_tier_used == "nemotron-nano" and rec.attempts[0].code == "import subprocess"
        assert rec.verifications[0].status == "fail"
        assert "subprocess" in rec.verifications[0].message
        assert rec.attempts[1].model_tier_used == "nemotron-super"
    second = [s for s in seen if s[0] == 2]
    assert all(p.startswith("generated code rejected before running") for _, p, _ in second)
    assert all("def calculate_discount" in src for _, _, src in seen)  # real file source passed


def test_exhausted_gap_is_flagged_for_human_review(fixture_repo, tmp_path):
    def always_rejected(gap, example_tests, attempt=1, prior_failure=None, *, source=None):
        raise generator.CandidateRejected(["no function named test_* found"], code="", tier="nemotron-nano")

    result = _run(fixture_repo, tmp_path, always_rejected, attempts=1)
    assert all(r.final_status == "exhausted" for r in result.records)
    assert result.report_markdown.count("**Flagged for human review**") == 3


def test_collect_example_tests_reads_repo_tests_not_scratch(fixture_repo, tmp_path):
    url, _, sha = fixture_repo
    sb = LocalSandboxClient(cwd=str(tmp_path))
    assert sb.run(f"git clone -q {url} repo && cd repo && git checkout -q {sha}").ok
    (tmp_path / "repo" / "_scratch_test_x.py").write_text("SCRATCH")
    (tmp_path / "repo" / "pkg").mkdir()
    (tmp_path / "repo" / "pkg" / "test_more.py").write_text("def test_more(): pass\n")
    examples = collect_example_tests(sb, "repo", limit=3)
    assert len(examples) == 2
    assert "test_calculate_discount_for_member" in examples[1]  # ./test_billing.py sorts after ./pkg/
    assert all("SCRATCH" not in e for e in examples)
    assert len(collect_example_tests(sb, "repo", limit=1)) == 1
