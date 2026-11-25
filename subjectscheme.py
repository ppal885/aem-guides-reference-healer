"""Attribute values that a subject scheme no longer allows, and what they should be now
(garage-week PoC). No model.

A subject scheme map lists the values an attribute may take: <enumerationdef> names the attribute
(<attributedef name="platform"/>) and a subject (<subjectdef keyref="os"/>); the allowed values are
the keys of that subject and of the subjects under it. A topic says platform="linux windows". When
the scheme's key "linux" is renamed, every such value in every topic is wrong, and nothing breaks
visibly: AEM's Broken links report does not list attribute values, filtering stops matching, and the
editor offers only the new names.

This module finds those values and, where the scheme's previous version proves it, the new name:

    renamed   the old key had a label (navtitle) and exactly one subject has that label now, under
              a key that the old version did not have. Proven: the repair is applied with "Fix all".
    moved     the old key had no label, and the subject in its place (same parent, same position)
              has a key the old version did not have. Likely, not proven: the author decides.
    removed   the old key is gone and nothing took its place: no repair, the author decides.
    typo      the value was never in the scheme: the allowed value closest in spelling, if one is
              close, for the author to decide.

A repair rewrites the whole attribute value ("linux windows" -> "gnu-linux windows"), so the editor's
"Fix all" applies it like any other attribute edit.
"""
import difflib
import re
import xml.etree.ElementTree as ET

import refcheck

STAGE = "subject scheme rule"


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _parse(raw):
    try:
        return ET.fromstring(refcheck.readable(raw or ""))
    except ET.ParseError:
        return None


def _is_scheme(tree):
    return tree is not None and (_local(tree.tag) == "subjectScheme" or "subjectScheme/subjectScheme" in (tree.get("class") or ""))


def _label(el):
    if el.get("navtitle"):
        return " ".join(el.get("navtitle").split())
    for child in el:
        if _local(child.tag) == "topicmeta":
            for meta in child.iter():
                if _local(meta.tag) == "navtitle":
                    return " ".join("".join(meta.itertext()).split())
    return ""


def read_scheme(raw):
    """{"subjects": {key: {"label", "parent", "index"}}, "enums": [{"attribute", "element", "category"}]},
    or None when the XML is not a subject scheme."""
    tree = _parse(raw)
    if not _is_scheme(tree):
        return None
    subjects, enums = {}, []

    def walk(el, parent):
        index = 0
        for child in el:
            name = _local(child.tag)
            if name == "enumerationdef":
                attribute = next((c.get("name") for c in child if _local(c.tag) == "attributedef"), None)
                element = next((c.get("name") for c in child if _local(c.tag) == "elementdef"), None)
                category = next((c.get("keyref") or (c.get("keys") or "").split(" ")[0]
                                 for c in child if _local(c.tag) == "subjectdef"), None)
                if attribute and category:
                    enums.append({"attribute": attribute, "element": element, "category": category})
                continue
            if name == "subjectdef":
                keys = (child.get("keys") or "").split()
                for key in keys:
                    subjects.setdefault(key, {"label": _label(child), "parent": parent, "index": index})
                # A subjectdef with keyref adds subjects under a subject defined elsewhere in the scheme.
                walk(child, keys[0] if keys else child.get("keyref") or parent)
                index += 1
            else:
                walk(child, parent)

    walk(tree, None)
    return {"subjects": subjects, "enums": enums}


def allowed(scheme, category):
    """The keys of a subject and of every subject under it."""
    found, frontier = {category}, [category]
    while frontier:
        parent = frontier.pop()
        for key, subject in scheme["subjects"].items():
            if subject["parent"] == parent and key not in found:
                found.add(key)
                frontier.append(key)
    return found


def _line(raw, attribute, value):
    position = raw.find('%s="%s"' % (attribute, value))
    if position < 0:
        position = raw.find("%s='%s'" % (attribute, value))
    return raw.count("\n", 0, position) + 1 if position >= 0 else 0


def _what_became_of(token, schemes):
    """(kind, new key or None, label, scheme path) for a value the current schemes do not allow."""
    for path, now, olds in schemes:
        for old in olds:
            before = old["subjects"].get(token)
            if before is None:
                continue
            fresh = {k: s for k, s in now["subjects"].items() if k not in old["subjects"]}
            if before["label"]:
                same = [k for k, s in now["subjects"].items() if s["label"].lower() == before["label"].lower()]
                if len(same) == 1 and same[0] in fresh:
                    return "renamed", same[0], before["label"], path
            in_place = [k for k, s in fresh.items() if s["parent"] == before["parent"] and s["index"] == before["index"]]
            if len(in_place) == 1:
                return "moved", in_place[0], before["label"] or now["subjects"][in_place[0]]["label"], path
            return "removed", None, before["label"], path
    return "typo", None, "", schemes[0][0] if schemes else ""


