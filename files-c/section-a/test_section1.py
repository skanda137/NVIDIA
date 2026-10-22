"""
Tests for the Section 1 audit fixes. Run: python -m unittest -v test_section1
(also collected by pytest). They use a fake sandbox, so they exercise our logic
against canned coverage XML in the shape coverage.py 7.16.2 really produced in
the audit (E1: `missing-branches="8"`). They do NOT run coverage.py or pytest.
"""

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from coverage_diff import changed_lines_by_file, compute_gaps, find_coverage_key, parse_coverage_xml
from models import CandidateTest, Gap
from sandbox_client import CommandResult, LocalSandboxClient
from verifier import CANDIDATE_RUN_CMD, find_gaps, verify_test


def xml(filename: str, *lines: str) -> str:
    return (f'<?xml version="1.0" ?><coverage><packages><package name="p"><classes>'
            f'<class filename="{filename}"><lines>{"".join(lines)}</lines></class>'
            f'</classes></package></packages></coverage>')


BRANCH_50 = '<line number="5" hits="1" branch="true" condition-coverage="50% (1/2)" missing-branches="8"/>'


def diff_adding(path: str, n_lines: int) -> str:
    body = "".join(f"+line{i}\n" for i in range(1, n_lines + 1))
    return f"--- a/{path}\n+++ b/{path}\n@@ -0,0 +1,{n_lines} @@\n{body}"


class FakeSandbox:
    """Records commands; `responder(cmd)` returns a CommandResult or None (-> ok)."""

    def __init__(self, responder=None, files=None):
        self.commands, self.written = [], {}
        self.files = dict(files or {})
        self.responder = responder or (lambda cmd: None)

    def run(self, command, timeout=120, network=False):
        self.commands.append(command)
        return self.responder(command) or CommandResult("", "", 0)

    run_disposable = run

    def write_file(self, path, content):
        self.written[path] = content
        return CommandResult("", "", 0)

    def read_file(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]


def partial_gap():
    return Gap("billing.py", 5, 5, "calculate_discount", "partial_branch", missing_branches=("5:8",))


def candidate(gap, code="def test_x():\n    assert True\n"):
    return CandidateTest(code=code, target_gap=gap, model_tier_used="stub")


class ParseDiff(unittest.TestCase):
    def test_no_newline_marker_does_not_shift_lines(self):
        diff = ("--- a/m.py\n+++ b/m.py\n@@ -1,2 +1,3 @@\n x = 1\n-y = 2\n"
                "\\ No newline at end of file\n+y = 3\n+z = 4\n")
        self.assertEqual(changed_lines_by_file(diff), {"m.py": {2, 3}})

    def test_added_line_that_looks_like_a_header_is_content(self):
        diff = "--- a/m.py\n+++ b/m.py\n@@ -1 +1,3 @@\n+++ counter\n+-- x\n x = 1\n"
        self.assertEqual(changed_lines_by_file(diff), {"m.py": {1, 2}})

    def test_removed_line_that_looks_like_a_header_is_content(self):
        diff = "--- a/m.py\n+++ b/m.py\n@@ -1,2 +1,2 @@\n--- old\n+new\n x = 1\n"
        self.assertEqual(changed_lines_by_file(diff), {"m.py": {1}})

    def test_deleted_file_then_next_file(self):
        diff = ("diff --git a/old.py b/old.py\n--- a/old.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-a\n-b\n"
                "diff --git a/new.py b/new.py\n--- /dev/null\n+++ b/new.py\n@@ -0,0 +1,2 @@\n+a\n+b\n")
        self.assertEqual(changed_lines_by_file(diff), {"new.py": {1, 2}})

    def test_two_hunks_and_no_prefix_paths(self):
        diff = "--- m.py\n+++ m.py\n@@ -1 +1,2 @@\n a\n+b\n@@ -10,2 +11,2 @@\n-c\n+C\n d\n"
        self.assertEqual(changed_lines_by_file(diff), {"m.py": {2, 11}})


class ParseAndMatch(unittest.TestCase):
    def test_missing_branches_parsed(self):
        cov = parse_coverage_xml(xml("billing.py", BRANCH_50))
        self.assertEqual(cov["billing.py"][5].missing_branches, ("8",))

    def test_exit_token_kept_raw(self):
        line = '<line number="3" hits="1" branch="true" condition-coverage="50% (1/2)" missing-branches="exit"/>'
        self.assertEqual(parse_coverage_xml(xml("a.py", line))["a.py"][3].missing_branches, ("exit",))

    def test_suffix_match_source_pkg_and_src_layout(self):  # audit E3
        self.assertEqual(find_coverage_key({"mod.py": {}}, "pkg/mod.py"), "mod.py")
        self.assertEqual(find_coverage_key({"pkg/mod.py": {}}, "src/pkg/mod.py"), "pkg/mod.py")
        self.assertIsNone(find_coverage_key({"other.py": {}}, "pkg/mod.py"))

    def test_longest_suffix_wins(self):
        cov = {"__init__.py": {}, "sub/__init__.py": {}}
        self.assertEqual(find_coverage_key(cov, "pkg/sub/__init__.py"), "sub/__init__.py")


