"""
Run the real pipeline (Nemotron on Token Factory, bwrap sandbox) over the seeded
repos from build_repos.py and write docs/evidence/eval_<date>.{md,csv}.

    ~/.venvs/vtga/bin/python eval/run_eval.py --repeats 3 --max-calls 180
    ~/.venvs/vtga/bin/python eval/run_eval.py --dry-run    # no LLM: base suites + gaps only
    ~/.venvs/vtga/bin/python eval/run_eval.py --repos-dir ~/heldout-repos --tag heldout

--repos-dir: every subdirectory is a git repo with exactly two commits (base, then
head); the PR diff is base..head and the files analysed are its non-test .py files.
Without it, the seeded repos from build_repos.py are built and used.

Every LLM call goes through Budget: past --max-calls the run aborts (recorded,
not hidden). A repo whose suite is red or whose deps fail to install is a result.
Nothing here changes prompts, models or lint; the report records the
generator.py hash, model IDs and commit so runs can be compared.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "eval"), str(ROOT / "files-c" / "section-c")]
import _paths  # noqa: E402,F401  (section-a and section-b on sys.path)
import generator  # noqa: E402
from build_repos import RepoSpec, build_all  # noqa: E402
from cli import changed_py_files_from_diff  # noqa: E402
from pipeline_models import PipelineConfig  # noqa: E402
from run_pipeline import checkout_repo, run_pipeline  # noqa: E402
from sandbox_client import LocalSandboxClient  # noqa: E402
from verifier import COVERAGE_RUN, find_gaps, prepare_env  # noqa: E402

EVIDENCE = ROOT / "docs" / "evidence"
MAX_ATTEMPTS = 3


class BudgetExhausted(RuntimeError):
    pass


@dataclass
class Budget:
    """Hard cap on Token Factory calls; attributes each call's usage to the current gap."""
    max_calls: int
    calls: int = 0
    current: tuple = ()
    per_gap: dict = field(default_factory=dict)  # gap key -> [(model, tok_in, tok_out, seconds)]
    usage: list = field(default_factory=list)    # every call, never consumed

    def llm(self, model: str, messages: list, temperature: float) -> str:
        if self.calls >= self.max_calls:
            raise BudgetExhausted(f"Token Factory call budget of {self.max_calls} reached")
        self.calls += 1
        before = len(generator.USAGE)
        try:
            return generator.token_factory_llm(model, messages, temperature)
        finally:
            self.per_gap.setdefault(self.current, []).extend(generator.USAGE[before:])
            self.usage.extend(generator.USAGE[before:])

    def generate(self, gap, example_tests, attempt=1, prior_failure=None, *, source=None):
        self.current = (gap.file, gap.start_line, gap.end_line)
        return generator.generate_test(gap, example_tests, attempt=attempt, prior_failure=prior_failure,
                                       source=source, llm=self.llm)

    def totals(self) -> tuple[int, int]:
        return sum(u[1] for u in self.usage), sum(u[2] for u in self.usage)


def run_metadata(source: str = "seeded repos") -> dict:
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    # Content changes only: run from WSL on a Windows checkout, every CRLF file
    # otherwise shows as modified (run A on 2026-10-23 was flagged that way).
    changed = subprocess.run(["git", "diff", "--ignore-cr-at-eol", "--name-only", "HEAD", "--", "files-c", "eval"],
                             cwd=ROOT, capture_output=True, text=True).stdout
    untracked = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "files-c", "eval"],
                               cwd=ROOT, capture_output=True, text=True).stdout
    dirty = (changed + untracked).split()
    gen_src = (ROOT / "files-c" / "section-b" / "generator.py").read_bytes()
    return {
        "date": dt.date.today().isoformat(),
        "source": source,
        "commit": head + (f" (DIRTY: {', '.join(dirty)})" if dirty else " (clean)"),
        "generator_sha256": hashlib.sha256(gen_src).hexdigest()[:12],
        "models": {t: os.getenv(generator._TIER_ENV[t], "") for t in generator.TIERS},
    }


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def load_repos(repos_dir: Path) -> list[RepoSpec]:
    """One RepoSpec per subdirectory of repos_dir. Each must be a git repo with exactly two
    commits, base then head; anything else raises (no guessing which commits to diff)."""
    subdirs = sorted(p for p in repos_dir.iterdir() if p.is_dir())
    if not subdirs:
        raise ValueError(f"{repos_dir} has no repo subdirectories")
    specs = []
    for repo in subdirs:
        if not (repo / ".git").exists():
            raise ValueError(f"{repo} is not a git repo")
        shas = _git(repo, "rev-list", "--reverse", "HEAD").split()
        if len(shas) != 2:
            raise ValueError(f"{repo}: expected exactly 2 commits (base, head), found {len(shas)}")
        diff = _git(repo, "diff", f"{shas[0]}..{shas[1]}")
        changed = changed_py_files_from_diff(diff)
        if not changed:
            raise ValueError(f"{repo}: base..head changes no non-test .py file")
        specs.append(RepoSpec(repo.name, str(repo.resolve()), shas[0], shas[1], diff, changed))
    return specs


