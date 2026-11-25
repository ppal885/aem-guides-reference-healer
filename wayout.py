"""Ways out for a reference whose content was removed for good (garage-week PoC).

A finder agent can conclude that the piece a reference pointed at is gone and nothing replaces
it. That is where the author's work starts, so the agents do not stop there. Three ways out exist:

    restore   put the piece back where it lived, from the previous version: one edit, and every
              reference works again
    remove    take the references out of the topics that still carry them
    inline    keep the text in those topics as plain content, without the reference

Which of them are possible is worked out here in code. The planner recommends one with its
reason; a person chooses. Nothing here is ever applied without a person.

Safety content (a note of type warning, danger or caution, a hazard statement) is never offered
for removal: a topic that silently loses a warning is the worst outcome this tool could have.
"""
import re
import xml.etree.ElementTree as ET

import refcheck

SAFETY_NOTE_TYPES = ("warning", "danger", "caution")
KINDS = {"restore_at_source": "restore", "remove_references": "remove", "keep_text_in_topics": "inline"}


def _span(xml, element_id, start=0, end=None):
    """(start, end) of the source text of the first element with this id between start and end, or None."""
    end = len(xml or "") if end is None else end
    pattern = re.compile(r'<([A-Za-z_][\w.-]*)(?=[\s/>])[^<>]*?\sid\s*=\s*(["\'])%s\2[^<>]*?(/?)>' % re.escape(element_id))
    found = pattern.search(xml or "", start, end)
    if not found:
        return None
    if found.group(3):
        return found.start(), found.end()
    depth, tags = 1, re.compile(r"<(/?)%s(?=[\s/>])[^<>]*?(/?)>" % re.escape(found.group(1)))
    for tag in tags.finditer(xml, found.end(), end):
        if tag.group(1):
            depth -= 1
        elif not tag.group(2):
            depth += 1
        if depth == 0:
            return found.start(), tag.end()
    return None


def element_xml(xml, element_id, topic_id=None):
    """The source text of the element with this id, or "" when it cannot be cut out cleanly. With
    topic_id, only inside that topic: ids are unique per topic, and a file with two topics may use
    one id in both. Without it the first in the file was taken (24 Nov 2026): a danger note removed
    from one topic was read as the other topic's plain note, and removing it was offered."""
    start, end = 0, None
    if topic_id:
        topic = _span(xml, topic_id)
        if not topic:
            return ""
        start, end = topic
    found = _span(xml, element_id, start, end)
    return xml[found[0]:found[1]] if found else ""


_NOTE = re.compile(r"<note(?=[\s/>])([^>]*)>")


def _attribute(attributes, name):
    found = re.search(r'\s%s\s*=\s*["\']([^"\']*)["\']' % name, attributes)
    return found.group(1).strip().lower() if found else ""


def is_safety(xml):
    """True when the piece is or holds a warning, danger or caution note (also type="other" with that
    othertype) or a hazard statement. Only the piece's own tag was looked at before (24 Nov 2026): a
    shared section, paragraph or steps with a warning inside was offered for removal."""
    if re.search(r"<hazardstatement(?=[\s/>])", xml or ""):
        return True
    for attributes in _NOTE.findall(xml or ""):
        kind = _attribute(attributes, "type")
        if kind in SAFETY_NOTE_TYPES or (kind == "other" and _attribute(attributes, "othertype") in SAFETY_NOTE_TYPES):
            return True
    return False


def anchor(old_xml, element_id, ids_now, topic_id=None):
    """Where the piece goes back: after or before a neighbour that still exists, else at the end
    of its parent. {"after": id} | {"before": id} | {"into": id} | {"into_tag": tag}. With topic_id,
    only inside that topic. ids_now: the ids the editor can find in the file today (it looks an id up
    in the whole file, so only ids that are there once)."""
    try:
        tree = ET.fromstring(refcheck.readable(old_xml))
    except ET.ParseError:
        return None
    scope = tree
    if topic_id:
        scope = next((el for el in tree.iter() if el.get("id") == topic_id), None)
        if scope is None:
            return None
    for parent in scope.iter():
        children = list(parent)
        index = next((i for i, child in enumerate(children) if child.get("id") == element_id), None)
        if index is None:
            continue
        before = next((c.get("id") for c in reversed(children[:index]) if c.get("id") in ids_now), None)
        if before:
            return {"after": before}
        after = next((c.get("id") for c in children[index + 1:] if c.get("id") in ids_now), None)
        if after:
            return {"before": after}
        if parent.get("id") in ids_now:
            return {"into": parent.get("id")}
        return {"into_tag": refcheck.local(parent.tag)}
    return None


def without_id(xml):
    """The element as plain content of a topic: without the id it had in the shared file. For a
    range of elements (a conref with a conrefend), each element of the range loses its id."""
    out, depth, at = [], 0, 0
    for tag in re.finditer(r"<(/?)([A-Za-z_][\w.-]*)(?=[\s/>])[^<>]*?(/?)>", xml or ""):
        if not tag.group(1) and depth == 0:
            out.append(xml[at:tag.start()])
            out.append(re.sub(r'\sid\s*=\s*(["\'])[^"\']*\1', "", tag.group(0), count=1))
            at = tag.end()
        if tag.group(1):
            depth -= 1
        elif not tag.group(3):
            depth += 1
    return "".join(out) + (xml or "")[at:]


