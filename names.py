"""The names a map gives its keys, so every card and row shows a name where a topic says it by key.

A key's name is what a reader sees where a topic writes <keyword keyref="product-name"/>: the
keyword, link text or navigation title of the key definition, or else the title of the topic it
points at. Keys in submaps and bookmaps count; a key inside a key scope is also named scope.key.
A key gone from the map in this version (renamed, say) is named from the map's earlier versions,
so a broken reference still says what it used to show.

Read with patterns, not a parser: the same way alttext.vocabulary reads 57,782 files in seconds.

    key_names(files)            {key: name}
    shown(text_with_marks, names) the text with each mark replaced by its name, or [key]
"""
import os
import re

MAP_ENDINGS = (".ditamap", ".bookmap")

# The start tag of an element that defines keys. What follows it, up to its first child reference or
# its end, holds its topicmeta: start tags never overlap, so a topicref's keys and the keys of the
# topicrefs inside it are all read.
_KEY_DEF = re.compile(r"<([\w.-]+)\b([^>]*\skeys\s*=\s*\"[^\"]+\"[^>]*?)(/?)>")
_CHILD_REF = r"<(?:topicref|keydef|mapref|topichead|topicgroup|chapter|part|appendix)\b"
_SCOPED = re.compile(r"<([\w.-]+)\b[^>]*\skeyscope\s*=\s*\"([^\"]+)\"[^>]*>(.*?)</\1>", re.S)
_TITLE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.S)
# A key in a text: what duplicates.blocks_of puts where an element says it by key and shows nothing.
MARK = re.compile(r"⟦([^⟧]+)⟧")


def _plain(xml):
    text = re.sub(r"<[^>]+>", " ", xml or "")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")
    return " ".join(text.split())


def _attribute(tag, name):
    found = re.search(r"\s%s\s*=\s*\"([^\"]*)\"" % name, tag)
    return found.group(1) if found else ""


def _titles(files):
    """The title of each topic, by its path (without the leading slash) and by its GUID."""
    titles = {}
    for entry in files:
        path = (entry.get("path") or "").lstrip("/")
        if path.endswith(MAP_ENDINGS):
            continue
        found = _TITLE.search(entry.get("xml") or "")
        if found:
            title = _plain(found.group(1))
            titles[path] = title
            if entry.get("id"):
                titles[entry["id"]] = title
    return titles


def _target_title(map_path, href, titles):
    target = href.split("#")[0]
    if not target:
        return ""
    guid = os.path.splitext(os.path.basename(target))[0]
    if guid.startswith("GUID-") and guid in titles:
        return titles[guid]
    return titles.get(os.path.normpath(os.path.join(os.path.dirname(map_path), target)), "")


def _name_of(attributes, inside, map_path, titles):
    """What a reader sees for one key definition, best first."""
    for pattern in (r"<keyword\b[^>]*>(.*?)</keyword>", r"<linktext\b[^>]*>(.*?)</linktext>", r"<navtitle\b[^>]*>(.*?)</navtitle>"):
        found = re.search(pattern, inside or "", re.S)
        if found and _plain(found.group(1)):
            return _plain(found.group(1))
    if _attribute(attributes, "navtitle"):
        return _attribute(attributes, "navtitle")
    return _target_title(map_path, _attribute(attributes, "href"), titles)


def _definitions(map_path, xml, titles, scope=""):
    """(key, name) for every key the map text defines, scope-qualified inside a key scope."""
    out = []
    for scoped in _SCOPED.finditer(xml):
        for name in scoped.group(2).split():
            out += [("%s.%s" % (name, key), named) for key, named in _definitions(map_path, scoped.group(3), titles)]
    for found in _KEY_DEF.finditer(xml):
        inside = ""
        if not found.group(3):
            rest = xml[found.end():]
            stop = re.search(r"%s|</%s\s*>" % (_CHILD_REF, re.escape(found.group(1))), rest)
            inside = rest[:stop.start()] if stop else rest
        name = _name_of(found.group(2), inside, map_path, titles)
        for key in _attribute(found.group(2), "keys").split():
            out.append((scope + key, name))
    return out


def key_names(files):
    """{key: name} for the keys of the maps in files; the first definition of a key wins, as in DITA.
    A key no map defines now, but an earlier version of a map did, gets the name it had then."""
    titles = _titles(files)
    names, earlier = {}, {}
    for entry in files:
        path = (entry.get("path") or "").lstrip("/")
        if not path.endswith(MAP_ENDINGS):
            continue
        for key, name in _definitions(path, entry.get("xml") or "", titles):
            if name:
                names.setdefault(key, name)
        for old in entry.get("previous") or []:
            for key, name in _definitions(path, old or "", titles):
                if name:
                    earlier.setdefault(key, name)
    for key, name in earlier.items():
        names.setdefault(key, name)
    return names


# An element with an id and a title right inside it: a section, a table, a figure.
_TITLED = re.compile(r"<[\w.-]+\b[^>]*\sid\s*=\s*\"([^\"]+)\"[^>]*>\s*<title\b[^>]*>(.*?)</title>", re.S)


def link_titles(files):
    """What a link with no text of its own shows: {target: title} for each topic ("a/b.dita",
    "GUID-1.dita", with "#topic-id") and each titled element in it ("a/b.dita#topic-id/element-id").
    An element gone from this version (a broken link) has the title of its earlier version."""
    out = {}
    for entry in files:
        _titles_of(entry, entry.get("xml") or "", out)
    for entry in files:
        for old in entry.get("previous") or []:
            _titles_of(entry, old or "", out)
    return out


def _titles_of(entry, xml, out):
    """Adds what entry's text (now, or an earlier version) names to out; what is there wins."""
    path = (entry.get("path") or "").lstrip("/")
    if path.endswith(MAP_ENDINGS):
        return
    root = re.search(r"<[\w.-]+\b[^>]*\sid\s*=\s*\"([^\"]+)\"", xml)
    found = _TITLE.search(xml)
    for name in [path] + (["%s.dita" % entry["id"]] if entry.get("id") else []):
        if found:
            out.setdefault(name, _plain(found.group(1)))
            if root:
                out.setdefault("%s#%s" % (name, root.group(1)), out[name])
        if root:
            for element in _TITLED.finditer(xml):
                out.setdefault("%s#%s/%s" % (name, root.group(1), element.group(1)), _plain(element.group(2)))


def _name_for(mark, names, links):
    if mark == "*":
        return "[varies]"
    if mark.startswith("@"):
        target = mark[1:]
        return links.get(target) or links.get(target.split("#")[0]) or "[%s]" % os.path.basename(target.split("#")[0])
    return names.get(mark) or "[%s]" % mark


def shown(text, names, links=None):
    """The text a reader sees: each key mark replaced by the key's name, each empty link by its
    target's title, [key] or [file] when neither is known, and [varies] where copies differ."""
    text = " ".join(MARK.sub(lambda m: _name_for(m.group(1), names, links or {}), text or "").split())
    return re.sub(r"\s+([.,;:!?)])", r"\1", text)
