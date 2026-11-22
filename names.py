"""The names a map gives its keys, so every card and row shows a name where a topic says it by key.

A key's name is what a reader sees where a topic writes <keyword keyref="product-name"/>: the
keyword, link text or navigation title of the key definition, or else the title of the topic it
points at. Keys in submaps and bookmaps count; a key inside a key scope is also named scope.key.
A key gone from the map in this version (renamed, say) is named from the map's earlier versions,
so a broken reference still says what it used to show.

Read with patterns, not a parser: the same way alttext.vocabulary reads 57,782 files in seconds.

    key_names(files)            {key: name}
    shown(text_with_marks, names) the text with each mark replaced by its name, or [key]
    spellings(files)            the names the topics write more than one way ("HX-200", "HX 200")
"""
import collections
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


# ---- one name, one spelling ------------------------------------------------------------------
# The same name written two ways ("HX-200" and "HX 200", "Admin Console" and "Admin
# console") reads as two things to a reader and to a search. The documentation's own names are the ones
# it marks up as names (keyword, tm, wintitle; not uicontrol, which is mostly keys to press, "Enter",
# and verbs, "Log in"); each is looked for in the text of every topic, outside
# code, and the spellings of one name are grouped. Measured on a customer export of 57,323 topics
# (23 Nov 2026), in about 2 s: 17 names written with other separators (a model number with a dash 251
# times and with a space 43 times in 4 topics), 6 more only in capitals.
# Counting uicontrol as well gave 17 names, nearly all keys and verbs: "Enter" and "ENTER", "Log in" and "Login".

NAME_TAGS = ("keyword", "tm", "wintitle")
_NAMED = re.compile(r"<(%s)\b[^>]*>(.*?)</\1>" % "|".join(NAME_TAGS), re.S)
# Text a reader does not read as prose: code, commands, screens; and comments.
_NOT_PROSE = re.compile(r"<!--.*?-->|<(codeblock|codeph|pre|screen|msgblock|cmdname|filepath|varname|userinput|systemoutput)\b[^>]*>.*?</\1>", re.S)
MIN_SAME = 5            # a name shorter than this, once spaces and dashes are taken out, is not compared


def _same(name):
    """The form two spellings of one name share: lower case, no spaces, dashes, dots or underscores."""
    return re.sub(r"[\s\-_./]+", "", name.lower())


def _prose(xml):
    return _plain(_NOT_PROSE.sub(" ", xml or ""))


# The parts of a name, and what may stand between two parts of one name: a space, a dash, a dot, a
# slash or an underscore, or nothing ("HX-200", "HX 200", "HX200").
_PART = re.compile(r"[^\W_]+")
_JOIN = re.compile(r"\s+|[\-_./]")
MAX_PARTS = 6


def _spans(text, wanted, starts):
    """Each run of parts in text that, without its separators and in lower case, is in wanted;
    starts holds every beginning of a wanted name, so a run stops as soon as it cannot become one."""
    parts = list(_PART.finditer(text))
    lower = [part.group(0).lower() for part in parts]
    for i, first in enumerate(parts):
        if lower[i] not in starts or (first.start() and text[first.start() - 1] == "-"):
            continue
        joined = ""
        for j in range(i, min(i + MAX_PARTS, len(parts))):
            if j > i and not _JOIN.fullmatch(text[parts[j - 1].end():parts[j].start()]):
                break
            joined += lower[j]
            if joined not in starts:
                break
            end = parts[j].end()
            if joined in wanted and not (text[end:end + 1] == "-" and text[end + 1:end + 2].isalnum()):
                yield text[first.start():end]


# Not a name: a placeholder ("1xxx-xxxx"), or a name in code ("modifyGroup", "add_user") that a
# topic writes outside <codeph>.
_PLACEHOLDER = re.compile(r"[\d\s\-]*[xX]{3,}[\dxX\s\-]*")
_CODE_NAME = re.compile(r"[a-z]{2,}[A-Z]\w*|\w+_\w+")


def spellings(files):
    """[{"id", "main", "forms": [{"form", "count", "files", "per_topic"}], "case_only", "places", "topics"}]: the names
    written more than one way, the most used spelling first; places and topics count the other
    spellings. A name the topics mark up is looked for in their text with other separators too; a
    spelling that differs only in capitals counts when it is marked up as a name as well, since in
    plain text it is often the ordinary words ("the system console"). case_only: the spellings differ
    only in capital letters ("POWER", "Power"), which may be meant."""
    topics = [entry for entry in files if not (entry.get("path") or "").endswith(MAP_ENDINGS)]
    tagged = {}
    for entry in topics:
        for found in _NAMED.finditer(entry.get("xml") or ""):
            name = _plain(found.group(2)).rstrip(".,;:")
            if len(_same(name)) >= MIN_SAME and len(name) <= 80 and not _PLACEHOLDER.fullmatch(name):
                tagged.setdefault(_same(name), set()).add(name)
    # A product name, model or code has a digit or a capital past its first letter in one of its spellings.
    tagged = {same: names for same, names in tagged.items() if any(re.search(r"\d|.[A-Z]", n) for n in names)}
    if not tagged:
        return []
    starts = {same[:n] for same in tagged for n in range(1, len(same) + 1)}
    counts, where = {}, {}
    for entry in topics:
        path = "/" + (entry.get("path") or "").lstrip("/")
        for name in _spans(_prose(entry.get("xml")), tagged, starts):
            same = _same(name)
            known = tagged.get(same)
            # Not a name the topics mark up, or the same letters in other capitals not marked up anywhere.
            if not known or (name not in known and (name.lower() in {k.lower() for k in known} or _CODE_NAME.fullmatch(name))):
                continue
            counts[name] = counts.get(name, 0) + 1
            where.setdefault(name, collections.Counter())[path] += 1
    groups = {}
    for name in counts:
        groups.setdefault(_same(name), []).append(name)
    out = []
    for names in groups.values():
        if len(names) < 2:
            continue
        # The most used first; of two used as often, the one marked up as a name.
        used = sorted(names, key=lambda n: (-counts[n], n not in tagged[_same(n)], n))
        others = used[1:]
        out.append({"main": used[0],
                    "forms": [{"form": n, "count": counts[n], "files": sorted(where[n]), "per_topic": dict(where[n])}
                              for n in used],
                    "case_only": len({n.lower() for n in used}) == 1,
                    "places": sum(counts[n] for n in others),
                    "topics": len(set().union(*(set(where[n]) for n in others)))})
    out.sort(key=lambda s: (s["case_only"], -s["places"], s["main"]))
    for index, entry in enumerate(out):
        entry["id"] = "s%d" % index
    return out


def without(spelled, written):
    """spelled (from spellings) less the spellings already written over: written holds (file, form)
    for each topic where an author made form say the name's main spelling. A name left with one
    spelling is no longer listed."""
    out = []
    for entry in spelled:
        forms = []
        for form in entry["forms"]:
            per_topic = {path: n for path, n in form["per_topic"].items() if (path, form["form"]) not in written}
            if per_topic:
                forms.append(dict(form, per_topic=per_topic, files=sorted(per_topic), count=sum(per_topic.values())))
        if len(forms) < 2:
            continue
        # The main spelling stays first; when it was itself written over, the most used one left is.
        if forms[0]["form"] != entry["main"]:
            forms.sort(key=lambda f: -f["count"])
        others = forms[1:]
        out.append(dict(entry, main=forms[0]["form"], forms=forms, places=sum(f["count"] for f in others),
                        topics=len(set().union(*(set(f["files"]) for f in others)))))
    for index, entry in enumerate(out):
        entry["id"] = "s%d" % index
    return out
