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
def _no_token_factory_env(monkeypatch):
    for name in list(os.environ):
        if name.startswith("TOKEN_FACTORY_"):
            monkeypatch.delenv(name)


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
