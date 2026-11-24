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
    for entry in _maps_in_key_order(files):
        path = (entry.get("path") or "").lstrip("/")
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


_HREF_TAG = re.compile(r"<[\w.-]+\b[^>]*\shref\s*=\s*\"([^\"]+)\"[^>]*>")


def _maps_in_key_order(files):
    """The maps among files in the order DITA reads key definitions (refcheck.breadth_first): a root
    map's definition of a key wins over its submap's, whatever order the files came in."""
    import refcheck
    maps = [e for e in files if (e.get("path") or "").lstrip("/").endswith(MAP_ENDINGS)]
    by_name = {}
    for entry in maps:
        path = (entry.get("path") or "").lstrip("/")
        by_name[path] = entry
        if entry.get("id"):
            by_name[entry["id"] + os.path.splitext(path)[1]] = entry
    children = {}
    for entry in maps:
        path = (entry.get("path") or "").lstrip("/")
        kids = []
        for found in _HREF_TAG.finditer(entry.get("xml") or ""):
            link = found.group(1).split("#")[0]
            submap = (_attribute(found.group(0), "format") == "ditamap" or link.lower().endswith(MAP_ENDINGS))
            if not submap or refcheck.HAS_SCHEME.match(link) or _attribute(found.group(0), "scope") == "external":
                continue
            target = by_name.get(os.path.basename(link)) if os.path.basename(link).upper().startswith("GUID-") else \
                by_name.get(os.path.normpath(os.path.join(os.path.dirname(path), link)))
            if target is not None:
                kids.append((target.get("path") or "").lstrip("/"))
        children[path] = kids
    order = refcheck.breadth_first([(e.get("path") or "").lstrip("/") for e in maps], children)
    return [by_name[path] for path in order]


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
    _reused_into(files, out)
    return out


# Inside a reused phrase, what a reader does not see in the sentence: a link's hover text, index
# entries, comments to the writers, footnotes (shown apart), data. On the OASIS source a conkeyref
# brought "universal attributes" and, with the link's <desc>, a list of 20 attribute names.
_UNSEEN = {"desc", "indexterm", "draft-comment", "fn", "data", "required-cleanup"}


def _read(el, top=False):
    """The text of an element as a reader sees it in a sentence; the tail is the caller's."""
    if not top and el.tag.rsplit("}", 1)[-1] in _UNSEEN:
        return ""
    return (el.text or "") + "".join(_read(child) + (child.tail or "") for child in el)


_REUSE = re.compile(r"\s(conref|conkeyref)\s*=\s*\"([^\"]+)\"")


def _reused_into(files, out):
    """Adds what a phrase that reuses text brings: "=<file>#<topic>/<id>" for a conref (resolved as
    duplicates._shown marks it), "=~<key>/<id>" for a conkeyref. Only the targets that are reused
    are read. On the OASIS DITA source (24 Nov 2026) 22 of 212 groups of repeated text showed
    "available on this element: , , , and keyref." where three conkeyrefs bring the names."""
    import duplicates
    import xml.etree.ElementTree as ET
    wanted = set()
    for entry in files:
        path = (entry.get("path") or "").lstrip("/")
        for kind, value in _REUSE.findall(entry.get("xml") or ""):
            wanted.add((kind, path, value))
    if not wanted:
        return
    by_path, keys = {}, {}
    for entry in files:
        path = (entry.get("path") or "").lstrip("/")
        by_path[path] = entry
        if entry.get("id"):
            by_path["%s.dita" % entry["id"]] = entry
        if path.endswith(MAP_ENDINGS):
            for found in _KEY_DEF.finditer(entry.get("xml") or ""):
                href = _attribute(found.group(2), "href").split("#")[0]
                for key in _attribute(found.group(2), "keys").split():
                    if href:
                        keys.setdefault(key, duplicates._resolved_href(path, href))
    parsed = {}

    def text_of(file, element):
        if file not in parsed:
            entry = by_path.get(file)
            try:
                parsed[file] = ET.fromstring(re.sub(r"<!DOCTYPE[^>\[]*(\[[^\]]*\])?[^>]*>", "", entry.get("xml") or "",
                                                    count=1)) if entry else None
            except ET.ParseError:
                parsed[file] = None
        root = parsed[file]
        found = next((el for el in root.iter() if el.get("id") == element), None) if root is not None and element else None
        return " ".join(_read(found, True).split()) if found is not None else ""
    for kind, path, value in wanted:
        if kind == "conref":
            mark = duplicates._resolved_href(path, value)
            file, _, fragment = mark.partition("#")
        else:
            mark = "~" + value
            key, _, fragment = value.partition("/")
            file = keys.get(key)
        text = text_of(file, fragment.split("/")[-1]) if file and fragment else ""
        if text:
            out.setdefault("=" + mark, text)


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
    if mark.startswith("="):
        return links.get(mark) or "[shared text]"
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
# (23 Nov 2026), in about 2.5 s: 16 names written with other separators (a model number with a dash 223
# times and with a space 43 times in 4 topics), 4 more only in capitals.
# Counting uicontrol as well gave 17 names, nearly all keys and verbs: "Enter" and "ENTER", "Log in" and "Login".

