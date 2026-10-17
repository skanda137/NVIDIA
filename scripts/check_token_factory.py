"""Evidence check for the Nebius Token Factory inference API.

Reads TOKEN_FACTORY_BASE_URL and TOKEN_FACTORY_API_KEY from the environment,
lists models, prints Nemotron IDs and the nano/super/ultra tier picks, then makes
ONE chat completion (max_tokens 32) on the smallest Nemotron model. Exits
non-zero on any failure. Never prints the key.
"""
import os
import re
import sys
import time

from openai import OpenAI


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"ERROR: {name} is not set")
    return value


def _size_b(model_id: str):
    """Total parameter count in billions: the first size in the ID (30B in 30B-A3B), or None."""
    sizes = [float(m) for m in re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)[bB](?![a-zA-Z])", model_id)]
    return sizes[0] if sizes else None


def main() -> int:
    base_url = _env("TOKEN_FACTORY_BASE_URL")
    client = OpenAI(base_url=base_url, api_key=_env("TOKEN_FACTORY_API_KEY"), timeout=60, max_retries=0)

    ids = sorted(m.id for m in client.models.list())
    nemotron = [i for i in ids if "nemotron" in i.lower()]
    print(f"base_url: {base_url}")
    print(f"models listed: {len(ids)}; nemotron: {len(nemotron)}")
    for i in nemotron:
        print(f"  {i}")
    if not nemotron:
        print("ERROR: no Nemotron model IDs listed", file=sys.stderr)
        return 1

    for tier in ("nano", "super", "ultra"):
        matches = [i for i in nemotron if tier in i.lower()]
        if not matches:
            print(f"TIER {tier}: MISSING")
        else:
            note = f" (chosen from {len(matches)} matches: lexicographically greatest)" if len(matches) > 1 else ""
            print(f"TIER {tier}: {max(matches)}{note}")

    sized = [(s, i) for i in nemotron if (s := _size_b(i)) is not None]
    if not sized:
        print("ERROR: no Nemotron ID has a parseable parameter size; cannot pick the smallest", file=sys.stderr)
        return 1
    size, model = min(sized)
    print(f"smallest nemotron: {model} ({size:g}B)")

    start = time.monotonic()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with the single word: pong"}],
        max_tokens=32,
    )
    latency = time.monotonic() - start
    usage = resp.usage
    print(f"completion model: {resp.model}")
    print(f"latency_s: {latency:.2f}")
    print(f"usage: prompt={usage.prompt_tokens} completion={usage.completion_tokens} total={usage.total_tokens}")
    print(f"reply: {(resp.choices[0].message.content or '').strip()[:200]!r}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # report the failure type and message, then exit non-zero
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
