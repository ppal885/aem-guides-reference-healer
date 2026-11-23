#!/usr/bin/env python3
"""Seeded evaluation of the reference healer (garage-week PoC).

Takes a real DITA repository, makes a copy without its git history, breaks references in the
copy in ways whose right repair is known, runs refheal.py on it, and scores the answers.

    python3 refeval.py <folder> [--per-kind 3] [--seed 7] [--backend cli|sdk] [--out out-refeval]

Kinds of break:
    rename-file   a referenced topic gets a new file name          right repair: the new path
    move-file     a referenced topic moves to another folder       right repair: the new path
    rename-id     an element id that is referenced changes         right repair: the new id
    rename-key    a key changes its name in the map                right repair: the new key
    delete-file   a referenced topic is deleted                    right repair: none

References that were already broken before the seeding are left out of the scoring.
"""
import argparse
import json
import os
import random
import re
import shutil

import refcheck
import refheal
import usage


def copy_repo(source, target):
    if os.path.exists(target):
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git", "node_modules", "out", "build", ".gradle", "temp"))


def signature(ref):
    return (ref["file"], ref["attribute"], ref["value"])


def seed_breaks(root, per_kind, rng):
    repo = refcheck.Repo(root)
    direct = {}      # target file -> refs that point at it by href or conref
    by_element = {}  # (file, topic, element) -> refs
    by_key = {}
    for ref in repo.refs:
        if repo.check(ref):
            continue
        if ref["attribute"] in refcheck.PATH_ATTRS:
            target, topic_id, element_id = repo.split_target(ref)
            if target in repo.files and target != ref["file"] and ref["element"] != "keydef":
                direct.setdefault(target, []).append(ref)
            if element_id and target in repo.files:
                by_element.setdefault((target, topic_id, element_id), []).append(ref)
        else:
            by_key.setdefault(ref["value"].partition("/")[0], []).append(ref)

    seeds, used_files = [], set()

    def pick_files(count):
        pool = sorted(f for f in direct if f.endswith(".dita") and f not in used_files
                      and not any(k["target"] == f for k in repo.keys.values()))
        rng.shuffle(pool)
        chosen = pool[:count]
        used_files.update(chosen)
        return chosen

    for path in pick_files(per_kind):
        folder, name = os.path.split(path)
        new = os.path.join(folder, name.replace(".dita", "-guide.dita"))
        os.rename(os.path.join(root, path), os.path.join(root, new))
        seeds.append({"kind": "rename-file", "old": path, "truth": {"path": new}})
    for path in pick_files(per_kind):
        folders = sorted({os.path.dirname(p) for p in repo.files if os.path.dirname(p) not in ("", os.path.dirname(path))})
        new = os.path.join(rng.choice(folders), os.path.basename(path))
        if os.path.exists(os.path.join(root, new)):
            continue
        os.rename(os.path.join(root, path), os.path.join(root, new))
        seeds.append({"kind": "move-file", "old": path, "truth": {"path": new}})
    for path in pick_files(per_kind):
        os.remove(os.path.join(root, path))
        seeds.append({"kind": "delete-file", "old": path, "truth": None})

    elements = sorted(k for k in by_element if k[0] not in used_files)
    rng.shuffle(elements)
    for target, topic_id, element_id in elements[:per_kind]:
        full = os.path.join(root, target)
        with open(full, encoding="utf-8") as handle:
            text = handle.read()
        if text.count('id="%s"' % element_id) != 1:
            continue
        new_id = element_id + "-details"
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(text.replace('id="%s"' % element_id, 'id="%s"' % new_id))
        used_files.add(target)
        seeds.append({"kind": "rename-id", "old": "%s#%s/%s" % (target, topic_id, element_id),
                      "truth": {"path": target, "topic": topic_id, "element": new_id}})

    keys = sorted(k for k, refs in by_key.items() if len(refs) >= 2 and not repo.keys[k]["external"]
                  and repo.keys[k]["target"] not in used_files)
    rng.shuffle(keys)
    for key in keys[:per_kind]:
        full = os.path.join(root, repo.keys[key]["defined_in"])
        with open(full, encoding="utf-8") as handle:
            text = handle.read()
        if text.count('keys="%s"' % key) != 1:
            continue
        new_key = key + "-topic"
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(text.replace('keys="%s"' % key, 'keys="%s"' % new_key))
        seeds.append({"kind": "rename-key", "old": key, "truth": {"key": new_key}})
    return seeds


def seed_of(repo, item, seeds):
    """Which seeded break caused this broken reference, if any."""
    ref = item
    if ref["attribute"] in ("keyref", "conkeyref"):
        key = ref["value"].partition("/")[0]
        return next((s for s in seeds if s["kind"] == "rename-key" and s["old"] == key), None)
    target, topic_id, element_id = repo.split_target(ref)
    for seed in seeds:
        if seed["kind"] in ("rename-file", "move-file", "delete-file") and seed["old"] == target:
            return seed
        if seed["kind"] == "rename-id" and seed["old"] == "%s#%s/%s" % (target, topic_id, element_id):
            return seed
    return None


def is_right(repo, item, seed):
    repair = item["repair"]
    if seed["truth"] is None:
        return repair["new_value"] is None
    if repair.get("verdict") == "covered":
        return True   # the planner repaired it with one edit where the target lives; its re-check passed
    if not repair["new_value"]:
        return False
    truth = seed["truth"]
    if "key" in truth:
        return repair["new_value"].partition("/")[0] == truth["key"]
    target, topic_id, element_id = repo.split_target(dict(item, value=repair["new_value"]))
    if target != truth["path"]:
        return False
    return "element" not in truth or element_id == truth["element"]


