"""Live evidence for the Nebius Token Factory inference API. 4 API calls in total.

Reads TOKEN_FACTORY_API_KEY and TOKEN_FACTORY_BASE_URL from the environment or the
repo-root .env (never prints the key). GETs {base}/models, prints every Nemotron ID with
the fields the endpoint returns about features or context, picks the nano/super/ultra
tiers with generator.discover_tier_models (keyword only), then makes ONE chat completion
per tier with the generator's real SYSTEM_PROMPT and thinking switch, the user message
"Reply with exactly: OK" and max_tokens 64. Prints latency, finish_reason, content,
whether the message carries reasoning (it should not), usage, and `export` lines for the
chosen tier IDs. Exits non-zero if a tier
has no keyword match or any call fails.

    python scripts/check_token_factory.py
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "files-c" / "section-b"))
import generator  # noqa: E402  (SYSTEM_PROMPT, discover_tier_models, _TIER_ENV)

from openai import OpenAI  # noqa: E402

FIELD_WORDS = ("feature", "context")


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"ERROR: {name} is not set")
    return value


def _matching_fields(data, prefix=""):
    """(dotted key, value) for every field whose key mentions a FIELD_WORDS word."""
    out = []
    if isinstance(data, dict):
        for k, v in data.items():
            key = f"{prefix}{k}"
            if any(w in str(k).lower() for w in FIELD_WORDS):
                out.append((key, v))
            else:
                out.extend(_matching_fields(v, key + "."))
    return out


def main() -> int:
    generator.load_env_file()  # repo-root .env; variables already exported win
    base_url = _env("TOKEN_FACTORY_BASE_URL")
    client = OpenAI(base_url=base_url, api_key=_env("TOKEN_FACTORY_API_KEY"), timeout=60, max_retries=0)

    models = list(client.models.list())
    nemotron = sorted((m for m in models if "nemotron" in m.id.lower()), key=lambda m: m.id)
    print(f"base_url: {base_url}")
    print(f"models listed: {len(models)}; nemotron: {len(nemotron)}")
    for m in nemotron:
        print(f"  {m.id}")
        for key, value in _matching_fields(m.model_dump()):
            print(f"      {key}: {value!r}")

    tiers = generator.discover_tier_models([m.id for m in nemotron])
    missing = [t for t in generator.TIERS if t not in tiers]
    for tier in generator.TIERS:
        print(f"TIER {tier}: {tiers.get(tier, 'MISSING (no keyword match)')}")
    if missing:
        print(f"STOP: no keyword match for {', '.join(missing)}; not substituting by size", file=sys.stderr)
        return 1

    failed, prompt_total, completion_total = False, 0, 0
    for tier in generator.TIERS:
        model = tiers[tier]
        print(f"\n--- {tier}: {model}")
        start = time.monotonic()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": generator.SYSTEM_PROMPT},
                          {"role": "user", "content": "Reply with exactly: OK"}],
                max_tokens=64,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},  # as generator.py sends
            )
        except Exception as exc:  # report and keep going, so one call per tier still happens
            print(f"ERROR after {time.monotonic() - start:.2f}s: {type(exc).__name__}: {exc}")
            failed = True
            continue
        latency = time.monotonic() - start
        choice, usage = resp.choices[0], resp.usage
        msg = choice.message
        extra = msg.model_extra or {}
        reasoning = {k: extra.get(k) for k in ("reasoning", "reasoning_content") if extra.get(k)}
        print(f"model: {resp.model}")
        print(f"latency_s: {latency:.2f}")
        print(f"finish_reason: {choice.finish_reason}")
        print(f"content: {(msg.content or '')[:200]!r}")
        print(f"has_reasoning: {bool(reasoning)}" + "".join(
            f"\n{k}: {str(v)[:200]!r}" for k, v in reasoning.items()))
        print(f"usage: prompt={usage.prompt_tokens} completion={usage.completion_tokens} total={usage.total_tokens}")
        prompt_total += usage.prompt_tokens
        completion_total += usage.completion_tokens

    print(f"\nTOTAL tokens: prompt={prompt_total} completion={completion_total} total={prompt_total + completion_total}")
    print("\n# tier IDs for the repo-root .env")
    print(f"export TOKEN_FACTORY_BASE_URL={base_url}")
    for tier in generator.TIERS:
        print(f"export {generator._TIER_ENV[tier]}={tiers[tier]}")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
