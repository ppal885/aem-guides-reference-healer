#!/usr/bin/env python3
"""What happens when an author accepts a repair the agents only proposed (garage-week PoC).

    python3 revieweval.py [--runs 2] [--backend cli|sdk] [--out eval/refs/review-eval.json]

"Fix all" applies what is proven. Everything else the finder agent found is shown "to review",
and an author who presses "Replace link" or "Apply to all" applies the first candidate as it is.
Nothing checks that press except that the reference resolves. So this asks, for every repair
shown to review on the two samples with a known right answer: would accepting the first
candidate have been right? Split by what the reviewer agent said, because that is what the row
tells the author:

    reviewer agreed       the reviewer agent agreed with the finder (and the repair still waits,
                          for another reason: the text changed, two pieces could be meant)
    reviewer disagreed    the reviewer agent did not agree
    no reviewer           settled without a reviewer (a rule or an earlier answer)

Counted per reference and per broken target: 53 references to one renamed id are one decision.
"""
import argparse
import collections
import json
import os
import time

import planeval
import rankeval
import refplan

HERE = os.path.dirname(os.path.abspath(__file__))
SAID = {True: "reviewer agreed", False: "reviewer disagreed", None: "no reviewer"}


def large(backend):
    names = planeval.expected_names()
    out = refplan.plan_files(planeval.payload(os.path.join(HERE, "samples", "large-demo")), backend=backend,
                             log=lambda message: None, memory={})
    for repair in out["repairs"]:
        if repair["verdict"] == "review" and repair.get("new"):
            yield repair, planeval.score(repair, names) == "asked, right"


def ranking(backend):
    root = os.path.join(HERE, "samples", "rank-demo")
    with open(os.path.join(root, "expected.json"), encoding="utf-8") as handle:
        cases = {(c["file"], c["attribute"], c["old"]): c for c in json.load(handle)}
    out = refplan.plan_files(rankeval.payload(root), backend=backend, log=lambda message: None, memory={})
    for repair in out["repairs"]:
        case = cases.get((repair["file"].lstrip("/"), repair["attribute"], repair["old"]))
        if case and repair["verdict"] == "review" and repair.get("new"):
            yield repair, rankeval.score(case, repair)[0] == "first right"


def tally(rows):
    """{what the reviewer said: {"references": [right, all], "targets": [right, all]}}. A target
    counts as right only when every reference to it would have been repaired right."""
    table = {said: {"references": [0, 0], "targets": [0, 0]} for said in SAID.values()}
    targets = collections.defaultdict(list)
    for repair, right in rows:
        said = SAID[(repair.get("detail") or {}).get("reviewer")]
        table[said]["references"][0] += right
        table[said]["references"][1] += 1
        targets[(said, repair["attribute"], repair["old"].rsplit("/", 1)[-1])].append(right)
    for (said, _, _), rights in targets.items():
        table[said]["targets"][0] += all(rights)
        table[said]["targets"][1] += 1
    return table


def wrong_ones(rows):
    seen = {}
    for repair, right in rows:
        if not right:
            seen.setdefault((repair["attribute"], repair["old"], repair["new"]), {
                "attribute": repair["attribute"], "old": repair["old"], "proposed": repair["new"],
                "reviewer": SAID[(repair.get("detail") or {}).get("reviewer")], "references": 0})["references"] += 1
    return list(seen.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--backend", default="cli", choices=["cli", "sdk"])
    parser.add_argument("--out", default=os.path.join(HERE, "eval", "refs", "review-eval.json"))
    args = parser.parse_args()
    runs = []
    for number in range(1, args.runs + 1):
        started = time.time()
        samples = {}
        for name, rows in (("large-demo", list(large(args.backend))), ("rank-demo", list(ranking(args.backend)))):
            samples[name] = {"accepting_the_first_candidate": tally(rows), "wrong": wrong_ones(rows)}
            for said, counts in samples[name]["accepting_the_first_candidate"].items():
                if counts["references"][1]:
                    print("run %d  %-10s %-19s right for %d of %d references, %d of %d broken targets" % (
                        number, name, said, counts["references"][0], counts["references"][1],
                        counts["targets"][0], counts["targets"][1]))
            for wrong in samples[name]["wrong"]:
                print("        wrong: %s %s -> %s (%s, %d references)" % (
                    wrong["attribute"], wrong["old"][-40:], wrong["proposed"][-40:], wrong["reviewer"], wrong["references"]))
        runs.append({"run": number, "seconds": round(time.time() - started), "samples": samples})
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as handle:
        json.dump({"backend": args.backend, "runs": runs}, handle, indent=1)
    print("Wrote %s" % args.out)


if __name__ == "__main__":
    main()
