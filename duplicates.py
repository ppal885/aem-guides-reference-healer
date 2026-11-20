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
import difflib
import hashlib
import os
import re
import sys
import xml.etree.ElementTree as ET

BLOCK_TAGS = {"p", "note", "step", "cmd", "li", "shortdesc", "section", "info", "stepresult", "context", "dd",
              "example", "lq", "postreq", "prereq", "result", "abstract",
              # A table cell: on a customer export (20 Nov 2026) 161 groups, 417 copies, were in cells.
              "entry"}
MIN_CHARS = 40
MIN_FILES = 2
# A whole list or step copied word for word (its items, its markup) is one piece: one conref takes
# its place instead of one for each item, and the items stay in step. Only an exact copy: a list
# with one item different is left to its items.
WHOLE_TAGS = {"ul", "ol", "step"}
MIN_PARTS = 2
WORDING_SIMILARITY = 0.85
CONTAINED = 0.9            # or: nearly all of the shorter copy's word triples are in the longer one
# And at most this many words added, removed or changed. Measured on 19 Nov 2026 on 50 groups of
# customer content (labelled from the text, not by a writer): without it, 24 of 44 wording groups
# were a sentence and a longer sentence that says more ("...is posted" and "...is posted and is checked
# by the controller", a made-up example), not copies; with 3, 4 of 19, and 5 real copies are no longer found.
MAX_CHANGED_WORDS = 3
EDGE_MIN_WORDS = 8         # copies this long or longer are compared word by word when their ends match
EDGE_MAX_BUCKET = 40       # more blocks than this with the same three first (or last) words: no evidence
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


def _resolved_href(path, href):
    """A relative href resolved against the file's folder, so the same target compares equal from
    any folder; a GUID, a URL or an absolute path as it is."""
    if re.match(r"^(GUID-|[a-z]+:|/|#)", href):
        return href
    target, _, fragment = href.partition("#")
    return os.path.normpath(os.path.join(os.path.dirname(path), target)) + ("#" + fragment if fragment else "")


def markup_of(path, el):
    """The markup inside a block, without its text: '<b><xref href=content/a.dita>'. Ids are left out,
    so are namespaced attributes; an href is resolved. Two copies with the same text and different
    markup (bold here, not there; a link to another topic) are not the same piece. The editor
    computes the same string from the file (markup.ts)."""
    parts = []
    for d in el.iter():
        if d is el:
            continue
        attrs = sorted((k, _resolved_href(path, v) if k == "href" else v) for k, v in d.attrib.items()
                       if k != "id" and not k.startswith("{") and ":" not in k)
        parts.append("<%s%s>" % (_local(d.tag), "".join(" %s=%s" % kv for kv in attrs)))
    return "".join(parts)


# The attributes that decide who reads a block (filtering) or how it is flagged. Two copies with the
# same text and other values here publish to other readers, so they are not the same piece.
CONDITIONS = ("audience", "platform", "product", "props", "otherprops", "deliveryTarget", "rev")


# Folders that name a language (AEM keeps a language copy of the content per folder: /en, /fr-FR).
LANGUAGES = {"ar", "cs", "da", "de", "el", "en", "es", "fi", "fr", "he", "hi", "hu", "id", "it", "ja", "ko", "nb", "nl",
             "no", "pl", "pt", "ro", "ru", "sv", "th", "tr", "uk", "vi", "zh"}


def language_of(path, root):
    """The topic's language, its main code only ("fr" for fr-FR): its xml:lang, or a language folder
    on its path; '' when neither says."""
    lang = root.get("{http://www.w3.org/XML/1998/namespace}lang") if root is not None else None
    if lang:
        return lang.lower().replace("_", "-").split("-")[0]
    for part in path.lower().split("/"):
        code = part.replace("_", "-")
        if code.split("-")[0] in LANGUAGES and re.match(r"^[a-z]{2}(-[a-z]{2,4})?$", code):
            return code.split("-")[0]
    return ""