def range_xml(xml, first_id, last_id, topic_id=None):
    """The source text from the element with first_id to the end of the one with last_id, its sibling
    later in the file: what a conref with a conrefend reuses. "" when it cannot be cut out cleanly."""
    start, end = 0, None
    if topic_id:
        topic = _span(xml, topic_id)
        if not topic:
            return ""
        start, end = topic
    first = _span(xml, first_id, start, end)
    last = _span(xml, last_id, first[1], end) if first else None
    return xml[first[0]:last[1]] if first and last else ""


def _range_end(repo, ref):
    """The element id the conrefend beside this conref names, or None when it has none."""
    for other in getattr(repo, "refs", []):
        if (other["file"], other["location"], other["attribute"]) == (ref["file"], ref["location"], "conrefend"):
            return other["value"].rpartition("#")[2].rpartition("/")[2] or None
    return None


def target_of(repo, ref):
    """(file, topic id, element id, renamed key) a broken reference points at; file is None when the
    target is not an element. topic id: the topic the reference names, None when it names none (a key
    whose definition names no topic). renamed key: the key's name today, when version history shows
    that the key of the reference was renamed as well; the reference then has to follow it."""
    if ref["attribute"] in refcheck.PATH_ATTRS:
        target, topic_id, element_id = repo.split_target(ref)
        return (target, topic_id, element_id, None) if element_id else (None, None, None, None)
    import refheal
    key, _, element_id = ref["value"].partition("/")
    renamed = None
    if key not in repo.keys:
        found = refheal.renamed_key(repo, key)
        renamed = found[0] if found else None
    definition = repo.definition_of(renamed or key)
    if definition and definition["target"] and element_id:
        topic_id = ((definition.get("href") or "").partition("#")[2]).split("/")[0] or None
        return definition["target"], topic_id, element_id, renamed
    return None, None, None, None


def ways_out(repo, refs, previous_xml):
    """What can be done about references to an element that is gone.

    previous_xml: {path: [earlier versions of the file, newest first]}.
    Returns {"was", "safety", "options": [{"kind", "label", ...}]}; options is empty when the
    old piece cannot be found in an earlier version, or the target is not an element.
    """
    first = refs[0]
    target, topic_id, element_id, renamed_key = target_of(repo, first)
    found = {"was": "", "safety": False, "options": [], "renamed_key": renamed_key}
    # The end of a range is put back, kept or removed together with its start (the conref group):
    # alone it is only part of what the topics reused.
    if not target or target not in repo.files or first["attribute"] == "conrefend":
        return found
    old_file = next((xml for xml in previous_xml.get(target, []) if element_xml(xml, element_id, topic_id)), None)
    if not old_file:
        return found
    # A conref with a conrefend reused a range of elements, not one: every one of them comes back
    # or is kept (25 Nov 2026: only the first of three steps was, and the card said all worked again).
    ends = {_range_end(repo, ref) for ref in refs} if first["attribute"] == "conref" else {None}
    if len(ends) > 1:
        return found    # topics reuse different ranges from here: no one piece fits them all
    last_id = ends.pop()
    piece = range_xml(old_file, element_id, last_id, topic_id) if last_id else element_xml(old_file, element_id, topic_id)
    if not piece:
        return found
    found.update(was=piece, safety=is_safety(piece))
    files = len({r["file"] for r in refs})
    now = repo.files[target]
    # The editor finds a place, and whether the piece is back, by an id in the whole file: an id that
    # is in the file more than once (in two topics) could put it in the other topic, or say it is back.
    counts = {}
    for (_topic, eid) in now["elements"]:
        counts[eid] = counts.get(eid, 0) + 1
    for (_topic, eid), more in now.get("copies", {}).items():
        counts[eid] = counts.get(eid, 0) + more - 1
    for tid in now["topics"]:
        counts[tid] = counts.get(tid, 0) + 1
    once = {eid for eid, n in counts.items() if n == 1}
    where = None if element_id in counts else anchor(old_file, element_id, once, topic_id)
    if where and "into_tag" in where and len(now["topics"]) > 1:
        where = None    # "at the end of a <body>" is in whichever topic comes last
    if where:
        found["options"].append({
            "kind": "restore", "file": "/" + target, "xml": piece, "anchor": where,
            "label": "Put it back in %s: one edit, and all %d references work again" % (target.rsplit("/", 1)[-1], len(refs))})
    if first["attribute"] in ("conref", "conkeyref"):
        found["options"].append({
            # file: where the piece was, so the editor writes its links (href) from each topic's folder.
            "kind": "inline", "xml": without_id(piece), "file": "/" + target,
            "label": "Keep the text in the %d topics as their own content, without the reference" % files})
        if not found["safety"]:
            found["options"].append({
                "kind": "remove", "label": "Remove the %d references from the %d topics" % (len(refs), files)})
    return found
