"""
Section 3's own data shapes.

Gap / CandidateTest / VerificationResult come from Section 1's models.py --
we import them, we never redefine them. These three types are the ones
Section 3 itself owns: they describe pipeline-level state, not a single
gap/test/verification.
"""

from dataclasses import dataclass, field
from typing import Literal, Optional

import _paths  # noqa: F401  (section-a on sys.path)
from models import CandidateTest, Gap, VerificationResult

GapFinalStatus = Literal["verified_pass", "exhausted", "skipped_budget"]


@dataclass
class GapRecord:
    """Everything that happened for one Gap across every retry attempt."""
    gap: Gap
    attempts: list[CandidateTest] = field(default_factory=list)
    verifications: list[VerificationResult] = field(default_factory=list)
    final_status: GapFinalStatus = "exhausted"
    # Set when no test was generated for this gap because the test verified for
    # an earlier gap (covered_by) also closes it.
    covered_by: Optional[Gap] = None

    @property
    def best_candidate(self) -> Optional[CandidateTest]:
        """The passing candidate if one exists, otherwise the last attempt
        made (so the report can still show 'here's what we tried')."""
        for cand, ver in zip(self.attempts, self.verifications):
            if ver.verified:
                return cand
        return self.attempts[-1] if self.attempts else None

    @property
    def last_verification(self) -> Optional[VerificationResult]:
        return self.verifications[-1] if self.verifications else None


@dataclass
class PipelineResult:
    repo: str
    diff_summary: str
    gaps_found: int
    tests_generated: int
    tests_verified_pass: int
    tests_verified_fail: int
    tests_errored: int
    duration_seconds: float
    records: list[GapRecord] = field(default_factory=list)
    report_markdown: Optional[str] = None
    gaps_closed_by_earlier_test: int = 0
    gaps_skipped: int = 0  # over PipelineConfig.max_gaps, never attempted


@dataclass
class PipelineConfig:
    max_attempts_per_gap: int = 3
    # Gaps that may call the LLM (at most max_attempts_per_gap x 2 calls each, one
    # repair round per attempt). Gaps closed by an earlier verified test don't count.
    max_gaps: int = 10
    model_tier: str = "nemotron-nano"
    run_gaps_in_parallel: bool = False  # keep False until verify_test is confirmed thread-safe in a real sandbox