def own_attributes(el):
    """The block's own condition attributes: 'audience=internal;product=ledger'. Other attributes
    (a note's type, outputclass) do not split a group; the Fix keeps them on each copy."""
    return ";".join("%s=%s" % (a, " ".join(sorted(el.get(a).split()))) for a in CONDITIONS if el.get(a))


def blocks_of(path, raw):
    """[{file, location, tag, text, id, markup}] for the blocks of one file."""
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
            if name in WHOLE_TAGS and sum(1 for c in child if _local(c.tag) in BLOCK_TAGS) >= MIN_PARTS:
                text = _text(child)
                if len(text) >= MIN_CHARS:
                    found.append({"file": path, "location": here, "tag": name, "text": text, "id": child.get("id") or "",
                                  "markup": markup_of(path, child), "own": own_attributes(child), "whole": True,
                                  "inner_ids": sorted({d.get("id") for d in child.iter() if d is not child and d.get("id")})})
            holds_block = any(_local(d.tag) in BLOCK_TAGS for d in child.iter() if d is not child)
            if name in BLOCK_TAGS and not holds_block:
                text = _text(child)
                if len(text) >= MIN_CHARS:
                    found.append({"file": path, "location": here, "tag": name, "text": text, "id": child.get("id") or "",
                                  "markup": markup_of(path, child), "own": own_attributes(child)})
            else:
                walk(child, here)

    walk(tree, "/%s[1]" % _local(tree.tag))
    # Topics of two languages are never one piece: a conref would join the languages (gap found on
    # 20 Nov 2026 by eval/cases.json, copies-13). The language goes with the conditions into the key.
    lang = language_of(path, tree)
    if lang:
        for block in found:
            block["own"] = ";".join(filter(None, [block["own"], "lang=" + lang]))
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


# Short forms that say the same as their long form ("Don't" and "Do not"): one copy that uses the
# short form has not changed a word. Keys are lower case words, so "don't" is "don t".
CONTRACTIONS = [("don t", "do not"), ("doesn t", "does not"), ("didn t", "did not"), ("can t", "cannot"),
                ("can not", "cannot"), ("won t", "will not"), ("isn t", "is not"), ("aren t", "are not"),
                ("wasn t", "was not"), ("weren t", "were not"), ("shouldn t", "should not"), ("couldn t", "could not"),
                ("wouldn t", "would not"), ("haven t", "have not"), ("hasn t", "has not"), ("it s", "it is"),
                ("you re", "you are"), ("we re", "we are"), ("they re", "they are"), ("you ll", "you will"),
                ("we ll", "we will"), ("that s", "that is"), ("there s", "there is"), ("let s", "let us")]


def long_forms(key):
    """A key with every short form written out."""
    out = " %s " % key
    for short, full in CONTRACTIONS:
        out = out.replace(" %s " % short, " %s " % full)
    return out.strip()


SAYS_MORE_SHARE = 0.4      # the shorter copy is at least this share of the longer one's words


def _says_more(a, b):
    """Whether one text (a key) is the other with words added, none changed or left out, and the
    shorter is not a small part of the longer (a sentence that happens to stand in a long paragraph)."""
    x, y = long_forms(a).split(), long_forms(b).split()
    if not x or not y or min(len(x), len(y)) < SAYS_MORE_SHARE * max(len(x), len(y)):
        return False
    ops = {op for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, x, y, autojunk=False).get_opcodes() if op != "equal"}
    return ops in ({"insert"}, {"delete"})


def _changed_words(a, b):
    """How many words differ between two texts (their keys): added, removed or replaced. A short form
    and its long form are the same words."""
    x, y = long_forms(a).split(), long_forms(b).split()
    return sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in
               difflib.SequenceMatcher(None, x, y, autojunk=False).get_opcodes() if op != "equal")