NAME_TAGS = ("keyword", "tm", "wintitle")
_NAMED = re.compile(r"<(%s)\b[^>]*>(.*?)</\1>" % "|".join(NAME_TAGS), re.S)
# Text a reader does not read as prose: code, commands, screens; comments, CDATA and processing
# instructions. The editor's writer leaves out the same (names_apply.ts NOT_PROSE).
_NOT_PROSE = re.compile(r"<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>|<(codeblock|codeph|pre|screen|msgblock|cmdname|filepath|varname|userinput|systemoutput|apiname|parmname|option|synph|kwd|msgph|msgnum)\b(?:[^>]*[^/>])?>.*?</\1\s*>", re.S)
MIN_SAME = 5            # a name shorter than this, once spaces and dashes are taken out, is not compared


def _same(name):
    """The form two spellings of one name share: lower case, no spaces, dashes, dots or underscores,
    except between two digits: "Atlas 1.10" and "Atlas 11.0" are two versions, not one name."""
    return re.sub(r"[\s\-_./]+", lambda m: _between(name.lower(), m), name.lower())


def _between(text, separator):
    """What a separator leaves in the shared form: itself (any space as one) between two digits, else nothing."""
    before, after = text[separator.start() - 1:separator.start()], text[separator.end():separator.end() + 1]
    return _kept(separator.group(0)) if before.isdigit() and after.isdigit() else ""


def _kept(separator):
    return " " if separator.isspace() else separator


_TAG = re.compile(r"<[^>]*>")


def _pieces(xml):
    """The prose of a topic, one piece for each run of text between two tags: a name is counted only
    where it is whole in one piece, as the editor can write it there ("<tm>POWER</tm> 8" is not)."""
    for piece in _TAG.split(_NOT_PROSE.sub("<x>", xml or "")):
        # Most pieces are white space between tags, and most hold no entity: _plain only where needed.
        if not piece.isspace() and piece:
            yield _plain(piece) if "&" in piece else " ".join(piece.split())


# The parts of a name, and what may stand between two parts of one name: a space, a dash, a dot, a
# slash or an underscore, or nothing ("HX-200", "HX 200", "HX200").
_PART = re.compile(r"[^\W_]+")
_JOIN = re.compile(r"\s+|[\-_./]")
MAX_PARTS = 6


def _joined_before(text, at):
    """A name does not start right after a dash ("A-HX 200"), nor inside a file name, path or address:
    after "_", ".", "/", "=" or "#" that follows a letter or digit ("setup_HX200", "example.com/HX200",
    "?model=HX200", "page.html#HX200")."""
    before = text[at - 1:at]
    return before == "-" or (before in ("_", ".", "/", "=", "#") and text[at - 2:at - 1].isalnum())


def _joined_after(text, at):
    """A name does not end where a dash, "_" or "." joins it to more letters or digits ("HX-200X",
    "HX200_setup.exe", "HX200.pdf"): a longer name or a file name. "HX200." ends a sentence, and
    "HX 200/CX9" is a list of models (an address is caught by its start: "example.com/HX200")."""
    return text[at:at + 1] in ("-", "_", ".") and text[at + 1:at + 2].isalnum()


