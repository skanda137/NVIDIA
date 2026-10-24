"""
Read 10 random verified gaps from an eval run and classify every check in their tests.

    ~/.venvs/vtga/bin/python eval/sample_verified.py docs/evidence/eval_<date>_<tag>.jsonl

Writes docs/evidence/verified_sample_<date>.md. Fixed seed, so the same JSONL
gives the same sample. Read-only: changes no test and no lint rule.

Each assert is one of: constant (`assert True`), weak (`is not None`, `isinstance`,
`hasattr`, `callable`), compares (==, !=, <, in, is <value> ...), truthy (anything
else: `assert result`, `assert f(x)`). pytest.raises/warns and mock assert_* calls
are listed separately. A test counts as checking a value if it has at least one
compares assert, a pytest.raises, or a mock assert_called_with-style call.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from build_repos import REPOS, _strip_markers  # noqa: E402

SEED, N = 20261024, 10
WEAK_CALLS = {"isinstance", "hasattr", "callable"}


def classify_assert(node: ast.Assert) -> str:
    t = node.test
    if isinstance(t, ast.Constant):
        return "constant"
    if isinstance(t, ast.Call) and getattr(t.func, "id", "") in WEAK_CALLS:
        return "weak"
    if isinstance(t, ast.Compare):
        if (len(t.ops) == 1 and isinstance(t.ops[0], ast.IsNot)
                and isinstance(t.comparators[0], ast.Constant) and t.comparators[0].value is None):
            return "weak"
        return "compares"
    return "truthy"


def checks(code: str) -> list[tuple[str, str]]:
    """(class, source text) for every assert, pytest.raises/warns and mock assert_* call."""
    tree = ast.parse(code)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            out.append((classify_assert(node), ast.unparse(node)))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("raises", "warns"):
                out.append(("raises", ast.unparse(node)))
            elif node.func.attr.startswith("assert_"):
                out.append(("mock-assert", ast.unparse(node)))
    return out


def source_lines(repo: str, file: str, start: int, end: int) -> str:
    text = _strip_markers(file, REPOS[repo][1][file], {})
    lines = text.splitlines()
    return "\n".join(f"{n:>4}  {lines[n - 1]}" for n in range(start, end + 1))


def main() -> None:
    jsonl = Path(sys.argv[1])
    gaps = [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]
    verified = [g for g in gaps if g["final_status"] == "verified_pass"]
    sample = random.Random(SEED).sample(verified, min(N, len(verified)))

    out = [f"# Sample of verified tests, {dt.date.today().isoformat()}", "",
           f"Source: `{jsonl.relative_to(ROOT).as_posix()}`; {len(verified)} verified gap-runs, "
           f"{len(sample)} sampled with seed {SEED}. Read-only: no test or lint rule was changed.", ""]
    tally = {}
    value_checked = 0
    for i, g in enumerate(sample, 1):
        final = next(a for a in g["attempts"] if a["verified"])
        cs = checks(final["code"])
        for c, _ in cs:
            tally[c] = tally.get(c, 0) + 1
        checks_value = any(c in ("compares", "raises", "mock-assert") for c, _ in cs)
        value_checked += checks_value
        how = f"reused test from {g['covered_by']}" if g["covered_by"] else f"generated, {final['tier']}"
        out += [f"## {i}. {g['repo']} r{g['repeat']} `{g['file']}:{g['start_line']}-{g['end_line']}` "
                f"[{g['category']}, {g['reason']}]", "",
                f"{how}; verdict: {final['message']}", "",
                "Gap lines:", "```python", source_lines(g["repo"], g["file"], g["start_line"], g["end_line"]), "```",
                "Test:", "```python", final["code"].rstrip(), "```",
                "Checks:", ""] + [f"- **{c}**: `{s}`" for c, s in cs] + [
                "", f"Checks a value: **{'yes' if checks_value else 'NO'}**", ""]
    summary = ["## Summary", "",
               f"- Tests that check a value (compares assert, pytest.raises or mock assert): "
               f"**{value_checked}/{len(sample)}**",
               "- Checks by class: " + ", ".join(f"{k} {v}" for k, v in sorted(tally.items())), ""]
    out[4:4] = summary
    dest = ROOT / "docs" / "evidence" / f"verified_sample_{dt.date.today().isoformat()}.md"
    dest.write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
