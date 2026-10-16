"""Unit tests for cli.py's --install-deps guard. No network, no subprocess."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cli  # noqa: E402


def _argv(*extra):
    return ["cli.py", "--repo-url", "x", "--ref", "main", "--diff-file", "does-not-exist.diff",
            "--changed-files", "a.py", *extra]


def test_install_deps_local_refused_outside_venv(monkeypatch, capsys):
    monkeypatch.setattr(sys, "prefix", "/usr")
    monkeypatch.setattr(sys, "base_prefix", "/usr")
    monkeypatch.setattr(sys, "argv", _argv("--install-deps", "--sandbox", "local"))
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert "refusing outside a virtualenv" in capsys.readouterr().err


def test_install_deps_local_allowed_inside_venv(monkeypatch):
    monkeypatch.setattr(sys, "prefix", "/home/u/.venvs/vtga")
    monkeypatch.setattr(sys, "base_prefix", "/usr")
    monkeypatch.setattr(sys, "argv", _argv("--install-deps", "--sandbox", "local"))
    # Guard passes, so main() proceeds to open the (missing) diff file.
    with pytest.raises(FileNotFoundError):
        cli.main()