def categories_for(spec: RepoSpec, gap) -> str:
    """Markers on the gap's lines, or for a partial branch on the line its missing branch jumps to."""
    lines = set(range(gap.start_line, gap.end_line + 1))
    lines |= {int(b.split(":")[1]) for b in gap.missing_branches if b.split(":")[1].isdigit()}
    cats = sorted({c for (f, line), c in spec.categories.items() if f == gap.file and line in lines})
    return "+".join(cats) or "unmarked"


def sandbox_for(spec: RepoSpec, work: Path, label: str) -> LocalSandboxClient:
    cwd = work / label
    cwd.mkdir(parents=True)
    return LocalSandboxClient(cwd=str(cwd), ro_paths=[spec.path])


# --------------------------------------------------------------------------
# Dry run: no LLM
# --------------------------------------------------------------------------

def dry_run(specs: list[RepoSpec], work: Path) -> None:
    for spec in specs:
        sb = sandbox_for(spec, work, f"{spec.name}-dry")
        checkout_repo(sb, "repo", spec.path, spec.base_sha)
        prepare_env(sb, "repo")
        base = sb.run(f"cd repo && {COVERAGE_RUN}", timeout=300)
        checkout_repo(sb, "repo", spec.path, spec.pr_sha)
        prepare_env(sb, "repo")
        gaps = find_gaps(sb, "repo", spec.diff, spec.changed_files)
        print(f"## {spec.name}: base suite {'GREEN' if base.ok else 'RED'}; {len(gaps)} gap(s), "
              f"{len(spec.categories)} marker(s)")
        if not base.ok:
            print((base.stdout + base.stderr)[-1500:])
        for g in gaps:
            print(f"  {g.file}:{g.start_line}-{g.end_line} {g.reason:<15} {categories_for(spec, g):<12} "
                  f"in {g.function_context} {getattr(g, 'missing_branches', '')}")
        hit = {(f, l) for (f, l) in spec.categories
               if any(g.file == f and g.start_line <= l <= g.end_line for g in gaps)}
        for key in sorted(set(spec.categories) - hit):
            print(f"  marker with no gap: {key} {spec.categories[key]}")


# --------------------------------------------------------------------------
# Real run
# --------------------------------------------------------------------------

FIELDS = ["repo", "repeat", "gap", "kind", "category", "outcome", "attempts_used", "tiers",
          "success_tier", "success_attempt", "llm_calls", "tokens_in", "tokens_out", "seconds", "last_failure"]


def gap_detail(spec: RepoSpec, repeat: int, r) -> dict:
    """Every attempt's code and verdict for one gap, for the JSONL (and sample_verified.py)."""
    return {"repo": spec.name, "repeat": repeat, "file": r.gap.file, "start_line": r.gap.start_line,
            "end_line": r.gap.end_line, "reason": r.gap.reason, "category": categories_for(spec, r.gap),
            "final_status": r.final_status, "covered_by": str(r.covered_by) if r.covered_by else None,
            "attempts": [{"tier": a.model_tier_used, "code": a.code, "status": v.status, "verified": v.verified,
                          "message": v.message} for a, v in zip(r.attempts, r.verifications)]}


