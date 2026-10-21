"""
Section 3's proof-of-work demo.

Unlike Section 1's demo.py (which had to hand-build coverage.xml because
their container had no network to install pytest/coverage), this one has
network access, so it runs the REAL thing end to end: a real local git
repo, a real `git clone` into a sandbox working directory, a real
`pytest` + `coverage` run, real gap-finding via Section 1's unmodified
verifier.find_gaps(), and a real retry loop via run_pipeline(). Only
generate_test() is stubbed (generator_stub, so the demo runs offline with no
credentials; cli.py --generator llm uses Section 2's Nemotron generator) --
everything else below is the actual pipeline code, not a mock.

Run: python3 demo_pipeline.py
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import _paths  # noqa: F401  (section-a and section-b on sys.path)
import generator_stub
from pipeline_models import PipelineConfig
from run_pipeline import run_pipeline
from sandbox_client import LocalSandboxClient


def build_fixture_repo(tmp_dir: Path) -> tuple[str, str, str]:
    """Builds the same toy PR Section 1's demo.py uses (billing.py gaining
    calculate_discount(), member path tested, member=False path and the
    new helper function left untested) -- but as a REAL git repo with two
    real commits, so run_pipeline()'s checkout_repo() has something real
    to `git clone` and `git checkout`."""
    repo = tmp_dir / "fixture_repo"
    repo.mkdir()
    run = lambda *args: subprocess.run(args, cwd=repo, check=True, capture_output=True, text=True)

    run("git", "init", "-q")
    run("git", "config", "user.email", "test@example.com")
    run("git", "config", "user.name", "Test")

    (repo / "billing.py").write_text('"""Billing helpers."""\n')
    (repo / "test_billing.py").write_text("def test_placeholder():\n    assert True\n")
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "base")

    (repo / "billing.py").write_text(
        '"""Billing helpers."""\n\n\n'
        "def calculate_discount(amount: float, is_member: bool) -> float:\n"
        "    if is_member:\n"
        "        discount = amount * 0.20\n"
        "    else:\n"
        "        discount = amount * 0.05\n"
        "        log_non_member_purchase(amount)\n"
        "    return amount - discount\n\n\n"
        "def log_non_member_purchase(amount: float) -> None:\n"
        '    print(f"non-member purchase: {amount}")\n'
    )
    (repo / "test_billing.py").write_text(
        "from billing import calculate_discount\n\n\n"
        "def test_calculate_discount_for_member():\n"
        "    assert calculate_discount(100.0, is_member=True) == 80.0\n"
    )
    run("git", "add", "-A")
    run("git", "commit", "-q", "-m", "add calculate_discount, only member path tested")

    diff = run("git", "diff", "HEAD~1", "HEAD").stdout
    pr_sha = run("git", "rev-parse", "HEAD").stdout.strip()
    return str(repo), diff, pr_sha


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        repo_url, diff, pr_sha = build_fixture_repo(tmp_path)

        # LocalSandboxClient's cwd is just where subprocess runs from --
        # checkout_repo() clones to an absolute repo_path regardless, same
        # as it would against NebiusSandboxClient.
        sandbox = LocalSandboxClient(cwd=str(tmp_path))
        # Relative to the sandbox cwd; absolute paths also work now (audit B11 fixed).
        repo_path = "checked_out_repo"

        print(f"=== Checking out PR {pr_sha[:8]} into sandbox, running pytest+coverage for real ===")
        result = run_pipeline(
            sandbox=sandbox,
            repo_url=repo_url,
            ref=pr_sha,
            diff=diff,
            changed_py_files=["billing.py"],  # test_billing.py is the test file itself, not a gap target
            config=PipelineConfig(max_attempts_per_gap=2),
            repo_path=repo_path,
            generate=generator_stub.generate_test,  # offline demo: canned tests, no LLM
        )

        print(f"\ngaps_found={result.gaps_found} "
              f"tests_generated={result.tests_generated} "
              f"verified_pass={result.tests_verified_pass} "
              f"verified_fail={result.tests_verified_fail} "
              f"errored={result.tests_errored} "
              f"duration={result.duration_seconds:.2f}s")

        # Sanity checks mirroring Section 1's demo.py style: assert on the
        # real pipeline's real output, not just print it.
        assert result.gaps_found == 3, f"expected 3 gaps (matches Section 1's own demo), got {result.gaps_found}"
        assert result.tests_verified_pass == 3, (
            f"expected all 3 gaps verified -- two on attempt 1, one (the "
            f"else-body gap) only after a real retry fixes a real failure, "
            f"got {result.tests_verified_pass}"
        )
        # The else-body gap is the one that proves the retry loop, not just
        # the happy path: attempt 1 is a genuinely broken candidate (bad
        # import), real pytest reports a real ModuleNotFoundError, that
        # failure text flows back into generate_test() as prior_failure,
        # and attempt 2 passes AND hits the target lines.
        else_body = next(r for r in result.records if r.gap.start_line == 8)
        assert len(else_body.attempts) == 2, "expected the else-body gap to need exactly 2 attempts"
        assert else_body.verifications[0].status == "fail", "attempt 1 should have genuinely failed in real pytest"
        assert "ModuleNotFoundError" in else_body.verifications[0].message
        assert else_body.verifications[1].verified, "attempt 2 should pass AND hit the target lines"
        print(f"\nRetry loop proven: {else_body.gap} failed on attempt 1 with a real")
        print(f"ModuleNotFoundError from pytest, then passed on attempt 2 once the")
        print(f"(stubbed) generator used that failure message to fix the import.")

        print("\n=== Rendered report ===\n")
        print(result.report_markdown)

        print("\nOK: full pipeline -- real git checkout, real pytest/coverage run,")
        print("    real gap-finding, real retry loop -- proven end to end.")


if __name__ == "__main__":
    main()
