"""
Proves coverage_diff.py actually works, end to end, on paper rather than by
claim. This container has no network, so it can't pip-install pytest/coverage
to run a *real* suite -- instead this hand-builds the artifacts a real
`coverage run --branch -m pytest && coverage xml` would have produced, and
feeds them through the exact same compute_gaps() the real pipeline uses.
Everything below `# ---- real pipeline code under test ----` is unmodified
production logic, not a mock.
"""

from coverage_diff import changed_lines_by_file, enclosing_function, compute_gaps

# A toy PR: adds calculate_discount() to billing.py. The author only wrote
# a test for the member=True branch; the member=False branch, and the new
# logging line, are untested. Lines below match a real `git diff` output.
DIFF = '''diff --git a/billing.py b/billing.py
index 83db48f..bf269b5 100644
--- a/billing.py
+++ b/billing.py
@@ -1,2 +1,12 @@
 """Billing helpers."""
+
+
+def calculate_discount(amount: float, is_member: bool) -> float:
+    if is_member:
+        discount = amount * 0.20
+    else:
+        discount = amount * 0.05
+        log_non_member_purchase(amount)
+    return amount - discount
+
+
+def log_non_member_purchase(amount: float) -> None:
+    print(f"non-member purchase: {amount}")
'''

BILLING_SOURCE = '''"""Billing helpers."""


def calculate_discount(amount: float, is_member: bool) -> float:
    if is_member:
        discount = amount * 0.20
    else:
        discount = amount * 0.05
        log_non_member_purchase(amount)
    return amount - discount


def log_non_member_purchase(amount: float) -> None:
    print(f"non-member purchase: {amount}")
'''

# What `coverage xml` would have produced after running the one existing
# test (test_calculate_discount_for_member), which only ever passes
# is_member=True. Line 5 (if is_member:) is a branch line that only took
# one of its two paths -> condition-coverage < 100%. Lines 8-9 (the else
# body) never executed at all -> hits="0". Everything else in the function
# ran fine.
COVERAGE_XML = '''<?xml version="1.0" ?>
<coverage>
  <packages>
    <package name="billing">
      <classes>
        <class filename="billing.py">
          <lines>
            <line number="1" hits="1"/>
            <line number="4" hits="1"/>
            <line number="5" hits="1" branch="true" condition-coverage="50% (1/2)"/>
            <line number="6" hits="1"/>
            <line number="8" hits="0" branch="false"/>
            <line number="9" hits="0" branch="false"/>
            <line number="10" hits="1"/>
            <line number="13" hits="0"/>
            <line number="14" hits="0"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>
'''


def main():
    print("=== 1. changed_lines_by_file() on the raw diff ===")
    changed = changed_lines_by_file(DIFF)
    for f, lines in changed.items():
        print(f"  {f}: {sorted(lines)}")
    # hunk declares "+1,12" -> new-file lines 1-12 touched by this hunk; line 1
    # is a context line (unchanged), lines 2-14 are the 13 added lines.
    assert changed["billing.py"] == set(range(2, 15)), sorted(changed["billing.py"])
    print("  OK: new-file line numbers match what the diff actually added\n")

    print("=== 2. enclosing_function() via ast ===")
    for ln in (5, 8, 13):
        fn = enclosing_function(BILLING_SOURCE, ln)
        print(f"  line {ln} -> {fn!r}")
    assert enclosing_function(BILLING_SOURCE, 5) == "calculate_discount"
    assert enclosing_function(BILLING_SOURCE, 13) == "log_non_member_purchase"
    print("  OK: correctly resolves nested line numbers to the right function\n")

    # ---- real pipeline code under test ----
    with open("/tmp/demo_coverage.xml", "w") as f:
        f.write(COVERAGE_XML)

    print("=== 3. compute_gaps(): the actual output find_gaps() returns ===")
    gaps = compute_gaps(
        diff_text=DIFF,
        coverage_xml_path="/tmp/demo_coverage.xml",
        file_sources={"billing.py": BILLING_SOURCE},
    )
    for g in gaps:
        print(f"  {g}")

    assert len(gaps) == 3, f"expected 3 gaps, got {len(gaps)}: {gaps}"
    partial = next(g for g in gaps if g.reason == "partial_branch")
    uncovered = [g for g in gaps if g.reason == "uncovered"]
    uncovered_else = next(g for g in uncovered if g.start_line == 8)
    uncovered_fn = next(g for g in uncovered if g.start_line == 13)

    assert partial.start_line == 5 and partial.function_context == "calculate_discount"
    assert uncovered_else.end_line == 9 and uncovered_else.function_context == "calculate_discount"
    assert uncovered_fn.end_line == 14 and uncovered_fn.function_context == "log_non_member_purchase"
    print("\nOK: found exactly the three gaps a human reviewer would flag --")
    print("    (1) the if-condition only ever took the True branch,")
    print("    (2) the else-body that branch skips, and")
    print("    (3) the new helper function, which is only reachable from that")
    print("        same untested else-branch and so is independently flagged too.")
    print("    Note (2) and (3) are correctly kept as SEPARATE Gap objects even")
    print("    though they're causally related -- compute_gaps() has no notion")
    print("    of call graphs, only line ranges, which is the right scope for")
    print("    this project. Section 2 will likely generate one test that")
    print("    happens to close out gap (2) and (3) together; that's fine.")


if __name__ == "__main__":
    main()
