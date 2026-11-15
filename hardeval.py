#!/usr/bin/env python3
"""Scores the agents on a sample where the obvious new target is the wrong one (garage-week PoC).

    python3 samples/gen_hard.py
    python3 hardeval.py [--runs 2] [--backend cli|sdk] [--out eval/refs/hard-eval.json]

samples/hard-demo has eight broken references, each with a decoy closer in name or wording than
the right target; one has no right target at all (expected.json). The planner runs on it with an
empty memory. Per reference:

    first right     the proposed target is the right one (or nothing is proposed for content that is gone)
    first wrong     a target is proposed and it is not the right one
    missed          a right target exists and nothing is proposed

and, next to it, what was done with the proposal: "fix" (applied by "Fix all" without a look),
"review" (shown to the author), "none". Two numbers matter most:

    applied without asking and wrong    a wrong target with verdict "fix". Must be 0.
    wrong proposals the reviewer caught a first-wrong proposal the reviewer agent disagreed with.
                                        This is what the reviewer is for.

The finder may avoid every decoy; then the second number says nothing. So the reviewer agent is
also asked alone (--reviewer-runs): it is shown the decoy and the right target of each case as if
a finder had proposed them. "decoys rejected" and "right targets accepted" are its two scores.
"""
import argparse
import collections
import concurrent.futures
import json
import os
import time

import rankeval
import refcheck
import refheal
import refplan

HERE = os.path.dirname(os.path.abspath(__file__))
SAID = {True: "agreed", False: "disagreed", None: "no reviewer"}


def score(case, repair):
    """(outcome, verdict, what the reviewer said, was the right one among the candidates)."""
    repair = repair or {}
    proposed, verdict = repair.get("new"), repair.get("verdict") or "none"
    detail = repair.get("detail") or {}
    offered = [c["value"] for c in detail.get("candidates", [])]
    listed = bool(case["right"]) and any(rankeval.same(value, case["right"]) for value in offered)
    if case["right"] is None:
        outcome = "first right" if not proposed else "first wrong"
    elif not proposed:
        outcome = "missed"
    else:
        outcome = "first right" if rankeval.same(proposed, case["right"]) else "first wrong"
    return outcome, verdict, SAID[detail.get("reviewer")], listed


def summary(rows):
    wrong = [row for row in rows if row["outcome"] == "first wrong"]
    right = [row for row in rows if row["outcome"] == "first right" and row["proposed"]]
    return {
        "scores": dict(collections.Counter(row["outcome"] for row in rows)),
        "applied_without_asking_and_wrong": sum(1 for row in wrong if row["verdict"] == "fix"),
        "wrong_proposals": len(wrong),
        "wrong_proposals_the_reviewer_caught": sum(1 for row in wrong if row["reviewer"] == "disagreed"),
        "wrong_proposals_with_the_right_one_in_the_list": sum(1 for row in wrong if row["right_in_list"]),
        "right_proposals": len(right),
        "right_proposals_the_reviewer_doubted": sum(1 for row in right if row["reviewer"] == "disagreed"),
    }


def proposal_of(repo, ref, value):
    """A target value ("lib.dita#lib/x", or a key name) in the form the reviewer is asked about."""
    if ref["attribute"] in ("keyref", "conkeyref"):
        key, _, element_id = value.partition("/")
        return {"target_path": "", "topic_id": "", "element_id": element_id, "key": key}
    target, topic_id, element_id = repo.split_target(dict(ref, value=value))
    return {"target_path": target, "topic_id": topic_id or "", "element_id": element_id or "", "key": ""}


