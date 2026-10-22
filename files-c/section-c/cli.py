"""
Minimal CLI entry point for run_pipeline(), for anyone who wants to point
this at a real PR instead of the fixture in demo_pipeline.py.

    python3 cli.py --repo-url <git-url> --ref <sha-or-branch> --diff-file <path-to-diff.txt>

--changed-files defaults to every .py file the diff adds lines to, minus test
files (test_*.py, *_test.py, conftest.py).

--generator llm (default) calls Nemotron on Nebius Token Factory and needs
TOKEN_FACTORY_API_KEY, TOKEN_FACTORY_BASE_URL and TOKEN_FACTORY_MODEL_NANO /
_SUPER / _ULTRA (one per attempt tier), from the environment or the repo-root
.env. --generator stub is the offline placeholder from generator_stub.py
(canned tests for the billing fixture only).

For a real GitHub PR you'd typically fetch the diff via `gh pr diff` / the
GitHub API first, then pass it here --
that fetching step is intentionally left out of this file since it depends
on which git host / auth this project ends up wired to.
"""

from __future__ import annotations

import argparse
import os
import sys

import _paths  # noqa: F401  (section-a and section-b on sys.path)
import generator
import generator_stub
from coverage_diff import changed_lines_by_file
from pipeline_models import PipelineConfig
from run_pipeline import run_pipeline
from sandbox_client import LocalSandboxClient


def is_test_file(path: str) -> bool:
    name = os.path.basename(path)
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def changed_py_files_from_diff(diff: str) -> list[str]:
    """Non-test .py files the diff adds or changes lines in (deletion-only files have nothing to cover)."""
    return sorted(f for f, lines in changed_lines_by_file(diff).items()
                  if lines and f.endswith(".py") and not is_test_file(f))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the verified test-gap agent against a PR diff.")
    parser.add_argument("--repo-url", required=True, help="git URL or local path to clone")
    parser.add_argument("--ref", required=True, help="commit SHA or branch to check out (the PR head)")
    parser.add_argument("--diff-file", required=True, help="path to a file containing the PR's unified diff")
    parser.add_argument("--changed-files", default=None,
                        help="comma-separated .py files to analyse; default: the non-test .py files in the diff")
    parser.add_argument("--max-attempts", type=int, default=PipelineConfig.max_attempts_per_gap)
    parser.add_argument("--max-gaps", type=int, default=PipelineConfig.max_gaps,
                        help="gaps that may call the LLM; the rest are reported as skipped")
    parser.add_argument("--generator", choices=["llm", "stub"], default="llm",
                        help="llm: Nemotron on Nebius Token Factory (needs TOKEN_FACTORY_* env). "
                             "stub: offline canned tests, demos/tests only")
    parser.add_argument("--sandbox-cwd", default="/tmp/_pipeline_sandbox",
                        help="bwrap sandbox working dir, the only path that persists between commands")
    parser.add_argument("--repo-path", default="checked_out_repo",
                        help="where the repo is cloned inside the sandbox (relative to --sandbox-cwd)")
    parser.add_argument("--install-deps", action="store_true",
                        help="pip-install pytest, coverage and requirements.txt into the sandbox workdir "
                             "after checkout (with network)")
    parser.add_argument("--output", default=None, help="write the markdown report here; default: stdout")
    args = parser.parse_args()

    if args.generator == "llm":
        generator.load_env_file()
        missing = generator.missing_env(args.max_attempts)
        if missing:
            parser.error(f"--generator llm needs {', '.join(missing)} in the environment "
                         "(Nebius Token Factory); use --generator stub only for offline demos")
        generate = generator.generate_test
    else:
        generate = generator_stub.generate_test

    with open(args.diff_file) as f:
        diff = f.read()
    if args.changed_files is None:
        changed_py_files = changed_py_files_from_diff(diff)
        print(f"Analysing {len(changed_py_files)} file(s) from the diff: {', '.join(changed_py_files)}",
              file=sys.stderr)
    else:
        changed_py_files = [f.strip() for f in args.changed_files.split(",") if f.strip()]

    os.makedirs(args.sandbox_cwd, exist_ok=True)
    # A local repo path must be visible read-only inside bwrap for git clone.
    ro_paths = [args.repo_url] if os.path.isdir(args.repo_url) else []
    sandbox = LocalSandboxClient(cwd=args.sandbox_cwd, ro_paths=ro_paths)

    result = run_pipeline(
        sandbox=sandbox,
        repo_url=args.repo_url,
        ref=args.ref,
        diff=diff,
        changed_py_files=changed_py_files,
        config=PipelineConfig(max_attempts_per_gap=args.max_attempts, max_gaps=args.max_gaps),
        repo_path=args.repo_path,
        install_deps=args.install_deps,
        generate=generate,
    )

    if args.output:
        with open(args.output, "w") as f:
            f.write(result.report_markdown)
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(result.report_markdown)


if __name__ == "__main__":
    main()
