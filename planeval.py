#!/usr/bin/env python3
"""Evaluates the planner agent on the large sample, where the right answer is known (garage-week PoC).

    python3 samples/gen_large.py samples/large-demo
    python3 planeval.py [--runs 3] [--mode planner|pipeline] [--backend cli|sdk] [--out eval/refs/<mode>-eval.json]

The sample's v2 was made from v1 by a known list of changes (samples/gen_large.py, CHANGES), so for
every broken reference it is known what it should point at now, or that nothing replaces it.
The planner runs several times on the same input, with an empty memory of author answers, and
each run is scored reference by reference:

    applied right    repaired (or covered by an edit at the source) to the right target
    applied wrong    repaired to a wrong target, or repaired although the content is gone
    asked, right     left to the author with the right target proposed
    asked, wrong     left to the author with a wrong target proposed
    none, right      reported as gone, and it is gone
    missed           reported as gone although a target exists

"applied wrong" is the number that must be zero: those would be changed by "Fix all" without a
person looking. The runs are also compared with each other, because the planner is a model and
does not decide the same way every time.

The files get made-up GUID ids, so the planner works as it does behind AEM (an edit at the source
for a key is "rename back", not a second name).
"""
import argparse
import collections
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "samples"))

import gen_large  # noqa: E402
import refheal  # noqa: E402
import refplan  # noqa: E402


def expected_names():
    """{old id or key: new id or key, or None when it is gone}."""
    names = {}
    for changes in gen_large.CHANGES.values():
        for old, (kind, new, _text) in changes.items():
            # For a split, the first piece named is the closer match and counts as the right answer.
            names[old] = None if kind == "remove" else (new.rsplit("/", 1)[-1] if new else None)
    return names


def payload(root):
    files = []
    for folder, _, names in os.walk(os.path.join(root, "v2")):
        for name in sorted(names):
            rel = os.path.relpath(os.path.join(folder, name), os.path.join(root, "v2"))
            old = os.path.join(root, "v1", rel)
            with open(os.path.join(folder, name), encoding="utf-8") as handle:
                xml = handle.read()
            previous = []
            if os.path.exists(old):
                with open(old, encoding="utf-8") as handle:
                    previous = [handle.read()]
            files.append({"id": "GUID-eval-%04d" % len(files), "path": "/content/dam/large-demo/" + rel, "xml": xml,
                          "previous": previous})
    return {"files": files}


def truth(old_value, attribute, names):
    """(has a target, the parts of the old value that were renamed -> their new names)."""
    parts = old_value.split("/") if attribute in ("keyref", "conkeyref") else [old_value.rsplit("/", 1)[-1]]
    renamed = {part: names[part] for part in parts if part in names}
    return all(new is not None for new in renamed.values()), renamed


def score(repair, names):
    exists, renamed = truth(repair["old"], repair["attribute"], names)
    verdict, new = repair["verdict"], repair.get("new") or ""
    right_target = exists and all(new_name in new.replace("#", "/").split("/") for new_name in renamed.values())
    if verdict == "covered":
        return "applied right" if exists else "applied wrong"
    if verdict == "fix":
        return "applied right" if right_target else "applied wrong"
    if verdict == "review":
        return "asked, right" if right_target else "asked, wrong"
    return "none, right" if not exists else "missed"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", default=os.path.join(HERE, "samples", "large-demo"))
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--backend", default="cli", choices=["cli", "sdk"])
    parser.add_argument("--mode", default="planner", choices=["planner", "pipeline"],
                        help="pipeline: the fixed order of refheal.py without the planner, for comparison")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    args.out = args.out or os.path.join(HERE, "eval", "refs", "%s-eval.json" % args.mode)
    names, data = expected_names(), payload(args.sample)
    runs, per_target = [], collections.defaultdict(list)
    for number in range(1, args.runs + 1):
        started = time.time()
        fresh = json.loads(json.dumps(data))
        if args.mode == "pipeline":
            out = refheal.heal_files(fresh, backend=args.backend, log=lambda message: None)
        else:
            out = refplan.plan_files(fresh, backend=args.backend, log=lambda message: None, memory={})
        counts = collections.Counter(score(r, names) for r in out["repairs"])
        # Which targets went wrong, and what was proposed: a count alone does not say what to look at.
        said = {True: "reviewer agreed", False: "reviewer disagreed", None: "no reviewer"}
        wrong = collections.Counter((r["attribute"], r["old"], r.get("new") or "",
                                     "%s, %s" % (r["verdict"], said[(r.get("detail") or {}).get("reviewer")]))
                                    for r in out["repairs"] if score(r, names) in ("applied wrong", "asked, wrong", "missed"))
        seen = {}
        for repair in out["repairs"]:
            seen[(repair["attribute"], repair["old"].rsplit("/", 2)[-1] if repair["attribute"] in ("href", "conref") else repair["old"])] = repair["verdict"]
        for target, verdict in seen.items():
            per_target[target].append(verdict)
        runs.append({"run": number, "seconds": round(time.time() - started), "references": len(out["repairs"]),
                     "scores": dict(counts), "source_edits": len(out["source_fixes"]),
                     "planner_steps": out["stats"].get("planner_steps"), "plan": out.get("plan"),
                     "wrong": [{"attribute": a, "old": o, "proposed": n, "verdict": v, "references": c}
                               for (a, o, n, v), c in wrong.items()]})
        print("run %d: %3d s  %s  edits at the source: %d" % (
            number, runs[-1]["seconds"], "  ".join("%s %d" % (k, v) for k, v in sorted(counts.items())), len(out["source_fixes"])))
        for item in runs[-1]["wrong"]:
            print("   wrong: %s %s -> %s (%s, %d references)" % (item["attribute"], item["old"][-44:], item["proposed"][-44:] or "(nothing)",
                                                                  item["verdict"], item["references"]))
    same = sum(1 for verdicts in per_target.values() if len(set(verdicts)) == 1)
    differing = {"%s %s" % target: verdicts for target, verdicts in per_target.items() if len(set(verdicts)) > 1}
    result = {"sample": os.path.relpath(args.sample, HERE), "mode": args.mode, "backend": args.backend, "runs": runs,
              "targets": len(per_target), "targets_decided_the_same_in_every_run": same, "targets_that_differed": differing}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as handle:
        json.dump(result, handle, indent=1)
    print("%d of %d targets got the same decision in all %d runs" % (same, len(per_target), args.runs))
    for target, verdicts in differing.items():
        print("  differed: %-44s %s" % (target, " / ".join(verdicts)))
    print("Wrote %s" % args.out)


if __name__ == "__main__":
    main()
