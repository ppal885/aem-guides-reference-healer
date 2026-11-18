"""Text that is copied into several topics instead of reused (garage-week PoC). No model.

A paragraph, note or step that stands in ten topics is ten things to keep in step: change one and
the others still say the old thing. DITA's answer is one shared piece and a conref in each place.
This module finds the copies, among the blocks of the files of one check:

    same       the same text (case, spaces and punctuation aside)
    numbers    the same text except for its numbers: "kept for 30 days" and "kept for 60 days".
               These are not only copies: they may contradict each other, and they are never
               merged without the author choosing the right one. (Or the number is meant to
               differ, a release number in release notes: a variable inside a shared piece.)
    wording    nearly the same words (word triples shared by at least 85 percent, or 90 percent of
               the shorter copy's triples in the longer one: a copy with words added), a copy that
               drifted; when its numbers differ too, it is reported as wording

A block is an element of one of BLOCK_TAGS that holds no other such element, so a list item and
the paragraph inside it are not counted twice. Text shorter than MIN_CHARS is left out, and so is
everything already reused (an element with conref or conkeyref, and what is inside it).

    python3 duplicates.py <folder> [--top 20]
"""
import argparse
import collections
import hashlib
import os
import re
import sys
import xml.etree.ElementTree as ET

BLOCK_TAGS = {"p", "note", "step", "cmd", "li", "shortdesc", "section", "info", "stepresult", "context", "dd",
              "example", "lq", "postreq", "prereq", "result", "abstract"}
MIN_CHARS = 40
MIN_FILES = 2
WORDING_SIMILARITY = 0.85
CONTAINED = 0.9            # or: nearly all of the shorter copy's word triples are in the longer one
BANDS, ROWS = 20, 5          # MinHash LSH: 100 hashes; pairs near 0.85 meet in a band almost always


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _text(el):
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def _parse(raw):
    try:
        return ET.fromstring(re.sub(r"<!DOCTYPE[^>\[]*(\[[^\]]*\])?[^>]*>", "", raw or "", count=1))
    except ET.ParseError:
        return None


def blocks_of(path, raw):
    """[{file, location, tag, text}] for the blocks of one file."""
    tree = _parse(raw)
    if tree is None:
        return []
    found = []

    def walk(el, location):
        counts = {}
        for child in el:
            name = _local(child.tag)
            if not name:
                continue
            counts[name] = counts.get(name, 0) + 1
            here = "%s/%s[%d]" % (location, name, counts[name])
            if child.get("conref") or child.get("conkeyref"):
                continue                              # already reused, and so is what is inside it
            holds_block = any(_local(d.tag) in BLOCK_TAGS for d in child.iter() if d is not child)
            if name in BLOCK_TAGS and not holds_block:
                text = _text(child)
                if len(text) >= MIN_CHARS:
                    found.append({"file": path, "location": here, "tag": name, "text": text, "id": child.get("id") or ""})
            else:
                walk(child, here)

    walk(tree, "/%s[1]" % _local(tree.tag))
    return found


