#!/usr/bin/env python3
"""Scores how the finder agent ranks candidates when two targets are plausible (garage-week PoC).

    python3 samples/gen_rank.py
    python3 rankeval.py [--runs 2] [--backend cli|sdk] [--out eval/refs/rank-eval.json]

samples/rank-demo has nine broken references; for each, two pieces of the new content could be
meant, and the sentence around the reference says which one is right (expected.json). The planner
runs on it with an empty memory. Scored per reference:

    first right     the proposed target is the right one
    in the list     the right one is among the candidates shown to the author, but not first
    not offered     the right one is not among the candidates

Two of the nine share one old target but mean different pieces. The agents give one answer per
broken target, so at most one of those two can be "first right"; the other shows whether the
second meaning is at least offered.
"""
import argparse
import collections
import json
import os
import time

import refplan
import usage

HERE = os.path.dirname(os.path.abspath(__file__))


def payload(root):
    files = []
    for name in sorted(os.listdir(os.path.join(root, "v2"))):
        with open(os.path.join(root, "v2", name), encoding="utf-8") as handle:
            xml = handle.read()
        previous, old = [], os.path.join(root, "v1", name)
        if os.path.exists(old):
            with open(old, encoding="utf-8") as handle:
                previous = [handle.read()]
        files.append({"path": "/" + name, "xml": xml, "previous": [p for p in previous if p != xml]})
    return {"files": files}


def same(value, right):
    """A whole topic may be named with or without its topic id: "a.dita" and "a.dita#a"."""
    return bool(value) and (value == right or ("#" not in right and "/" not in value.partition("#")[2]
                                                and value.partition("#")[0] == right))


def score(case, repair):
    if not repair:
        return "not offered", 0
    offered = [c["value"] for c in (repair.get("detail") or {}).get("candidates", [])]
    if same(repair.get("new"), case["right"]):
        return "first right", len(offered)
    return ("in the list" if any(same(v, case["right"]) for v in offered) else "not offered"), len(offered)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", default=os.path.join(HERE, "samples", "rank-demo"))
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--backend", default="cli", choices=["cli", "sdk"])
    parser.add_argument("--out", default=os.path.join(HERE, "eval", "refs", "rank-eval.json"))
    args = parser.parse_args()
    with open(os.path.join(args.sample, "expected.json"), encoding="utf-8") as handle:
        cases = json.load(handle)
    runs, mark = [], usage.position()
    for number in range(1, args.runs + 1):
        started = time.time()
        out = refplan.plan_files(payload(args.sample), backend=args.backend, log=lambda message: None, memory={})
        by_ref = {(r["file"].lstrip("/"), r["attribute"], r["old"]): r for r in out["repairs"]}
        rows, counts = [], collections.Counter()
        for case in cases:
            repair = by_ref.get((case["file"], case["attribute"], case["old"]))
            outcome, offered = score(case, repair)
            counts[outcome] += 1
            rows.append({"file": case["file"], "old": case["old"], "right": case["right"], "proposed": (repair or {}).get("new"),
                         "verdict": (repair or {}).get("verdict"), "candidates": offered, "outcome": outcome,
                         "likelihoods": [c["likelihood"] for c in ((repair or {}).get("detail") or {}).get("candidates", [])]})
        applied_wrong = sum(1 for r in rows if r["verdict"] == "fix" and r["outcome"] != "first right")
        runs.append({"run": number, "seconds": round(time.time() - started), "scores": dict(counts),
                     "applied_without_asking_and_wrong": applied_wrong, "rows": rows})
        print("run %d: %3d s  %s  applied without asking and wrong: %d" % (
            number, runs[-1]["seconds"], "  ".join("%s %d" % (k, v) for k, v in sorted(counts.items())), applied_wrong))
        for row in rows:
            print("   %-13s %-8s %d candidates %-14s %s" % (row["outcome"], row["verdict"], row["candidates"],
                                                             row["likelihoods"], row["file"]))
    usage.refuse_unanswered(*usage.failed_since(mark), "the ranking eval")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as handle:
        json.dump({"sample": os.path.relpath(args.sample, HERE), "backend": args.backend, "cases": len(cases), "runs": runs},
                  handle, indent=1)
    print("Wrote %s" % args.out)


if __name__ == "__main__":
    main()
