"""Full pipeline with the REAL Nemotron model (no scripted LLM). Run on your machine:
    export TOKEN_FACTORY_API_KEY=...
    python live_pipeline.py
Uses the toy billing repo from demo_pipeline.py; real git, pytest, coverage and Nemotron."""
import tempfile
from pathlib import Path

import generator as g
from demo_pipeline import build_fixture_repo
from pipeline_models import PipelineConfig
from run_pipeline import run_pipeline
from sandbox_client import LocalSandboxClient

print("provider:", g._provider()[0], "| tiers:", g.resolved_tiers())
with tempfile.TemporaryDirectory() as tmp:
    url, diff, sha = build_fixture_repo(Path(tmp))
    r = run_pipeline(LocalSandboxClient(cwd=tmp), url, sha, diff, ["billing.py"],
                     config=PipelineConfig(max_attempts_per_gap=3), repo_path="checked_out_repo")
print(r.report_markdown)
for rec in r.records:
    print(rec.gap, "->", rec.final_status,
          [(c.model_tier_used, v.status, v.coverage_hit) for c, v in zip(rec.attempts, rec.verifications)])
