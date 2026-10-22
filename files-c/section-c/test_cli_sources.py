"""cli.py diff sources: --pr-url (GitHub API stubbed, no network) and --base-ref (real git in bwrap)."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cli  # noqa: E402
from demo_pipeline import build_fixture_repo  # noqa: E402
from sandbox_client import LocalSandboxClient  # noqa: E402

PR = {"head": {"sha": "abc123", "repo": {"clone_url": "https://github.com/fork/proj.git"}}}
DIFF = "--- a/x.py\n+++ b/x.py\n@@ -0,0 +1 @@\n+y = 1\n"


def _fake_github(calls, pr=PR):
    def get(url, accept):
        calls.append((url, accept))
        return DIFF.encode() if accept.endswith(".diff") else json.dumps(pr).encode()
    return get


def test_fetch_pr_returns_head_clone_url_and_diff(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_github_get", _fake_github(calls))
    assert cli.fetch_pr("https://github.com/owner/proj/pull/42") == ("https://github.com/fork/proj.git", "abc123", DIFF)
    assert {u for u, _ in calls} == {"https://api.github.com/repos/owner/proj/pulls/42"}


@pytest.mark.parametrize("url", ["https://github.com/owner/proj", "https://gitlab.com/o/p/pull/1",
                                 "https://github.com/owner/proj/pull/42/files"])
def test_fetch_pr_rejects_non_pr_urls(url):
    with pytest.raises(ValueError, match="not a GitHub PR URL"):
        cli.fetch_pr(url)


def test_fetch_pr_deleted_head_repo(monkeypatch):
    monkeypatch.setattr(cli, "_github_get", _fake_github([], {"head": {"sha": "abc", "repo": None}}))
    with pytest.raises(ValueError, match="head repository was deleted"):
        cli.fetch_pr("https://github.com/owner/proj/pull/42")


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
