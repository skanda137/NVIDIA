"""eval/run_eval.py --repos-dir: loading two-commit repos. No LLM, no sandbox."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_eval  # noqa: E402


def _git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _repo(root: Path, name: str, commits: int) -> Path:
    repo = root / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-q", "-b", "main")
    (repo / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (repo / "test_calc.py").write_text("from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    for i in range(1, commits):
        (repo / "calc.py").write_text((repo / "calc.py").read_text() + f"\n\ndef f{i}(x):\n    return x * {i}\n")
        _git(repo, "commit", "-q", "-am", f"head {i}")
    return repo


def test_load_repos_two_commit_fixture(tmp_path):
    repo = _repo(tmp_path / "repos", "calc", commits=2)
    (spec,) = run_eval.load_repos(tmp_path / "repos")
    base, head = _git(repo, "rev-list", "--reverse", "HEAD").split()
    assert (spec.name, spec.base_sha, spec.pr_sha) == ("calc", base, head)
    assert spec.diff == _git(repo, "diff", f"{base}..{head}") + "\n"
    assert "+def f1(x):" in spec.diff
    assert spec.changed_files == ["calc.py"]
    assert spec.categories == {}


@pytest.mark.parametrize("commits", [1, 3])
def test_load_repos_rejects_other_commit_counts(tmp_path, commits):
    _repo(tmp_path / "repos", "calc", commits=commits)
    with pytest.raises(ValueError, match=f"expected exactly 2 commits \\(base, head\\), found {commits}"):
        run_eval.load_repos(tmp_path / "repos")


def test_load_repos_rejects_empty_dir_and_non_git(tmp_path):
    (tmp_path / "repos").mkdir()
    with pytest.raises(ValueError, match="no repo subdirectories"):
        run_eval.load_repos(tmp_path / "repos")
    (tmp_path / "repos" / "plain").mkdir()
    with pytest.raises(ValueError, match="is not a git repo"):
        run_eval.load_repos(tmp_path / "repos")