# The same short forms, as a person writes them ("don't"), for the text of a copy.
CONTRACTION_WORDS = {short.replace(" ", "'"): full for short, full in CONTRACTIONS if " " in short and short.endswith((" t", " s", " re", " ll"))}

NEGATIONS = {"not", "no", "never", "cannot", "none", "nor", "without", "neither", "nothing", "t"}  # "t": don't, isn't


def _says_otherwise(a, b):
    """Why two nearly equal texts still say different things, or None: one says "not" (or never, no,
    don't...) where the other does not, or a name is put in place of other words (Payroll for Billing,
    Acme Payroll for the customer).
    Words only added or left out are not a different name; the changed-words limit covers those."""
    # Short forms written out first, so "Don't" and "Do not" are the same words (and the same "not").
    expand = lambda text: re.findall(r"[A-Za-z0-9]+", " " + " ".join(
        w if not CONTRACTION_WORDS.get(w.lower()) else CONTRACTION_WORDS[w.lower()] for w in re.findall(r"[A-Za-z0-9']+", text)))
    words_a, words_b = expand(a), expand(b)
    negations = lambda words: sorted("not" if w.lower() == "t" else w.lower() for w in words if w.lower() in NEGATIONS)
    if negations(words_a) != negations(words_b):
        return "negation"
    capital = lambda words: {w.lower() for w in words if w[0].isupper()}
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [w.lower() for w in words_a], [w.lower() for w in words_b],
                                                      autojunk=False).get_opcodes():
        # The first word is a capital by place, not a name; a one-word change of a few letters is a typo.
        # One word written as two ("Webclient", "Web client") is the same word, not a name.
        if op == "replace" and "".join(words_a[i1:i2]).lower() == "".join(words_b[j1:j2]).lower():
            continue
        left, right = capital(words_a[max(i1, 1):i2]), capital(words_b[max(j1, 1):j2])
        typo = i2 - i1 == j2 - j1 == 1 and difflib.SequenceMatcher(None, words_a[i1].lower(), words_b[j1].lower()).ratio() >= 0.8
        # A name on either side: "the customer" and "Acme Payroll" are other readers, not a reworded copy.
        if op == "replace" and (left or right) and not typo:
            return "name"
        # Two words or more put in place of two words or more that are not the same words in other
        # case or punctuation: another statement ("checking their eligibility" for "scheduling a
        # demo"), seen on customer content (19 Nov 2026). One word for another stays a copy.
        if op == "replace" and i2 - i1 >= 2 and j2 - j1 >= 2:
            plain_a = " ".join(re.findall(r"[a-z0-9]+", " ".join(words_a[i1:i2]).lower()))
            plain_b = " ".join(re.findall(r"[a-z0-9]+", " ".join(words_b[j1:j2]).lower()))
            if difflib.SequenceMatcher(None, plain_a, plain_b).ratio() < 0.8:
                return "other words"
    return None


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
    whole_groups, blocks = _whole(files, blocks)
    # Units: the blocks with the same text (case, spaces and punctuation aside) of one element type
    # and the same own attributes (conditions).
    by_text = collections.defaultdict(list)
    for block in blocks:
        by_text[(block["tag"], block["own"], _key(block["text"]))].append(block)
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
    for index, ((tag, own, key), _) in enumerate(units):
        by_template[(tag, own, re.sub(r"\d+", "#", key))].append(index)
    for members in by_template.values():
        for a, b in zip(members, members[1:]):
            join(a, b)
    # Nearly the same words: MinHash LSH finds the candidate pairs, the word triples decide.
    shingles = [_shingles(members[0]["text"]) for _, members in units]
    buckets = collections.defaultdict(list)
    for index, ((tag, own, key), _) in enumerate(units):
        if len(key.split()) < 6:
            continue
        signature = _minhash(shingles[index])
        for band in range(BANDS):
            buckets[(tag, own, band, tuple(signature[band * ROWS:(band + 1) * ROWS]))].append(index)
    # Pairs that would be copies but for two words or more put for two others: maybe the same thing
    # in other words ("service desk", "support team"), maybe another statement ("receipts", "payments").
    # Code cannot tell; they become "maybe" groups for the author or the reuse agent to settle.
    maybe = []

    def join_or_maybe(a, b):
        why = _says_otherwise(units[a][1][0]["text"], units[b][1][0]["text"])
        if why is None:
            join(a, b)
        elif why == "other words":
            maybe.append((a, b, why))

    # One copy that holds every word of the other and more than MAX_CHANGED_WORDS words besides: a
    # lost instruction or a part meant for some topics only. On 50 labelled groups of customer content
    # (20 Nov 2026) the 26 such pairs were 15 drifted, 8 on purpose, 3 unclear: code cannot tell, so
    # they become "maybe" groups (why "says more") instead of being left out.
    def judge(a, b):
        changed = _changed_words(units[a][0][2], units[b][0][2])
        if changed <= MAX_CHANGED_WORDS:
            join_or_maybe(a, b)
        elif _says_more(units[a][0][2], units[b][0][2]):
            maybe.append((a, b, "says more"))
    for members in buckets.values():
        for a, b in zip(members, members[1:]):
            if _jaccard(shingles[a], shingles[b]) >= WORDING_SIMILARITY or _contained(shingles[a], shingles[b]) >= CONTAINED:
                judge(a, b)
    # Short copies: one changed word changes three word triples, so in a sentence of fifteen words
    # the triples of two copies never meet (seen on samples/dupes-drift: "and the attachments" added,
    # "service desk" for "support team"). Copies that keep their first or last three words are
    # compared word by word; an opening that many blocks share ("Select the ...") is no evidence.
    edges = collections.defaultdict(list)
    for index, ((tag, own, key), _) in enumerate(units):
        words = key.split()
        if len(words) >= EDGE_MIN_WORDS:
            edges[(tag, own, "head", " ".join(words[:3]))].append(index)
            edges[(tag, own, "tail", " ".join(words[-3:]))].append(index)
    for members in edges.values():
        if len(members) > EDGE_MAX_BUCKET:
            continue
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                if root(a) != root(b):
                    judge(a, b)
    clusters = collections.defaultdict(list)
    for index in range(len(units)):
        clusters[root(index)].append(index)
    groups = []
    for indexes in clusters.values():
        members = [b for i in indexes for b in units[i][1]]
        if len({b["file"] for b in members}) < MIN_FILES:
            continue
        templates = {re.sub(r"\d+", "#", units[i][0][2]) for i in indexes}
        kind = "same" if len(indexes) == 1 else "numbers" if len(templates) == 1 else "wording"
        groups.append(_group(kind, units[indexes[0]][0][0], members))
    groups.extend(_maybe_groups(maybe, root, clusters, units))
    groups.extend(whole_groups)
    return sorted(groups, key=lambda g: (-len(g["files"]), -len(g["copies"]), g["text"]))


