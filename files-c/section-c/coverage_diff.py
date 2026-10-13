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

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_lines_by_file(diff_text: str) -> dict[str, set[int]]:
    """Parse a standard `git diff` and return, per target file, the set of
    line numbers (in the NEW version of the file) that were added or
    modified. Deleted lines are irrelevant -- they don't exist to cover."""
    result: dict[str, set[int]] = {}
    current_file: Optional[str] = None
    new_line_no = 0

    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path == "/dev/null":
                current_file = None
            else:
                # "+++ b/app/billing.py" -> "app/billing.py"
                current_file = path.split("/", 1)[1] if path.startswith(("a/", "b/")) else path
                result.setdefault(current_file, set())
            continue

        if line.startswith("@@"):
            m = _HUNK_HEADER.match(line)
            if m:
                new_line_no = int(m.group(1))
            continue

        if current_file is None:
            continue

        if line.startswith("+") and not line.startswith("+++"):
            result[current_file].add(new_line_no)
            new_line_no += 1
        elif line.startswith("-") and not line.startswith("---"):
            pass  # removed line, doesn't exist in new file, don't advance counter
        else:
            new_line_no += 1  # context line, exists in both, advance counter

    return result


# ---------- 2. Parse coverage.py's Cobertura XML: what's covered, what isn't? ----------

@dataclass
class LineCoverage:
    hits: int
    is_branch: bool
    condition_coverage_pct: Optional[int]  # None if not a branch line


def parse_coverage_xml(xml_path: str) -> dict[str, dict[int, LineCoverage]]:
    """Returns {relative_file_path: {line_number: LineCoverage}}."""
    tree = ET.parse(xml_path)
    root = tree.getroot()
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
            lines[number] = LineCoverage(hits=hits, is_branch=is_branch, condition_coverage_pct=pct)
        out[filename] = lines

    return out


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
    coverage_xml_path: str,
    file_sources: dict[str, str],
) -> list[Gap]:
    """
    file_sources: {relative_path: full_file_text_at_PR_head} -- needed for
    AST-based function-context lookup. Caller reads these from the sandbox
    (coverage.xml alone doesn't carry the source text).
    """
    changed = changed_lines_by_file(diff_text)
    coverage = parse_coverage_xml(coverage_xml_path)
    gaps: list[Gap] = []

    for file, touched_lines in changed.items():
        if file not in coverage or file not in file_sources:
            continue  # not a covered/known Python file (e.g. a .md or .json change)

        line_cov = coverage[file]
        source = file_sources[file]

        # bucket consecutive untested lines of the same kind into ranges
        pending_start: Optional[int] = None
        pending_end: Optional[int] = None
        pending_reason: Optional[str] = None

        def flush():
            nonlocal pending_start, pending_end, pending_reason
            if pending_start is not None:
                gaps.append(Gap(
                    file=file,
                    start_line=pending_start,
                    end_line=pending_end,
                    function_context=enclosing_function(source, pending_start),
                    reason=pending_reason,  # type: ignore[arg-type]
                ))
            pending_start = None
            pending_end = None
            pending_reason = None

        for line_no in sorted(touched_lines):
            cov = line_cov.get(line_no)
            reason = None
            if cov is not None:
                if cov.hits == 0:
                    reason = "uncovered"
                elif cov.is_branch and cov.condition_coverage_pct is not None and cov.condition_coverage_pct < 100:
                    reason = "partial_branch"

            if reason is None:
                flush()
                continue

            contiguous = (pending_end is not None and line_no == pending_end + 1)
            same_reason = (reason == pending_reason)

            if pending_start is not None and contiguous and same_reason:
                pending_end = line_no  # extend the current range
            else:
                flush()  # close out whatever was pending (no-op if nothing pending)
                pending_start, pending_end, pending_reason = line_no, line_no, reason

        flush()

    return gaps
