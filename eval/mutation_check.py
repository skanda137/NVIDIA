"""
Mutation check of the verified tests saved by a seeded eval run. Report only: it gates
nothing and makes no LLM calls.

    ~/.venvs/vtga/bin/python eval/mutation_check.py docs/evidence/eval_<date>_<tag>.jsonl $HOME/work/mutation

For each verified gap-run, every mutation site on the gap's lines gets one mutant (one
change each): == <-> !=, < <-> <=, > <-> >=, + <-> -, True <-> False, a returned value
-> None and -> 0, and `if c` -> `if not c`. Each mutant replaces the module in a
throwaway copy of the repo inside the bwrap sandbox; the saved test is run against it.
Killed = the test fails or errors (or times out); survived = it still passes. The test
must pass on the unmutated code first. Surviving mutants include equivalent mutants
(changes no test could detect), so the kill rate is a lower bound on test strength.
Writes docs/evidence/mutation_<run>.md.
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "eval"), str(ROOT / "files-c" / "section-c")]
import _paths  # noqa: E402,F401
from build_repos import build_repo  # noqa: E402
from sandbox_client import LocalSandboxClient  # noqa: E402
from verifier import PYTHON, prepare_env  # noqa: E402

TEST_FILE = "_mutation_test.py"
FLIP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.LtE, ast.LtE: ast.Lt, ast.Gt: ast.GtE, ast.GtE: ast.Gt}
BINFLIP = {ast.Add: ast.Sub, ast.Sub: ast.Add}
RUN = (f"cd repo && find . -name __pycache__ -prune -exec rm -rf {{}} + ; "
       f"PYTHONDONTWRITEBYTECODE=1 {PYTHON} -m pytest -q -x -p no:cacheprovider {TEST_FILE}")


def sites(tree: ast.AST, lines: set[int]) -> list[tuple[int, str]]:
    """(node index in ast.walk order, operator) for every mutation on the gap lines."""
    out = []
    for i, n in enumerate(ast.walk(tree)):
        if getattr(n, "lineno", None) not in lines:
            continue
        if isinstance(n, ast.Compare):
            out += [(i, f"cmp{k}") for k, op in enumerate(n.ops) if type(op) in FLIP]
        elif isinstance(n, ast.BinOp) and type(n.op) in BINFLIP:
            out.append((i, "binop"))
        elif isinstance(n, ast.Constant) and isinstance(n.value, bool):
            out.append((i, "bool"))
        elif isinstance(n, ast.Return) and n.value is not None:
            out += [(i, "return-None"), (i, "return-0")]
        elif isinstance(n, ast.If):
            out.append((i, "negate-if"))
    return out


def mutate(tree: ast.AST, index: int, kind: str) -> tuple[str, str]:
    """(mutated source, description) with exactly one change at node `index`."""
    t = copy.deepcopy(tree)
    n = list(ast.walk(t))[index]
    before = ast.unparse(n).splitlines()[0]
    if kind.startswith("cmp"):
        k = int(kind[3:])
        n.ops[k] = FLIP[type(n.ops[k])]()
    elif kind == "binop":
        n.op = BINFLIP[type(n.op)]()
    elif kind == "bool":
        n.value = not n.value
    elif kind == "return-None":
        n.value = ast.Constant(None)
    elif kind == "return-0":
        n.value = ast.Constant(0)
    elif kind == "negate-if":
        n.test = ast.UnaryOp(ast.Not(), n.test)
    after = ast.unparse(n).splitlines()[0]
    return ast.unparse(ast.fix_missing_locations(t)) + "\n", f"line {n.lineno}: `{before}` -> `{after}`"


def main() -> None:
    jsonl, work = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
    work.mkdir(parents=True, exist_ok=True)
    gaps = [json.loads(l) for l in jsonl.read_text().splitlines() if l.strip()]
    verified = [g for g in gaps if g["final_status"] == "verified_pass"]
    start = time.monotonic()
    specs, sandboxes, results = {}, {}, []
    for g in verified:
        name = g["repo"]
        if name not in specs:
            specs[name] = build_repo(work / "repos", name)
            cwd = work / f"sbx_{name}"
            cwd.mkdir()
            shutil.copytree(specs[name].path, cwd / "repo", ignore=shutil.ignore_patterns(".git"))
            sandboxes[name] = LocalSandboxClient(str(cwd))
            prepare_env(sandboxes[name], "repo")
        sb, spec = sandboxes[name], specs[name]
        original = (Path(spec.path) / g["file"]).read_text()
        tree = ast.parse(original)
        test = next(a for a in g["attempts"] if a["verified"])["code"]
        sb.write_file(f"repo/{TEST_FILE}", test)
        base = sb.run(RUN, timeout=60)
        row = {"gap": f"{name} r{g['repeat']} {g['file']}:{g['start_line']}-{g['end_line']}",
               "category": g["category"], "baseline_ok": base.ok, "killed": 0, "survived": [], "total": 0}
        if base.ok:
            for index, kind in sites(tree, set(range(g["start_line"], g["end_line"] + 1))):
                src, desc = mutate(tree, index, kind)
                sb.write_file(f"repo/{g['file']}", src)
                r = sb.run(RUN, timeout=60)
                row["total"] += 1
                if r.ok:
                    row["survived"].append(desc)
                else:
                    row["killed"] += 1
            sb.write_file(f"repo/{g['file']}", original)
        results.append(row)
        print(f"{row['gap']}: {row['killed']}/{row['total']} killed", file=sys.stderr, flush=True)

    def rate(rows):
        k, t = sum(r["killed"] for r in rows), sum(r["total"] for r in rows)
        return f"{k}/{t} ({100 * k / t:.0f}%)" if t else "0/0"

    ok = [r for r in results if r["baseline_ok"]]
    out = [f"# Mutation check, {dt.date.today().isoformat()}", "",
           f"Command: `python eval/mutation_check.py {jsonl.relative_to(ROOT).as_posix()} $HOME/work/mutation`  ",
           f"Source: {len(verified)} verified gap-runs (each with its saved test; reused gaps use the earlier "
           f"gap's test). No LLM calls. {time.monotonic() - start:.0f} s.", "",
           "Killed = the verified test fails on the mutant. Survivors include **equivalent mutants** "
           "(e.g. `<` -> `<=` where the boundary value cannot occur), so the kill rate is a lower bound. "
           "This is a report only; nothing is gated on it.", "",
           f"- Baseline (test passes on unmutated code): {len(ok)}/{len(results)}",
           f"- Gap-runs with at least one mutation site: {sum(1 for r in ok if r['total'])}",
           f"- **Overall kill rate: {rate(ok)}**", "",
           "| category | gap-runs | mutants killed |", "|---|---|---|"]
    for cat in sorted({r["category"] for r in ok}):
        rs = [r for r in ok if r["category"] == cat]
        out.append(f"| {cat} | {len(rs)} | {rate(rs)} |")
    survivors = [(r["gap"], r["category"], d) for r in ok for d in r["survived"]]
    out += ["", f"## Surviving mutants ({len(survivors)} total; first 5 distinct shown)", ""]
    seen = set()
    for gap, cat, d in survivors:
        if (gap.split(" r")[0], d) in seen:
            continue
        seen.add((gap.split(" r")[0], d))
        out.append(f"- {gap} [{cat}]: {d}")
        if len(seen) == 5:
            break
    out += ["", "## Baseline failures", ""] + ([f"- {r['gap']}" for r in results if not r["baseline_ok"]] or ["None."])
    dest = ROOT / "docs" / "evidence" / f"mutation_{jsonl.stem.removeprefix('eval_')}.md"
    dest.write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
