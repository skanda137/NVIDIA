"""
Section 3 -- turns a PipelineResult into a markdown report (PR-comment
shaped, since that's the most demo-friendly and most realistic real-world
output target). Kept as a separate module from run_pipeline.py so the
orchestration logic and the presentation logic can change independently.
"""

from __future__ import annotations

from pipeline_models import GapRecord, PipelineResult

_STATUS_ICON = {
    "verified_pass": "✅",   # check
    "exhausted": "\U0001F7E1",   # yellow circle
    "skipped_error": "⚠️",  # warning
}


def _render_gap_section(record: GapRecord) -> str:
    gap = record.gap
    icon = _STATUS_ICON.get(record.final_status, "❓")
    lines = [f"### {icon} `{gap}`"]

    if record.final_status == "verified_pass":
        lines.append(f"Verified in {len(record.attempts)} attempt(s). Generated test:")
        lines.append("```python")
        lines.append(record.best_candidate.code.rstrip())
        lines.append("```")
    else:
        lines.append(
            f"No passing, gap-covering test found after {len(record.attempts)} attempt(s)."
        )
        if record.last_verification:
            lines.append(f"Last result: **{record.last_verification.status}** -- {record.last_verification.message}")
        if record.best_candidate:
            lines.append("Last candidate tried:")
            lines.append("```python")
            lines.append(record.best_candidate.code.rstrip())
            lines.append("```")

    return "\n".join(lines)


def render_markdown(result: PipelineResult) -> str:
    header = (
        f"## Verified Test-Gap Report -- `{result.repo}`\n\n"
        f"{result.diff_summary}\n\n"
        f"**{result.gaps_found}** gap(s) found, "
        f"**{result.tests_verified_pass}** verified with a passing test, "
        f"**{result.tests_verified_fail}** attempted but not verified, "
        f"**{result.tests_errored}** errored out "
        f"({result.tests_generated} test(s) generated total, "
        f"{result.duration_seconds:.1f}s).\n"
    )
    sections = [_render_gap_section(r) for r in result.records]
    return header + "\n" + "\n\n".join(sections) if sections else header + "\nNo gaps found."
