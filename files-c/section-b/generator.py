"""Section 2: generate_test -- turns a coverage Gap into a candidate pytest test using Nemotron.

Contract (owned by Section 2):
    generate_test(gap, example_tests, attempt=1, prior_failure=None) -> CandidateTest

Design notes
- Talks to Nebius Token Factory (OpenAI-compatible endpoint) with the `openai` SDK.
  Needs TOKEN_FACTORY_API_KEY and TOKEN_FACTORY_BASE_URL.
- Model tiers: attempt 1 uses a small/fast Nemotron, later attempts escalate to bigger ones.
  Model IDs come only from TOKEN_FACTORY_MODEL_NANO / _SUPER / _ULTRA.
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
from typing import Callable, Optional

import _paths  # noqa: F401  (section-a on sys.path)
from models import CandidateTest, Gap  # Section 1's shared types; no fallback


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
# Provider and model tiers: Nebius Token Factory only, IDs only from env.
# Pick the IDs with scripts/check_token_factory.py (uses discover_tier_models).
# --------------------------------------------------------------------------

TIERS = ("nemotron-nano", "nemotron-super", "nemotron-ultra")  # attempt 1, 2, 3+
_TIER_ENV = {
    "nemotron-nano": "TOKEN_FACTORY_MODEL_NANO",
    "nemotron-super": "TOKEN_FACTORY_MODEL_SUPER",
    "nemotron-ultra": "TOKEN_FACTORY_MODEL_ULTRA",
}


def _provider() -> tuple[str, str]:
    """(api_key, base_url) for Nebius Token Factory. Raises if either is unset."""
    key, base = os.getenv("TOKEN_FACTORY_API_KEY"), os.getenv("TOKEN_FACTORY_BASE_URL")
    if not key:
        raise RuntimeError("TOKEN_FACTORY_API_KEY is not set (Nebius Token Factory)")
    if not base:
        raise RuntimeError("TOKEN_FACTORY_BASE_URL is not set (Nebius Token Factory)")
    return key, base


def missing_env(max_attempts: int) -> list[str]:
    """Env vars the LLM generator needs for `max_attempts` attempts that are unset."""
    needed = ["TOKEN_FACTORY_API_KEY", "TOKEN_FACTORY_BASE_URL"]
    needed += [_TIER_ENV[TIERS[min(a, len(TIERS)) - 1]] for a in range(1, max_attempts + 1)]
    return [v for v in dict.fromkeys(needed) if not os.getenv(v)]


def _param_billions(model_id: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)\s*[bB]\b|[-_](\d+)[bB](?![a-zA-Z])", model_id)
    return float(next(g for g in m.groups() if g)) if m else 0.0


def discover_tier_models(model_ids: list[str]) -> dict[str, str]:
    """Pick one Nemotron model per tier from a provider's model list, by keyword only
    ('nano' / 'super' / 'ultra' in the id). Several hits: the largest parameter count in
    the id. A tier with no keyword hit is left out. Pure function, easy to test."""
    nem = [i for i in model_ids if "nemotron" in i.lower()]
    out: dict[str, str] = {}
    for tier in TIERS:
        key = tier.split("-")[1]
        hits = [i for i in nem if key in i.lower()]
        if hits:
            out[tier] = max(hits, key=_param_billions)
    return out


def tier_for_attempt(attempt: int) -> tuple[str, str]:
    """attempt 1 -> nano, 2 -> super, 3+ -> ultra. Raises if that tier's env var is unset."""
    tier = TIERS[max(0, min(attempt - 1, len(TIERS) - 1))]
    model = os.getenv(_TIER_ENV[tier])
    if not model:
        raise RuntimeError(f"{_TIER_ENV[tier]} is not set (model ID for {tier}, attempt {attempt})")
    return tier, model


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
- Write exactly one test function, named test_* (helpers/fixtures are fine). The runner executes
  the whole file, so every test in it must pass. Use plain pytest (assert statements).
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


def _branch_hint(branch: str) -> str:
    """'5:8' / '5:exit' (coverage.py missing branch, as in Gap.missing_branches) -> words."""
    src, dst = branch.split(":", 1)
    if dst == "exit":
        return (f"the branch from line {src} to the function exit is never taken; choose inputs that "
                f"make the function finish without entering the block after line {src}")
    return f"the branch from line {src} to line {dst} is never taken; choose inputs that take it"


def _reason_instruction(gap) -> str:
    if _field(gap, "reason") == "partial_branch":
        missing = gap.get("missing_branches", ()) if isinstance(gap, dict) else gap.missing_branches
        hints = "".join(f"\n- {_branch_hint(b)}" for b in missing)
        return (
            "A branch on these lines is only partly covered: an existing test takes one side. "
            "Write input that forces the OTHER side of the condition." + hints
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


class CandidateRejected(ValueError):
    """Generated code still fails lint after the repair round. args[0] is the problems list;
    `code` and `tier` let Section 3 record the attempt."""

    def __init__(self, problems: list[str], *, code: str, tier: str):
        super().__init__(problems)
        self.problems, self.code, self.tier = problems, code, tier


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
# Nebius Token Factory client
# --------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _client():
    from openai import OpenAI  # lazy so tests don't need the package

    key, base = _provider()
    # The SDK retries only connection errors, 408/409/429 and 5xx; auth and
    # bad-request errors fail on the first call.
    return OpenAI(base_url=base, api_key=key, max_retries=2)


def token_factory_llm(model: str, messages: list, temperature: float) -> str:
    """Call a Nemotron model on Nebius Token Factory."""
    resp = _client().chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        top_p=0.95,
        max_tokens=1800,
        timeout=90,
    )
    return resp.choices[0].message.content or ""


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
    Optional, but strongly recommended: without it the model only sees the function name.
    Raises CandidateRejected if the code still fails lint after the one repair round."""
    llm = llm or token_factory_llm
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
        problems = lint_candidate(code)
        if problems:
            raise CandidateRejected(problems, code=code, tier=tier)

    return CandidateTest(
        code=code, target_gap=gap, model_tier_used=tier, attempt_number=attempt
    )
