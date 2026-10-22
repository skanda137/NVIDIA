"""cli.py --generator: llm fails fast without Token Factory env. No network."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cli  # noqa: E402


def _argv(*extra):
    return ["cli.py", "--repo-url", "x", "--ref", "main", "--diff-file", "does-not-exist.diff",
            "--changed-files", "a.py", *extra]


@pytest.fixture(autouse=True)
def _no_token_factory_env(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith("TOKEN_FACTORY_"):
            monkeypatch.delenv(name)
    monkeypatch.setattr(cli.generator, "ENV_FILE", tmp_path / "no.env")  # not the real repo .env


def test_llm_reads_repo_env_file(monkeypatch, tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text("TOKEN_FACTORY_API_KEY=k\nexport TOKEN_FACTORY_BASE_URL='https://x/v1/'\nOTHER=1\n")
    monkeypatch.setattr(cli.generator, "ENV_FILE", env)
    for name in ("TOKEN_FACTORY_API_KEY", "TOKEN_FACTORY_BASE_URL"):  # so teardown removes what the load sets
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    monkeypatch.setattr(sys, "argv", _argv())
    with pytest.raises(SystemExit):
        cli.main()
    err = capsys.readouterr().err
    assert "TOKEN_FACTORY_MODEL_NANO" in err and "TOKEN_FACTORY_API_KEY" not in err
    assert os.environ["TOKEN_FACTORY_BASE_URL"] == "https://x/v1/" and "OTHER" not in os.environ


def test_changed_files_default_to_non_test_py_files_in_diff():
    diff = ("--- a/app/b.py\n+++ b/app/b.py\n@@ -1 +1,2 @@\n x\n+y\n"
            "--- a/tests/test_b.py\n+++ b/tests/test_b.py\n@@ -0,0 +1 @@\n+t\n"
            "--- a/README.md\n+++ b/README.md\n@@ -0,0 +1 @@\n+r\n"
            "--- a/gone.py\n+++ b/gone.py\n@@ -1 +0,0 @@\n-z\n"
            "--- a/conftest.py\n+++ b/conftest.py\n@@ -0,0 +1 @@\n+c\n")
    assert cli.changed_py_files_from_diff(diff) == ["app/b.py"]


def test_llm_is_default_and_fails_fast_without_env(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", _argv())
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "--generator llm needs TOKEN_FACTORY_API_KEY" in err
    assert "TOKEN_FACTORY_MODEL_ULTRA" in err  # default 3 attempts -> all three tiers


def test_llm_only_requires_tiers_the_attempts_use(monkeypatch, capsys):
    for v in ("TOKEN_FACTORY_API_KEY", "TOKEN_FACTORY_BASE_URL", "TOKEN_FACTORY_MODEL_NANO"):
        monkeypatch.setenv(v, "x")
    monkeypatch.setattr(sys, "argv", _argv("--max-attempts", "2"))
    with pytest.raises(SystemExit):
        cli.main()
    err = capsys.readouterr().err
    assert "TOKEN_FACTORY_MODEL_SUPER" in err and "TOKEN_FACTORY_MODEL_ULTRA" not in err


def test_stub_needs_no_env(monkeypatch):
    monkeypatch.setattr(sys, "argv", _argv("--generator", "stub"))
    with pytest.raises(FileNotFoundError):  # got past the env check to opening the diff file
        cli.main()