class ComputeGaps(unittest.TestCase):
    def test_src_layout_now_finds_gap(self):  # E3 used to return []
        report = xml("pkg/mod.py", '<line number="1" hits="0"/>')
        gaps = compute_gaps(diff_adding("src/pkg/mod.py", 1), report, {"src/pkg/mod.py": "x = 1\n"})
        self.assertEqual([(g.file, g.start_line, g.reason) for g in gaps], [("src/pkg/mod.py", 1, "uncovered")])

    def test_py_file_missing_from_report_raises(self):  # E4b used to return []
        with self.assertRaises(ValueError) as cm:
            compute_gaps(diff_adding("m.py", 2), xml("other.py", '<line number="1" hits="1"/>'), {"m.py": "x\ny\n"})
        self.assertIn("m.py", str(cm.exception))

    def test_non_python_file_in_diff_ignored(self):
        self.assertEqual(compute_gaps(diff_adding("README.md", 3), xml("a.py"), {}), [])

    def test_blank_and_comment_lines_do_not_split_one_block(self):  # E4c
        # lines 2 and 5-6 uncovered; 3-4 are a blank line and a comment (unmeasured)
        report = xml("m.py", '<line number="2" hits="0"/>', '<line number="5" hits="0"/>', '<line number="6" hits="0"/>')
        gaps = compute_gaps(diff_adding("m.py", 6), report, {"m.py": "\n" * 6})
        self.assertEqual([(g.start_line, g.end_line) for g in gaps], [(2, 6)])

    def test_untouched_line_between_still_splits(self):
        # diff adds lines 2 and 4; line 3 is unchanged context (and uncovered). It is not a
        # new line, so it must not be swallowed into a gap range spanning 2-4.
        diff = "--- a/m.py\n+++ b/m.py\n@@ -2,1 +2,3 @@\n+a\n b\n+c\n"
        report = xml("m.py", '<line number="2" hits="0"/>', '<line number="3" hits="0"/>', '<line number="4" hits="0"/>')
        gaps = compute_gaps(diff, report, {"m.py": "\n" * 4})
        self.assertEqual([(g.start_line, g.end_line) for g in gaps], [(2, 2), (4, 4)])

    def test_covered_line_between_splits(self):
        report = xml("m.py", '<line number="1" hits="0"/>', '<line number="2" hits="1"/>', '<line number="3" hits="0"/>')
        gaps = compute_gaps(diff_adding("m.py", 3), report, {"m.py": "\n" * 3})
        self.assertEqual([(g.start_line, g.end_line) for g in gaps], [(1, 1), (3, 3)])

    def test_partial_branch_gap_carries_missing_branches(self):
        gaps = compute_gaps(diff_adding("billing.py", 5), xml("billing.py", BRANCH_50), {"billing.py": "\n" * 5})
        self.assertEqual(gaps[0].missing_branches, ("5:8",))

    def test_partial_branch_without_attribute_raises(self):
        line = '<line number="1" hits="1" branch="true" condition-coverage="50% (1/2)"/>'
        with self.assertRaises(ValueError):
            compute_gaps(diff_adding("a.py", 1), xml("a.py", line), {"a.py": "x\n"})


class FindGaps(unittest.TestCase):
    def test_failure_message_includes_stdout(self):  # E6 had an empty message
        sb = FakeSandbox(lambda cmd: CommandResult("ModuleNotFoundError: No module named 'requests'", "", 1))
        with self.assertRaises(RuntimeError) as cm:
            find_gaps(sb, "/repo", "", ["a.py"])
        self.assertIn("requests", str(cm.exception))

    def test_runs_with_source_dot(self):
        sb = FakeSandbox(files={"/repo/coverage.xml": xml("a.py", '<line number="1" hits="1"/>'), "/repo/a.py": "x\n"})
        find_gaps(sb, "/repo", diff_adding("a.py", 1), ["a.py"])
        self.assertIn("--source=.", sb.commands[0])
        self.assertIn("--branch", sb.commands[0])


