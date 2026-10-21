"""Section 2 unit tests never reach the network: every test starts with no
TOKEN_FACTORY_* variables and an OpenAI client constructor that raises."""
import os

import openai
import pytest

import generator


class NetworkBlocked(RuntimeError):
    pass


def _no_client(*args, **kwargs):
    raise NetworkBlocked("unit tests must not construct an OpenAI client; pass llm=")


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    for name in list(os.environ):
        if name.startswith("TOKEN_FACTORY_"):
            monkeypatch.delenv(name)
    monkeypatch.setattr(openai, "OpenAI", _no_client)
    generator._client.cache_clear()
    yield
    generator._client.cache_clear()
