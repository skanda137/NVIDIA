"""Child processes run by the sandbox clients must not see API keys."""
import os
import sys

import pytest

from sandbox_client import LocalSandboxClient, scrubbed_env

PLANTED = "planted-fake-value-3f9c1e"


def test_local_sandbox_env_does_not_leak_token_factory_key(monkeypatch, tmp_path):
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", PLANTED)
    assert os.environ["TOKEN_FACTORY_API_KEY"] == PLANTED
    r = LocalSandboxClient(cwd=str(tmp_path)).run("env")
    assert r.ok
    assert "PATH=" in r.stdout
    assert PLANTED not in r.stdout + r.stderr


def test_scrubbed_env_drop_rules(monkeypatch):
    for name in ("OPENAI_API_KEY", "GH_TOKEN", "my_secret", "NEBIUS_PROFILE", "TOKEN_FACTORY_BASE_URL"):
        monkeypatch.setenv(name, "x")
    monkeypatch.setenv("KEEP_ME_NOT", "x")  # contains KEY? no: "KEEP" is not "KEY"
    env = scrubbed_env()
    for name in ("OPENAI_API_KEY", "GH_TOKEN", "my_secret", "NEBIUS_PROFILE", "TOKEN_FACTORY_BASE_URL"):
        assert name not in env
    assert env["KEEP_ME_NOT"] == "x"
    assert "PATH" in env


# Isolation proofs: the bwrap mounts, not just the env scrub, keep generated code in.
REPO_ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")


@pytest.mark.parametrize("exe", ["/tmp/clone/.venv/bin/python", "/mnt/c/Users/x/repo/.venv/bin/python"])
def test_python_hidden_by_sandbox_fails_fast(monkeypatch, tmp_path, exe):
    """The fresh-clone failure: a .venv inside a clone under /tmp or /mnt/c is masked inside
    bwrap. The client must refuse up front instead of failing every test run later."""
    if exe.startswith("/mnt/c") and not os.path.isdir("/mnt/c"):
        pytest.skip("no /mnt/c on this machine")
    monkeypatch.setattr(sys, "executable", exe)
    with pytest.raises(RuntimeError, match=r"under /(tmp|mnt/c), which the sandbox hides.*venv under \$HOME"):
        LocalSandboxClient(cwd=str(tmp_path))


def test_python_under_home_is_accepted(tmp_path):
    assert sys.executable.startswith(os.path.expanduser("~")), "test suite must run from a venv under $HOME"
    LocalSandboxClient(cwd=str(tmp_path))


def test_hidden_python_really_is_not_found_inside_the_sandbox(tmp_path):
    """Reproduces the failure the check prevents: an interpreter under /tmp is not there inside bwrap."""
    fake = tmp_path / "venv" / "bin" / "python"
    fake.parent.mkdir(parents=True)
    fake.symlink_to(sys.executable)
    assert os.path.exists(fake)
    (tmp_path / "sbx").mkdir()
    sb = LocalSandboxClient(cwd=str(tmp_path / "sbx"))
    r = sb.run(f"{fake} -c 'print(1)'")
    assert not r.ok and "not found" in r.stderr, r.stderr


def test_writes_outside_workdir_fail_read_only(tmp_path):
    sb = LocalSandboxClient(cwd=str(tmp_path))
    for target in ("/usr/_sbx_probe", "/etc/_sbx_probe", os.path.join(sys.prefix, "_sbx_probe")):
        r = sb.run(f"echo x > {target}")
        assert not r.ok
        assert "Read-only file system" in r.stderr, r.stderr
        assert not os.path.exists(target)
    home_probe = os.path.expanduser("~/_sbx_probe")  # $HOME is a throwaway tmpfs inside
    assert sb.run(f"echo x > {home_probe}").ok
    assert not os.path.exists(home_probe)
    assert sb.run("echo x > inside.txt").ok
    assert (tmp_path / "inside.txt").read_text() == "x\n"


def test_repo_env_and_home_config_are_masked(tmp_path):
    sb = LocalSandboxClient(cwd=str(tmp_path))
    for secret in (REPO_ENV, os.path.expanduser("~/.config"), os.path.expanduser("~/.ssh")):
        r = sb.run(f"cat {secret} 2>&1; ls -A {secret} 2>&1")
        assert "TOKEN_FACTORY" not in r.stdout
        assert "No such file or directory" in r.stdout, r.stdout


def test_default_run_has_no_network(tmp_path):
    probe = ("python3 -c \"import socket; s = socket.socket(); s.settimeout(3); "
             "s.connect(('1.1.1.1', 443)); print('CONNECTED')\"")
    sb = LocalSandboxClient(cwd=str(tmp_path))
    r = sb.run(probe)
    assert not r.ok
    assert "CONNECTED" not in r.stdout
    assert "Network is unreachable" in r.stderr, r.stderr
