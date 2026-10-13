"""
STUB for Section 2's generate_test(). Not production logic -- a deterministic
placeholder so Section 3's orchestration loop is runnable and demoable today,
before Section 2's real Nemotron-backed generator exists.

Section 2's real signature (per the team's interface contract) is expected
to be:

    def generate_test(gap: Gap, example_tests: list[str], attempt: int = 1,
                       prior_failure: str | None = None) -> CandidateTest

This stub matches that signature exactly, so swapping it for the real
thing in run_pipeline.py is a one-line import change -- nothing in the
orchestrator needs to know which one it's calling.

What this stub actually does: for a Gap whose function_context and reason
it recognizes (the billing.py demo case), it hand-writes a real, correct
pytest test. For anything else, it deliberately returns a test that will
FAIL verification -- so the orchestrator's retry path is exercised honestly
rather than always taking the "everything passes first try" happy path.
"""

from __future__ import annotations

from models import CandidateTest, Gap

STUB_MODEL_TIER = "stub-deterministic"


def generate_test(
    gap: Gap,
    example_tests: list[str],
    attempt: int = 1,
    prior_failure: str | None = None,
) -> CandidateTest:
    if gap.function_context == "calculate_discount" and gap.reason == "partial_branch":
        code = (
            "def test_calculate_discount_for_non_member():\n"
            "    from billing import calculate_discount\n"
            "    result = calculate_discount(100.0, is_member=False)\n"
            "    assert result == 95.0\n"
        )
        return CandidateTest(code=code, target_gap=gap, model_tier_used=STUB_MODEL_TIER, attempt_number=attempt)

    if gap.function_context == "log_non_member_purchase" and gap.reason == "uncovered":
        code = (
            "def test_log_non_member_purchase_runs():\n"
            "    from billing import log_non_member_purchase\n"
            "    log_non_member_purchase(42.0)\n"
        )
        return CandidateTest(code=code, target_gap=gap, model_tier_used=STUB_MODEL_TIER, attempt_number=attempt)

    # The else-body gap (billing.py:8-9, uncovered, function_context
    # "calculate_discount"): deliberately broken on attempt 1 (imports a
    # function that doesn't exist), so verify_test() reports a genuine
    # failure and the retry loop has something real to retry against. On
    # attempt 2+, use prior_failure the way a real generator would -- see
    # the ModuleNotFoundError text got fed back in, so "fix" by importing
    # the right thing and actually exercising the else branch this time.
    if gap.function_context == "calculate_discount" and gap.reason == "uncovered":
        if attempt == 1:
            code = (
                "def test_calculate_discount_for_non_member_v1():\n"
                "    from nonexistent_module import this_does_not_exist\n"
                "    assert this_does_not_exist()\n"
            )
        else:
            code = (
                "def test_calculate_discount_for_non_member_v2():\n"
                "    # retry informed by prior_failure (a real generator would\n"
                "    # parse the ModuleNotFoundError and correct the import)\n"
                "    from billing import calculate_discount\n"
                "    result = calculate_discount(100.0, is_member=False)\n"
                "    assert result == 95.0\n"
            )
        return CandidateTest(code=code, target_gap=gap, model_tier_used=STUB_MODEL_TIER, attempt_number=attempt)

    # Any other, truly-unrecognized gap shape: give up gracefully rather
    # than crash -- a vacuous but non-crashing candidate, so the
    # orchestrator's "exhausted" path is still exercised for gap shapes
    # this stub has no canned answer for.
    code = (
        f"def test_stub_placeholder_for_{gap.start_line}():\n"
        f"    assert True  # stub has no real answer for this gap shape\n"
    )
    return CandidateTest(code=code, target_gap=gap, model_tier_used=STUB_MODEL_TIER, attempt_number=attempt)
