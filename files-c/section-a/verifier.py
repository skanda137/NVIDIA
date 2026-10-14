"""
The public interface: find_gaps() and verify_test(). This is the only file
Section 2 and Section 3 need to import from. Everything else in this
directory is an implementation detail they shouldn't need to know about.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from coverage_diff import compute_gaps, find_coverage_key, parse_coverage_xml
from models import CandidateTest, Gap, VerificationResult
from sandbox_client import TIMEOUT_RETURNCODE, SandboxClient

# --source=. : measure every .py under the repo root, so (a) report paths are
# relative to the repo root like diff paths, and (b) a new module no test
# imports still appears in the report (0% instead of missing).
COVERAGE_RUN = "coverage run --branch --source=. -m pytest -q"
COVERAGE_RUN_CMD = f"{COVERAGE_RUN} && coverage xml -o coverage.xml"

SUITE_TIMEOUT = 300       # seconds, whole existing suite
CANDIDATE_TIMEOUT = 120   # seconds, one generated test file
INSTALL_TIMEOUT = 600

SCRATCH_TEST = "_scratch_verify_test.py"
SCRATCH_XML = "_scratch_coverage.xml"

# PYTHONDONTWRITEBYTECODE: two same-size candidates written to the same scratch
# path within the same second let python reuse the first one's cached bytecode,
# so a correct retry was rejected 4/6 times (audit E8; 0/6 with this set).
# -p no:cacheprovider: no .pytest_cache churn between candidates.
CANDIDATE_RUN_CMD = (
    f"PYTHONDONTWRITEBYTECODE=1 coverage run --branch --source=. -m pytest -q "
    f"-p no:cacheprovider {SCRATCH_TEST} && coverage xml -o {SCRATCH_XML}"
)

_HAS_TEST_FN = re.compile(r"\bdef\s+test_\w+")


def prepare_env(sandbox: SandboxClient, repo_path: str) -> None:
    """Install pytest, coverage and the repo's requirements.txt into the sandbox.
    Call once after the repo is checked out and before find_gaps. Not called
    automatically: with LocalSandboxClient it pip-installs into the HOST
    interpreter, so only call it there from inside a throwaway venv.
    Needs outbound network from the sandbox (unverified on Nebius).
    Raises on any failure. A repo without requirements.txt gets only the two tools."""
    result = sandbox.run(
        f"cd {repo_path} && python3 -m pip install -q pytest coverage "
        f"&& {{ [ ! -f requirements.txt ] || python3 -m pip install -q -r requirements.txt; }}",
        timeout=INSTALL_TIMEOUT,
    )
    if not result.ok:
        raise RuntimeError(f"environment setup failed:\n{(result.stdout + result.stderr)[-2000:]}")


def find_gaps(sandbox: SandboxClient, repo_path: str, diff: str, changed_py_files: list[str]) -> list[Gap]:
    """
    repo_path: where the repo already lives *inside the sandbox* (caller is
               responsible for having cloned + checked out the PR head there --
               that's a Section 3 orchestration step, not this function's job).
    diff:      the unified diff for the PR, as text (from the GitHub API).
    changed_py_files: the .py files touched by the diff, so we only read back
               the source we actually need for AST function-context lookup.
    Raises if the suite does not run green on the PR as-is, and if a file in
    changed_py_files is missing from the coverage report (never a silent empty).
    """
    result = sandbox.run(f"cd {repo_path} && {COVERAGE_RUN_CMD}", timeout=SUITE_TIMEOUT)
    if not result.ok:
        # pytest prints failures and import errors to stdout, so report both streams.
        raise RuntimeError(f"test suite failed to run cleanly:\n{(result.stdout + result.stderr)[-2000:]}")

    xml_text = sandbox.read_file(f"{repo_path}/coverage.xml")
    file_sources = {
        path: sandbox.read_file(f"{repo_path}/{path}")
        for path in changed_py_files
    }
    return compute_gaps(diff, xml_text, file_sources)


def _closes_gap(cov: dict, gap: Gap) -> tuple[bool, str]:
    """Did this candidate's coverage run close `gap`?
    uncovered      -> some line of the gap now has hits > 0.
    partial_branch -> the candidate took at least one branch the baseline never
                      took. The `if` line itself is already executed by the
                      existing suite, so line hits cannot tell (audit E1: a test
                      re-running the covered branch was accepted as verified)."""
    key = find_coverage_key(cov, gap.file)
    if key is None:
        return False, f"{gap.file} is not in the candidate's coverage report"
    lines = cov[key]
    span = range(gap.start_line, gap.end_line + 1)

    if gap.reason == "partial_branch":
        if not gap.missing_branches:
            raise ValueError(f"{gap} has no missing_branches; build gaps with find_gaps()")
        # A branch counts as taken only if its source line is in this report and
        # no longer lists that destination. A line absent from the report proves nothing.
        taken = {b for b in gap.missing_branches
                 if int(b.split(":", 1)[0]) in lines
                 and b.split(":", 1)[1] not in lines[int(b.split(":", 1)[0])].missing_branches}
        if taken:
            return True, f"took previously missing branch(es): {sorted(taken)}"
        return False, f"did not take any of the missing branches {list(gap.missing_branches)}"

    if any(ln in lines and lines[ln].hits > 0 for ln in span):
        return True, "executed the target lines"
    return False, "never executed the target lines"


def verify_test(sandbox: SandboxClient, repo_path: str, candidate: CandidateTest) -> VerificationResult:
    """
    Drop the candidate test into a scratch file, run it under branch coverage,
    and require two independent things: it passes, and it closes the gap
    (see _closes_gap). Both must hold -- a green test that never touches the
    gap proves nothing.
    The whole scratch file is run (no ::node-id), so class-based tests and
    files with several tests work, and any failing test rejects the candidate.
    """
    if not _HAS_TEST_FN.search(candidate.code):
        return VerificationResult(status="error", coverage_hit=False,
                                  message="generated code has no `def test_...` function to run")

    sandbox.write_file(f"{repo_path}/{SCRATCH_TEST}", candidate.code)
    try:
        run = sandbox.run(f"cd {repo_path} && {CANDIDATE_RUN_CMD}", timeout=CANDIDATE_TIMEOUT)
        if run.returncode == TIMEOUT_RETURNCODE:
            return VerificationResult(status="fail", coverage_hit=False,
                                      message=f"timed out after {CANDIDATE_TIMEOUT}s (infinite loop?)")
        if not run.ok:
            return VerificationResult(status="fail", coverage_hit=False,
                                      message=(run.stdout + run.stderr)[-1500:])

        try:
            cov = parse_coverage_xml(sandbox.read_file(f"{repo_path}/{SCRATCH_XML}"))
        except (FileNotFoundError, ET.ParseError) as exc:
            return VerificationResult(status="error", coverage_hit=False,
                                      message=f"test passed but its coverage report was unreadable: {exc}")

        closed, why = _closes_gap(cov, candidate.target_gap)
        if closed:
            return VerificationResult(status="pass", coverage_hit=True, message=f"passed and {why}")
        return VerificationResult(status="pass", coverage_hit=False,
                                  message=f"passed but {why} -- a vacuous test, rejecting")
    finally:
        sandbox.run(f"cd {repo_path} && rm -f {SCRATCH_TEST} {SCRATCH_XML}")  # also on error paths