def plan(args, before):
    """Runs the planner agent on the seeded copy. Each file comes with its content before the
    seeding as its previous version, the way a repository with version history hands it over.
    Returns (repo, one item per broken target in the shape refheal reports, what else to store)."""
    import refplan
    files = []
    for folder, dirs, names in os.walk(args.work):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in refcheck.SKIP_DIRS]
        for name in sorted(names):
            if not name.endswith((".dita", ".ditamap", ".xml")):
                continue
            rel = os.path.relpath(os.path.join(folder, name), args.work)
            with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as handle:
                xml = handle.read()
            previous, original = [], os.path.join(args.folder, rel)
            if os.path.exists(original):
                with open(original, encoding="utf-8", errors="replace") as handle:
                    old = handle.read()
                previous = [old] if old != xml else []
            files.append({"path": "/" + rel, "xml": xml, "previous": previous})
    out = refplan.plan_files({"files": files}, backend=args.backend, model=args.model,
                             log=lambda m: print(m, flush=True), memory={})
    repo = refcheck.Repo(files=files)
    items, seen, already = [], set(), {"fix": 0, "review": 0, "none": 0, "covered": 0}
    for repair in out["repairs"]:
        ref = {"file": repair["file"].lstrip("/"), "attribute": repair["attribute"], "value": repair["old"]}
        if signature(ref) in before:
            already[repair["verdict"]] += 1     # broken before the seeding: no known answer, counted only
            continue
        match = next((r for r in repo.refs if signature(r) == signature(ref)), None)
        key = refheal.group_key(repo, match) if match else signature(ref)
        if key in seen or not match:
            continue
        seen.add(key)
        items.append(dict(match, uses=[1], repair={
            "new_value": repair["new"], "verdict": "review" if repair["verdict"] == "review" else repair["verdict"],
            "stage": repair.get("stage"), "reason": repair.get("reason", "")}))
    return repo, items, {"plan": out["plan"], "stats": out["stats"], "broken_before_the_seeding": already}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder")
    parser.add_argument("--per-kind", type=int, default=3)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--backend", choices=["cli", "sdk"], default="cli")
    parser.add_argument("--model")
    parser.add_argument("--work", default="/tmp/refeval-copy", help="where the seeded copy is written")
    parser.add_argument("--out", default="out-refeval")
    parser.add_argument("--mode", choices=["pipeline", "planner"], default="pipeline",
                        help="planner: the planner agent of refplan.py on the same seeded copy")
    args = parser.parse_args()

    copy_repo(args.folder, args.work)
    before = {signature(r) for r in refcheck.Repo(args.work).broken()}
    seeds = seed_breaks(args.work, args.per_kind, random.Random(args.seed))
    print("Seeded %d breaks: %s" % (len(seeds), ", ".join("%s %s" % (s["kind"], s["old"]) for s in seeds)), flush=True)

    mark = usage.position()
    if args.mode == "planner":
        repo, items, extra = plan(args, before)
    else:
        repo, report = refheal.heal(args.work, args.backend, args.model, None, lambda m: print(m, flush=True),
                                    only=lambda ref: signature(ref) not in before)
        items, extra = report["items"], {}
    rows, table = [], {}
    for item in items:
        seed = seed_of(repo, item, seeds)
        if seed is None:
            continue
        repair = item["repair"]
        right = is_right(repo, item, seed)
        outcome = ("right" if right else "wrong") if (repair["new_value"] or seed["truth"] is None) else "missed"
        if seed["truth"] is None and not right:
            outcome = "wrong"
        rows.append({"kind": seed["kind"], "old": seed["old"], "truth": seed["truth"], "element": item["element"],
                     "attribute": item["attribute"], "uses": len(item["uses"]), "stage": repair["stage"],
                     "verdict": repair["verdict"], "new_value": repair["new_value"], "outcome": outcome,
                     "reason": repair["reason"], "seconds": repair.get("seconds")})
        cell = table.setdefault(seed["kind"], {"right": 0, "wrong": 0, "missed": 0, "by_rule": 0, "wrong_marked_fix": 0})
        cell[outcome] += 1
        cell["by_rule"] += repair["stage"] == "rule"
        cell["wrong_marked_fix"] += (outcome == "wrong" and repair["verdict"] == "fix")

    usage.refuse_unanswered(*usage.failed_since(mark), "the seeded eval")
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "eval.json"), "w") as handle:
        json.dump(dict(extra, seeds=seeds, rows=rows, table=table, backend=args.backend, mode=args.mode), handle,
                  indent=1, ensure_ascii=False)
    print("\n%-12s %5s %5s %6s %8s %16s" % ("kind", "right", "wrong", "missed", "by rule", "wrong but 'fix'"))
    for kind, cell in table.items():
        print("%-12s %5d %5d %6d %8d %16d" % (kind, cell["right"], cell["wrong"], cell["missed"], cell["by_rule"], cell["wrong_marked_fix"]))
    total = {k: sum(c[k] for c in table.values()) for k in ("right", "wrong", "missed", "by_rule", "wrong_marked_fix")}
    print("%-12s %5d %5d %6d %8d %16d" % ("total", total["right"], total["wrong"], total["missed"], total["by_rule"], total["wrong_marked_fix"]))
    print("Wrote %s/eval.json" % args.out)


if __name__ == "__main__":
    main()
