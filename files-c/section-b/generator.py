"""Section 2: generate_test -- turns a coverage Gap into a candidate pytest test using Nemotron.

Contract (owned by Section 2):
    generate_test(gap, example_tests, attempt=1, prior_failure=None) -> CandidateTest

Design notes
- Talks to NVIDIA NIM (OpenAI-compatible endpoint) with the `openai` SDK.
- Model tiers: attempt 1 uses a small/fast Nemotron, later attempts escalate to bigger ones.
- The model never sees repo files directly: everything it needs must be in `gap`
  (especially gap["function_context"], which should hold the enclosing function's source)
  and `example_tests`.
- Output is linted statically (syntax, has a test function, no network/subprocess).
  One automatic repair round is attempted before handing back to Section 3.
  The *real* judge of correctness is Section 1's verify_test (it executes the test).
"""
from __future__ import annotations

import ast
import functools
import os
import re
import time
from typing import Callable, Literal, Optional, TypedDict

# --------------------------------------------------------------------------
# Shared types (match the contract so dicts flow between sections unchanged)
# --------------------------------------------------------------------------


try:  # Section 1's real shared types (frozen dataclasses)
    from models import CandidateTest, Gap
except ImportError:  # standalone fallback so this file still works on its own
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class Gap:  # type: ignore[no-redef]
        file: str
        start_line: int
        end_line: int
        function_context: str
        reason: str

    @dataclass(frozen=True)
    class CandidateTest:  # type: ignore[no-redef]
        code: str
        target_gap: "Gap"
        model_tier_used: str
        attempt_number: int = 1


def _field(gap, name: str):
    """Read a Gap field whether it's a dataclass (Section 1) or a plain dict."""
    return gap[name] if isinstance(gap, dict) else getattr(gap, name)


def _node_start(node) -> int:
    decos = [d.lineno for d in getattr(node, "decorator_list", [])]
    return min([node.lineno, *decos])


def find_function_source(source: str, name: str, line_no: int) -> str:
    """Source text of the innermost def called `name` that contains `line_no`."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            end = getattr(node, "end_lineno", node.lineno)
            if _node_start(node) <= line_no <= end and (
                best is None or (end - node.lineno) < (best.end_lineno - best.lineno)
            ):
                best = node
    if best is None:
        return ""
    lines = source.splitlines()
    return "\n".join(lines[_node_start(best) - 1 : best.end_lineno])


def code_context(gap, source: Optional[str]) -> str:
    """What the model sees as 'code under test'.

    Section 1 currently gives only the function NAME in gap.function_context, so we need the
    file text (`source`) to show real code. Falls back to a +-15 line window for module-level
    gaps, and to function_context itself if it already looks like code.
    """
    ctx = _field(gap, "function_context") or ""
    start, end = _field(gap, "start_line"), _field(gap, "end_line")
    if source:
        body = find_function_source(source, ctx, start) if ctx.isidentifier() else ""
        if not body:
            lines = source.splitlines()
            lo, hi = max(0, start - 16), min(len(lines), end + 15)
            body = "\n".join(lines[lo:hi])
        return body
    return ctx  # may be just a name; prompt tells the model it is limited


LLMFn = Callable[[str, list, float], str]  # (model, messages, temperature) -> text

# --------------------------------------------------------------------------
# Model tiers. Verify exact IDs at https://build.nvidia.com/models?q=nemotron
# and override with env vars if they differ / newer ones are available.
# --------------------------------------------------------------------------

NIM_BASE_URL = os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")

MODEL_TIERS: list[tuple[str, str]] = [
    ("nemotron-nano", os.getenv("NEMOTRON_NANO_MODEL", "nvidia/llama-3.1-nemotron-nano-8b-v1")),
    ("nemotron-super", os.getenv("NEMOTRON_SUPER_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1")),
    ("nemotron-ultra", os.getenv("NEMOTRON_ULTRA_MODEL", "nvidia/llama-3.1-nemotron-ultra-253b-v1")),
]


TOKEN_FACTORY_BASE_URL = os.getenv("TOKEN_FACTORY_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
_TIER_ENV = {
    "nemotron-nano": "NEMOTRON_NANO_MODEL",
    "nemotron-super": "NEMOTRON_SUPER_MODEL",
    "nemotron-ultra": "NEMOTRON_ULTRA_MODEL",
}


def _provider() -> tuple[str, Optional[str], str]:
    """(name, api_key, base_url). Nebius Token Factory if TOKEN_FACTORY_API_KEY is set, else NVIDIA NIM."""
    if os.getenv("TOKEN_FACTORY_API_KEY"):
        return "tokenfactory", os.getenv("TOKEN_FACTORY_API_KEY"), TOKEN_FACTORY_BASE_URL
    return "nim", os.getenv("NVIDIA_API_KEY"), NIM_BASE_URL


def _param_billions(model_id: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*[bB]\b|[-_](\d+)[bB](?![a-zA-Z])", model_id)
    return float(next(g for g in m.groups() if g)) if m else 0.0


def discover_tier_models(model_ids: list[str]) -> dict[str, str]:
    """Pick one Nemotron model per tier from a provider's model list.

    Keyword first ('nano' / 'super' / 'ultra' in the id); any tier still empty is filled by parameter
    count (smallest -> nano, middle -> super, largest -> ultra). Pure function, easy to test."""
    nem = [i for i in model_ids if "nemotron" in i.lower()]
    out: dict[str, str] = {}
    for tier in _TIER_ENV:
        key = tier.split("-")[1]
        hits = [i for i in nem if key in i.lower()]
        if hits:
            out[tier] = max(hits, key=_param_billions)
    rest = sorted((i for i in nem if i not in out.values()), key=_param_billions)
    for tier in (t for t in ("nemotron-nano", "nemotron-ultra", "nemotron-super") if t not in out):
        if not rest:
            break
        pick = rest[0] if tier == "nemotron-nano" else rest[-1] if tier == "nemotron-ultra" else rest[len(rest) // 2]
        out[tier] = pick
        rest.remove(pick)
    return out


_tiers_cache: Optional[list[tuple[str, str]]] = None


def resolved_tiers() -> list[tuple[str, str]]:
    """Tier -> model id. Env vars win; on Token Factory, missing ones are discovered via /models."""
    global _tiers_cache
    if _tiers_cache is not None:
        return _tiers_cache
    tiers = []
    found: dict[str, str] = {}
    if _provider()[0] == "tokenfactory" and not all(os.getenv(v) for v in _TIER_ENV.values()):
        try:
            found = discover_tier_models([m.id for m in _client().models.list()])
        except Exception:  # noqa: BLE001 - fall back to defaults; the first call will report the real error
            found = {}
    for (tier, default) in MODEL_TIERS:
        explicit = os.getenv(_TIER_ENV[tier])
        tiers.append((tier, explicit or found.get(tier) or default))
    _tiers_cache = tiers
    return tiers


def tier_for_attempt(attempt: int) -> tuple[str, str]:
    """attempt 1 -> nano, 2 -> super, 3+ -> ultra."""
    tiers = resolved_tiers()
    idx = max(0, min(attempt - 1, len(tiers) - 1))
    return tiers[idx]


def temperature_for_attempt(attempt: int) -> float:
    """Low first (deterministic), a bit more diversity on retries."""
    return min(0.2 + 0.2 * (attempt - 1), 0.8)


# --------------------------------------------------------------------------
# Prompting
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """detailed thinking off
You are a senior engineer writing a pytest unit test.