def _maybe_groups(pairs, root, clusters, units):
    """One "maybe" group for each set of copy groups (or single wordings) that pairs join: their copies
    together, in two topics or more. A group of copies stays as it is; the maybe group is listed
    beside it until someone says whether the wordings say the same."""
    parent = {}

    def top(r):
        while parent.get(r, r) != r:
            r = parent[r]
        return r
    for a, b, _ in pairs:
        ra, rb = top(root(a)), top(root(b))
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    sets = collections.defaultdict(set)
    whys = collections.defaultdict(set)
    for a, b, why in pairs:
        if root(a) == root(b):
            continue
        for r in (root(a), root(b)):
            sets[top(r)].add(r)
        whys[top(root(a))].add(why)
    out = []
    for key, roots in sets.items():
        if len(roots) < 2:
            continue
        members = [blk for r in sorted(roots) for i in clusters[r] for blk in units[i][1]]
        if len({blk["file"] for blk in members}) >= MIN_FILES:
            group = _group("maybe", units[min(roots)][0][0], members)
            # "says more" only when every pair is one copy with words added; else "other words".
            group["why"] = "says more" if whys[key] == {"says more"} else "other words"
            out.append(group)
    return out


def _linked_ids(files):
    """The element ids something links to: {(file, id)}, and {id} for a link by GUID, whose file
    is not known here (any element with that id counts as linked)."""
    by_file, anywhere = set(), set()
    for entry in files:
        path = (entry.get("path") or "").lstrip("/")
        for target, fragment in re.findall(r'\s(?:href|conref)\s*=\s*"([^"#]*)#([^"]+)"', entry.get("xml") or ""):
            element = fragment.split("/")[-1]
            if target.startswith("GUID-") or re.match(r"^[a-z]+:", target):
                anywhere.add(element)
            else:
                by_file.add((_resolved_href(path, target) if target else path, element))
    return by_file, anywhere