def gap_rows(spec: RepoSpec, repeat: int, result, budget: Budget) -> list[dict]:
    rows = []
    for r in result.records:
        g = r.gap
        usage = budget.per_gap.pop((g.file, g.start_line, g.end_line), []) if r.covered_by is None else []
        success = next((i for i, v in enumerate(r.verifications) if v.verified), None)
        if r.final_status == "skipped_budget":
            outcome = "skipped"
        elif r.covered_by is not None:
            outcome = "closed_reused"
        elif r.final_status == "verified_pass":
            outcome = "closed_generated"
        else:
            outcome = "exhausted"
        generated = r.covered_by is None
        rows.append({
            "repo": spec.name, "repeat": repeat, "gap": f"{g.file}:{g.start_line}-{g.end_line} ({g.function_context})",
            "kind": g.reason, "category": categories_for(spec, g), "outcome": outcome,
            "attempts_used": len(r.attempts) if generated else 0,
            "tiers": "/".join(a.model_tier_used for a in r.attempts) if generated else "",
            "success_tier": r.attempts[success].model_tier_used if generated and success is not None else "",
            "success_attempt": success + 1 if generated and success is not None else "",
            "llm_calls": len(usage), "tokens_in": sum(u[1] for u in usage), "tokens_out": sum(u[2] for u in usage),
            "seconds": round(r.seconds, 2),
            "last_failure": (r.last_verification.message[-400:].replace("\n", " | ")
                             if outcome == "exhausted" and r.last_verification else ""),
        })
    return rows


def pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "0/0"


