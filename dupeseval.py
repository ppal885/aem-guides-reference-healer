#!/usr/bin/env python3
"""Scores copy detection and the reuse agent on samples/dupes-demo (garage-week PoC).

    python3 dupeseval.py [--runs 2] [--backend cli|sdk] [--model NAME]

Per group of truth.json: found with the right kind, and the decision (share, variable, ask, skip,
use existing). Decoys must not form a group. "merged wrong": a group whose copies disagree on a
fact got "share" (must be 0).
"""
import argparse
import json
import os
import time

import duplicates
import reuse
import sidecar
import usage

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--backend", default="cli", choices=["cli", "sdk"])
    parser.add_argument("--model")
    parser.add_argument("--out", default=os.path.join(HERE, "eval", "refs", "dupes-eval.json"))
    args = parser.parse_args()
    sidecar.BACKEND = args.backend
    folder = os.path.join(HERE, "samples", "dupes-demo")
    truth = json.load(open(os.path.join(folder, "truth.json")))
    files = duplicates.files_of(folder)
    runs = []
    for number in range(1, args.runs + 1):
        started, mark = time.time(), usage.start()
        groups = reuse.decide(files, lambda s, u: sidecar.call_model(s, u, args.model))
        totals = usage.finish(mark)
        rows = []
        for want in truth["groups"]:
            got = next((g for g in groups if g["text"].startswith(want["text_starts"])
                        or any(v["text"].startswith(want["text_starts"]) for v in g["variants"])), None)
            rows.append({"group": want["text_starts"], "want": want["decision"], "got": got and got["decision"],
                         "kind_right": bool(got) and got["kind"] == want["kind"], "reason": got and got["reason"]})
        decoys = sum(1 for g in groups for d in truth["not_a_group"] if any(v["text"].startswith(d) for v in g["variants"]))
        right = sum(1 for r in rows if r["got"] == r["want"])
        merged_wrong = sum(1 for r in rows if r["want"] == "ask" and r["got"] == "share")
        runs.append({"run": number, "seconds": round(time.time() - started), "right": right, "of": len(rows),
                     "kinds_right": sum(r["kind_right"] for r in rows), "decoys_grouped": decoys,
                     "merged_wrong": merged_wrong, "model_calls": totals["model_calls"],
                     "input_tokens": totals["input_tokens"], "rows": rows})
        print("run %d: %d s  decisions right %d of %d, kinds right %d, decoys grouped %d, merged wrong %d, %d model calls" % (
            number, runs[-1]["seconds"], right, len(rows), runs[-1]["kinds_right"], decoys, merged_wrong, totals["model_calls"]))
        for r in rows:
            if r["got"] != r["want"]:
                print("   want %-12s got %-12s %s -- %s" % (r["want"], r["got"], r["group"], (r["reason"] or "")[:120]))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as handle:
        json.dump({"backend": args.backend, "model": args.model or "the CLI's default", "runs": runs}, handle, indent=1)
    print("Wrote %s" % args.out)


if __name__ == "__main__":
    main()
