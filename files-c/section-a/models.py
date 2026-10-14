"""
Shared data contract for the verified test-gap agent.

These two shapes are the interface boundary between Section 1 (this module),
Section 2 (test generation), and Section 3 (orchestration). All three people
build against these dataclasses, not against each other's internals.
"""

from dataclasses import dataclass
from typing import Literal, Optional

GapReason = Literal["uncovered", "partial_branch"]
VerificationStatus = Literal["pass", "fail", "error"]


@dataclass(frozen=True)
class Gap:
    """A contiguous range of new/changed lines a PR left untested."""
    file: str                 # path relative to repo root, e.g. "app/billing.py"
    start_line: int           # 1-indexed, inclusive
    end_line: int              # 1-indexed, inclusive
    function_context: str      # enclosing function/method name, "" if module-level
    reason: GapReason          # "uncovered" = never executed, "partial_branch" = one side of an if/else never taken

    def __str__(self) -> str:
        loc = f"{self.file}:{self.start_line}" if self.start_line == self.end_line \
            else f"{self.file}:{self.start_line}-{self.end_line}"
        ctx = f" (in {self.function_context})" if self.function_context else ""
        return f"{loc}{ctx} [{self.reason}]"


@dataclass(frozen=True)
class CandidateTest:
    """What Section 2 hands back after generating a test for a Gap."""
    code: str                  # full test function source, ready to drop into a test file
    target_gap: Gap
    model_tier_used: str        # e.g. "nemotron-nano", "nemotron-super", "nemotron-ultra"
    attempt_number: int = 1


@dataclass(frozen=True)
class VerificationResult:
    """What Section 1 hands back after trying a CandidateTest in the sandbox."""
    status: VerificationStatus  # "pass" = test ran, passed, and hit the gap
    coverage_hit: bool          # did execution actually reach the target lines?
    message: str                 # stdout/stderr tail or a human-readable reason

    @property
    def verified(self) -> bool:
        """True only if the test is both green AND provably exercises the gap.

        This is the whole point of the project: a test that passes but never
        touches the target line is worthless, and `status == "pass"` alone
        does not tell you that. See: mutation testing / the test-oracle problem.
        """
        return self.status == "pass" and self.coverage_hit
