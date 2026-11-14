#!/usr/bin/env python3
"""Evaluates the planner's suggestion for content that is gone (garage-week PoC).

    python3 wayouteval.py [--runs 2] [--backend cli|sdk] [--out eval/refs/wayout-eval.json]

Ten pieces were removed from a shared file; topics still refer to them. Nothing replaces them, so
the planner can only suggest a way out: put the piece back ("restore"), keep the text in the
topics ("inline"), or remove the references ("remove"). For each piece this file says which ways
a writer would plausibly pick. Scored per piece and run:

    right        the suggestion is one of the plausible ways
    other        a suggestion outside them (listed, to be read by a person)
    no suggestion  the planner left the references broken without suggesting a way
    safety removed  "remove" suggested for safety content: must be zero, and code refuses it

The expectations are one person's judgement of ten made-up pieces. This measures whether the
suggestion is sensible and stable on them, not whether it is right for real content.
"""
import argparse
import collections
import json
import os
import time

import refplan

HERE = os.path.dirname(os.path.abspath(__file__))

# id: (element, plausible ways, the title of the topics that use it)
PIECES = collections.OrderedDict([
    ("slow", ('<note id="slow" type="caution">This operation can take up to an hour for large resources.</note>',
              {"restore"}, "Resize a volume")),
    ("power", ('<note id="power" type="danger">Disconnect the power supply before you open the housing.</note>',
               {"restore"}, "Replace the fan")),
    ("hot", ('<hazardstatement id="hot" type="warning"><messagepanel><typeofhazard>Hot surface</typeofhazard>'
             '<howtoavoid>Let the unit cool for ten minutes before you touch it.</howtoavoid></messagepanel></hazardstatement>',
             {"restore"}, "Clean the heat sink")),
    ("data-loss", ('<note id="data-loss" type="warning">Deleting a workspace removes all of its projects. This cannot be undone.</note>',
                   {"restore"}, "Delete a workspace")),
    ("legacy-ui", ('<p id="legacy-ui">The old settings page is still available until the end of March.</p>',
                   {"remove"}, "Change your settings")),
    ("webinar", ('<p id="webinar">Join the launch webinar on 12 May to see the new dashboard.</p>',
                 {"remove"}, "Open the dashboard")),
    ("beta", ('<note id="beta">This feature is in beta until version 2.0 is released.</note>',
              {"remove"}, "Share a report")),
    ("old-importer", ('<p id="old-importer">Use the legacy importer, which is deprecated and will be removed in version 3.</p>',
                      {"remove", "inline"}, "Import data")),
    ("definition", ('<p id="definition">A workspace is a container for projects and their members.</p>',
                    {"restore", "inline"}, "Create a workspace")),
    ("support-hours", ('<p id="support-hours">Support is available on working days from 8:00 to 18:00 CET.</p>',
                       {"restore", "inline"}, "Contact support")),
])
SAFETY = {"slow", "power", "hot", "data-loss"}
HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n'


def payload():
    """The shared file without the ten pieces, its previous version with them, and two topics per piece."""
    kept = '<p id="sign-in">Sign in to the console with an administrator account.</p>'
    library = HEAD + '<topic id="lib"><title>Shared pieces</title><body>%s</body></topic>'
    files = [{"id": "GUID-way-lib", "path": "/content/dam/way/lib.dita", "xml": library % kept,
              "previous": [library % (kept + "".join(piece[0] for piece in PIECES.values()))]}]
    for name, (element, _ways, title) in PIECES.items():
        tag = element[1:element.index(" ")]
        for number in (1, 2):
            topic = (HEAD + '<topic id="%s_%d"><title>%s%s</title><body><p conref="GUID-way-lib.dita#lib/sign-in"/>'
                     '<%s conref="GUID-way-lib.dita#lib/%s"/><p>Then follow the steps on the page.</p></body></topic>'
                     % (name.replace("-", "_"), number, title, "" if number == 1 else " (advanced)", tag, name))
            files.append({"id": "GUID-way-%s-%d" % (name, number), "path": "/content/dam/way/%s_%d.dita" % (name, number),
                          "xml": topic, "previous": []})
    return {"files": files}


def suggestions(out):
    """{piece: suggested kind or None} from a planner result."""
    found = {}
    for repair in out["repairs"]:
        name = repair["old"].rsplit("/", 1)[-1]
        if name not in PIECES:
            continue
        ways = (repair.get("detail") or {}).get("ways_out") or {}
        recommended = ways.get("recommended") or {}
        if repair["verdict"] != "none":
            found[name] = "not gone: " + repair["verdict"]
        else:
            found[name] = recommended.get("kind")
    return found


def score(name, kind):
    if kind is None:
        return "no suggestion"
    if name in SAFETY and kind == "remove":
        return "safety removed"
    return "right" if kind in PIECES[name][1] else "other"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--backend", default="cli", choices=["cli", "sdk"])
    parser.add_argument("--out", default=os.path.join(HERE, "eval", "refs", "wayout-eval.json"))
    args = parser.parse_args()
    runs, per_piece = [], collections.defaultdict(list)
    for number in range(1, args.runs + 1):
        started = time.time()
        out = refplan.plan_files(payload(), backend=args.backend, log=lambda message: None, memory={})
        found = suggestions(out)
        scores = collections.Counter(score(name, found.get(name)) for name in PIECES)
        for name in PIECES:
            per_piece[name].append(found.get(name))
        runs.append({"run": number, "seconds": round(time.time() - started), "scores": dict(scores), "suggested": found})
        print("run %d: %3d s  %s" % (number, runs[-1]["seconds"], "  ".join("%s %d" % item for item in sorted(scores.items()))),
              flush=True)
    for name, kinds in per_piece.items():
        expected = "/".join(sorted(PIECES[name][1]))
        print("   %-13s expected %-15s suggested %s%s" % (name, expected, ", ".join(str(k) for k in kinds),
                                                       "" if len(set(kinds)) == 1 else "   (differs between runs)"), flush=True)
    result = {"pieces": {name: {"was": piece[0], "plausible": sorted(piece[1]), "safety": name in SAFETY}
                         for name, piece in PIECES.items()},
              "runs": runs, "same_in_every_run": sum(1 for kinds in per_piece.values() if len(set(kinds)) == 1)}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
    print("Wrote %s" % args.out)


if __name__ == "__main__":
    main()
