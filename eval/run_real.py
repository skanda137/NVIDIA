"""
Run the real pipeline on public GitHub PRs and write docs/evidence/real_repos_<date>.md.

    ~/.venvs/vtga/bin/python eval/run_real.py --max-calls 70 <pr-url> [<pr-url> ...]

Each PR's clone URL, head SHA and diff are cached under docs/evidence/pr_cache/
on first use; later runs (and the demo) read the cache and never call the
GitHub API. Stages run separately so a failure gets a class: checkout
(network), deps (prepare_env), suite (red or timed out in the sandbox),
coverage mapping, or LLM budget.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shlex
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "eval"), str(ROOT / "files-c" / "section-c")]
import cli  # noqa: E402  (fetch_pr, changed_py_files_from_diff; puts section-a/b on sys.path)
import generator  # noqa: E402
from pipeline_models import PipelineConfig  # noqa: E402
from run_eval import EVIDENCE, MAX_ATTEMPTS, Budget, BudgetExhausted, run_metadata  # noqa: E402
from run_pipeline import checkout_repo, run_pipeline  # noqa: E402
from sandbox_client import LocalSandboxClient  # noqa: E402
from verifier import prepare_env  # noqa: E402

CACHE = EVIDENCE / "pr_cache"


def cached_pr(pr_url: str) -> tuple[str, str, str, str]:
    """(upstream clone_url, head_sha, diff, fetch_ref), from the cache or the GitHub API (then cached)."""
    m = cli.PR_URL.match(pr_url)
    if not m:
        raise ValueError(f"not a GitHub PR URL: {pr_url}")
    stem = CACHE / "__".join(m.groups())
    if not stem.with_suffix(".json").is_file():
        clone_url, sha, diff, fetch_ref = cli.fetch_pr(pr_url)
        CACHE.mkdir(parents=True, exist_ok=True)
        stem.with_suffix(".json").write_text(json.dumps({"pr_url": pr_url, "clone_url": clone_url, "head_sha": sha,
                                                         "fetch_ref": fetch_ref}, indent=2) + "\n")
        stem.with_suffix(".diff").write_text(diff)
    meta = json.loads(stem.with_suffix(".json").read_text())
    return meta["clone_url"], meta["head_sha"], stem.with_suffix(".diff").read_text(), meta["fetch_ref"]


def classify(exc: Exception) -> str:
    text = str(exc)
    if isinstance(exc, BudgetExhausted):
        return "llm budget"
    if "test suite failed" in text:
        return "suite timeout" if "timed out" in text else "suite red"
    if "coverage report" in text or "not in the coverage" in text:
        return "coverage mapping / import path"
    return f"other ({type(exc).__name__})"


def run_one(pr_url: str, work: Path, budget: Budget) -> dict:
    row = {"pr": pr_url, "checkout": "", "deps": "", "suite": "", "gaps": "", "closed": "", "generated": "",
           "reused": "", "exhausted": "", "failure": "", "seconds": 0.0, "detail": ""}
    start = time.monotonic()
    stage = "fetch"
    try:
        clone_url, sha, diff, fetch_ref = cached_pr(pr_url)
        changed = cli.changed_py_files_from_diff(diff)
        row["detail"] = f"head {sha[:8]}; non-test .py files in diff: {', '.join(changed) or 'none'}"
        sb_dir = work / re.sub(r"\W+", "_", pr_url.split("github.com/")[1])
        sb_dir.mkdir(parents=True)
        sb = LocalSandboxClient(cwd=str(sb_dir))
        stage = "checkout"
        checkout_repo(sb, "repo", clone_url, sha, fetch_ref)
        row["checkout"] = "ok"
        stage = "deps"
        prepare_env(sb, "repo")
        has_req = sb.run("test -f repo/requirements.txt").ok
        row["deps"] = "ok" + ("" if has_req else " (no requirements.txt: pytest+coverage only)")
        stage = "pipeline"
        result = run_pipeline(sb, clone_url, sha, diff, changed,
                              config=PipelineConfig(max_attempts_per_gap=MAX_ATTEMPTS, max_gaps=10),
                              repo_path="repo", install_deps=False, generate=budget.generate, fetch_ref=fetch_ref)
        row["suite"] = "green"
        recs = result.records
        row.update(gaps=result.gaps_found,
                   closed=sum(r.final_status == "verified_pass" for r in recs),
                   generated=sum(r.final_status == "verified_pass" and r.covered_by is None for r in recs),
                   reused=result.gaps_closed_by_earlier_test,
                   exhausted=sum(r.final_status == "exhausted" for r in recs))
        report = EVIDENCE / f"real_{sb_dir.name}.md"
        report.write_text(result.report_markdown)
        row["detail"] += f"; full report: {report.relative_to(ROOT).as_posix()}"
    except Exception as exc:
        row["failure"] = classify(exc) if stage == "pipeline" else f"{stage} ({type(exc).__name__})"
        if stage == "pipeline" and row["failure"].startswith("suite"):
            row["suite"] = row["failure"].split()[1]
        row["detail"] += "; " + " ".join(str(exc).split())[-600:]
        if isinstance(exc, BudgetExhausted):
            raise
    finally:
        row["seconds"] = round(time.monotonic() - start, 1)
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("pr_urls", nargs="+")
    ap.add_argument("--max-calls", type=int, default=70)
    args = ap.parse_args()

    generator.load_env_file()
    missing = generator.missing_env(MAX_ATTEMPTS)
    if missing:
        sys.exit(f"missing {', '.join(missing)}")
    meta = run_metadata()
    budget = Budget(args.max_calls)
    work = Path(tempfile.mkdtemp(prefix="vtga_real_", dir="/tmp"))
    rows = []
    for url in args.pr_urls:
        try:
            rows.append(run_one(url, work, budget))
        except BudgetExhausted:
            print("STOPPED: call budget reached", file=sys.stderr)
            break
        print(rows[-1], file=sys.stderr, flush=True)

    tok_in, tok_out = budget.totals()
    cmd = "python eval/run_real.py " + " ".join(shlex.quote(a) for a in sys.argv[1:])
    cols = ["pr", "checkout", "deps", "suite", "gaps", "closed", "generated", "reused", "exhausted", "failure", "seconds"]
    out = [f"# Real public repos, {meta['date']}", "",
           f"Command: `{cmd}`  ",
           f"Commit: `{meta['commit']}`; generator.py sha256 `{meta['generator_sha256']}`  ",
           "Models: " + ", ".join(f"{t} = `{m}`" for t, m in meta["models"].items()) + "  ",
           f"Token Factory calls: {budget.calls} (cap {budget.max_calls}); tokens in {tok_in}, out {tok_out}.  ",
           "PR metadata and diffs are cached in `docs/evidence/pr_cache/`.", "",
           "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
    out += ["", "## Details", ""] + [f"- {r['pr']}: {r['detail']}" for r in rows]
    out += ["", "## Token Factory calls by model", "", "| model | calls | mean seconds | max seconds | mean tokens in / out |",
            "|---|---|---|---|---|"]
    for model in sorted({u[0] for u in budget.usage}):
        us = [u for u in budget.usage if u[0] == model]
        out.append(f"| `{model}` | {len(us)} | {sum(u[3] for u in us) / len(us):.1f} | {max(u[3] for u in us):.1f} | "
                   f"{sum(u[1] for u in us) / len(us):.0f} / {sum(u[2] for u in us) / len(us):.0f} |")
    stem = EVIDENCE / f"real_repos_{meta['date']}.md"
    stem.write_text("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"TOTAL: {budget.calls} Token Factory calls, {tok_in} tokens in, {tok_out} out", file=sys.stderr)


if __name__ == "__main__":
    main()
