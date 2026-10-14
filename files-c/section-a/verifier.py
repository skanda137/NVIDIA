"""
The public interface: find_gaps() and verify_test(). This is the only file
Section 2 and Section 3 need to import from. Everything else in this
directory is an implementation detail they shouldn't need to know about.
"""

from __future__ import annotations

import re

from coverage_diff import compute_gaps
from models import CandidateTest, Gap, VerificationResult
from sandbox_client import SandboxClient

COVERAGE_RUN_CMD = "coverage run --branch -m pytest -q && coverage xml -o coverage.xml"


def find_gaps(sandbox: SandboxClient, repo_path: str, diff: str, changed_py_files: list[str]) -> list[Gap]:
    """
    repo_path: where the repo already lives *inside the sandbox* (caller is
               responsible for having cloned + checked out the PR head there --
               that's a Section 3 orchestration step, not this function's job).
    diff:      the unified diff for the PR, as text (from the GitHub API).
    changed_py_files: the .py files touched by the diff, so we only read back
               the source we actually need for AST function-context lookup.
    """
    result = sandbox.run(f"cd {repo_path} && {COVERAGE_RUN_CMD}")
    if not result.ok:
        # Suite doesn't even run on the PR as-is -- that's a real signal,
        # surface it rather than silently returning no gaps.
        raise RuntimeError(f"test suite failed to run cleanly:\n{result.stderr[-2000:]}")

    xml_text = sandbox.read_file(f"{repo_path}/coverage.xml")
    local_xml_path = "/tmp/_coverage_fetch.xml"
    with open(local_xml_path, "w") as f:
        f.write(xml_text)

    file_sources = {
        path: sandbox.read_file(f"{repo_path}/{path}")
        for path in changed_py_files
    }

    return compute_gaps(diff, local_xml_path, file_sources)


_TEST_NAME_RE = re.compile(r"\bdef\s+(test_\w+)")


def verify_test(sandbox: SandboxClient, repo_path: str, candidate: CandidateTest) -> VerificationResult:
    """
    Drop the candidate test into a scratch file, run only that test under
    branch coverage, and check two independent things:
      1. did it pass (status)
      2. did it actually execute the target gap's lines (coverage_hit)
    Both have to be true for the test to count -- see Gap/VerificationResult
    docstrings for why #1 alone is not enough.
    """
    name_match = _TEST_NAME_RE.search(candidate.code)
    if not name_match:
        return VerificationResult(status="error", coverage_hit=False,
                                   message="generated code has no `def test_...` function to run")
    test_name = name_match.group(1)
    scratch_path = f"{repo_path}/_scratch_verify_test.py"

    sandbox.write_file(scratch_path, candidate.code)

    run = sandbox.run(
        f"cd {repo_path} && "
        f"coverage run --branch -m pytest -q _scratch_verify_test.py::{test_name} "
        f"&& coverage xml -o _scratch_coverage.xml"
    )

    passed = run.ok
    coverage_hit = False

    if passed:
        try:
            xml_text = sandbox.read_file(f"{repo_path}/_scratch_coverage.xml")
            local_xml_path = "/tmp/_scratch_coverage_fetch.xml"
            with open(local_xml_path, "w") as f:
                f.write(xml_text)
            from coverage_diff import parse_coverage_xml
            cov = parse_coverage_xml(local_xml_path)
            gap = candidate.target_gap
            file_cov = cov.get(gap.file, {})
            target_range = range(gap.start_line, gap.end_line + 1)
            coverage_hit = any(
                file_cov.get(ln) is not None and file_cov[ln].hits > 0
                for ln in target_range
            )
        except Exception as exc:  # noqa: BLE001 - a broken coverage read shouldn't crash the loop
            return VerificationResult(status="error", coverage_hit=False,
                                       message=f"test passed but coverage check failed: {exc}")

    sandbox.run(f"rm -f {scratch_path} {repo_path}/_scratch_coverage.xml")  # clean up before next attempt

    status = "pass" if passed else "fail"
    tail = (run.stdout or run.stderr)[-1500:]
    message = tail if not passed else (
        "passed and hit target lines" if coverage_hit else
        "passed but NEVER EXECUTED the target gap -- a vacuous test, rejecting"
    )
    return VerificationResult(status=status, coverage_hit=coverage_hit, message=message)
