"""
Minimal CLI entry point for run_pipeline(), for anyone who wants to point
this at a real PR instead of the fixture in demo_pipeline.py.

    python3 cli.py --pr-url https://github.com/<owner>/<repo>/pull/<n>
    python3 cli.py --repo-url <git-url-or-path> --ref <head> --base-ref <base>
    python3 cli.py --repo-url <git-url-or-path> --ref <head> --diff-file <pr.diff>

--pr-url reads the head SHA and diff from the public GitHub REST API (no auth:
public repos, 60 requests/hour), clones the upstream repo and fetches the PR's
pull/<n>/head ref, so a PR from a since-deleted fork still checks out. --base-ref diffs base...ref inside
the sandbox's clone, so it works for local paths and remote URLs alike.

--changed-files defaults to every .py file the diff adds lines to, minus test
files (test_*.py, *_test.py, conftest.py).

--generator llm (default) calls Nemotron on Nebius Token Factory and needs
TOKEN_FACTORY_API_KEY, TOKEN_FACTORY_BASE_URL and TOKEN_FACTORY_MODEL_NANO /
_SUPER / _ULTRA (one per attempt tier), from the environment or the repo-root
.env. --generator stub is the offline placeholder from generator_stub.py
(canned tests for the billing fixture only).

"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sys
import urllib.error
import urllib.request

import _paths  # noqa: F401  (section-a and section-b on sys.path)
import generator
import generator_stub
from coverage_diff import changed_lines_by_file
from pipeline_models import PipelineConfig
from run_pipeline import checkout_repo, run_pipeline
from sandbox_client import LocalSandboxClient


def is_test_file(path: str) -> bool:
    name = os.path.basename(path)
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"


def changed_py_files_from_diff(diff: str) -> list[str]:
    """Non-test .py files the diff adds or changes lines in (deletion-only files have nothing to cover)."""
    return sorted(f for f, lines in changed_lines_by_file(diff).items()
                  if lines and f.endswith(".py") and not is_test_file(f))


PR_URL = re.compile(r"https://github\.com/([\w.-]+)/([\w.-]+)/pull/(\d+)/?$")


def _github_get(url: str, accept: str) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "verified-test-gap-agent"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:  # 404: no such PR or a private repo; 403: rate limit
        raise RuntimeError(f"GitHub API {url}: HTTP {e.code} {e.reason}") from None


def fetch_pr(pr_url: str) -> tuple[str, str, str, str]:
    """(upstream clone_url, head_sha, unified diff, fetch_ref) of a public GitHub PR.
    The upstream repo, not the head fork: GitHub keeps pull/<n>/head there even
    after the fork is deleted, which is common for merged PRs."""
    m = PR_URL.match(pr_url)
    if not m:
        raise ValueError(f"not a GitHub PR URL: {pr_url} (want https://github.com/<owner>/<repo>/pull/<n>)")
    api = "https://api.github.com/repos/{}/{}/pulls/{}".format(*m.groups())
    pr = json.loads(_github_get(api, "application/vnd.github+json"))
    diff = _github_get(api, "application/vnd.github.diff").decode("utf-8")
    return pr["base"]["repo"]["clone_url"], pr["head"]["sha"], diff, f"pull/{m.group(3)}/head"


def diff_from_base_ref(sandbox, repo_path: str, repo_url: str, ref: str, base_ref: str) -> str:
    """Clone repo_url@ref into the sandbox and diff base_ref...HEAD there (offline).
    base_ref may be a SHA, a local branch, or a branch that only exists as origin/<name>."""
    checkout_repo(sandbox, repo_path, repo_url, ref)
    path = shlex.quote(repo_path)
    base, remote_base = shlex.quote(f"{base_ref}...HEAD"), shlex.quote(f"origin/{base_ref}...HEAD")
    result = sandbox.run(f"cd {path} && {{ git diff {base} 2>/dev/null || git diff {remote_base}; }}")
    if not result.ok:
        raise RuntimeError(f"git diff {base_ref}...{ref} failed:\n{result.stderr[-2000:]}")
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the verified test-gap agent against a PR diff.")
    parser.add_argument("--repo-url", help="git URL or local path to clone (not with --pr-url)")
    parser.add_argument("--ref", help="commit SHA or branch to check out, the PR head (not with --pr-url)")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pr-url", help="public GitHub PR: repo, head and diff all come from the API")
    source.add_argument("--base-ref", help="diff BASE_REF...REF inside the sandbox clone")
    source.add_argument("--diff-file", help="path to a file containing the PR's unified diff")
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
    if args.pr_url and (args.repo_url or args.ref):
        parser.error("--pr-url sets the repo and head itself; drop --repo-url/--ref")
    if not args.pr_url and not (args.repo_url and args.ref):
        parser.error("--repo-url and --ref are required unless --pr-url is given")

    if args.generator == "llm":
        generator.load_env_file()
        missing = generator.missing_env(args.max_attempts)
        if missing:
            parser.error(f"--generator llm needs {', '.join(missing)} in the environment "
                         "(Nebius Token Factory); use --generator stub only for offline demos")
        generate = generator.generate_test
    else:
        generate = generator_stub.generate_test

    os.makedirs(args.sandbox_cwd, exist_ok=True)
    # A local repo path must be visible read-only inside bwrap for git clone.
    ro_paths = [args.repo_url] if args.repo_url and os.path.isdir(args.repo_url) else []
    sandbox = LocalSandboxClient(cwd=args.sandbox_cwd, ro_paths=ro_paths)

    fetch_ref = None
    if args.pr_url:
        args.repo_url, args.ref, diff, fetch_ref = fetch_pr(args.pr_url)
        print(f"PR head {args.ref[:8]} from {args.repo_url}", file=sys.stderr)
    elif args.base_ref:
        diff = diff_from_base_ref(sandbox, args.repo_path, args.repo_url, args.ref, args.base_ref)
    else:
        with open(args.diff_file) as f:
            diff = f.read()
    if args.changed_files is None:
        changed_py_files = changed_py_files_from_diff(diff)
        print(f"Analysing {len(changed_py_files)} file(s) from the diff: {', '.join(changed_py_files)}",
              file=sys.stderr)
    else:
        changed_py_files = [f.strip() for f in args.changed_files.split(",") if f.strip()]

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
        fetch_ref=fetch_ref,
    )

    if args.output:
        with open(args.output, "w") as f:
            f.write(result.report_markdown)
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(result.report_markdown)


if __name__ == "__main__":
    main()
