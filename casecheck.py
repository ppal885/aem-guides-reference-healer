#!/usr/bin/env python3
"""The case matrix: every case of every feature, simple or edge, and where it stands (eval/cases.json).

    python3 casecheck.py                       # the agents' tests named in the matrix (no model, seconds)
    python3 casecheck.py --editor ~/xmleditor  # and the editor's tests it names (jest, a minute or two)
    python3 casecheck.py --markdown            # the table for the README

A case is "pass" or "fail" when a test checks it, "measured" when a model or AEM run checked it
(the file the result is written in is named), "gap" when it was tried and is not handled
yet (to be fixed), "known miss" when it is not handled on purpose, and "not built" when nothing
checks it yet. No model is called and AEM is not used.
"""
import argparse
import collections
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, "eval", "cases.json")


def load(path=CASES):
    with open(path) as f:
        return json.load(f)["cases"]


def run_py(name):
    """'pass', 'fail', or 'no such test' for one test of tests/ ("test_refs.Class.method")."""
    sys.path.insert(0, HERE)
    try:
        suite = unittest.defaultTestLoader.loadTestsFromName("tests." + name)
    except (AttributeError, ImportError):
        return "no such test"
    if suite.countTestCases() == 0 or any(type(t).__name__ == "_FailedTest" for t in suite):
        return "no such test"
    result = unittest.TestResult()
    suite.run(result)
    if result.errors and any("AttributeError" in text and "has no attribute" in text for _, text in result.errors):
        return "no such test"
    return "pass" if result.wasSuccessful() else "fail"


def run_editor(editor, path, name):
    """'pass' or 'fail' for the editor's jest tests in path whose name starts with name."""
    env = dict(os.environ, CI="true")
    proc = subprocess.run(["npx", "jest", path, "-t", name], cwd=editor, capture_output=True, text=True, env=env, timeout=600)
    out = proc.stdout + proc.stderr
    passed = "passed" in out and "failed" not in out.split("Tests:")[-1] and "Tests:" in out
    return "pass" if proc.returncode == 0 and passed else "fail"


def status(case, editor=None):
    check = case.get("check") or {}
    if "py" in check:
        return run_py(check["py"]), "test " + check["py"].split(".")[-1]
    if "editor" in check:
        if not editor:
            return "editor test", "%s: %s" % (os.path.basename(check["editor"]), check["name"])
        return run_editor(editor, check["editor"], check["name"]), "%s: %s" % (os.path.basename(check["editor"]), check["name"])
    if "measured" in check:
        there = os.path.exists(os.path.join(HERE, check["measured"]))
        return ("measured" if there else "fail"), "%s (%s)" % (check["says"], check["measured"])
    if "known_miss" in check:
        return "known miss", check["known_miss"]
    if "gap" in check:
        return "gap", check["gap"]
    return "not built", check.get("note", "")


def table(rows, markdown=False):
    lines = []
    if markdown:
        lines.append("| Case | Feature | Level | Status | How it is checked |")
        lines.append("|---|---|---|---|---|")
        for case, state, how in rows:
            lines.append("| %s %s | %s | %s | %s | %s |" % (case["id"], case["case"], case["feature"], case["level"], state, how))
    else:
        for case, state, how in rows:
            lines.append("%-14s %-6s %-12s %s" % (case["id"], case["level"], state, case["case"][:90]))
    return "\n".join(lines)


def summary(rows):
    counts = collections.OrderedDict()
    for case, state, _ in rows:
        key = (case["feature"], case["level"])
        counts.setdefault(key, collections.Counter())[state] += 1
    lines = []
    for (feature, level), c in counts.items():
        lines.append("%-18s %-6s %s" % (feature, level, ", ".join("%s %d" % (k, v) for k, v in sorted(c.items()))))
    total = collections.Counter(state for _, state, _ in rows)
    lines.append("all: " + ", ".join("%s %d" % (k, v) for k, v in sorted(total.items())))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--editor", help="the xmleditor checkout, to run its tests too")
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--feature", help="only this feature")
    args = parser.parse_args()
    cases = [c for c in load() if not args.feature or c["feature"] == args.feature]
    rows = [(c,) + status(c, args.editor) for c in cases]
    print(table(rows, args.markdown))
    print()
    print(summary(rows))
    return 1 if any(state in ("fail", "no such test") for _, state, _ in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
