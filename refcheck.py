#!/usr/bin/env python3
"""Finds broken references inside a DITA repository (garage-week PoC). Stdlib only.

Covers what wiki idea 5 names: links (href), content references (conref), key references
(keyref, conkeyref) and the key definitions they depend on.

    python3 refcheck.py <folder>

A reference is reported with the reason it is broken:

    file-missing        the file it points to does not exist
    topic-missing       the file exists, the topic id does not
    element-missing     the topic exists, the element id does not
    key-undefined       no map defines the key
    key-target-missing  the key is defined, but its target file does not exist
    type-mismatch       a conref points at an element of another type
"""
import json
import os
import re
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET

TOPIC_TAGS = {"topic", "concept", "task", "reference", "glossentry", "glossgroup", "troubleshooting",
              "dita", "learningContent", "learningOverview", "learningSummary", "learningAssessment",
              "learningPlan", "generalTask"}
SKIP_DIRS = {"node_modules", "out", "build", "target", "temp"}
BLOCK_TAGS = {"p", "li", "note", "cmd", "info", "entry", "shortdesc", "dd", "section", "stepresult", "context",
              "title", "topicmeta", "linktext"}
HAS_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
# Attributes whose value is "file#topic/element". conrefend closes a conref range and must exist too.
PATH_ATTRS = ("href", "conref", "conrefend")
CONTENT_ATTRS = ("conref", "conrefend", "conkeyref")
# The attributes a DITAVAL filter or a condition preset decides publishing on.
CONDITION_ATTRS = ("audience", "platform", "product", "props", "otherprops", "deliveryTarget")


def conditions_of(el):
    return {name: " ".join(el.get(name).split()) for name in CONDITION_ATTRS if (el.get(name) or "").strip()}


def local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


# Elements that sit inside a line of text. Every other element starts and ends a block, and a
# reader sees a break there: a section's title and its first paragraph are two things.
INLINE = {"ph", "b", "i", "u", "sup", "sub", "tt", "line-through", "overline", "codeph", "keyword", "term", "xref",
          "uicontrol", "wintitle", "menucascade", "filepath", "varname", "cmdname", "option", "parmname", "apiname",
          "userinput", "systemoutput", "q", "cite", "text", "tm", "abbreviated-form", "state", "msgph", "msgnum",
          "synph", "shortcut", "indexterm", "fn"}


def text_of(el, limit=200):
    """The text a reader sees in an element, on one line. Blocks are kept apart by a space: the
    text used to be joined as it stands in the file, which ran a title into the paragraph after
    it ("Storage limitsA bucket can hold ...")."""
    parts = []

    def walk(node):
        parts.append(node.text or "")
        for child in node:
            block = local(child.tag) not in INLINE
            if block:
                parts.append(" ")
            walk(child)
            if block:
                parts.append(" ")
            parts.append(child.tail or "")

    walk(el)
    return re.sub(r"\s+", " ", "".join(parts)).strip()[:limit]