def check(files):
    """The attribute values in the files that the subject schemes among them do not allow, with a
    repair where one is known. Returns {"repairs": [...], "plan": [lines], "values": n}."""
    schemes = []
    for entry in files:
        now = read_scheme(entry.get("xml"))
        if now:
            olds = [s for s in (read_scheme(raw) for raw in entry.get("previous") or []) if s]
            schemes.append(((entry.get("path") or "").lstrip("/"), now, olds))
    if not schemes:
        return {"repairs": [], "plan": [], "values": 0}
    rules = []   # (attribute, element or None, allowed keys)
    for _, now, _ in schemes:
        for enum in now["enums"]:
            if enum["category"] in now["subjects"]:
                rules.append((enum["attribute"], enum["element"], allowed(now, enum["category"])))
    known = {key for _, now, _ in schemes for key in now["subjects"]}
    fates, repairs, places = {}, {}, {}
    for entry in files:
        path = (entry.get("path") or "").lstrip("/")
        raw = entry.get("xml") or ""
        tree = _parse(raw)
        if tree is None or _is_scheme(tree):
            continue
        for el in tree.iter():
            for attribute, element, keys in rules:
                value = el.get(attribute)
                if value is None or (element and _local(el.tag) != element) or "(" in value:
                    continue
                bad = [t for t in value.split() if t not in keys and t not in known]
                if not bad:
                    continue
                new_tokens, verdicts, notes = value.split(), [], []
                for token in bad:
                    fate = fates.setdefault(token, _what_became_of(token, schemes))
                    kind, new, label, scheme_path = fate
                    if kind == "typo":
                        # Only a suggestion for the author ("review"), so a short swapped word counts:
                        # "wni" and "win" score 0.67. A misspelt old name ("admn" for "admin") leads
                        # to the name it has now.
                        renamed = _renames(token, schemes, fates)
                        close = difflib.get_close_matches(token, sorted(keys) + sorted(renamed), n=1, cutoff=0.6)
                        new = renamed.get(close[0], close[0]) if close else None
                    if new:
                        new_tokens = [new if t == token else t for t in new_tokens]
                    verdicts.append("fix" if kind == "renamed" else "review" if new else "none")
                    notes.append(_note(token, fate, new, attribute))
                    places.setdefault(token, set()).add(path)
                verdict = "none" if "none" in verdicts else "review" if "review" in verdicts else "fix"
                key = (path, attribute, value)
                if key in repairs:
                    continue
                new_value = " ".join(new_tokens) if verdict != "none" else None
                repairs[key] = {"file": "/" + path, "line": _line(raw, attribute, value), "attribute": attribute,
                                "old": value, "new": new_value, "verdict": verdict, "stage": STAGE,
                                "target": 'value "%s"' % new_value if new_value else None,
                                "reason": " ".join(notes), "caveat": "", "used_in": ["/" + path], "detail": {}}
    plan = []
    for token, (kind, new, label, scheme_path) in sorted(fates.items()):
        uses = sum(1 for (p, a, v), r in repairs.items() if token in v.split())
        where = len(places.get(token, ()))
        if not uses:
            continue
        verb = "uses" if uses == 1 else "use"
        if kind == "renamed":
            plan.append('Subject scheme: "%s"%s was renamed "%s" in %s; %s in %s still %s the old name. The scheme\'s '
                        'previous version proves the new one (same label), no AI needed.' % (
                            token, ' ("%s")' % label if label else "", new, scheme_path, _values(uses), _files(where), verb))
        elif kind == "typo":
            suggestion = [r["new"] for r in repairs.values() if token in r["old"].split() and r["new"]]
            plan.append('Subject scheme: "%s" was never a value in the scheme%s; %s in %s %s it.' % (
                token, '; it is probably a misspelling, see the suggestion' if suggestion else "", _values(uses), _files(where), verb))
        else:
            plan.append('Subject scheme: "%s" is no longer in %s (%s); %s in %s %s it.' % (
                token, scheme_path, 'likely now "%s", which sits in its place: for you to check' % new if kind == "moved" else
                "removed, nothing took its place", _values(uses), _files(where), verb))
    return {"repairs": list(repairs.values()), "plan": plan, "values": len(repairs)}


def _renames(token, schemes, fates):
    """{old key: key now} for the keys the schemes' previous versions prove or place as renamed."""
    found = {}
    for _, now, olds in schemes:
        for old in olds:
            for key in old["subjects"]:
                if key != token and key not in now["subjects"]:
                    kind, renamed_to, _, _ = fates.setdefault(key, _what_became_of(key, schemes))
                    if renamed_to:
                        found[key] = renamed_to
    return found


def _values(n):
    return "%d attribute %s" % (n, "value" if n == 1 else "values")


def _files(n):
    return "%d %s" % (n, "file" if n == 1 else "files")


def _note(token, fate, new, attribute):
    kind, renamed_to, label, scheme_path = fate
    if kind == "renamed":
        return ('The subject scheme (%s) renamed "%s" to "%s": its previous version had "%s" with the label "%s", '
                'and the label is now on "%s".' % (scheme_path, token, renamed_to, token, label, renamed_to))
    if kind == "moved":
        return ('The subject scheme (%s) no longer has "%s". "%s" now sits where it was (same parent, same position), '
                'but nothing proves it is the same subject: check it.' % (scheme_path, token, renamed_to))
    if kind == "removed":
        return ('The subject scheme (%s) no longer has "%s" and nothing took its place. Choose another value for %s, '
                'or remove this one.' % (scheme_path, token, attribute))
    return ('"%s" is not a value of %s in the subject scheme, now or in an earlier version.%s' % (
        token, attribute, ' Probably a misspelling of what is now "%s".' % new if new else ""))