Rules:
- Output exactly ONE ```python code block and nothing else of value outside it.
- Write EXACTLY ONE top-level function named test_* (helpers/fixtures are fine, but only one test
  function: the runner executes only the first test_* it finds). Use plain pytest (assert statements).
- The test must PASS against the current code and must execute the target lines.
- Assert on real, observable behaviour (return values, raised exceptions, state), not on implementation details.
- Be deterministic: no network, no subprocess, no sleeping, no randomness, no writing outside tmp_path.
- Use unittest.mock / monkeypatch for external dependencies instead of calling them.
- Import the code under test with the import line you are given. Do not redefine it.
- Match the style of the example tests when they are provided."""

MAX_EXAMPLE_CHARS = 2500
MAX_EXAMPLES = 3
MAX_CONTEXT_CHARS = 8000
MAX_FAILURE_CHARS = 3000


def module_path_from_file(path: str) -> str:
    """'src/pkg/mod.py' -> 'src.pkg.mod'  (hint only; Section 1's runner sets sys.path)."""
    p = path.replace("\\", "/")
    if p.endswith(".py"):
        p = p[:-3]
    p = p.strip("./")
    if p.endswith("/__init__"):
        p = p[: -len("/__init__")]
    return p.replace("/", ".")


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n# ... (truncated)"


def _reason_instruction(gap) -> str:
    if _field(gap, "reason") == "partial_branch":
        return (
            "A branch on these lines is only partly covered: an existing test takes one side. "
            "Write input that forces the OTHER side of the condition."
        )
    return "These lines are never executed by any existing test. Write input that reaches them."


def build_messages(
    gap,
    example_tests: list[str],
    attempt: int = 1,
    prior_failure: Optional[str] = None,
    source: Optional[str] = None,
) -> list[dict]:
    file, start, end = _field(gap, "file"), _field(gap, "start_line"), _field(gap, "end_line")
    module = module_path_from_file(file)
    examples = ""
    for i, ex in enumerate(example_tests[:MAX_EXAMPLES], 1):
        examples += f"\n# --- example test {i} ---\n{_truncate(ex, MAX_EXAMPLE_CHARS)}\n"
    if not examples:
        examples = "\n(no existing tests provided; use plain pytest style)\n"

    user = (
        f"File: {file}\n"
        f"Import line hint: from {module} import <name>\n"
        f"Target lines (in the file, 1-indexed): {start}-{end}\n"
        f"Why this is a gap: {_reason_instruction(gap)}\n\n"
        f"Enclosing code under test:\n```python\n{_truncate(code_context(gap, source), MAX_CONTEXT_CHARS)}\n```\n\n"
        f"Existing tests in this repo for style reference:\n{examples}\n"
        "Write the test now."
    )

    if prior_failure:
        user += (
            f"\n\nThis is attempt {attempt}. Your previous test was run in a sandbox and was REJECTED:\n"
            f"```\n{_truncate(prior_failure, MAX_FAILURE_CHARS)}\n```\n"
            "Diagnose the cause (wrong expected value? wrong import? bad input? it passed but never "
            "reached the target lines?) and return a corrected, complete test. Do not repeat the same mistake."
        )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


# --------------------------------------------------------------------------
# Output handling
# --------------------------------------------------------------------------


def extract_code(text: str) -> str:
    """Pull the python code out of an LLM reply (handles <think>, fences, unterminated fences)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", text, flags=re.S)
    if blocks:
        with_test = [b for b in blocks if "def test" in b]
        return max(with_test or blocks, key=len).strip()
    m = re.search(r"```(?:python|py)?[ \t]*\n(.*)$", text, flags=re.S)  # unterminated fence
    if m:
        return m.group(1).strip()
    return text