def parse(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            raw = handle.read()
        return raw, ET.fromstring(re.sub(r"<!DOCTYPE[^>\[]*(\[[^\]]*\])?[^>]*>", "", raw, count=1))
    except (ET.ParseError, OSError):
        return None, None


def is_dita(tree):
    """A topic or a map. Other XML that happens to sit in the folder is not scanned for references."""
    name = local(tree.tag)
    return name in TOPIC_TAGS or name.endswith("map") or tree.get("id") is not None and tree.find("title") is not None


def is_dita_path(path):
    return path.lower().endswith((".dita", ".ditamap", ".xml"))


class Repo:
    """Everything a reference can point at: files, topic ids, element ids and keys."""

    def __init__(self, root=None, files=None, assets=None, missing=None):
        """From a folder on disk, or from files handed over by a repository server.

        files is a list of {"path", "xml", "id"}. In AEM Guides a reference is stored as the
        target's GUID file name ("GUID-1234.dita"), so each id becomes an alias for its path and
        repairs are written back in the same form.
        """
        self.root = os.path.abspath(root) if root else None
        self.files = {}      # rel path -> {"title", "tag", "topics": {id: tag}, "elements": {(topic, id): {...}}}
        self.keys = {}       # key name -> {"target": rel path or None, "href", "keyword", "defined_in", "external"}
        self.refs = []
        # path -> the condition attributes on each topicref to it and on that topicref's ancestors, one
        # list per place a map includes the file. An output publishes the file if one of them passes.
        self.map_conditions = {}
        self.other_files = set()
        # Paths of files that are not DITA (images, PDFs, code) and exist in the repository, when the
        # server handed them over. None: not told, so such a target cannot be checked here.
        # An entry is a path, or {"path", "id"}: AEM Guides stores an image reference as the image's
        # GUID file name too ("GUID-1234.png"), so the id becomes an alias like a DITA file's.
        # missing: {stored name: path} for references whose target is gone; the repository still
        # knows which path the stored name stood for, and that path is what a repair is found by.
        self.assets = None if assets is None else set()
        self.alias = {}      # stored file name -> path
        self.submap_links = []  # (submap path, key scopes it is brought in under), see _scope_submap_keys
        self.previous = {}   # path -> earlier versions of the file, newest first, indexed like self.files
        self.stored_name = {}  # path -> stored file name
        for asset in assets or ():
            path = ((asset.get("path") if isinstance(asset, dict) else asset) or "").lstrip("/")
            guid = asset.get("id") if isinstance(asset, dict) else None
            if not path:
                continue
            self.assets.add(path)
            if guid and guid.upper().startswith("GUID-"):
                name = guid if "." in guid else guid + os.path.splitext(path)[1]
                self.alias[name] = path
                self.stored_name[path] = name
        for name, path in (missing or {}).items():
            if name and path:
                self.alias.setdefault(os.path.basename(name), path.lstrip("/"))
        if files is None:
            self._load()
        else:
            self._load_files(files)

    def _load_files(self, files):
        parsed = {}
        # Every stored name first: a file, or an earlier version of it, may point at any other file.
        for entry in files:
            path = (entry.get("path") or "").lstrip("/")
            guid = entry.get("id")
            if path and guid and guid.upper().startswith("GUID-"):
                name = guid + os.path.splitext(path)[1]
                self.alias[name] = path
                self.stored_name[path] = name
        for entry in files:
            path = (entry.get("path") or "").lstrip("/")
            raw = entry.get("xml") or ""
            if not path:
                continue
            try:
                tree = ET.fromstring(re.sub(r"<!DOCTYPE[^>\[]*(\[[^\]]*\])?[^>]*>", "", raw, count=1))
            except ET.ParseError:
                self.other_files.add(path)
                continue
            if is_dita(tree):
                parsed[path] = (raw, tree)
                self._remember_versions(path, raw, entry.get("previous") or [])
            else:
                self.other_files.add(path)
        for rel, (raw, tree) in parsed.items():
            self._index(rel, tree)
        for rel, (raw, tree) in parsed.items():
            self._collect_keys(rel, tree)
        self._scope_submap_keys()
        for rel, (raw, tree) in parsed.items():
            self._collect_refs(rel, raw, tree)

    def _remember_versions(self, path, raw, versions):
        """Earlier versions of a file, as the repository's version store holds them."""
        for old in versions[:5]:
            if not old or old == raw:
                continue
            try:
                tree = ET.fromstring(re.sub(r"<!DOCTYPE[^>\[]*(\[[^\]]*\])?[^>]*>", "", old, count=1))
            except ET.ParseError:
                continue
            current_files, current_keys, current_links = self.files, self.keys, self.submap_links
            self.files, self.keys, self.submap_links = {}, {}, []
            try:
                self._index(path, tree)
                self._collect_keys(path, tree)
                self.previous.setdefault(path, []).append(dict(self.files[path], keys=self.keys))
            finally:
                self.files, self.keys, self.submap_links = current_files, current_keys, current_links

    def resolve_path(self, from_file, href_path):
        """The repository path an href's file part points at."""
        name = os.path.basename(href_path)
        if name in self.alias:
            return self.alias[name]
        # An href is a URI: "my%20topic.dita" names the file "my topic.dita".
        return os.path.normpath(os.path.join(os.path.dirname(from_file), urllib.parse.unquote(href_path)))

    def _load(self):
        parsed = {}
        for folder, dirs, names in os.walk(self.root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS]
            for name in sorted(names):
                rel = os.path.relpath(os.path.join(folder, name), self.root)
                if name.lower().endswith((".dita", ".ditamap", ".xml")):
                    raw, tree = parse(os.path.join(folder, name))
                    if tree is not None and is_dita(tree):
                        parsed[rel] = (raw, tree)
                        continue
                self.other_files.add(rel)
        for rel, (raw, tree) in parsed.items():
            self._index(rel, tree)
        for rel, (raw, tree) in parsed.items():
            self._collect_keys(rel, tree)
        self._scope_submap_keys()
        for rel, (raw, tree) in parsed.items():
            self._collect_refs(rel, raw, tree)

    def _index(self, rel, tree):
        # copies: {(topic id, element id): how many elements carry it}, for ids used more than once
        # in a topic. A reference to such an id lands on the first element, so that is the one indexed.
        entry = {"title": "", "tag": local(tree.tag), "topics": {}, "elements": {}, "copies": {}}
        title = next((e for e in tree.iter() if local(e.tag) in ("title", "glossterm")), None)
        entry["title"] = text_of(title) if title is not None else ""

        def walk(el, topic_id):
            name = local(el.tag)
            el_id = el.get("id")
            is_topic = name in TOPIC_TAGS or (el is tree and not name.endswith("map"))
            if is_topic and el_id:
                entry["topics"][el_id] = name
                topic_id = el_id
            elif el_id and (topic_id, el_id) in entry["elements"]:
                entry["copies"][(topic_id, el_id)] = entry["copies"].get((topic_id, el_id), 1) + 1
            elif el_id:
                entry["elements"][(topic_id, el_id)] = {"tag": name, "text": text_of(el, 90),
                                                        "content": text_of(el, 100000)}
            for child in el:
                walk(child, topic_id)

        walk(tree, None)
        self.files[rel] = entry

    def _collect_keys(self, rel, tree):
        if not rel.endswith(".ditamap"):
            return

        def walk(el, scopes):
            own = (el.get("keyscope") or "").split()
            if own:
                scopes = scopes + [own[0]]
            link = el.get("href") or ""
            if (el is not tree and link and not HAS_SCHEME.match(link) and el.get("scope") != "external"
                    and (el.get("format") == "ditamap" or link.split("#")[0].lower().endswith(".ditamap"))):
                # A submap: its keys also live in the scopes of the element that brings it in.
                self.submap_links.append((self.resolve_path(rel, link.split("#")[0]), list(scopes)))
            names = el.get("keys")
            if names:
                href = el.get("href")
                external = el.get("scope") == "external" or bool(href and HAS_SCHEME.match(href))
                target = self.resolve_path(rel, href.split("#")[0]) if href and not external else None
                keyword = next((text_of(k) for k in el.iter() if local(k.tag) in ("keyword", "linktext")), "")
                # AEM Guides reads keys="a b" as one key named "a b" (seen 14 Nov 2026), so behind AEM
                # the scan does the same: a repair that only works by the DITA rule would not hold there.
                for name in ([names.strip()] if self.alias else names.split()):
                    # A key inside key scopes "a" and "b" can be named "key" in that scope, "b.key"
                    # one level up and "a.b.key" at the top. Which scope a referencing topic sits in
                    # is not worked out, so every one of these names counts as defined.
                    for depth in range(len(scopes), -1, -1):
                        # The first definition wins in DITA; keep it.
                        self.keys.setdefault(".".join(scopes[depth:] + [name]), {
                            "target": target, "href": href, "keyword": keyword, "defined_in": rel,
                            "keyref": (el.get("keyref") or "").strip().partition("/")[0],
                            "external": external, "element": local(el.tag), "names": names})
            for child in el:
                walk(child, scopes)

        walk(tree, [])

    def _scope_submap_keys(self):
        """Gives the keys of a submap the names they have where it is brought in: a mapref with
        keyscope="admin" makes the submap's key "settings" also "admin.settings". DITA's first
        definition still wins, so a key the parent map defines itself keeps its definition."""
        for target, scopes in self.submap_links:
            if not scopes:
                continue
            own = [(name, d) for name, d in list(self.keys.items()) if d.get("defined_in") == target]
            for name, definition in own:
                for depth in range(len(scopes) - 1, -1, -1):
                    self.keys.setdefault(".".join(scopes[depth:] + [name]), definition)

    def _collect_refs(self, rel, raw, tree):
        lines = raw.splitlines()
        places, seen = {}, {}

        def line_of(attr, value):
            """The line of this reference itself: the nth attr="value" of the file for its nth
            reference (elements are read in the order they are written). The first line that had the
            value anywhere was taken before: 378 of 2,343 references of the DITA-OT docs and 738 of
            3,726 of the OASIS source got another line (24 Nov 2026), "markdown" the line of a
            <codeph>markdown</codeph>."""
            if (attr, value) not in places:
                pattern = r"(?<![\w:.-])%s\s*=\s*([\"'])\s*%s\s*\1" % (re.escape(attr), re.escape(value))
                places[(attr, value)] = [raw.count("\n", 0, m.start()) + 1 for m in re.finditer(pattern, raw)]
            n = seen.get((attr, value), 0)
            seen[(attr, value)] = n + 1
            found = places[(attr, value)]
            if n < len(found):
                return found[n]
            return next((i + 1 for i, text in enumerate(lines) if value in text), 0)

        in_map = rel.endswith(".ditamap")

        def walk(el, location, block, topic_id, conditions=()):
            counts = {}
            for child in el:
                name = local(child.tag)
                if not name:
                    continue
                counts[name] = counts.get(name, 0) + 1
                child_location = "%s/%s[%d]" % (location, name, counts[name])
                child_block = child if name in BLOCK_TAGS else block
                child_topic = child.get("id") if (name in TOPIC_TAGS and child.get("id")) else topic_id
                own = conditions_of(child)
                child_conditions = conditions + ((own,) if own else ())
                if in_map and child.get("href") and not HAS_SCHEME.match(child.get("href")):
                    target = self.resolve_path(rel, child.get("href").split("#")[0])
                    self.map_conditions.setdefault(target, []).append(list(child_conditions))
                for attr in ("href", "conref", "conrefend", "keyref", "conkeyref"):
                    value = (child.get(attr) or "").strip()
                    if not value:
                        continue
                    if attr == "href" and (child.get("scope") in ("external", "peer") or HAS_SCHEME.match(value)):
                        continue
                    self.refs.append({
                        "file": rel, "line": line_of(attr, value), "location": child_location, "element": name,
                        "attribute": attr, "value": value, "format": child.get("format"),
                        "link_text": text_of(child, 120),
                        "context": text_of(child_block, 300) if child_block is not None else "",
                        "topic_title": self.files[rel]["title"], "in_topic": child_topic,
                        # Condition attributes on the element and on its ancestors, outermost first.
                        "conditions": list(child_conditions),
                        # DITA uses href when the key of a keyref is not defined, and conref for a conkeyref.
                        "fallback": (child.get({"keyref": "href", "conkeyref": "conref"}.get(attr, "")) or "").strip(),
                        # A conrefend beside a conkeyref: the key names its file and topic (DITA 1.3).
                        "with_key": (child.get("conkeyref") or "").strip() if attr == "conrefend" else "",
                    })
                walk(child, child_location, child_block, child_topic, child_conditions)

        root_topic = tree.get("id") if local(tree.tag) in TOPIC_TAGS else None
        root_conditions = conditions_of(tree)
        walk(tree, "/%s[1]" % local(tree.tag), None, root_topic, (root_conditions,) if root_conditions else ())

    # ---- resolving ------------------------------------------------------------------------

    def split_target(self, ref):
        """(target file, topic id, element id) for an href or conref value."""
        value = ref["value"]
        path, _, fragment = value.partition("#")
        target = self.resolve_path(ref["file"], path) if path else ref["file"]
        topic_id, _, element_id = fragment.partition("/")
        if topic_id == ".":
            # "#./id" is DITA shorthand for "an element in the topic I am in".
            topic_id = ref.get("in_topic")
        return target, topic_id or None, element_id or None

    def check_address(self, target, topic_id, element_id, element_tag=None):
        """None when the address exists, else the reason it is broken."""
        if target not in self.files:
            return None if (target in self.other_files and not topic_id) else "file-missing"
        entry = self.files[target]
        if topic_id and topic_id not in entry["topics"]:
            # In a map, "#id" addresses an element directly.
            if (None, topic_id) in entry["elements"] and not element_id:
                return None
            return "topic-missing"
        if element_id:
            found = entry["elements"].get((topic_id, element_id))
            if not found:
                return "element-missing"
            if element_tag and found["tag"] != element_tag:
                return "type-mismatch"
        return None

    def check(self, ref):
        """None when the reference resolves, else the reason it is broken."""
        attr = ref["attribute"]
        if attr == "conrefend" and ref.get("with_key"):
            # <dlentry conkeyref="components/install" conrefend="default.dita#ID/version">: the key's
            # target replaces "default.dita#ID", so only the element is looked for there. Read as a
            # file, it was "file missing" twice in the DITA-OT docs, where both ends exist. A key that
            # is not defined or a target that is missing is the conkeyref's own finding.
            key = ref["with_key"].partition("/")[0]
            element_id = ref["value"].split("#")[-1].split("/")[-1]
            reason = self.check(dict(ref, attribute="conkeyref", value="%s/%s" % (key, element_id), with_key="", fallback=""))
            return reason if reason in ("element-missing", "type-mismatch") else None
        if attr in ("keyref", "conkeyref"):
            key, _, element_id = ref["value"].partition("/")
            definition = self.definition_of(key)
            if definition is None:
                return None if self._fallback_works(ref) else "key-undefined"
            if definition["external"] or not definition["target"]:
                return None
            if definition["target"] not in self.files:
                if is_dita_path(definition["target"]) and definition["target"] not in self.other_files:
                    return "key-target-missing"
                # A key for an image or another asset: broken only when it is known to be missing.
                return "key-target-missing" if self.asset_exists(definition["target"]) is False else None
            if element_id:
                entry = self.files[definition["target"]]
                matches = [v for (topic, eid), v in entry["elements"].items() if eid == element_id]
                if not matches:
                    return "element-missing"
                if attr == "conkeyref" and all(m["tag"] != ref["element"] for m in matches):
                    return "type-mismatch"
            return None
        target, topic_id, element_id = self.split_target(ref)
        if ref["element"] == "coderef":
            # A coderef fragment is a line range in a code file, not an id.
            return "file-missing" if self.asset_exists(target) is False else None
        if attr == "href":
            is_dita = (ref.get("format") in (None, "dita", "ditamap")
                       and target.lower().endswith((".dita", ".ditamap", ".xml")))
            if not is_dita:
                # None: only DITA files were handed over; other assets cannot be checked here.
                return "file-missing" if self.asset_exists(target) is False else None
            return self.check_address(target, topic_id, element_id)
        return self.check_address(target, topic_id, element_id, ref["element"])

    def copies_at(self, ref, value):
        """How many elements carry the id that ref would point at with this value, when more than
        one does in that topic; 0 otherwise. Such a reference lands on the first of them."""
        if ref["attribute"] in ("keyref", "conkeyref"):
            key, _, element_id = value.partition("/")
            definition = self.definition_of(key)
            target, topic_id = (definition or {}).get("target"), None
        else:
            target, topic_id, element_id = self.split_target(dict(ref, value=value))
        copies = (self.files.get(target) or {}).get("copies") or {}
        return max([count for (topic, eid), count in copies.items()
                    if eid == element_id and topic_id in (None, topic)] or [0]) if element_id else 0

    def asset_exists(self, target):
        """True or False for a file that is not DITA; None when this cannot be told (the server
        handed over DITA files only and no list of the other assets)."""
        if target in self.files or target in self.other_files or (self.assets is not None and target in self.assets):
            return True
        if self.root is not None:
            return os.path.exists(os.path.join(self.root, target))
        return None if self.assets is None else False

    def definition_of(self, key):
        """The definition a key ends at. A key may be defined by pointing at another key."""
        definition = self.keys.get(key)
        for _ in range(8):
            if not definition or definition["target"] or definition["external"] or not definition.get("keyref"):
                return definition
            following = self.keys.get(definition["keyref"])
            if following is None:
                return definition
            definition = following
        return definition

    def _fallback_works(self, ref):
        """True when the reference has an href (for a keyref) or a conref (for a conkeyref) beside
        its key and that one resolves: the output is then not broken, only the key is unused."""
        value = ref.get("fallback")
        if not value or HAS_SCHEME.match(value):
            return bool(value)
        return self.check(dict(ref, attribute="href" if ref["attribute"] == "keyref" else "conref", value=value,
                               fallback="")) is None

    def missing_target(self, ref):
        """The file a broken reference needs, when the reason is that a file is not there."""
        if ref["attribute"] in ("keyref", "conkeyref"):
            definition = self.definition_of(ref["value"].partition("/")[0])
            return definition["target"] if definition else None
        return self.split_target(ref)[0]

    def git_ignored(self, paths):
        """Paths that git ignores: files a build generates, so their absence is not a broken reference."""
        # git refuses the whole batch if one path lies outside the repository.
        paths = sorted({p for p in paths if p and not p.startswith("..") and not os.path.isabs(p)})
        if not paths or self.root is None:
            return set()
        try:
            proc = subprocess.run(["git", "-C", self.root, "check-ignore", "--stdin"], input="\n".join(paths),
                                  capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return set()
        return set(proc.stdout.split("\n")) if proc.returncode in (0, 1) else set()

    def broken(self):
        """Broken references. Those whose target is a build-generated file get generated=True."""
        out = []
        for ref in self.refs:
            reason = self.check(ref)
            if reason:
                out.append(dict(ref, reason=reason, generated=False))
        candidates = {id(r): self.missing_target(r) for r in out if r["reason"] in ("file-missing", "key-target-missing")}
        ignored = self.git_ignored(candidates.values())
        for ref in out:
            ref["generated"] = candidates.get(id(ref)) in ignored
        return out

    # ---- building a reference value -------------------------------------------------------

    def compose(self, ref, target=None, topic_id=None, element_id=None, key=None):
        """The attribute value that points ref at the given target."""
        if ref["attribute"] in ("keyref", "conkeyref"):
            return key + ("/" + element_id if element_id else "")
        same_file = target == ref["file"]
        if same_file:
            path = ""
        elif target in self.stored_name:
            path = self.stored_name[target]
        else:
            path = os.path.relpath(target, os.path.dirname(ref["file"]) or ".").replace(os.sep, "/")
        fragment = ""
        if topic_id:
            fragment = "#" + topic_id + ("/" + element_id if element_id else "")
        return path + fragment


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    repo = Repo(sys.argv[1])
    found = repo.broken()
    generated = sum(1 for r in found if r["generated"])
    broken = [r for r in found if not r["generated"]]
    by_reason, by_attr = {}, {}
    for ref in repo.refs:
        by_attr[ref["attribute"]] = by_attr.get(ref["attribute"], 0) + 1
    for ref in broken:
        by_reason[ref["reason"]] = by_reason.get(ref["reason"], 0) + 1
        print("%-18s %-9s %-52s %s:%d" % (ref["reason"], ref["attribute"], ref["value"][:52], ref["file"], ref["line"]))
    print(json.dumps({"files": len(repo.files), "keys": len(repo.keys), "references": by_attr,
                      "broken": len(broken), "by_reason": by_reason,
                      "not_counted_target_is_build_generated": generated}))


if __name__ == "__main__":
    main()
