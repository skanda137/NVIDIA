"""
The one piece of this project nobody else has a template for: given a
unified diff and a coverage.py Cobertura XML report, find which *new or
changed* lines the diff introduced are not actually exercised by tests.

This is deliberately deterministic, not LLM-based -- it's the part of the
project's "verified" claim that's true rather than plausible-sounding.
"""

from __future__ import annotations

import ast
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional

from models import Gap


# ---------- 1. Parse the diff: which new-file lines did this PR touch? ----------

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def changed_lines_by_file(diff_text: str) -> dict[str, set[int]]:
    """Parse a standard `git diff` and return, per target file, the set of
    line numbers (in the NEW version of the file) that were added or
    modified. Deleted lines are irrelevant -- they don't exist to cover.

    Hunk bodies are consumed by the line counts in their `@@` header, so a
    body line is never mistaken for a header (an added line "++ x" shows up
    as "+++ x"), and `\\ No newline at end of file` never shifts the count."""
    result: dict[str, set[int]] = {}
    current_file: Optional[str] = None
    new_line_no = 0
    old_left = new_left = 0  # lines of the current hunk body not yet seen

    for line in diff_text.splitlines():
        if old_left > 0 or new_left > 0:
            if line.startswith("\\"):
                continue  # "\ No newline at end of file": not a line of either file
            if line.startswith("+"):
                if current_file is not None:
                    result[current_file].add(new_line_no)
                new_line_no += 1
                new_left -= 1
            elif line.startswith("-"):
                old_left -= 1  # removed line, doesn't exist in new file
            else:
                new_line_no += 1  # context line (or "" if its leading space was stripped)
                old_left -= 1
                new_left -= 1
            continue

        if line.startswith("+++ "):
            path = line[4:].split("\t", 1)[0].strip()
            if path == "/dev/null":
                current_file = None  # deleted file
            else:
                # "+++ b/app/billing.py" -> "app/billing.py"
                current_file = path.split("/", 1)[1] if path.startswith(("a/", "b/")) else path
                result.setdefault(current_file, set())
        elif line.startswith("@@"):
            m = _HUNK_HEADER.match(line)
            if m:
                old_left = int(m.group(1) if m.group(1) is not None else 1)
                new_line_no = int(m.group(2))
                new_left = int(m.group(3) if m.group(3) is not None else 1)

    return result


# ---------- 2. Parse coverage.py's Cobertura XML: what's covered, what isn't? ----------

@dataclass
class LineCoverage:
    hits: int
    is_branch: bool
    condition_coverage_pct: Optional[int]  # None if not a branch line
    # Destinations coverage.py reports as never taken from this line, raw tokens:
    # a line number ("8") or "exit". Empty for non-branch / fully covered lines.
    missing_branches: tuple[str, ...] = ()


def parse_coverage_xml(xml_text: str) -> dict[str, dict[int, LineCoverage]]:
    """Returns {file_path_as_in_report: {line_number: LineCoverage}}.
    Takes the XML *text* (read it out of the sandbox with read_file) so no
    temp file, and no hardcoded /tmp, is involved."""
    root = ET.fromstring(xml_text.encode("utf-8"))
    out: dict[str, dict[int, LineCoverage]] = {}

    for cls in root.iter("class"):
        filename = cls.get("filename")
        if not filename:
            continue
        lines: dict[int, LineCoverage] = {}
        for line_el in cls.iter("line"):
            number = int(line_el.get("number"))
            hits = int(line_el.get("hits", "0"))
            is_branch = line_el.get("branch") == "true"
            cc = line_el.get("condition-coverage")  # e.g. "50% (1/2)"
            pct = int(cc.split("%")[0]) if cc else None
            mb = tuple(t.strip() for t in (line_el.get("missing-branches") or "").split(",") if t.strip())
            lines[number] = LineCoverage(hits=hits, is_branch=is_branch,
                                         condition_coverage_pct=pct, missing_branches=mb)
        out[filename] = lines

    return out