def ask_the_reviewer(sample, cases, backend, runs):
    """The reviewer agent alone: it is shown the decoy and the right target of every case, as if a
    finder had proposed each, and says whether it agrees. The finder is not fooled by this sample,
    so this is the only way to see what the reviewer does with a wrong proposal."""
    repo = refcheck.Repo(files=rankeval.payload(sample)["files"])
    broken = {(r["file"], r["attribute"], r["value"]): r for r in repo.broken()}
    jobs = [(case, kind, run) for case in cases for kind in ("decoy", "right") if case.get(kind) for run in range(runs)]

    def ask(job):
        case, kind, _ = job
        ref = broken[(case["file"], case["attribute"], case["old"])]
        return refheal.review_proposal(repo, ref, proposal_of(repo, ref, case[kind]), backend, None)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        answers = list(pool.map(ask, jobs))
    rows = [{"file": case["file"], "shown": kind, "target": case[kind], "run": run + 1, "agree": answer["agree"],
             "reason": answer["reason"][:200]} for (case, kind, run), answer in zip(jobs, answers)]
    decoys = [row for row in rows if row["shown"] == "decoy"]
    rights = [row for row in rows if row["shown"] == "right"]
    result = {"decoys_shown": len(decoys), "decoys_rejected": sum(1 for row in decoys if row["agree"] is False),
              "right_targets_shown": len(rights), "right_targets_accepted": sum(1 for row in rights if row["agree"] is True),
              "not_answered": sum(1 for row in rows if row["agree"] is None), "rows": rows}
    print("reviewer alone: rejected %d of %d decoys, accepted %d of %d right targets, %d not answered" % (
        result["decoys_rejected"], result["decoys_shown"], result["right_targets_accepted"], result["right_targets_shown"],
        result["not_answered"]))
    for row in rows:
        mistake = (row["shown"] == "decoy") == (row["agree"] is True) and row["agree"] is not None
        if mistake:
            print("   mistake: %-5s %-22s %-34s run %d: %s" % (row["shown"], row["file"], row["target"][-34:], row["run"], row["reason"][:90]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", default=os.path.join(HERE, "samples", "hard-demo"))
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--backend", default="cli", choices=["cli", "sdk"])
    parser.add_argument("--out", default=os.path.join(HERE, "eval", "refs", "hard-eval.json"))
    parser.add_argument("--reviewer-runs", type=int, default=3, help="how often the reviewer alone is asked about each target")
    args = parser.parse_args()
    with open(os.path.join(args.sample, "expected.json"), encoding="utf-8") as handle:
        cases = json.load(handle)
    reviewer = ask_the_reviewer(args.sample, cases, args.backend, args.reviewer_runs) if args.reviewer_runs else None
    runs = []
    for number in range(1, args.runs + 1):
        started = time.time()
        out = refplan.plan_files(rankeval.payload(args.sample), backend=args.backend, log=lambda message: None, memory={})
        by_ref = {(r["file"].lstrip("/"), r["attribute"], r["old"]): r for r in out["repairs"]}
        rows = []
        for case in cases:
            repair = by_ref.get((case["file"], case["attribute"], case["old"]))
            outcome, verdict, reviewer, listed = score(case, repair)
            rows.append({"file": case["file"], "old": case["old"], "right": case["right"], "proposed": (repair or {}).get("new"),
                         "outcome": outcome, "verdict": verdict, "reviewer": reviewer, "right_in_list": listed,
                         "caveat": ((repair or {}).get("caveat") or "")[:200]})
        result = dict(summary(rows), run=number, seconds=round(time.time() - started), usage=out.get("usage"), rows=rows)
        runs.append(result)
        print("run %d: %3d s  %s" % (number, result["seconds"], "  ".join("%s %d" % kv for kv in sorted(result["scores"].items()))))
        print("   applied without asking and wrong: %d    wrong proposals the reviewer caught: %d of %d    "
              "right proposals the reviewer doubted: %d of %d" % (
                  result["applied_without_asking_and_wrong"], result["wrong_proposals_the_reviewer_caught"],
                  result["wrong_proposals"], result["right_proposals_the_reviewer_doubted"], result["right_proposals"]))
        for row in rows:
            print("   %-11s %-6s reviewer %-11s %-22s -> %s" % (row["outcome"], row["verdict"], row["reviewer"], row["file"],
                                                                  row["proposed"] or "(nothing)"))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as handle:
        json.dump({"sample": os.path.relpath(args.sample, HERE), "backend": args.backend, "cases": len(cases),
                   "reviewer_alone": reviewer, "runs": runs},
                  handle, indent=1)
    print("Wrote %s" % args.out)


if __name__ == "__main__":
    main()
