"""
Section 3 — orchestration.

Owns run_pipeline(): the only function Sections 1 and 2 don't need to read
to understand, and the only function this project's entry point calls.

What this does NOT own (imported, not reimplemented):
  - find_gaps / verify_test              -- Section 1 (verifier.py)
  - generate_test                        -- Section 2 (section-b/generator.py;
                                             generator_stub.py is passed in
                                             as `generate=` for offline demos)
  - Gap / CandidateTest / VerificationResult -- Section 1 (models.py)

What this file owns:
  1. Getting a repo checked out *inside* the sandbox at repo_path --
     verifier.py's find_gaps() docstring is explicit that this is Section
     3's job, not Section 1's.
  2. The retry loop: generate -> verify -> retry on fail, up to
     max_attempts_per_gap.
  3. Aggregating per-gap outcomes into one PipelineResult.
  4. Handing the result to render.py for the human-facing report.

Generator: Section 2's generate_test by default. Anything with the same
signature can be passed as `generate=` (the stub, or generate_test with a
fake llm in tests) -- that's the point of building against the shared
models.py contract.
"""

from __future__ import annotations

import shlex
import time
from dataclasses import replace
from typing import Callable

import openai

import _paths  # noqa: F401  (section-a and section-b on sys.path)
from generator import CandidateRejected, generate_test
from models import CandidateTest, Gap, VerificationResult
from pipeline_models import GapRecord, PipelineConfig, PipelineResult
from sandbox_client import SandboxClient
from verifier import find_gaps, prepare_env, verify_test

# The only LLM errors a gap survives: the SDK has already retried them (max_retries=2),
# so this gap's attempt is spent and the next attempt moves up a tier. Auth, bad
# request, missing env and everything else propagate: they would fail every gap.
TRANSIENT_LLM_ERRORS = (openai.APITimeoutError, openai.RateLimitError)


def checkout_repo(sandbox: SandboxClient, repo_path: str, repo_url: str, ref: str,
                  fetch_ref: str | None = None) -> None:
    """Clone + checkout the PR head inside the sandbox. find_gaps() assumes
    this has already happened -- see verifier.py's docstring. The one step
    besides prepare_env() that runs with network (a remote repo_url).
    fetch_ref: fetched from origin before the checkout, for a ref a plain clone
    does not bring along (a GitHub PR's `pull/<n>/head`)."""
    # rm -rf first: a rerun into the same sandbox otherwise fails with
    # "destination path already exists" (audit R6/E7).
    path, url, rev = shlex.quote(repo_path), shlex.quote(repo_url), shlex.quote(ref)
    fetch = f"git fetch --quiet origin {shlex.quote(fetch_ref)} && " if fetch_ref else ""
    result = sandbox.run(f"rm -rf {path} && git clone --quiet {url} {path} "
                         f"&& cd {path} && {fetch}git checkout --quiet {rev}", network=True)
    if not result.ok:
        raise RuntimeError(f"failed to check out {repo_url}@{ref} into sandbox:\n{result.stderr[-2000:]}")


def collect_example_tests(sandbox: SandboxClient, repo_path: str, limit: int = 3) -> list[str]:
    """Up to `limit` existing test_*.py files from the checked-out repo (sorted, hidden
    dirs and _scratch_* skipped), as style examples for the generator."""
    result = sandbox.run(
        f"cd {shlex.quote(repo_path)} && find . -type f -name 'test_*.py' "
        f"-not -name '_scratch_*' -not -path '*/.*' | sort"
    )
    if not result.ok:
        raise RuntimeError(f"listing example tests failed:\n{result.stderr[-2000:]}")
    paths = [p for p in result.stdout.splitlines() if p.strip()][:limit]
    return [sandbox.read_file(f"{repo_path}/{p[2:] if p.startswith('./') else p}") for p in paths]