class VerifyTest(unittest.TestCase):
    def run_verify(self, gap, report_xml, code="def test_x():\n    assert True\n", responder=None):
        sb = FakeSandbox(responder, files={"/repo/_scratch_coverage.xml": report_xml} if report_xml else {})
        return sb, verify_test(sb, "/repo", candidate(gap, code))

    def test_E1_partial_branch_candidate_rerunning_covered_branch_is_rejected(self):
        # candidate only takes the True side: line 5 still reports branch 8 missing
        sb, r = self.run_verify(partial_gap(), xml("billing.py", BRANCH_50))
        self.assertEqual((r.status, r.coverage_hit, r.verified), ("pass", False, False))
        self.assertIn("vacuous", r.message)

    def test_partial_branch_candidate_taking_missing_branch_is_accepted(self):
        # candidate takes the else side: now the *other* destination (6) is the one missing
        other = '<line number="5" hits="1" branch="true" condition-coverage="50% (1/2)" missing-branches="6"/>'
        sb, r = self.run_verify(partial_gap(), xml("billing.py", other))
        self.assertTrue(r.verified, r.message)

    def test_branch_line_absent_from_report_is_not_taken(self):
        sb, r = self.run_verify(partial_gap(), xml("billing.py", '<line number="9" hits="1"/>'))
        self.assertFalse(r.verified, r.message)

    def test_exit_branch_is_verifiable(self):
        gap = Gap("a.py", 3, 3, "f", "partial_branch", missing_branches=("3:exit",))
        still = '<line number="3" hits="1" branch="true" condition-coverage="50% (1/2)" missing-branches="exit"/>'
        done = '<line number="3" hits="1" branch="true" condition-coverage="50% (1/2)" missing-branches="4"/>'
        self.assertFalse(self.run_verify(gap, xml("a.py", still))[1].verified)
        self.assertTrue(self.run_verify(gap, xml("a.py", done))[1].verified)

    def test_uncovered_gap_needs_a_hit(self):
        gap = Gap("billing.py", 8, 9, "f", "uncovered")
        hit = xml("billing.py", '<line number="8" hits="1"/>', '<line number="9" hits="1"/>')
        miss = xml("billing.py", '<line number="8" hits="0"/>', '<line number="9" hits="0"/>')
        self.assertTrue(self.run_verify(gap, hit)[1].verified)
        self.assertFalse(self.run_verify(gap, miss)[1].verified)

    def test_partial_branch_gap_without_data_raises(self):
        bare = Gap("a.py", 3, 3, "f", "partial_branch")
        with self.assertRaises(ValueError):
            self.run_verify(bare, xml("a.py", BRANCH_50))

    def test_failing_test_returns_fail_with_output(self):
        _, r = self.run_verify(partial_gap(), None,
                               responder=lambda c: CommandResult("1 failed: AttributeError", "", 1) if "pytest" in c else None)
        self.assertEqual(r.status, "fail")
        self.assertIn("AttributeError", r.message)

    def test_timeout_is_a_fail_with_reason(self):
        _, r = self.run_verify(partial_gap(), None,
                               responder=lambda c: CommandResult("", "", 124) if "pytest" in c else None)
        self.assertEqual(r.status, "fail")
        self.assertIn("timed out", r.message)

    def test_class_based_test_accepted_and_whole_file_run(self):  # B14
        code = "class TestX:\n    def test_y(self):\n        assert True\n"
        sb, r = self.run_verify(partial_gap(), xml("billing.py", BRANCH_50), code=code)
        self.assertNotEqual(r.status, "error")
        self.assertNotIn("::", "".join(c for c in sb.commands if "pytest" in c))

    def test_no_test_function_is_error_and_touches_nothing(self):
        sb, r = self.run_verify(partial_gap(), None, code="print('x')")
        self.assertEqual(r.status, "error")
        self.assertEqual((sb.commands, sb.written), ([], {}))

    def test_bytecode_and_cache_disabled_for_candidate_run(self):  # B3
        self.assertIn("PYTHONDONTWRITEBYTECODE=1", CANDIDATE_RUN_CMD)
        self.assertIn("-p no:cacheprovider", CANDIDATE_RUN_CMD)
        self.assertIn("--source=.", CANDIDATE_RUN_CMD)

    def test_cleanup_runs_even_when_report_is_unreadable(self):
        sb, r = self.run_verify(partial_gap(), None)  # no scratch xml -> FileNotFoundError path
        self.assertEqual(r.status, "error")
        self.assertIn("rm -f", sb.commands[-1])

    def test_cleanup_runs_when_gap_data_is_invalid(self):
        sb = FakeSandbox(files={"/repo/_scratch_coverage.xml": xml("a.py", BRANCH_50)})
        with self.assertRaises(ValueError):
            verify_test(sb, "/repo", candidate(Gap("a.py", 3, 3, "f", "partial_branch")))
        self.assertIn("rm -f", sb.commands[-1])


@unittest.skipIf(os.name != "posix", "process-group kill is POSIX only")
class LocalClient(unittest.TestCase):
    def test_timeout_kills_tree_and_returns_124(self):  # B7
        with tempfile.TemporaryDirectory() as d:
            t0 = time.time()
            r = LocalSandboxClient(d).run("sleep 30; echo unreachable", timeout=1)
            self.assertEqual(r.returncode, 124)
            self.assertLess(time.time() - t0, 5)
            self.assertIn("timed out", r.stderr)

    def test_absolute_paths_roundtrip(self):  # B11 / E5
        with tempfile.TemporaryDirectory() as d:
            c = LocalSandboxClient(d)
            c.write_file(os.path.join(d, "abs.txt"), "hi")
            self.assertEqual(c.read_file(os.path.join(d, "abs.txt")), "hi")

    def test_relative_paths_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            c = LocalSandboxClient(d)
            c.write_file("rel.txt", "hi")
            self.assertEqual(c.read_file("rel.txt"), "hi")


if __name__ == "__main__":
    unittest.main()
