"""Child processes run by the sandbox clients must not see API keys."""
import os

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