def _run_gap(
    gap: Gap,
    sandbox: SandboxClient,
    repo_path: str,
    example_tests: list[str],
    config: PipelineConfig,
    generate: Callable[..., CandidateTest],
) -> GapRecord:
    """The retry loop for a single gap: generate -> verify -> retry on fail."""
    record = GapRecord(gap=gap)
    prior_failure: str | None = None
    source = sandbox.read_file(f"{repo_path}/{gap.file}")  # once per gap; failures raise

    for attempt in range(1, config.max_attempts_per_gap + 1):
        try:
            candidate: CandidateTest = generate(
                gap, example_tests, attempt=attempt, prior_failure=prior_failure, source=source,
            )
        except CandidateRejected as exc:
            # Lint still failed after Section 2's repair round: count it as a
            # failed attempt (never sent to the sandbox) and feed the reason back.
            record.attempts.append(CandidateTest(code=exc.code, target_gap=gap,
                                                 model_tier_used=exc.tier, attempt_number=attempt))
            rejected = VerificationResult(status="fail", coverage_hit=False,
                                          message=f"generated code rejected before running: {'; '.join(exc.problems)}")
            record.verifications.append(rejected)
            prior_failure = rejected.message
            continue
        except TRANSIENT_LLM_ERRORS as exc:
            # No code came back; prior_failure is left alone (the model did nothing wrong).
            record.attempts.append(CandidateTest(code="", target_gap=gap,
                                                 model_tier_used="(no response)", attempt_number=attempt))
            record.verifications.append(VerificationResult(
                status="error", coverage_hit=False,
                message=f"Token Factory call failed after SDK retries: {type(exc).__name__}: {exc}"))
            continue
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


def _closed_by_earlier(gap: Gap, verified: list[GapRecord], sandbox: SandboxClient,
                       repo_path: str) -> GapRecord | None:
    """Re-verify each already-verified test against `gap` (one sandbox run each, no
    LLM call). The same verify_test check applies: the test must take this gap's
    missing branch or execute its lines, not merely pass."""
    for earlier in verified:
        candidate = replace(earlier.best_candidate, target_gap=gap)
        verification = verify_test(sandbox, repo_path, candidate)
        if verification.verified:
            return GapRecord(gap=gap, attempts=[candidate], verifications=[verification],
                             final_status="verified_pass", covered_by=earlier.gap)
    return None


def run_pipeline(
    sandbox: SandboxClient,
    repo_url: str,
    ref: str,
    diff: str,
    changed_py_files: list[str],
    example_tests: list[str] | None = None,
    config: PipelineConfig | None = None,
    repo_path: str = "checked_out_repo",
    install_deps: bool = False,
    generate: Callable[..., CandidateTest] = generate_test,
    fetch_ref: str | None = None,
) -> PipelineResult:
    """
    Entry point. repo_url/ref are used to check the PR head out inside the
    sandbox (step the real find_gaps() explicitly leaves to the caller).
    diff and changed_py_files are passed straight through to find_gaps(),
    matching verifier.py's real signature exactly.
    repo_path: relative to the sandbox workdir (the only place that persists).
    install_deps: run verifier.prepare_env() after checkout (pip-installs pytest,
    coverage and requirements.txt into the sandbox workdir, with network).
    example_tests: None = collect up to 3 test_*.py files from the checked-out repo.
    fetch_ref: passed to checkout_repo (a PR's `pull/<n>/head`).
    generate: Section 2's generate_test, or anything with its signature.
    """
    config = config or PipelineConfig()
    start = time.monotonic()

    checkout_repo(sandbox, repo_path, repo_url, ref, fetch_ref)
    if install_deps:
        prepare_env(sandbox, repo_path)
    if example_tests is None:
        example_tests = collect_example_tests(sandbox, repo_path, limit=3)

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

    verified: list[GapRecord] = []  # gaps whose test was generated (not reused) and verified
    gaps_attempted = 0
    for gap in gaps:
        gap_start = time.monotonic()
        record = _closed_by_earlier(gap, verified, sandbox, repo_path)
        if record is None and gaps_attempted >= config.max_gaps:
            record = GapRecord(gap=gap, final_status="skipped_budget")
        elif record is None:
            gaps_attempted += 1
            record = _run_gap(gap, sandbox, repo_path, example_tests, config, generate)
            if record.final_status == "verified_pass":
                verified.append(record)
        record.seconds = time.monotonic() - gap_start
        records.append(record)

    tests_generated = sum(1 for r in records if r.covered_by is None for a in r.attempts if a.code)
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
        gaps_closed_by_earlier_test=sum(1 for r in records if r.covered_by is not None),
        gaps_skipped=sum(1 for r in records if r.final_status == "skipped_budget"),
    )

    from render import render_markdown
    result.report_markdown = render_markdown(result)
    return result