def _inside(location, taken):
    parts = location.split("/")
    return any("/".join(parts[:n]) in taken for n in range(2, len(parts)))


def _whole(files, blocks):
    """Groups of whole lists and steps copied word for word, markup and all, into MIN_FILES files or
    more; and the other blocks, without the items inside those copies (the whole list is shared,
    not its items). A copy with an item something links to is left to its items: a conref would
    take that id away."""
    whole = [b for b in blocks if b.get("whole")]
    rest = [b for b in blocks if not b.get("whole")]
    by_file, anywhere = _linked_ids(files)

    def linked(file, element_id):
        return (file, element_id) in by_file or element_id in anywhere
    # A whole list or step that is itself a shared piece (something pulls it in by conref): its
    # items are the piece's, not copies of their own.
    pieces = [b for b in whole if b["id"] and linked(b["file"], b["id"])]
    keep = [b for b in whole if not any(linked(b["file"], i) for i in b["inner_ids"])]
    for _ in range(2):                                # a copied list inside a copied step goes with the step
        by_text = collections.defaultdict(list)
        for block in keep:
            by_text[(block["tag"], _key(block["text"]), block["markup"], block["own"])].append(block)
        chosen = [m for m in by_text.values() if len({b["file"] for b in m}) >= MIN_FILES]
        taken = collections.defaultdict(set)
        for block in pieces:
            taken[block["file"]].add(block["location"])
        for members in chosen:
            for block in members:
                taken[block["file"]].add(block["location"])
        keep = [b for b in keep if not _inside(b["location"], taken[b["file"]])]
    groups = [_group("same", m[0]["tag"], m) for m in chosen if not any(_inside(b["location"], taken[b["file"]]) for b in m)]
    return groups, [b for b in rest if not _inside(b["location"], taken[b["file"]])]


def _group(kind, tag, members):
    counts = collections.Counter(b["text"] for b in members)
    return {"kind": kind, "tag": tag, "text": counts.most_common(1)[0][0],
            "files": sorted({b["file"] for b in members}), "copies": members,
            "variants": [{"text": text, "count": count} for text, count in counts.most_common()]}


# ---- maps -----------------------------------------------------------------------------------
# A group of topic references (a topichead with its topics, a chapter, a relationship table) copied
# into several maps of one check is the same thing to keep in step: add a topic to one copy and the
# others miss it. Maps hold almost no text, so a copy is compared by its references: for each
# element in it, its name and its href, keyref, keys, navtitle, format, scope and type.

MAP_REFS = {"topicref", "topichead", "topicgroup", "chapter", "part", "appendix", "appendices", "keydef",
            "mapref", "glossref", "anchorref", "topicset", "topicsetref", "frontmatter", "backmatter", "notices"}