def _key(text):
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _shingles(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {" ".join(words[i:i + 3]) for i in range(max(1, len(words) - 2))}


_PRIME = (1 << 31) - 1
_PERMS = [((seed * 2654435761 + 97) % _PRIME or 1, (seed * 40503 + 7) % _PRIME) for seed in range(1, BANDS * ROWS + 1)]


def _minhash(shingles):
    """BANDS*ROWS min-hashes: each shingle is hashed once, then permuted (a*x+b mod p). With numpy
    when it is there (100,000 blocks in seconds), in plain Python otherwise."""
    xs = [int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big") % _PRIME for s in shingles]
    try:
        import numpy
    except ImportError:
        return [min((a * x + b) % _PRIME for x in xs) for a, b in _PERMS]
    x = numpy.array(xs, dtype=numpy.int64)
    a = numpy.array([p[0] for p in _PERMS], dtype=numpy.int64)[:, None]
    b = numpy.array([p[1] for p in _PERMS], dtype=numpy.int64)[:, None]
    return list(((a * x + b) % _PRIME).min(axis=1))


def _contained(a, b):
    """How much of the smaller set is in the larger: a copy with words added is still the copy."""
    small, large = (a, b) if len(a) <= len(b) else (b, a)
    return len(small & large) / float(len(small)) if small else 0.0


def _jaccard(a, b):
    return len(a & b) / float(len(a | b)) if a and b else 0.0


def find(files):
    """Groups of copied blocks, most files first:
    [{kind, tag, text, files, copies: [{file, location, tag, text, id}], variants: [{text, count}]}]."""
    blocks = []
    for entry in files:
        path = (entry.get("path") or "").lstrip("/")
        if path.endswith(".dita"):
            blocks.extend(blocks_of(path, entry.get("xml") or ""))
    # Units: the blocks with the same text (case, spaces and punctuation aside) of one element type.
    by_text = collections.defaultdict(list)
    for block in blocks:
        by_text[(block["tag"], _key(block["text"]))].append(block)
    units = list(by_text.items())
    parent = list(range(len(units)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def join(a, b):
        if root(a) != root(b):
            parent[root(a)] = root(b)
    # The same text but for its numbers.
    by_template = collections.defaultdict(list)
    for index, ((tag, key), _) in enumerate(units):
        by_template[(tag, re.sub(r"\d+", "#", key))].append(index)
    for members in by_template.values():
        for a, b in zip(members, members[1:]):
            join(a, b)
    # Nearly the same words: MinHash LSH finds the candidate pairs, the word triples decide.
    shingles = [_shingles(members[0]["text"]) for _, members in units]
    buckets = collections.defaultdict(list)
    for index, ((tag, key), _) in enumerate(units):
        if len(key.split()) < 6:
            continue
        signature = _minhash(shingles[index])
        for band in range(BANDS):
            buckets[(tag, band, tuple(signature[band * ROWS:(band + 1) * ROWS]))].append(index)
    for members in buckets.values():
        for a, b in zip(members, members[1:]):
            if _jaccard(shingles[a], shingles[b]) >= WORDING_SIMILARITY or _contained(shingles[a], shingles[b]) >= CONTAINED:
                join(a, b)
    clusters = collections.defaultdict(list)
    for index in range(len(units)):
        clusters[root(index)].append(index)
    groups = []
    for indexes in clusters.values():
        members = [b for i in indexes for b in units[i][1]]
        if len({b["file"] for b in members}) < MIN_FILES:
            continue
        templates = {re.sub(r"\d+", "#", units[i][0][1]) for i in indexes}
        kind = "same" if len(indexes) == 1 else "numbers" if len(templates) == 1 else "wording"
        groups.append(_group(kind, units[indexes[0]][0][0], members))
    return sorted(groups, key=lambda g: (-len(g["files"]), -len(g["copies"]), g["text"]))


def _group(kind, tag, members):
    counts = collections.Counter(b["text"] for b in members)
    return {"kind": kind, "tag": tag, "text": counts.most_common(1)[0][0],
            "files": sorted({b["file"] for b in members}), "copies": members,
            "variants": [{"text": text, "count": count} for text, count in counts.most_common()]}


def files_of(folder):
    out = []
    for directory, _, names in os.walk(folder):
        for name in sorted(names):
            if name.endswith(".dita"):
                full = os.path.join(directory, name)
                with open(full, encoding="utf-8", errors="replace") as handle:
                    out.append({"path": os.path.relpath(full, folder), "xml": handle.read()})
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder")
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args()
    files = files_of(args.folder)
    groups = find(files)
    kinds = collections.Counter(g["kind"] for g in groups)
    copies = sum(len(g["copies"]) for g in groups)
    print("%d files, %d groups of copied blocks (%s), %d copies; %d could become conrefs" % (
        len(files), len(groups), ", ".join("%s %d" % kv for kv in sorted(kinds.items())), copies, copies - len(groups)))
    for g in groups[:args.top]:
        print("%5d copies in %4d files  %-8s <%s> %s" % (len(g["copies"]), len(g["files"]), g["kind"], g["tag"], g["text"][:80]))
        if g["kind"] != "same":
            for v in g["variants"][:3]:
                print("        %4dx %s" % (v["count"], v["text"][:100]))


if __name__ == "__main__":
    sys.exit(main())
