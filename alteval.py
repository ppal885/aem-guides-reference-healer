#!/usr/bin/env python3
"""Scores the alt texts the model suggests for the made-up images of samples/alt-demo against
samples/alt-demo/truth.json: a right alt has one word of each list there (a decorative image: the
model says it is decorative), and keeps the rules (no "Image of", not the file name, at most
alttext.MAX_CHARS characters). Calls the model once per image and run.

    python3 alteval.py --runs 2 [--backend cli|sdk] [--out eval/refs/alt-eval.json]
"""
import argparse
import json
import os
import time

import alttext
import duplicates
import sidecar
import usage

SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "samples", "alt-demo")


def score(name, out, truth):
    want = truth[name]
    if want.get("decorative"):
        return {"right": bool(out["decorative"]), "why": "decorative" if out["decorative"] else "not called decorative"}
    text = out["alt"].lower()
    missing = [words for words in want["words"] if not any(w in text for w in words)]
    rules = [] if out["alt"] and not alttext.why_weak(out["alt"], name) else ["says nothing"]
    if len(out["alt"]) > alttext.MAX_CHARS + 1:
        rules.append("too long")
    return {"right": not missing and not rules, "why": "; ".join(["missing one of %s" % m for m in missing] + rules) or "ok"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--backend", default="cli", choices=["cli", "sdk"])
    parser.add_argument("--out", default=os.path.join("eval", "refs", "alt-eval.json"))
    args = parser.parse_args()
    sidecar.BACKEND = args.backend
    with open(os.path.join(SAMPLE, "truth.json")) as f:
        truth = json.load(f)
    groups = alttext.images(duplicates.files_of(SAMPLE))
    runs = []
    for run in range(1, args.runs + 1):
        mark, started, rows = usage.start(), time.time(), []
        for group in groups:
            name = os.path.basename(group["image"])
            with open(os.path.join(SAMPLE, "images", name), "rb") as f:
                data = f.read()
            with usage.as_agent("alt"):
                answer = sidecar.call_model(alttext.SYSTEM, alttext.prompt_for(group), image=(data, "image/png"))
            out = alttext.clean(answer, group["image"])
            rows.append(dict(image=name, alt=out["alt"], decorative=out["decorative"], caveat=out["caveat"],
                             **score(name, out, truth)))
            print("%d %-20s %-5s %s" % (run, name, rows[-1]["right"], out["alt"] or "(decorative)"), flush=True)
        totals = usage.finish(mark)
        runs.append({"run": run, "right": sum(r["right"] for r in rows), "of": len(rows), "seconds": round(time.time() - started),
                     "model_calls": totals["model_calls"], "input_tokens": totals["input_tokens"],
                     "output_tokens": totals["output_tokens"], "cost_usd": totals["cost_usd"], "rows": rows})
        print("run %d: %d of %d right, %d calls, $%s, %d s" % (run, runs[-1]["right"], len(rows), totals["model_calls"],
                                                           totals["cost_usd"], runs[-1]["seconds"]), flush=True)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump({"backend": args.backend, "runs": runs}, f, indent=1)


if __name__ == "__main__":
    main()