MAP_GROUP_TAGS = MAP_REFS | {"reltable"}
MAP_ATTRIBUTES = ("href", "keyref", "keys", "navtitle", "format", "scope", "type")
MIN_REFS = 2          # a group holds at least this many references below it


def _refs_below(el):
    return sum(1 for d in el.iter() if d is not el and _local(d.tag) in MAP_REFS)


def map_signature(el):
    """The references of an element as the file says them: 'topichead|navtitle=Setup;topicref|href=a.dita'.
    The editor computes the same string from the file before it replaces a copy."""
    parts = []
    for d in el.iter():
        name = _local(d.tag)
        if name in MAP_GROUP_TAGS or name in ("relrow", "relcell", "relheader", "relcolspec"):
            parts.append("|".join([name] + ["%s=%s" % (a, d.get(a)) for a in MAP_ATTRIBUTES if d.get(a)]))
    return ";".join(parts)


def _resolved(signature, path):
    """The signature with each relative href resolved against the map's folder, so two maps in
    different folders that point at the same topics compare equal."""
    folder = os.path.dirname(path)

    def resolve(match):
        href = match.group(1)
        if re.match(r"^(GUID-|[a-z]+:|/)", href):
            return "href=" + href
        target, _, fragment = href.partition("#")
        return "href=" + os.path.normpath(os.path.join(folder, target)) + ("#" + fragment if fragment else "")
    return re.sub(r"href=([^|;]+)", resolve, signature)


def map_blocks_of(path, raw):
    """[{file, location, tag, text, id, refs}] for the groups of a map: the largest elements of
    MAP_GROUP_TAGS with at least MIN_REFS references below them (a relationship table: at least one
    row). Elements already reused (conref) are left out."""
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
                continue
            refs = _refs_below(child)
            rows = sum(1 for d in child.iter() if _local(d.tag) == "relrow")
            if name in MAP_GROUP_TAGS and (refs >= MIN_REFS or (name == "reltable" and rows >= 1)):
                found.append({"file": path, "location": here, "tag": name, "text": map_signature(child),
                              "id": child.get("id") or "", "refs": refs, "navtitle": _navtitle(child)})
            walk(child, here)

    walk(tree, "/%s[1]" % _local(tree.tag))
    return found


def _navtitle(el):
    if el.get("navtitle"):
        return el.get("navtitle")
    for d in el:
        if _local(d.tag) == "topicmeta":
            for t in d:
                if _local(t.tag) == "navtitle":
                    return _text(t)
    return ""


def find_maps(files):
    """Groups of map elements copied into several maps (or twice into one), the largest only: a
    group inside a copied group is not reported again. Most references first:
    [{kind: "map", tag, text, navtitle, files, copies, variants, refs}]."""
    blocks = []
    for entry in files:
        path = (entry.get("path") or "").lstrip("/")
        if path.endswith(".ditamap"):
            blocks.extend(map_blocks_of(path, entry.get("xml") or ""))
    by_key = collections.defaultdict(list)
    for block in blocks:
        by_key[(block["tag"], _resolved(block["text"], block["file"]))].append(block)
    copied = [members for members in by_key.values() if len(members) > 1]
    places = {(b["file"], b["location"]) for members in copied for b in members}
    groups = []
    for members in copied:
        # Inside another copied group: that group is the one to share.
        if all(any((b["file"], b["location"].rsplit("/", n)[0]) in places
                   for n in range(1, b["location"].count("/"))) for b in members):
            continue
        group = _group("map", members[0]["tag"], members)
        group.update(navtitle=next((b["navtitle"] for b in members if b["navtitle"]), ""), refs=members[0]["refs"])
        groups.append(group)
    return sorted(groups, key=lambda g: (-g["refs"], -len(g["copies"]), g["text"]))


def files_of(folder, maps=False):
    out = []
    for directory, _, names in os.walk(folder):
        for name in sorted(names):
            if name.endswith(".dita") or (maps and name.endswith(".ditamap")):
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
