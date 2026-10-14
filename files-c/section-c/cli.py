"""
Minimal CLI entry point for run_pipeline(), for anyone who wants to point
this at a real PR instead of the fixture in demo_pipeline.py.

    python3 cli.py --repo-url <git-url> --ref <sha-or-branch> \
        --diff-file <path-to-diff.txt> --changed-files billing.py,other.py

For a real GitHub PR you'd typically fetch the diff and the changed-file
list via `gh pr diff` / the GitHub API first, then pass the results here --
that fetching step is intentionally left out of this file since it depends
on which git host / auth this project ends up wired to.
"""

from __future__ import annotations

import argparse
import os
import sys

import _paths  # noqa: F401  (section-a on sys.path)
from pipeline_models import PipelineConfig
from run_pipeline import run_pipeline
from sandbox_client import LocalSandboxClient, NebiusSandboxClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the verified test-gap agent against a PR diff.")
    parser.add_argument("--repo-url", required=True, help="git URL or local path to clone")
    parser.add_argument("--ref", required=True, help="commit SHA or branch to check out (the PR head)")
    parser.add_argument("--diff-file", required=True, help="path to a file containing the PR's unified diff")
    parser.add_argument("--changed-files", required=True, help="comma-separated list of changed .py files")
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--sandbox", choices=["local", "nebius"], default="local",
                        help="local: plain subprocess, NO isolation (trusted code only). "
                             "nebius: contree CLI, needs `contree auth` first (unverified end to end)")
    parser.add_argument("--sandbox-cwd", default="/tmp/_pipeline_sandbox", help="LocalSandboxClient working dir")
    parser.add_argument("--repo-path", default="checked_out_repo",
                        help="where the repo is cloned inside the sandbox (relative to --sandbox-cwd, or absolute)")
    parser.add_argument("--install-deps", action="store_true",
                        help="pip-install pytest, coverage and requirements.txt in the sandbox after checkout; "
                             "with --sandbox local this installs into the current interpreter")
    parser.add_argument("--output", default=None, help="write the markdown report here; default: stdout")
    args = parser.parse_args()

    with open(args.diff_file) as f:
        diff = f.read()
    changed_py_files = [f.strip() for f in args.changed_files.split(",") if f.strip()]

    if args.sandbox == "nebius":
        sandbox = NebiusSandboxClient()
    else:
        os.makedirs(args.sandbox_cwd, exist_ok=True)
        sandbox = LocalSandboxClient(cwd=args.sandbox_cwd)

    result = run_pipeline(
        sandbox=sandbox,
        repo_url=args.repo_url,
        ref=args.ref,
        diff=diff,
        changed_py_files=changed_py_files,
        config=PipelineConfig(max_attempts_per_gap=args.max_attempts),
        repo_path=args.repo_path,
        install_deps=args.install_deps,
    )

    if args.output:
        with open(args.output, "w") as f:
            f.write(result.report_markdown)
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(result.report_markdown)


if __name__ == "__main__":
    main()
