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


def element_xml(xml, element_id):
    """The source text of the element with this id, or "" when it cannot be cut out cleanly."""
    start = re.search(r'<([A-Za-z_][\w.-]*)(?=[\s/>])[^<>]*?\sid\s*=\s*(["\'])%s\2[^<>]*?(/?)>' % re.escape(element_id), xml or "")
    if not start:
        return ""
    if start.group(3):
        return start.group(0)
    depth, tags = 1, re.compile(r"<(/?)%s(?=[\s/>])[^<>]*?(/?)>" % re.escape(start.group(1)))
    for tag in tags.finditer(xml, start.end()):
        if tag.group(1):
            depth -= 1
        elif not tag.group(2):
            depth += 1
        if depth == 0:
            return xml[start.start():tag.end()]
    return ""


def is_safety(xml):
    """True for a warning, danger or caution note and for a hazard statement."""
    tag = re.match(r"<([A-Za-z_][\w.-]*)([^>]*)>", xml or "")
    if not tag:
        return False
    kind = re.search(r'\stype\s*=\s*["\']([^"\']*)["\']', tag.group(2))
    return tag.group(1) == "hazardstatement" or (tag.group(1) == "note" and bool(kind) and kind.group(1) in SAFETY_NOTE_TYPES)


def anchor(old_xml, element_id, ids_now):
    """Where the piece goes back: after or before a neighbour that still exists, else at the end
    of its parent. {"after": id} | {"before": id} | {"into": id} | {"into_tag": tag}."""
    try:
        tree = ET.fromstring(re.sub(r"<!DOCTYPE[^>\[]*(\[[^\]]*\])?[^>]*>", "", old_xml, count=1))
    except ET.ParseError:
        return None
    for parent in tree.iter():
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
        if parent.get("id") in ids_now or parent is tree:
            return {"into": parent.get("id")} if parent.get("id") else {"into_tag": refcheck.local(parent.tag)}
        return {"into_tag": refcheck.local(parent.tag)}
    return None


def without_id(xml):
    """The element as plain content of a topic: without the id it had in the shared file."""
    return re.sub(r'^(<[A-Za-z_][\w.-]*[^>]*?)\sid\s*=\s*(["\'])[^"\']*\2', r"\1", xml, count=1)


def target_of(repo, ref):
    """(file, element id, renamed key) a broken reference points at; file is None when the target
    is not an element. renamed key: the key's name today, when version history shows that the key
    of the reference was renamed as well; the reference then has to follow it."""
    if ref["attribute"] in refcheck.PATH_ATTRS:
        target, _topic, element_id = repo.split_target(ref)
        return (target, element_id, None) if element_id else (None, None, None)
    import refheal
    key, _, element_id = ref["value"].partition("/")
    renamed = None
    if key not in repo.keys:
        found = refheal.renamed_key(repo, key)
        renamed = found[0] if found else None
    definition = repo.definition_of(renamed or key)
    if definition and definition["target"] and element_id:
        return definition["target"], element_id, renamed
    return None, None, None


def ways_out(repo, refs, previous_xml):
    """What can be done about references to an element that is gone.

    previous_xml: {path: [earlier versions of the file, newest first]}.
    Returns {"was", "safety", "options": [{"kind", "label", ...}]}; options is empty when the
    old piece cannot be found in an earlier version, or the target is not an element.
    """
    first = refs[0]
    target, element_id, renamed_key = target_of(repo, first)
    found = {"was": "", "safety": False, "options": [], "renamed_key": renamed_key}
    if not target or target not in repo.files:
        return found
    old_file = next((xml for xml in previous_xml.get(target, []) if element_xml(xml, element_id)), None)
    if not old_file:
        return found
    piece = element_xml(old_file, element_id)
    found.update(was=piece, safety=is_safety(piece))
    files = len({r["file"] for r in refs})
    where = anchor(old_file, element_id, {eid for (_topic, eid) in repo.files[target]["elements"]} | set(repo.files[target]["topics"]))
    if where:
        found["options"].append({
            "kind": "restore", "file": "/" + target, "xml": piece, "anchor": where,
            "label": "Put it back in %s: one edit, and all %d references work again" % (target.rsplit("/", 1)[-1], len(refs))})
    if first["attribute"] in ("conref", "conkeyref"):
        found["options"].append({
            "kind": "inline", "xml": without_id(piece),
            "label": "Keep the text in the %d topics as their own content, without the reference" % files})
        if not found["safety"]:
            found["options"].append({
                "kind": "remove", "label": "Remove the %d references from the %d topics" % (len(refs), files)})
    return found
