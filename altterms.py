#!/usr/bin/env python3
"""Do suggested alt texts write the documentation's own names? Measured on a folder of DITA
(an export) that already has alt texts naming something from its own list of names
(alttext.vocabulary): each such alt is hidden, the model is asked for one with the old prompt
(image, topic title, figure title, text around it) and with the new one (also the names, the keys
and alt texts already written, the hidden one left out), and both are scored against the hidden alt:

- names right: names of the hidden alt that the suggestion writes exactly (spelling and capitals);
- names changed: written with other capitals or spacing (a name the reader would not find again);
- unknown numbers: model numbers found neither in the documentation nor in what the model was given;
- figure title repeated word for word.

Without --yes nothing is sent to a model: it lists the images it would send and how many calls.
The images and the text around them go to the model, so run it only with the owner's word on the
content it reads.

    python3 altterms.py FOLDER [--images 30] [--yes] [--new-only] [--backend cli|sdk] [--out out/altterms-eval.json]
"""
import argparse
import json
import mimetypes
import os
import re
import time
import xml.etree.ElementTree as ET

import alttext
import duplicates


def cases(folder, files, vocab, wanted):
    """The images whose alt names something from the documentation's names, spread over the folder."""
    # Product and model names (<keyword>, <tm>, keys), not a number alone: "10" is not a name.
    known = {n for n in set(vocab["names"]) | set(vocab["keys"].values()) if re.search(r"[A-Za-z]", n)}
    found, seen = [], set()
    for entry in files:
        path = "/" + entry["path"].lstrip("/")
        if not path.endswith(".dita") or path not in vocab["alts"]:
            continue
        try:
            root = ET.fromstring(re.sub(r"<!DOCTYPE[^>\[]*(\[[^\]]*\])?[^>]*>", "", entry["xml"], count=1))
        except ET.ParseError:
            continue
        parents = {child: parent for parent in root.iter() for child in parent}
        title = alttext._text(next((c for c in root if alttext._local(c.tag) == "title"), None))
        for el in root.iter():
            if alttext._local(el.tag) != "image" or not el.get("href"):
                continue
            alt_el = next((c for c in el if alttext._local(c.tag) == "alt"), None)
            alt = alttext._text(alt_el)
            said = sorted(n for n in known if re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(n), alt))
            image = os.path.normpath(os.path.join(folder, os.path.dirname(entry["path"]), el.get("href").split("#")[0]))
            if not said or alttext.why_weak(alt, image) or not os.path.isfile(image) or image in seen:
                continue
            seen.add(image)
            figure_title, around = alttext._context(el, parents)
            found.append({"file": path, "image": image, "alt": alt, "names": said, "topic_title": title,
                          "figure_title": figure_title, "context": around})
    step = max(1, len(found) // wanted) if wanted else 1
    return found[::step][:wanted], len(found)


def without(vocab, case):
    """The vocabulary without the hidden alt, so it is not given to the model as an example."""
    alts = dict(vocab["alts"])
    alts[case["file"]] = [a for a in alts.get(case["file"], []) if a != case["alt"]]
    return dict(vocab, alts=alts)


def score(case, out):
    text = alttext._as_read(out["alt"], {})
    right = [n for n in case["names"] if re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(n), text)]
    squash = lambda s: re.sub(r"[\s-]+", "", s).lower()  # noqa: E731
    changed = [n for n in case["names"] if n not in right and squash(n) in squash(text)]
    return {"names_right": len(right), "names_changed": changed,
            "unknown_numbers": "not found in this documentation" in out["caveat"],
            "figure_title_repeated": bool(case["figure_title"]) and text.lower() == case["figure_title"].lower()}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder")
    parser.add_argument("--images", type=int, default=30)
    parser.add_argument("--yes", action="store_true", help="send the images to the model")
    parser.add_argument("--new-only", action="store_true", help="ask with the new prompt only (half the calls)")
    parser.add_argument("--backend", default="cli", choices=["cli", "sdk"])
    # Not eval/refs: the rows hold the documentation's own alt texts, which stay out of the repository.
    parser.add_argument("--out", default=os.path.join("out", "altterms-eval.json"))
    args = parser.parse_args()
    files = duplicates.files_of(args.folder, maps=True)
    vocab = alttext.vocabulary(files)
    chosen, of = cases(args.folder, files, vocab, args.images)
    print("%d files; %d names, %d keys; %d images whose alt names one of them; %d chosen"
          % (len(files), len(vocab["names"]), len(vocab["keys"]), of, len(chosen)))
    if not args.yes:
        for case in chosen:
            print("  %s  %s" % (os.path.basename(case["image"]), case["names"]))
        calls = len(chosen) * (1 if args.new_only else 2)
        print("Nothing sent. With --yes: %d model calls." % calls)
        return
    import sidecar
    import usage
    sidecar.BACKEND = args.backend
    mark, started, rows = usage.start(), time.time(), []
    for case in chosen:
        with open(case["image"], "rb") as handle:
            data = handle.read()
        media = mimetypes.guess_type(case["image"])[0] or "image/png"
        group = {"image": case["image"], "uses": [dict(case, alt="", why="none")]}
        row = {"image": os.path.basename(case["image"]), "hidden_alt": case["alt"], "names": case["names"]}
        kinds = (("new", without(vocab, case)),) if args.new_only else (("old", None), ("new", without(vocab, case)))
        for kind, vocab_used in kinds:
            prompt = alttext.prompt_for(group, vocab_used)
            with usage.as_agent("alt"):
                answer = sidecar.call_model(alttext.SYSTEM, prompt, image=(data, media))
            out = alttext.clean(answer, case["image"], vocab_used, prompt)
            row[kind] = dict(alt=out["alt"], caveat=out["caveat"], **score(case, out))
        rows.append(row)
        print("%-24s %s" % (row["image"], row["new"]["alt"][:100]), flush=True)
    totals = usage.finish(mark)
    names = sum(len(r["names"]) for r in rows)
    summary = {kind: {"names_right": sum(r[kind]["names_right"] for r in rows), "of_names": names,
                      "names_changed": sum(len(r[kind]["names_changed"]) for r in rows),
                      "unknown_numbers": sum(r[kind]["unknown_numbers"] for r in rows),
                      "figure_title_repeated": sum(r[kind]["figure_title_repeated"] for r in rows)} for kind in ("old", "new") if rows and kind in rows[0]}
    for kind, s in summary.items():
        print("%s prompt: %d of %d names right, %d changed, %d with unknown numbers, %d figure titles repeated"
              % (kind, s["names_right"], s["of_names"], s["names_changed"], s["unknown_numbers"], s["figure_title_repeated"]))
    print("%d calls, $%s, %d s" % (totals["model_calls"], totals["cost_usd"], time.time() - started))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as handle:
        json.dump({"backend": args.backend, "images": len(rows), "summary": summary, "rows": rows,
                   "model_calls": totals["model_calls"], "cost_usd": totals["cost_usd"]}, handle, indent=1)


if __name__ == "__main__":
    main()