def find_coverage_key(coverage: dict[str, dict[int, LineCoverage]], file: str) -> Optional[str]:
    """Match a diff path to a path in the coverage report. The report's paths are
    relative to coverage's `source` root, which is not always the repo root
    (a .coveragerc with source=pkg, or a src/ layout), so exact match first,
    then the longest report path that is a path-suffix of the diff path."""
    if file in coverage:
        return file
    candidates = [k for k in coverage if file.endswith("/" + k)]
    return max(candidates, key=len) if candidates else None


# ---------- 3. Function context: what function/method encloses a given line? ----------

def enclosing_function(source: str, line_no: int) -> str:
    """Walk the AST and return the innermost function/method containing
    `line_no`, or "" if it's module-level code. Using `ast` instead of
    regex/indentation guessing because it's exact and handles nested
    functions, decorators, and async def correctly."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ""

    best: Optional[str] = None
    best_span = None  # (start, end) of the smallest enclosing def found so far

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno
            end = getattr(node, "end_lineno", None) or start
            if start <= line_no <= end:
                span = end - start
                if best_span is None or span < best_span:
                    best = node.name
                    best_span = span

    return best or ""


# ---------- 4. Tie it together: diff + coverage -> list of Gaps ----------

def compute_gaps(
    diff_text: str,
    coverage_xml: str,
    file_sources: dict[str, str],
) -> list[Gap]:
    """
    coverage_xml: the text of the coverage.xml produced by `coverage xml`.
    file_sources: {relative_path: full_file_text_at_PR_head}, for the .py files
        the caller wants analysed. Needed for AST function-context lookup.
        A changed file that is not in file_sources is ignored (not Python).
        A changed file that IS in file_sources but missing from the coverage
        report raises: silently returning no gaps for it hid real gaps before.
    """
    changed = changed_lines_by_file(diff_text)
    coverage = parse_coverage_xml(coverage_xml)
    gaps: list[Gap] = []

    for file, touched_lines in changed.items():
        if file not in file_sources:
            continue  # not a file the caller asked us to analyse

        key = find_coverage_key(coverage, file)
        if key is None:
            raise ValueError(
                f"{file} is in the diff but not in the coverage report "
                f"(report has: {sorted(coverage)[:8]}). Likely causes: the file is "
                f"excluded by the repo's coverage config (omit/source), or it is outside "
                f"the directory coverage was run from."
            )
        line_cov = coverage[key]
        source = file_sources[file]

        pending_start: Optional[int] = None
        pending_end: Optional[int] = None
        pending_reason: Optional[str] = None
        pending_branches: list[str] = []

        def flush():
            nonlocal pending_start, pending_end, pending_reason, pending_branches
            if pending_start is not None:
                gaps.append(Gap(
                    file=file,
                    start_line=pending_start,
                    end_line=pending_end,
                    function_context=enclosing_function(source, pending_start),
                    reason=pending_reason,  # type: ignore[arg-type]
                    missing_branches=tuple(pending_branches),
                ))
            pending_start = pending_end = pending_reason = None
            pending_branches = []

        def only_unmeasured_between(a: int, b: int) -> bool:
            # lines strictly between a and b must be added lines that coverage does
            # not measure (blank lines, comments, `else:`), otherwise it is not one block
            return all(l in touched_lines and l not in line_cov for l in range(a + 1, b))

        for line_no in sorted(touched_lines):
            cov = line_cov.get(line_no)
            if cov is None:
                continue  # unmeasured line: neither a gap nor a break in one

            reason = None
            if cov.hits == 0:
                reason = "uncovered"
            elif cov.is_branch and cov.condition_coverage_pct is not None and cov.condition_coverage_pct < 100:
                reason = "partial_branch"
                if not cov.missing_branches:
                    raise ValueError(
                        f"{file}:{line_no} is a partial branch but the report has no "
                        f"missing-branches attribute; cannot verify a test against it."
                    )

            if reason is None:
                flush()
                continue

            extends = (pending_start is not None and reason == pending_reason
                       and only_unmeasured_between(pending_end, line_no))
            if not extends:
                flush()
                pending_start, pending_reason = line_no, reason
            pending_end = line_no
            if reason == "partial_branch":
                pending_branches.extend(f"{line_no}:{t}" for t in cov.missing_branches)

        flush()

    return gaps
