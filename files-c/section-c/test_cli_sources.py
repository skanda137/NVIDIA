"""cli.py diff sources: --pr-url (GitHub API stubbed, no network) and --base-ref (real git in bwrap)."""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cli  # noqa: E402
from demo_pipeline import build_fixture_repo  # noqa: E402
from sandbox_client import LocalSandboxClient  # noqa: E402

PR = {"head": {"sha": "abc123", "repo": None},  # head fork deleted: must not matter
      "base": {"repo": {"clone_url": "https://github.com/owner/proj.git"}}}
DIFF = "--- a/x.py\n+++ b/x.py\n@@ -0,0 +1 @@\n+y = 1\n"


def _fake_github(calls, pr=PR):
    def get(url, accept):
        calls.append((url, accept))
        return DIFF.encode() if accept.endswith(".diff") else json.dumps(pr).encode()
    return get


def test_fetch_pr_returns_upstream_clone_url_head_sha_and_pull_ref(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_github_get", _fake_github(calls))
    assert cli.fetch_pr("https://github.com/owner/proj/pull/42") == (
        "https://github.com/owner/proj.git", "abc123", DIFF, "pull/42/head")
    assert {u for u, _ in calls} == {"https://api.github.com/repos/owner/proj/pulls/42"}


@pytest.mark.parametrize("url", ["https://github.com/owner/proj", "https://gitlab.com/o/p/pull/1",
                                 "https://github.com/owner/proj/pull/42/files"])
def test_fetch_pr_rejects_non_pr_urls(url):
    with pytest.raises(ValueError, match="not a GitHub PR URL"):
        cli.fetch_pr(url)


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def test_checkout_of_pr_ref_that_only_upstream_has(tmp_path):
    """Like a merged PR from a deleted fork: the head commit is on no branch of the
    upstream repo, only under refs/pull/7/head, so a plain clone cannot check it out."""
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "init", "-q", "-b", "main")
    _git(work, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "base")
    _git(work, "checkout", "-q", "-b", "feature")
    (work / "f.py").write_text("x = 1\n")
    _git(work, "add", "f.py")
    _git(work, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "pr")
    head = _git(work, "rev-parse", "HEAD")
    upstream = tmp_path / "upstream.git"
    _git(tmp_path, "init", "-q", "--bare", str(upstream))
    _git(work, "push", "-q", str(upstream), "main", f"{head}:refs/pull/7/head")

    (tmp_path / "sbx").mkdir()
    sb = LocalSandboxClient(cwd=str(tmp_path / "sbx"), ro_paths=[str(upstream)])
    url = f"file://{upstream}"  # real transport: a plain path clone would copy unreachable objects too
    with pytest.raises(RuntimeError, match="failed to check out"):
        cli.checkout_repo(sb, "repo", url, head)
    cli.checkout_repo(sb, "repo", url, head, fetch_ref="pull/7/head")
    assert sb.read_file("repo/f.py") == "x = 1\n"


def test_base_ref_diff_matches_git_diff(tmp_path):
    url, diff, sha = build_fixture_repo(tmp_path)
    (tmp_path / "sbx").mkdir()
    sb = LocalSandboxClient(cwd=str(tmp_path / "sbx"), ro_paths=[url])
    assert cli.diff_from_base_ref(sb, "repo", url, sha, f"{sha}~1") == diff


@pytest.mark.parametrize("argv, message", [
    (["--repo-url", "r", "--ref", "h"], "one of the arguments --pr-url --base-ref --diff-file is required"),
    (["--pr-url", "https://github.com/o/p/pull/1", "--ref", "h"], "drop --repo-url/--ref"),
    (["--base-ref", "main", "--ref", "h"], "--repo-url and --ref are required"),
])
def test_argument_rules(monkeypatch, capsys, argv, message):
    monkeypatch.setattr(sys, "argv", ["cli.py", *argv, "--generator", "stub"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert message in capsys.readouterr().err
