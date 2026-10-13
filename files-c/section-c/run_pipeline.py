"""
Section 3 — orchestration.

Owns run_pipeline(): the only function Sections 1 and 2 don't need to read
to understand, and the only function this project's entry point calls.

What this does NOT own (imported, not reimplemented):
  - find_gaps / verify_test              -- Section 1 (verifier.py)
  - generate_test                        -- Section 2 (generator_stub.py
                                             until the real one lands;
                                             see the import line below,
                                             it's the only line that changes)
  - Gap / CandidateTest / VerificationResult -- Section 1 (models.py)

What this file owns:
  1. Getting a repo checked out *inside* the sandbox at repo_path --
     verifier.py's find_gaps() docstring is explicit that this is Section
     3's job, not Section 1's.
  2. The retry loop: generate -> verify -> retry on fail, up to
     max_attempts_per_gap.
  3. Aggregating per-gap outcomes into one PipelineResult.
  4. Handing the result to render.py for the human-facing report.

Swap point for Section 2: when the real generator exists, change only the
import below from `generator_stub` to the real module. Nothing else in this
file needs to change -- that's the point of building against the shared
models.py contract.
"""

from __future__ import annotations

import time

from generator_stub import generate_test  # <-- swap for Section 2's real module when ready
from models import CandidateTest, Gap
from pipeline_models import GapRecord, PipelineConfig, PipelineResult
from sandbox_client import SandboxClient
from verifier import find_gaps, verify_test


def checkout_repo(sandbox: SandboxClient, repo_path: str, repo_url: str, ref: str) -> None:
    """Clone + checkout the PR head inside the sandbox. find_gaps() assumes
    this has already happened -- see verifier.py's docstring. Using git
    clone/checkout rather than any file-upload API, consistent with
    sandbox_client.py's documented approach (upload/`contree cp` syntax is
    unconfirmed, so nothing here depends on it)."""
    result = sandbox.run(f"git clone --quiet {repo_url} {repo_path} && cd {repo_path} && git checkout --quiet {ref}")
    if not result.ok:
        raise RuntimeError(f"failed to check out {repo_url}@{ref} into sandbox:\n{result.stderr[-2000:]}")


def _run_gap(
    gap: Gap,
    sandbox: SandboxClient,
    repo_path: str,
    example_tests: list[str],
    config: PipelineConfig,
) -> GapRecord:
    """The retry loop for a single gap: generate -> verify -> retry on fail."""
    record = GapRecord(gap=gap)
    prior_failure: str | None = None

    for attempt in range(1, config.max_attempts_per_gap + 1):
        candidate: CandidateTest = generate_test(
            gap, example_tests, attempt=attempt, prior_failure=prior_failure,
        )
        record.attempts.append(candidate)

        verification = verify_test(sandbox, repo_path, candidate)
        record.verifications.append(verification)

        if verification.verified:
            record.final_status = "verified_pass"
            return record

        if verification.status == "error":
            # Malformed candidate (e.g. no def test_... found) or a broken
            # coverage read -- not a "the test ran and failed" signal, so
            # retrying with the same prior_failure text likely won't help,
            # but we still give Section 2 the chance since attempt budget
            # is cheap and the alternative is silently giving up early.
            prior_failure = f"[error] {verification.message}"
        else:
            prior_failure = verification.message

    record.final_status = "exhausted"
    return record


def run_pipeline(
    sandbox: SandboxClient,
    repo_url: str,
    ref: str,
    diff: str,
    changed_py_files: list[str],
    example_tests: list[str] | None = None,
    config: PipelineConfig | None = None,
    repo_path: str = "/tmp/_pipeline_repo",
) -> PipelineResult:
    """
    Entry point. repo_url/ref are used to check the PR head out inside the
    sandbox (step the real find_gaps() explicitly leaves to the caller).
    diff and changed_py_files are passed straight through to find_gaps(),
    matching verifier.py's real signature exactly.
    """
    config = config or PipelineConfig()
    example_tests = example_tests or []
    start = time.monotonic()

    checkout_repo(sandbox, repo_path, repo_url, ref)

    gaps = find_gaps(sandbox, repo_path, diff, changed_py_files)

    records: list[GapRecord] = []
    if config.run_gaps_in_parallel:
        # Deliberately not implemented yet -- verify_test()'s sandbox.run()
        # calls share one evolving session/filesystem (see sandbox_client.py's
        # module docstring on session keying), so concurrent gaps could step
        # on each other's _scratch_verify_test.py. Needs a per-gap scratch
        # filename or a session-per-gap sandbox before this is safe. Falling
        # back to sequential rather than silently racing.
        raise NotImplementedError(
            "parallel gap verification needs per-gap sandbox isolation first; "
            "set PipelineConfig.run_gaps_in_parallel=False"
        )

    for gap in gaps:
        records.append(_run_gap(gap, sandbox, repo_path, example_tests, config))

    tests_generated = sum(len(r.attempts) for r in records)
    tests_verified_pass = sum(1 for r in records if r.final_status == "verified_pass")
    # "fail" bucket = the test suite ran (no crash/malformed-code error) but
    # the candidate was rejected -- either it genuinely failed, or (the
    # subtler case the project's whole premise is about) it reported
    # status="pass" while never touching the gap's lines, i.e. .verified is
    # False even though .status == "pass". Both belong in "attempted but
    # not verified", not in "errored".
    tests_verified_fail = sum(
        1 for r in records
        if r.final_status == "exhausted"
        and r.last_verification is not None
        and r.last_verification.status in ("pass", "fail")
        and not r.last_verification.verified
    )
    tests_errored = sum(
        1 for r in records
        if r.final_status == "exhausted" and r.last_verification and r.last_verification.status == "error"
    )

    result = PipelineResult(
        repo=repo_url,
        diff_summary=f"{len(changed_py_files)} file(s) changed: {', '.join(changed_py_files)}",
        gaps_found=len(gaps),
        tests_generated=tests_generated,
        tests_verified_pass=tests_verified_pass,
        tests_verified_fail=tests_verified_fail,
        tests_errored=tests_errored,
        duration_seconds=time.monotonic() - start,
        records=records,
    )

    from render import render_markdown
    result.report_markdown = render_markdown(result)
    return result
