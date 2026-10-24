"""
Run the generator's undefined-name and oracle lint rules over human-written test files
that are known to pass, and report every flag (each one is a false positive).

    ~/.venvs/vtga/bin/python eval/lint_precision.py $HOME/work/lint_repos

Inputs: the seeded eval repos' test files (base and PR commits, from build_repos.py),
the demo billing fixture, and every test file at the head of each cached real PR
(cloned with git into <work_dir>; no repo code is executed). Rules are not changed.
Writes docs/evidence/lint_precision_<date>.md.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "eval"), str(ROOT / "files-c" / "section-c")]
import _paths  # noqa: E402,F401
import generator  # noqa: E402
from build_repos import REPOS, _strip_markers  # noqa: E402

CACHE = ROOT / "docs" / "evidence" / "pr_cache"


def is_test_file(path: Path) -> bool:
    return path.suffix == ".py" and (path.name.startswith("test_") or path.name.endswith("_test.py"))


def seeded_files() -> list[tuple[str, str]]:
    out = []
    for name, (base, pr) in REPOS.items():
        for commit, files in (("base", base), ("pr", pr)):
            out += [(f"seeded/{name}@{commit}/{p}", _strip_markers(p, t, {})) for p, t in files.items()
                    if is_test_file(Path(p))]
    billing = ROOT / "files-c" / "section-c" / "demo_pipeline.py"
    src = billing.read_text()
    # The billing fixture's test file text, as demo_pipeline.py writes it at the PR commit.
    start = src.index('(repo / "test_billing.py").write_text(\n') + len('(repo / "test_billing.py").write_text(\n')
    text = ast.literal_eval("(" + src[start:src.index("\n    )", start)] + ")")
    return out + [("seeded/billing@pr/test_billing.py", text)]


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def real_files(work: Path) -> list[tuple[str, str]]:
    out = []
    for meta_path in sorted(CACHE.glob("*.json")):
        meta = json.loads(meta_path.read_text())
        repo = work / meta_path.stem
        if not repo.is_dir():
            git(work, "clone", "-q", meta["clone_url"], str(repo))
            git(repo, "fetch", "-q", "origin", meta["fetch_ref"])
        git(repo, "checkout", "-q", meta["head_sha"])
        for f in sorted(repo.rglob("*.py")):
            if is_test_file(f) and ".git" not in f.parts:
                out.append((f"real/{meta_path.stem}@{meta['head_sha'][:8]}/{f.relative_to(repo).as_posix()}",
                            f.read_text(encoding="utf-8", errors="replace")))
    return out


def why(func) -> str:
    """Heuristic label for a flagged test (the rule itself is unchanged)."""
    nodes = list(ast.walk(func))
    if any(isinstance(n, ast.Raise) for n in nodes):
        return "manual raise"
    calls = [n.func for n in nodes if isinstance(n, ast.Call)]
    names = [c.attr if isinstance(c, ast.Attribute) else getattr(c, "id", "") for c in calls]
    if any(nm.startswith(("_test", "check", "_check", "verify", "_verify", "_assert")) for nm in names):
        return "check in a helper"
    return "no check: smoke test that passes if nothing raises"


def flags(code: str) -> tuple[list[str], list[str], int]:
    """(oracle flags, undefined-name flags, test functions) using the generator's own rules."""
    tree = ast.parse(code)
    tests = [n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")]
    oracle = [f"{n.name}` ({why(n)})" for n in tests if not generator._has_oracle(n)]
    return oracle, generator._undefined_names(tree), len(tests)


def main() -> None:
    work = Path(sys.argv[1])
    work.mkdir(parents=True, exist_ok=True)
    files = seeded_files() + real_files(work)
    rows, n_tests, fp_oracle, fp_undef = [], 0, [], []
    for label, code in files:
        try:
            oracle, undef, n = flags(code)
        except SyntaxError as e:
            rows.append(f"| {label} | parse error: {e.msg} | | |")
            continue
        n_tests += n
        fp_oracle += [(label, t) for t in oracle]
        fp_undef += [(label, u) for u in undef]
        rows.append(f"| {label} | {n} | {len(oracle)} | {len(undef)} |")

    out = [f"# Lint precision on human-written tests, {dt.date.today().isoformat()}", "",
           "Command: `python eval/lint_precision.py $HOME/work/lint_repos`  ",
           "Rules: `generator._has_oracle` (oracle lint) and `generator._undefined_names`, unchanged. "
           "Every file here is from a suite that runs green, so every flag is a false positive "
           "(a valid human test the lint would reject).", "",
           f"- Files: {len(files)}; test functions: {n_tests}",
           f"- Oracle-lint false positives: **{len(fp_oracle)}** test function(s)",
           f"- Undefined-name false positives: **{len(fp_undef)}** name(s)", "",
           "| file | test functions | oracle flags | undefined-name flags |", "|---|---|---|---|", *rows, "",
           "## Oracle-lint false positives", ""]
    kinds = {}
    for _, t in fp_oracle:
        k = t.split("(", 1)[1].rstrip(")")
        kinds[k] = kinds.get(k, 0) + 1
    out += ["By heuristic kind: " + "; ".join(f"{k}: {v}" for k, v in sorted(kinds.items())) + ". "
            "The smoke tests are arguably correct flags (they check nothing beyond not raising).", ""]
    out += [f"- `{f}` :: `{t}" for f, t in fp_oracle] or ["None."]
    out += ["", "## Undefined-name false positives", ""]
    out += [f"- `{f}` :: `{u}`" for f, u in fp_undef] or ["None."]
    dest = ROOT / "docs" / "evidence" / f"lint_precision_{dt.date.today().isoformat()}.md"
    dest.write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