def summarize(rows: list[dict], runs: list[dict], budget: Budget, meta: dict, cmd: str) -> str:
    gen = [r for r in rows if r["outcome"] in ("closed_generated", "exhausted")]
    closed = [r for r in rows if r["outcome"].startswith("closed")]
    first = [r for r in gen if r["success_attempt"] == 1]
    rescued = [r for r in gen if r["success_attempt"] in (2, 3)]
    tok_in, tok_out = budget.totals()
    out = [f"# Eval: {meta['source']}, {meta['date']}", "",
           f"Command: `{cmd}`  ",
           f"Commit: `{meta['commit']}`; generator.py sha256 `{meta['generator_sha256']}`  ",
           "Models: " + ", ".join(f"{t} = `{m}`" for t, m in meta["models"].items()) + "  ",
           f"Attempts per gap: {MAX_ATTEMPTS} (nano, super, ultra); one lint-repair call allowed per attempt.  ",
           f"Token Factory calls: {budget.calls} (cap {budget.max_calls}); tokens in {tok_in}, out {tok_out}.", "",
           "## Repo runs", "", "| repo | repeat | result | gaps | seconds |", "|---|---|---|---|---|"]
    out += [f"| {r['repo']} | {r['repeat']} | {r['result']} | {r['gaps']} | {r['seconds']:.0f} |" for r in runs]
    out += ["", "## Headline", "",
            "Each gap counted once per repeat. 'Generated' = the LLM was asked for a test for this gap; "
            "'reused' = a test verified for an earlier gap in the same run also closes it (re-verified under "
            "coverage, no LLM call). 'Verified' means the test passes, executes the gap (takes its missing "
            "branch for partial branches), and lint found a non-constant assert. It does not mean the test "
            "would catch a bug in the gap.", "",
            "| metric | value |", "|---|---|",
            f"| gap-runs | {len(rows)} |",
            f"| final closed (generated + reused) | {pct(len(closed), len(rows))} |",
            f"| closed by reuse, no LLM call | {pct(sum(r['outcome'] == 'closed_reused' for r in rows), len(rows))} |",
            f"| generated gaps closed on attempt 1 (nano) | {pct(len(first), len(gen))} |",
            f"| generated gaps rescued on attempt 2-3 (escalation) | {pct(len(rescued), len(gen))} |",
            f"| generated gaps exhausted | {pct(sum(r['outcome'] == 'exhausted' for r in gen), len(gen))} |"]
    for tier in generator.TIERS:
        out.append(f"| closed with first success at {tier} | {sum(r['success_tier'] == tier for r in gen)} |")
    if gen:
        out += [f"| mean LLM calls per generated gap | {sum(r['llm_calls'] for r in gen) / len(gen):.2f} |",
                f"| mean tokens in / out per generated gap | {sum(r['tokens_in'] for r in gen) / len(gen):.0f} / "
                f"{sum(r['tokens_out'] for r in gen) / len(gen):.0f} |",
                f"| mean seconds per generated gap | {sum(r['seconds'] for r in gen) / len(gen):.1f} |"]
    out += ["", "## By category", "",
            "| category | gap-runs | closed | attempt-1 closed (of generated) | reused | exhausted |",
            "|---|---|---|---|---|---|"]
    for cat in sorted({r["category"] for r in rows}):
        rs = [r for r in rows if r["category"] == cat]
        g = [r for r in rs if r["outcome"] in ("closed_generated", "exhausted")]
        out.append(f"| {cat} | {len(rs)} | {pct(sum(r['outcome'].startswith('closed') for r in rs), len(rs))} | "
                   f"{pct(sum(r['success_attempt'] == 1 for r in g), len(g))} | "
                   f"{sum(r['outcome'] == 'closed_reused' for r in rs)} | {sum(r['outcome'] == 'exhausted' for r in rs)} |")
    exhausted = [r for r in rows if r["outcome"] == "exhausted"]
    out += ["", f"## Exhausted gaps ({len(exhausted)})", ""]
    out += [f"- {r['repo']} r{r['repeat']} `{r['gap']}` [{r['category']}], tiers {r['tiers']}: {r['last_failure']}"
            for r in exhausted] or ["None."]
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--max-calls", type=int, default=180)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--tag", default="", help="suffix for the output files, e.g. runB")
    ap.add_argument("--repos-dir", type=Path, default=None,
                    help="evaluate these two-commit repos instead of the seeded ones (see the module docstring)")
    args = ap.parse_args()

    work = Path(tempfile.mkdtemp(prefix="vtga_eval_", dir="/tmp"))
    specs = load_repos(args.repos_dir) if args.repos_dir else build_all(work / "repos")
    if args.dry_run:
        dry_run(specs, work)
        return

    generator.load_env_file()
    missing = generator.missing_env(MAX_ATTEMPTS)
    if missing:
        sys.exit(f"missing {', '.join(missing)}")
    meta = run_metadata(f"repos in {args.repos_dir}" if args.repos_dir else "seeded repos")
    budget = Budget(args.max_calls)
    rows, runs, details = [], [], []
    try:
        for repeat in range(1, args.repeats + 1):
            for spec in specs:
                sb = sandbox_for(spec, work, f"{spec.name}-r{repeat}")
                start = dt.datetime.now()
                try:
                    result = run_pipeline(sb, spec.path, spec.pr_sha, spec.diff, spec.changed_files,
                                          config=PipelineConfig(max_attempts_per_gap=MAX_ATTEMPTS, max_gaps=100),
                                          repo_path="repo", install_deps=True, generate=budget.generate)
                except BudgetExhausted:
                    runs.append({"repo": spec.name, "repeat": repeat, "result": "aborted: call budget reached",
                                 "gaps": "", "seconds": (dt.datetime.now() - start).total_seconds()})
                    raise
                except Exception as exc:  # suite red, deps, checkout: a result, not a skip
                    runs.append({"repo": spec.name, "repeat": repeat,
                                 "result": f"failed: {type(exc).__name__}: {str(exc)[:200]}".replace("\n", " "),
                                 "gaps": "", "seconds": (dt.datetime.now() - start).total_seconds()})
                    continue
                new = gap_rows(spec, repeat, result, budget)
                rows += new
                details += [gap_detail(spec, repeat, r) for r in result.records]
                runs.append({"repo": spec.name, "repeat": repeat, "result": "ok", "gaps": len(new),
                             "seconds": result.duration_seconds})
                print(f"{spec.name} r{repeat}: {sum(r['outcome'].startswith('closed') for r in new)}/{len(new)} "
                      f"closed, calls so far {budget.calls}", file=sys.stderr, flush=True)
    except BudgetExhausted as exc:
        print(f"STOPPED: {exc}", file=sys.stderr)

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    stem = EVIDENCE / f"eval_{meta['date']}" if not args.tag else EVIDENCE / f"eval_{meta['date']}_{args.tag}"
    with open(f"{stem}.jsonl", "w") as f:
        f.writelines(json.dumps(d) + "\n" for d in details)
    with open(f"{stem}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    cmd = "python eval/run_eval.py " + " ".join(shlex.quote(a) for a in sys.argv[1:])
    report = summarize(rows, runs, budget, meta, cmd)
    Path(f"{stem}.md").write_text(report)
    print(report)
    tok_in, tok_out = budget.totals()
    print(f"TOTAL: {budget.calls} Token Factory calls, {tok_in} tokens in, {tok_out} out", file=sys.stderr)


if __name__ == "__main__":
    main()