BANNED_MODULES = {"subprocess", "socket", "requests", "urllib", "http", "httpx", "shutil", "ctypes"}
BANNED_CALLS = {"eval", "exec", "__import__"}


def lint_candidate(code: str) -> list[str]:
    """Cheap static checks. Returns a list of problems (empty = looks OK)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"SyntaxError: {e.msg} (line {e.lineno})"]
    problems: list[str] = []
    has_test = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            has_test = True
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in BANNED_MODULES:
                    problems.append(f"imports banned module '{a.name}'")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in BANNED_MODULES:
                problems.append(f"imports banned module '{node.module}'")
        elif isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in BANNED_CALLS:
                problems.append(f"calls banned builtin '{f.id}'")
            elif (
                isinstance(f, ast.Attribute)
                and isinstance(f.value, ast.Name)
                and f.value.id == "os"
                and f.attr in {"system", "popen", "remove", "rmdir"}
            ):
                problems.append(f"calls os.{f.attr}")
    if not has_test:
        problems.append("no function named test_* found")
    return problems


# --------------------------------------------------------------------------
# NVIDIA NIM client
# --------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _client():
    from openai import OpenAI  # lazy so tests don't need the package

    name, key, base = _provider()
    if not key:
        raise RuntimeError("Set TOKEN_FACTORY_API_KEY (Nebius Token Factory) or NVIDIA_API_KEY (build.nvidia.com)")
    return OpenAI(base_url=base, api_key=key)


def nvidia_llm(model: str, messages: list, temperature: float) -> str:
    """Call a Nemotron model on NIM, retrying transient failures with backoff."""
    last: Exception | None = None
    for i in range(3):
        try:
            resp = _client().chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                top_p=0.95,
                max_tokens=1800,
                timeout=90,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001 - rate limits / timeouts / 5xx
            last = e
            time.sleep(2**i)
    raise RuntimeError(f"NIM call failed after retries: {last}")


# --------------------------------------------------------------------------
# Public entry point (Section 2 contract)
# --------------------------------------------------------------------------


def generate_test(
    gap,
    example_tests: list[str],
    attempt: int = 1,
    prior_failure: Optional[str] = None,
    *,
    source: Optional[str] = None,
    llm: Optional[LLMFn] = None,
) -> CandidateTest:
    """`source` = full text of gap.file at PR head (Section 3 can get it via sandbox.read_file).
    Optional, but strongly recommended: without it the model only sees the function name."""
    llm = llm or nvidia_llm
    tier, model = tier_for_attempt(attempt)
    temp = temperature_for_attempt(attempt)
    messages = build_messages(gap, example_tests, attempt, prior_failure, source)

    raw = llm(model, messages, temp)
    code = extract_code(raw)

    problems = lint_candidate(code)
    if problems:  # one cheap repair round before bothering the sandbox
        messages = messages + [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": "Your answer has problems: "
                + "; ".join(problems)
                + ". Return the corrected full test in a single ```python block.",
            },
        ]
        code = extract_code(llm(model, messages, temp))

    return CandidateTest(
        code=code, target_gap=gap, model_tier_used=tier, attempt_number=attempt
    )