def _spans(text, wanted, starts):
    """Each run of parts in text that, without its separators and in lower case, is in wanted;
    starts holds every beginning of a wanted name, so a run stops as soon as it cannot become one.
    The longest name wins: in "HX 200 Gateway" only "HX 200 Gateway" is found, not "HX 200" too."""
    parts = list(_PART.finditer(text))
    lower = [part.group(0).lower() for part in parts]
    i = 0
    while i < len(parts):
        first, best = parts[i], None
        if lower[i] in starts and not _joined_before(text, first.start()):
            joined = ""
            for j in range(i, min(i + MAX_PARTS, len(parts))):
                if j > i and not _JOIN.fullmatch(text[parts[j - 1].end():parts[j].start()]):
                    break
                if j > i and lower[j - 1][-1:].isdigit() and lower[j][:1].isdigit():
                    joined += _kept(text[parts[j - 1].end():parts[j].start()])
                joined += lower[j]
                if joined not in starts:
                    break
                end = parts[j].end()
                if joined in wanted and not _joined_after(text, end):
                    best = j
        if best is None:
            i += 1
            continue
        yield text[first.start():parts[best].end()]
        i = best + 1


# Not a name: a placeholder ("1xxx-xxxx"), or a name in code ("modifyGroup", "add_user") that a
# topic writes outside <codeph>.
_PLACEHOLDER = re.compile(r"[\d\s\-]*[xX]{3,}[\dxX\s\-]*")
_CODE_NAME = re.compile(r"[a-z]{2,}[A-Z]\w*|\w+_\w+")


def spellings(files):
    """[{"id", "main", "forms": [{"form", "count", "files", "per_topic"}], "case_only", "places", "topics", "inside"}]: the names
    written more than one way, the most used spelling first; places and topics count the other
    spellings. A name the topics mark up is looked for in their text with other separators too; a
    spelling that differs only in capitals counts when it is marked up as a name as well, since in
    plain text it is often the ordinary words ("the system console"). case_only: the spellings differ
    only in capital letters ("POWER", "Power"), which may be meant. inside: the longer names found
    that hold one of the spellings (_longer), which a write of this name must leave alone."""
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
    counts, where, seen = {}, {}, set()
    for entry in topics:
        path = "/" + (entry.get("path") or "").lstrip("/")
        for name in (found for piece in _pieces(entry.get("xml")) for found in _spans(piece, tagged, starts)):
            seen.add(name)
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
                    "topics": len(set().union(*(set(where[n]) for n in others))),
                    "inside": _longer(used, seen)})
    out.sort(key=lambda s: (s["case_only"], -s["places"], s["main"]))
    for index, entry in enumerate(out):
        entry["id"] = "s%d" % index
    return out


def _longer(forms, seen):
    """The longer names found in the text that hold one of forms ("HX 200 Gateway" for "HX 200"), as
    they are written: the place is theirs, so the editor's writer leaves them as they are."""
    patterns = [re.compile(r"(?<![^\W_])%s(?![^\W_])" % re.escape(form)) for form in forms]
    return sorted(text for text in seen if text not in forms and any(p.search(text) for p in patterns))


def without(spelled, written):
    """spelled (from spellings) after what authors wrote since: written is [(file, form, now)], in the
    order written, for each topic where an author made form say now (an author may write A over B,
    then B over A). Each topic's places count for what it says now; the spelling authors wrote most
    places with becomes the main one, as they chose it. A name left with one spelling is not listed."""
    by_file = {}
    for path, was, now in written:
        by_file.setdefault(path, []).append((was, now))
    out = []
    for entry in spelled:
        forms, moved = {}, collections.Counter()
        topics = {}
        for form in entry["forms"]:
            for path, n in form["per_topic"].items():
                topics.setdefault(path, collections.Counter())[form["form"]] += n
        for path, says in topics.items():
            for was, now in by_file.get(path, []):
                if says.get(was) and was != now:
                    moved[now] += says[was]
                    says[now] += says.pop(was)
            for name, n in says.items():
                if n:
                    forms.setdefault(name, {})[path] = n
        if len(forms) < 2:
            continue
        main = moved.most_common(1)[0][0] if moved else entry["main"]
        if main not in forms:
            main = max(forms, key=lambda name: sum(forms[name].values()))
        order = sorted(forms, key=lambda name: (name != main, -sum(forms[name].values()), name))
        listed = [{"form": name, "count": sum(forms[name].values()), "files": sorted(forms[name]),
                   "per_topic": dict(forms[name])} for name in order]
        others = listed[1:]
        out.append(dict(entry, main=order[0], forms=listed, places=sum(f["count"] for f in others),
                        topics=len(set().union(*(set(f["files"]) for f in others)))))
    for index, entry in enumerate(out):
        entry["id"] = "s%d" % index
    return out
