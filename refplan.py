#!/usr/bin/env python3
"""A planner agent that repairs the broken references of a whole map (garage-week PoC).

refheal.py settles one broken reference at a time in a fixed order. Here an agent is given the
whole job and decides how to do it:

    planner agent
      overview            what is broken, grouped by target, with what code already proved
      investigate         hands groups to finder agents; a reviewer agent checks each answer
      decide              per group: repair the references, repair at the source, ask the
                          author, or leave it broken
      apply_and_recheck   applies its decisions to a copy of the files and scans again;
                          what is still broken becomes the next round
      finish              a summary for the author

The planner cannot write to the repository. It works on a copy held in memory; the result is a
list of edits that a person applies ("Fix all") or not. Code checks every decision: a repair
must have passed the reviewer, and an edit at the source must not break a reference that works.
If the planner fails or stops early, the remaining groups get the cautious default.
"""
import collections
import concurrent.futures
import hashlib
import json
import os
import re
import threading
import time

import agentloop
import alttext
import duplicates
import names
import refcheck
import refheal
import subjectscheme
import usage
import wayout

# What the planner learned from authors, kept between checks:
#   answers   {"attribute|old value": new value}   a repair an author accepted; not asked about again
#   rejected  {"attribute|old value": [values]}    targets an author passed over, or that AEM kept
#                                                  reporting as broken after they were applied
#   renames   [{"kind", "old", "new", ...}]        the rename behind an accepted answer, so that the
#                                                  same old target reached through another attribute
#                                                  or file needs no second question
#   by_map    {map path: {"attribute|old value": new value}}   the map each answer was given for. An answer
#                                                  is applied without asking only in its own map; in another
#                                                  map it is a suggestion to review. 24 Nov 2026: an answer
#                                                  given for one team's map was applied without asking in
#                                                  another team's map that used the same shared keys.
MEMORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "author-answers.json")
# What the editor applied with the last "Fix all", so the next check can see what became of it.
APPLIED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "last-fix-all.json")


def _memory(data):
    """The stored memory in today's form. The first version was a flat {"attribute|old": new}."""
    data = data if isinstance(data, dict) else {}
    if not any(key in data for key in ("answers", "rejected", "renames", "no_source_edit")):
        data = {"answers": {k: v for k, v in data.items() if isinstance(v, str)}}
    data.setdefault("answers", {})
    data.setdefault("rejected", {})
    data.setdefault("renames", [])
    data.setdefault("by_map", {})
    data.setdefault("no_source_edit", [])   # "keys" / "id": edits at the source that did not hold in the repository
    return data


def _read(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


# The sidecar answers several requests at once (two maps checked side by side, an author's answer
# during a check). Everything that reads a stored file, changes it and writes it back does so
# under this lock, so one request does not write over what another has just stored.
_LOCK = threading.RLock()


def _write(path, data):
    """Writes the whole file or nothing: a reader never sees a half-written file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = "%s.%d.%d.tmp" % (path, os.getpid(), threading.get_ident())
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1, ensure_ascii=False)
    os.replace(temporary, path)


def applied_path(map_path=None):
    """Where the record of the last "Fix all" of a map is kept: one file per map, so the check of
    one map neither reads nor clears what was applied in another."""
    if not map_path:
        return APPLIED_PATH
    name = hashlib.sha1(map_path.encode("utf-8")).hexdigest()[:12]
    return APPLIED_PATH[:-len(".json")] + "-" + name + ".json"


def merge_cache(path, started_with, now):
    """Stores what one check added to the findings and decisions, on top of what is in the file
    now: another check may have stored its own in the meantime. Returns what was written."""
    with _LOCK:
        stored = _read(path)
        stored = stored if isinstance(stored, dict) else {}
        stored.update({key: value for key, value in now.items() if started_with.get(key) != value})
        _write(path, stored)
        return stored


def load_memory(path=None):
    return _memory(_read(path or MEMORY_PATH))


def _renames(attribute, old, new):
    """What was renamed, read off an accepted answer. A rename is tied to the file or key it
    happened in; an element id reached through a key is not, and counts as a weaker hint."""
    source = "%s|%s" % (attribute, old)
    if attribute in ("keyref", "conkeyref"):
        old_key, _, old_id = old.partition("/")
        new_key, _, new_id = new.partition("/")
        found = [{"kind": "key", "old": old_key, "new": new_key}] if old_key != new_key else []
        if old_id and new_id and old_id != new_id:
            found.append({"kind": "element", "old": old_id, "new": new_id})
    else:
        old_file, _, old_part = old.partition("#")
        new_file, _, new_part = new.partition("#")
        if old_file == new_file:
            found = [{"kind": "fragment", "file": old_file, "old": old_part, "new": new_part}]
        elif old_part == new_part:
            found = [{"kind": "file", "old": old_file, "new": new_file}]
        else:
            found = [{"kind": "address", "old": old, "new": new}]
    return [dict(entry, source=source) for entry in found]


def learned(memory, attribute, value, map_path=None):
    """(new value, exact) from the renames authors accepted, or None. exact is False when the hint
    is an element id that was renamed behind some key (it may be another file's element), or a
    rename accepted in another map than map_path."""
    exact, new = True, value
    if any(r.get("map") != map_path for r in memory["renames"] if _uses(r, attribute, value)):
        exact = False
    if attribute in ("keyref", "conkeyref"):
        key, _, element_id = value.partition("/")
        for rename in memory["renames"]:
            if rename["kind"] == "key" and rename["old"] == key:
                key = rename["new"]
            elif rename["kind"] == "element" and element_id and rename["old"] == element_id:
                element_id, exact = rename["new"], False
        new = key + ("/" + element_id if element_id else "")
    else:
        file_part, _, fragment = value.partition("#")
        for rename in memory["renames"]:
            if rename["kind"] == "fragment" and rename["file"] == file_part and rename["old"] == fragment:
                fragment = rename["new"]
            elif rename["kind"] == "file" and rename["old"] == file_part:
                file_part = rename["new"]
            elif rename["kind"] == "address" and rename["old"] == value:
                file_part, _, fragment = rename["new"].partition("#")
        new = file_part + ("#" + fragment if fragment else "")
    return (new, exact) if new != value else None


def _uses(rename, attribute, value):
    """Whether learned() could follow this rename for attribute="value"."""
    if attribute in ("keyref", "conkeyref"):
        key, _, element_id = value.partition("/")
        return (rename["kind"] == "key" and rename["old"] == key) or (
            rename["kind"] == "element" and bool(element_id) and rename["old"] == element_id)
    file_part = value.partition("#")[0]
    return rename.get("old") in (value, file_part) or rename.get("file") == file_part


def remember(attribute, old, new, path=None, rejected=None, map_path=None):
    """Records that an author accepted the repair old -> new in map_path, and which other candidates
    they passed over. Returns how many answers are stored."""
    if not all(isinstance(v, str) and v.strip() for v in (attribute, old, new)) or old == new:
        raise ValueError("attribute, old and new must be different, non-empty strings")
    path = path or MEMORY_PATH
    with _LOCK:
        memory, key = load_memory(path), "%s|%s" % (attribute, old)
        memory["answers"][key] = new
        if map_path:
            memory["by_map"].setdefault(map_path, {})[key] = new
        memory["renames"] = [r for r in memory["renames"] if r.get("source") != key] + [
            dict(r, map=map_path or "") for r in _renames(attribute, old, new)]
        declined = [v for v in (rejected or []) if isinstance(v, str) and v and v != new]
        kept = [v for v in memory["rejected"].get(key, []) if v != new]
        if kept or declined:
            memory["rejected"][key] = list(dict.fromkeys(kept + declined))
        else:
            memory["rejected"].pop(key, None)
        _write(path, memory)
        return len(memory["answers"])


def reject(attribute, old, new, path=None):
    """Records that old -> new is not the repair: an author said so, or AEM kept reporting it."""
    path = path or MEMORY_PATH
    with _LOCK:
        memory, key = load_memory(path), "%s|%s" % (attribute, old)
        if memory["answers"].get(key) == new:
            forget(attribute, old, path)
            memory = load_memory(path)
        memory["rejected"][key] = list(dict.fromkeys(memory["rejected"].get(key, []) + [new]))
        _write(path, memory)


def forget(attribute, old, path=None):
    """Drops an accepted answer and what was learned from it. Returns whether there was one."""
    path = path or MEMORY_PATH
    with _LOCK:
        memory, key = load_memory(path), "%s|%s" % (attribute, old)
        had = memory["answers"].pop(key, None) is not None
        for answers in memory["by_map"].values():
            had = answers.pop(key, None) is not None or had
        memory["renames"] = [r for r in memory["renames"] if r.get("source") != key]
        _write(path, memory)
        return had


def record_applied(edits, failed=None, path=None, map_path=None):
    """What "Fix all" wrote in one map, for that map's next check: [{"file", "attribute", "old", "new"}]."""
    kept = [{k: e[k] for k in ("file", "attribute", "old", "new")} for e in edits or []
            if isinstance(e, dict) and all(isinstance(e.get(k), str) and e.get(k) for k in ("file", "attribute", "old", "new"))]
    _write(path or applied_path(map_path), {"when": time.time(), "checks": 0, "edits": kept,
                                  "failed": [f for f in failed or [] if isinstance(f, str)]})
    return len(kept)


# How long after "Fix all" the repository may still list a repaired reference before the planner
# concludes the repair did not hold. Measured on 14 Nov 2026: after keys were renamed back in a map,
# AEM listed the 198 references to them for more than ten minutes, then dropped them by itself.
SETTLE_SECONDS = 1800
# What finder and reviewer agents concluded, kept between checks so that a check after "Fix all", or
# the next morning, does not pay for the same search again. An entry is used only while the broken
# target, what it used to show and the file (or the maps) it lives in are all unchanged.
CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "agent-findings.json")
CACHE_DAYS = 7
# How many broken targets finder agents look at in one check. One agent per target is about two
# minutes for 15 targets and was 47 minutes for 388; past this number the targets with the most
# references go first and the rest wait for the next check.
MAX_GROUPS = int(os.environ.get("REFHEAL_MAX_GROUPS", "40"))
# What one check may spend, in fresh-input-token terms (usage.cost_since: cached input a tenth, output
# five times), all agents. When it is reached, the finder agents
# that have not started yet do not start; their targets wait for the next check, the biggest first.
# 0: no limit. A first check took about 7,000 tokens per broken target, so the default lets
# about 40 targets through, as MAX_GROUPS does.
TOKEN_BUDGET = int(os.environ.get("REFHEAL_TOKEN_BUDGET", "300000"))
# Broken targets that nothing in the files names (a GUID file name, no link text, nothing in a previous
# version) are not sent to finder agents unless this is set: on a customer export (20 Nov 2026) they
# were 2,259 of 2,280 targets, and agents could only guess from the sentence around them.
TRACE_ALL = os.environ.get("REFHEAL_TRACE_ALL", "") not in ("", "0", "false")
# What one finder agent is guessed to spend before any finder of the check is done (the first estimate,
# about 7,000 tokens a target; on a customer export with long topics it was about 30,000).
FINDER_TOKENS = int(os.environ.get("REFHEAL_FINDER_TOKENS", "7000"))
FINDER_TOKENS_KEY = "finder-tokens"     # in the findings cache: what a finder spent on average in the last check
# What the planner is guessed to spend after its finder agents are done (deciding, checking again), kept
# out of the limit for finders so the check ends near the limit, not past it. On a customer export
# (21 Nov 2026) it was about 72,000 in cost terms and the check ended at 338,860 against 300,000; in the
# next check, where the planner read its overview pages before the finders, it was 18,309, then 10,256
# and 28,257. Since its overview leaves out the groups already decided, the planner's whole share of a
# finder check was about 14,000 tokens in, so 20,000 is the guess for a content's first check.
# After a check the planner's own figure is kept in the findings cache and used instead.
PLANNER_CLOSING_TOKENS = int(os.environ.get("REFHEAL_PLANNER_CLOSING_TOKENS", "20000"))
PLANNER_CLOSING_KEY = "planner-closing-tokens"
OVERVIEW_PAGE_CHARS = 14000   # one overview page, under agentloop.MAX_RESULT_CHARS (16,000)
# decide and apply_and_recheck name at most this many group ids and give the full count. Every
# tool result is sent again with each later planner call; on a map with 2,298 groups the full
# lists filled the 16,000-character limit and the planner re-read them on every call after.
LIST_IN_RESULT = 20
GUID_FILE = re.compile(r"^(?:.*/)?GUID-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\.\w+$")

CHOOSE_SYSTEM = """A shared piece of DITA content was changed and references to it broke. Two or three candidate targets could replace it. Different topics may have meant different candidates.

You get what the old target showed, the candidates with what each shows now, and the references: the topic each sits in and the sentence around it. For every reference choose the candidate that fits what that topic needs there. When nothing in the topic or sentence tells them apart, choose candidate 1.

Reply with one JSON object and nothing else: {"choices": [{"reference": <number>, "candidate": <number>}]}""" + refheal.DATA_RULE
MAX_PLANNER_CALLS = 14
MAX_ROUNDS = 4
ACTIONS = ("repair_references", "repair_at_source", "ask_author", "leave_broken") + tuple(wayout.KINDS)
# Decisions that hand a group to the author instead of changing it in the working copy.
HANDED_OVER = ("ask_author", "leave_broken") + tuple(wayout.KINDS)

PLANNER_SYSTEM = """You are in charge of repairing the broken references of one DITA map. Other agents work for you.

A clean-up of shared content broke many references: ids and keys were renamed, content was reworded, moved, merged or removed. Your job is to get as many references as possible pointing at the right thing again with as few and as safe edits as possible, and to hand the author a short, clear list of what only a person can decide.

You work with tools:
- overview: the broken references of the current round, grouped by what they point at, a page at a time. A group may already carry a repair that code proved from the file's version history. Targets that nothing in the files names are counted apart (nothing_names_them): code already listed them for the author; they are not unreviewed. Groups already decided, and groups waiting for the next check, are counted apart too (already_decided, waiting_for_the_next_check) and are not on the pages. The next check looks at the waiting ones by itself: they are not for the author to review, so do not send the author to them in your summary.
- investigate: give groups without a repair to finder agents. Each answer is checked by a reviewer agent. Send all such groups in one call; they run in parallel.
- decide: choose what to do with one or more groups, with your reason.
- apply_and_recheck: apply your decisions to a working copy and scan again. References that are still broken, or newly broken, come back as the next round.
- finish: when nothing is left that you can settle.

The four decisions:
- repair_references: rewrite each reference to the repair. Allowed only when the repair has verdict "fix".
- repair_at_source: one edit where the target lives instead of one edit per reference. Offered only when code found it safe, and the option says what the edit is. An edit that adds a second name to a key is harmless and saves many edits. An edit that renames a key or an element id back undoes a colleague's rename and breaks any reference you repair to the new name in the same round, so choose it only when the saving is large and you decide every group that touches that key or id consistently. It is not accepted at all for a rename that the version history proves (the repair says so): that rename was made on purpose, so repair the references.
- ask_author: a target was found but with doubt (verdict "review" or a caveat), or two readings are possible. The author sees the proposal and the doubt.
- leave_broken: the content is gone and nothing replaces it. Say what it used to be so the author can decide what the topics should say.

When the content is gone, do not stop at leave_broken if the group lists ways_out. Recommend one of them instead; the author sees every way out and your recommendation with its reason, and chooses. None of them is applied by you.
- restore_at_source: put the removed piece back where it lived, from the previous version. One edit repairs every reference. Right when the removal looks like a mistake, or when the piece is safety content (safety_content true): a warning must not disappear from the topics that carry it.
- remove_references: take the references out of the topics. Right when the old text is out of date and the topics read well without it, for example a notice about something that has ended. Never offered for safety content.
- keep_text_in_topics: the topics keep the old text as their own content. Right when the shared piece was removed on purpose but these topics still need the sentence.
Read the old text (was) before you choose, and say in your reason what in the text made you choose.

How to work:
1. Call overview. Read it before you act. When it says there are more pages, read them too. On a large map each group is given in a few words: call overview with group_ids for the full detail of the groups you are about to decide.
2. Investigate every group that has no repair, in one call: group_ids ["all"] takes them all, on every page. Groups where the finders found nothing and nothing can be put back are left broken by code (left_broken_by_code); do not decide them again.
3. Decide every group. Group your decide calls by action. The reason is shown to the author as it is: one sentence of at most 25 plain words that says why, with an example from the content if it helps. No group ids, no file paths, no jargon such as "verdict".
4. Call apply_and_recheck. Read what is still broken. An edit can uncover a second break in the same reference (a renamed key hid a renamed id). Handle the next round the same way.
5. Finish when the recheck shows nothing left that you can settle. The summary is two short sentences for the author: what they should do next, and what to look at first. The counts are shown elsewhere; do not repeat them.

A wrong repair is worse than none: a conref to the wrong element silently publishes wrong content. When in doubt, ask the author.""" + refheal.DATA_RULE

# Where the text before and after cannot be read (no previous version), a finder's "repair" can be
# confirmed by a second run of the finder. Off since 17 Nov 2026: on the large sample without
# previous versions it cost about 13% more model calls, caught no wrong repair in 2 runs and sent
# right repairs to the author instead (eval/refs/no-history-second-run-*.json). The reviewer agent
# still checks every answer. REFHEAL_SECOND_RUN=1 turns it on again.
SECOND_RUN = os.environ.get("REFHEAL_SECOND_RUN", "0") == "1"

# References that pull content in, where a wrong target changes what is published without a broken link to show for it.
REUSE_ATTRS = ("conref", "conrefend", "conkeyref")

# The model of the finder agents alone; the planner and the reviewer keep theirs. Empty: the
# finders run on the model of the session. Set to measure a cheaper finder (planeval.py --finder-model).
FINDER_MODEL = os.environ.get("REFHEAL_FINDER_MODEL") or None

FINISH = {"name": "finish", "description": "End the job.",
          "properties": {"summary": {"type": "string", "description": "for the author, two short plain sentences: what to do next and what to look at first"}},
          "required": ["summary"]}


def apply_attribute_edits(xml, edits):
    """edits: [(attribute, old value, new value)]. Every occurrence in that attribute changes."""
    changed = 0
    for attribute, old, new in dict.fromkeys(edits):
        pattern = re.compile(r'(\s%s\s*=\s*)(["\'])%s\2' % (re.escape(attribute), re.escape(refcheck_escape(old))))
        xml, count = pattern.subn(lambda m: m.group(1) + m.group(2) + refcheck_escape(new) + m.group(2), xml)
        changed += count
    return xml, changed


def refcheck_escape(value):
    return value.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


def _one_sentence(text, limit=170):
    """The first sentence of a reason, without the planner's internal group ids."""
    text = re.sub(r"\s*\((?:r\d+-)?g\d+(?:[^)]*)\)", "", text)
    text = re.sub(r"\b(?:r\d+-)?g\d+\b,?\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    first = re.split(r"(?<=[.!?])\s", text, 1)[0]
    return first if len(first) <= limit else first[:limit].rsplit(" ", 1)[0] + "…"


def _plain(text):
    return re.sub(r"\s+", " ", text or "").strip()


WHOLE = 0.8


def carries_whole(old_text, new_text):
    """True when a target shows what the old one showed, reworded at most a little: at least 80%
    of the old text's words are in it. A piece that holds half of the old text (the old one was
    split) does not; a text of fewer than five words says too little to tell."""
    old = re.findall(r"[a-z0-9]+", old_text.lower())
    if len(old) < 5:
        return False
    new = set(re.findall(r"[a-z0-9]+", new_text.lower()))
    return sum(1 for word in old if word in new) / len(old) >= WHOLE


def _count(number, word):
    return "%s %s%s" % (format(number, ","), word, "" if number == 1 else "s")


def _whole_sentences(text, limit):
    """text cut to the limit at the end of a sentence."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "))
    return cut[:end + 1] if end > limit // 3 else cut.rstrip() + "…"


def _keep_key_scope(repo, ref, known):
    """A key reference names its scope ("admin.settings"); a new key found inside that scope is named
    the same way ("admin.site-settings"), not by its bare name, which resolves only inside the submap.
    The scan counts every scope's names as defined, so a bare name would pass the re-check and still
    be wrong in the output. Candidates are corrected the same way."""
    if ref["attribute"] not in ("keyref", "conkeyref"):
        return
    old_key = ref["value"].partition("/")[0]
    scope = old_key.rpartition(".")[0]
    if not scope:
        return

    def scoped(value):
        if not value:
            return value
        key, slash, rest = value.partition("/")
        if key.startswith(scope + "."):
            return value
        definition = repo.keys.get(key) or {}
        # Scoped when that name exists, or when the key's map is linked from nowhere while a mapref
        # with this keyscope points at a map that is gone: the submap was renamed and its mapref
        # broke with it, so once the mapref is repaired the key is reached under the scope again.
        home = definition.get("defined_in")
        orphan = bool(home) and not any(t == home for t, _ in repo.submap_links)
        scope_lost = any(scopes and scopes[-1] == scope and target not in repo.files for target, scopes in repo.submap_links)
        if (scope + "." + key) in repo.keys or (orphan and scope_lost):
            return scope + "." + key + slash + rest
        return value

    known["new_value"] = scoped(known.get("new_value"))
    for candidate in known.get("candidates") or []:
        candidate["new_value"] = scoped(candidate.get("new_value"))


def _searched(steps):
    """A finder's tool calls in a form an author can read and a check can count:
    [{"tool", "asked", "got"}], at most the eight it may make."""
    out = []
    for step in steps[:refheal.MAX_TOOL_CALLS]:
        args = step.get("args") or {}
        asked = " ".join(str(args[key]) for key in ("query", "path", "id_or_key", "tag") if args.get(key))
        out.append({"tool": step.get("tool", ""), "asked": " ".join(asked.split())[:80], "got": str(step.get("result", ""))[:80]})
    return out


def _key_definitions(map_xml):
    """The key definitions of a map as sorted [keys, file] pairs; the element inside the file is left out."""
    found = []
    for tag in re.findall(r"<[A-Za-z][^<>]*\skeys\s*=\s*[\"'][^<>]*>", map_xml):
        keys = re.search(r"\skeys\s*=\s*([\"'])(.*?)\1", tag)
        href = re.search(r"\shref\s*=\s*([\"'])(.*?)\1", tag)
        found.append([" ".join(sorted(keys.group(2).split())), href.group(2).split("#")[0] if href else ""])
    return sorted(found)


class Session:
    """The planner's working copy and the tools it acts through."""

    def __init__(self, files, backend="cli", model=None, log=print, progress=None, memory=None, reported=None,
                 outside=None, timeline=None, cache=None, max_groups=None,
                 choose=None, assets=None, missing=None, token_budget=None, trace_all=None, map_path=None):
        self.backend, self.model, self.log = backend, model, log
        self.map_path = map_path or None        # the map checked: an author's answer applies without asking only there
        self.trace_all = TRACE_ALL if trace_all is None else trace_all
        self.token_budget = TOKEN_BUDGET if token_budget is None else token_budget
        self.token_mark = usage.position()      # the tokens of this check are counted from here
        self.over_budget = []                   # groups whose finder did not start: the limit was reached
        self.unanswered = []                    # groups whose finder's model calls failed
        self.finders_done = None                # usage.position() when the last finders of this check were done
        # Who is doing what, as rows for a live view: [{"id", "state", "who", "text"}], state is
        # "done", "active" or "waiting". on_timeline gets the whole list after every change.
        self.steps, self.on_timeline = [], timeline or (lambda steps: None)
        self.cache = cache                      # None: remember nothing between checks
        self.max_groups = MAX_GROUPS if max_groups is None else max_groups
        self.choose = choose or self._ask_which_candidate
        self.reused = 0                         # findings taken from the cache in this check
        self.tool_uses = collections.Counter()  # which tools the finder agents used in this check
        self.count_lock = threading.Lock()
        self.decided_keys = set()               # what the decisions of this check rest on (see _decision_key)
        self.replaying = False                  # True while earlier decisions are used again
        self.reuse_line = None                  # where the plan says finders' answers were reused
        self.memory = _memory(memory or {})
        # What the repository itself reports as broken: {(file, attribute, value)}, or None when not told.
        self.reported = None if reported is None else {
            (str(r.get("file", "")).lstrip("/"), r.get("attribute"), r.get("value")) for r in reported if isinstance(r, dict)}
        # Files outside this map that point into a file of it: {path: [paths]}. The map's files are all the planner sees.
        self.outside = {str(k).lstrip("/"): list(v) for k, v in (outside or {}).items() if isinstance(v, list)}
        self.aem_only = []        # reported as broken by the repository, resolving in the files given
        self.distrust = []        # kinds of edit at the source the last "Fix all" showed not to hold in the repository
        self.waiting = set()      # repaired by the last "Fix all", still listed by the repository until it has indexed them
        self.progress = progress or (lambda text: None)   # one line on what is happening now, for a live view
        self.original = [dict(f) for f in files]
        self.files = [dict(f) for f in files]
        # The names the maps give their keys (names.py), so a card says "key cli-name (atlasctl)".
        import names
        self.key_names = names.key_names(self.original)
        self.assets = assets   # the files that are not DITA and exist, when the server told us
        self.missing = missing  # {stored name: path} of targets that are gone, when the server told us
        self.rounds = []          # [{"repo", "groups": {id: group}}], the last one is open
        self.edits = []           # per round: [(file, attribute, old, new)]
        self.source_edits = []    # [(file, element, attribute, current, new, label, group ids)]
        self.left = {}            # (file, attribute, value) -> group that was left to the author
        self.plan = []            # what the planner did, in words, for the author
        self.summary = ""
        self._open_round()

    def step(self, step_id, state, who, text):
        """Adds a row to the live view, or changes the row with that id."""
        row = next((s for s in self.steps if s["id"] == step_id), None)
        if row is None:
            row = {"id": step_id}
            self.steps.append(row)
        row.update(state=state, who=who, text=text)
        self.on_timeline([dict(s) for s in self.steps])

    def _short(self, group):
        """The broken id or key of a group, without its file."""
        return re.split(r"[#/]", self.readable(group["refs"][0]["value"]))[-1]

    def _found(self, group):
        """One line on what the finder and the reviewer made of a group."""
        known = group["known"]
        if not known["new_value"]:
            return "%s: gone, nothing replaces it" % self._short(group)
        new = re.split(r"[#/]", self.readable(known["new_value"]))[-1]
        review = {True: "reviewer agreed", False: "reviewer disagreed"}.get(known.get("reviewer"), "no review")
        verdict = "same text, safe to repair" if known["verdict"] == "fix" else "text changed, ask the author"
        return "%s: found %s. %s. %s" % (self._short(group), new, review.capitalize(), verdict.capitalize())

    # ---- rounds ----------------------------------------------------------------------------

    def _open_round(self):
        repo = refcheck.Repo(files=self.files, assets=self.assets, missing=self.missing)
        groups, by_key = {}, {}
        for ref in repo.broken():
            if ref["generated"] or (ref["file"], ref["attribute"], ref["value"]) in self.left:
                continue
            by_key.setdefault(refheal.group_key(repo, ref), []).append(ref)
        number = len(self.rounds) + 1
        for index, refs in enumerate(by_key.values(), 1):
            group = {"id": "r%d-g%d" % (number, index), "refs": refs, "known": None, "source": None, "decision": None,
                     "reason": ""}
            quick = refheal.rule_fix(repo, refs[0])
            if quick:
                proven = quick["reason"].startswith("In the previous version")
                group["known"] = {"new_value": refheal.new_value(repo, refs[0], quick),
                                  "verdict": quick.get("verdict", "fix"), "how": "history" if proven else "rule",
                                  "reason": quick["reason"], "caveat": quick.get("caveat", "")}
            if not group["known"]:
                self._recall(repo, group)
            elif group["known"]["new_value"] in self._declined(refs[0]):
                # An author said this is not it. The rule's or the history's answer is set aside and
                # the finder agents look for another target (see _from_cache and heal_one).
                group["known"] = None
            missing = "" if group["known"] else refheal.never_defined(repo, refs[0])
            if missing:
                # Nothing to find and nothing to put back: settled here, without an agent.
                group["known"] = {"new_value": None, "verdict": "none", "how": "rule", "reason": missing, "caveat": "",
                                  "never_defined": True}
            self._source_option(repo, group)
            groups[group["id"]] = group
        self.rounds.append({"repo": repo, "groups": groups})
        return groups

    def planner_closing(self):
        """What the planner is guessed to spend after its finders are done: its own figure from the
        last check, else PLANNER_CLOSING_TOKENS."""
        return ((self.cache or {}).get(PLANNER_CLOSING_KEY) or {}).get("spent") or PLANNER_CLOSING_TOKENS

    def keep_planner_closing(self, thread):
        """After the planner is done: keeps what it spent, in its own thread, after its last finders."""
        if self.cache is not None and self.finders_done is not None:
            spent = usage.cost_since(self.finders_done, thread=thread)
            if spent:
                self.cache[PLANNER_CLOSING_KEY] = {"when": time.time(), "spent": round(spent)}

    def _declined(self, ref):
        return set(self.memory["rejected"].get("%s|%s" % (ref["attribute"], ref["value"]), []))

    def _recall(self, repo, group):
        """An author accepted this repair in an earlier check, or the rename behind it: use it, if
        it still resolves and nobody declined it since."""
        first = group["refs"][0]
        key = "%s|%s" % (first["attribute"], first["value"])
        own = (self.memory["by_map"].get(self.map_path) or {}).get(key) if self.map_path else None
        new, exact, caveat = own, True, ""
        reason = "An author accepted this repair in an earlier check of this map."
        if not new and self.memory["answers"].get(key):
            # Given for another map (or before answers were kept per map): the same broken value can
            # mean another thing there, so the author reads it first.
            new, exact = self.memory["answers"][key], False
            reason = "An author accepted this repair in an earlier check of another map."
            caveat = "It was accepted for another map, which may mean something else by it; check that it is right here."
        if not new:
            hint = learned(self.memory, first["attribute"], first["value"], self.map_path)
            if hint:
                new, exact = hint
                reason = "An author accepted the same rename for another reference in an earlier check."
                caveat = "" if exact else ("The rename was accepted for an element reached another way, or in another "
                                           "map; check that this is the same element.")
        if new and new not in self._declined(first) and repo.check(dict(first, value=new)) is None:
            group["known"] = {"new_value": new, "verdict": "fix" if exact else "review", "how": "author", "reason": reason,
                              "caveat": caveat}

    def _drop_declined(self, ref, known):
        """Takes targets an author declined out of a finder's answer; the next candidate moves up."""
        declined = self._declined(ref)
        if not declined:
            return
        left = [c for c in known.get("candidates") or [] if c["new_value"] not in declined]
        if known["new_value"] in declined:
            if left:
                known.update(new_value=left[0]["new_value"], verdict="review", reason=left[0]["why"],
                             caveat="The first choice was declined in an earlier check; this is the next candidate.")
            else:
                known.update(new_value=None, verdict="none", caveat="",
                             reason="The only target found was declined in an earlier check.")
        known["candidates"] = left

    def _weigh(self, repo, ref, known):
        """Settles "repair" or "ask the author" for a finder's answer on a fact, not on how sure the
        model sounded in this run: the text the reference showed before, against the text at the
        new target. The same text is repaired, changed text is asked about. Where the two texts
        cannot be read, the finder's answer stands as the reviewer agent left it; with SECOND_RUN a
        second run of the finder must also name the same target without doubt."""
        if not known["new_value"]:
            return
        was = _plain(refheal.text_at(repo, ref, ref["value"], previous=True, limit=100000))
        now = _plain(refheal.text_at(repo, ref, known["new_value"], limit=100000))
        if was and now:
            known["same_text"] = was == now
            if was == now and known.get("reviewer") is not False:
                known.update(verdict="fix", caveat="", reason=known["reason"].rstrip() +
                             " The text there is word for word what this reference showed before.")
            elif was != now:
                known.update(verdict="review", caveat=known["caveat"] or
                             "The text is not what this reference showed before; read both before accepting.")
            return
        if known["verdict"] == "fix" and ref["attribute"] in REUSE_ATTRS:
            # Reused content has no text of its own to hold against the target, and here no earlier
            # version says what it showed. A wrong piece would go into the published output without
            # a sign, so a finder's word alone does not apply it: the author reads the piece first.
            known.update(verdict="review", caveat=known["caveat"] or
                         "No earlier version shows what this reference reused. Read the piece before accepting.")
            return
        if known["verdict"] == "fix" and SECOND_RUN:
            if "second_run_agrees" not in known:
                second = refheal.heal_one(repo, ref, self.backend, FINDER_MODEL or self.model, False, self.log)
                known["second_run_agrees"] = second["new_value"] == known["new_value"] and second["verdict"] == "fix"
            if not known["second_run_agrees"]:
                known.update(verdict="review", caveat="A second, independent run of the finder agent did not confirm "
                                                      "this target without doubt.")

    def _used_outside(self, repo, group):
        """Files outside this map that point into the file a group's target lives in."""
        first = group["refs"][0]
        if first["attribute"] in refcheck.PATH_ATTRS:
            target = repo.split_target(first)[0]
        else:
            target = (repo.keys.get(first["value"].partition("/")[0]) or {}).get("target")
        return self.outside.get(target or "", [])

    def _source_option(self, repo, group):
        # Only in the first round: a later round sees keys and ids this session already edited.
        known = group["known"]
        if self.edits or not known or not known["new_value"]:
            return
        kind = "keys" if group["refs"][0]["attribute"] in ("keyref", "conkeyref") else "id"
        if kind in self.memory["no_source_edit"]:
            return  # learned from an earlier "Fix all": the repository kept reporting such references
        item = dict(group["refs"][0], uses=[{"file": r["file"]} for r in group["refs"]],
                    repair={"verdict": known["verdict"], "new_value": known["new_value"]})
        group["source"] = refheal.source_fix(repo, item)

    @property
    def current(self):
        return self.rounds[-1]

    def _uses(self, repo, group):
        """(file, attribute, old value, new value) for every reference of a group."""
        first, chosen = group["refs"][0], group.get("choice") or {}
        result = []
        for ref in group["refs"]:
            value = new = chosen.get(ref["file"], group["known"]["new_value"])
            if ref is not first and ref["attribute"] in refcheck.PATH_ATTRS:
                target, topic_id, element_id = repo.split_target(dict(first, value=new))
                value = repo.compose(ref, target=target, topic_id=topic_id, element_id=element_id)
            result.append((ref["file"], ref["attribute"], ref["value"], value))
        return result

    def readable(self, value):
        """A stored reference with the GUID file name replaced by the file's own name."""
        for stored, path in self.current["repo"].alias.items():
            value = value.replace(stored, os.path.basename(path))
        return value

    def _describe(self, group):
        first = group["refs"][0]
        entry = {"id": group["id"], "kind": first["attribute"], "broken_value": self.readable(first["value"]),
                 "why_broken": first["reason"], "references": len(group["refs"]),
                 "files": len({r["file"] for r in group["refs"]}), "repair": None}
        known = group["known"]
        if known:
            entry["repair"] = {"new_value": self.readable(known["new_value"]) if known["new_value"] else None,
                               "verdict": known["verdict"], "found_by": known["how"], "reason": known["reason"][:150]}
            if known["caveat"]:
                entry["repair"]["caveat"] = known["caveat"][:200]
            if "same_text" in known:
                entry["repair"]["text_unchanged"] = known["same_text"]
            if known.get("unnamed"):
                entry["repair"]["nothing_names_it"] = True
            if "removed" in known:
                entry["repair"]["removed"] = known["removed"]     # True only with a previous version as proof
        if known and not known["new_value"] and known.get("how") != "planner":
            ways = self._ways(self.current["repo"], group)
            if ways["options"]:
                entry["ways_out"] = [dict(decision=next(k for k, v in wayout.KINDS.items() if v == o["kind"]), what=o["label"])
                                     for o in ways["options"]]
                entry["was"] = _plain(re.sub(r"<[^>]+>", " ", ways["was"]))[:240]
                entry["safety_content"] = ways["safety"]
        outside = self._used_outside(self.current["repo"], group)
        if outside:
            entry["also_used_from_files_outside_this_map"] = len(outside)
        if group["source"]:
            entry["source_option"] = group["source"]["label"]
        if group["decision"]:
            entry["decided"] = group["decision"]
        return entry

    def _brief(self, group):
        """One group in a few words: what _describe says, cut to what the planner needs to choose what
        to read in full. On a customer export 250 full entries were about 125,000 characters, and reading
        them a page at a time doubled the planner's tokens."""
        full = self._describe(group)
        out = {k: full[k] for k in ("id", "kind", "references", "files") if k in full}
        out["broken_value"] = full["broken_value"][:90]
        repair = full.get("repair")
        if repair:
            out["repair"] = {"verdict": repair["verdict"], "new_value": (repair.get("new_value") or "")[:90] or None,
                             "reason": repair["reason"][:80]}
            for flag in ("nothing_names_it", "removed", "text_unchanged"):
                if flag in repair:
                    out["repair"][flag] = repair[flag]
        if "ways_out" in full:
            out["ways_out"] = [w["decision"] for w in full["ways_out"]]
            out["safety_content"] = full["safety_content"]
        for key in ("decided", "source_option"):
            if key in full:
                out[key] = True if key == "source_option" else full[key]
        return out

    def _entries(self, groups):
        """The planner's view of groups: full when they fit one page, else short (see _brief)."""
        full = [self._describe(g) for g in groups]
        if len(json.dumps(full, ensure_ascii=False)) <= OVERVIEW_PAGE_CHARS:
            return full, False
        return [self._brief(g) for g in groups], True

    # ---- tools -----------------------------------------------------------------------------

    def _nothing_names(self, repo, group):
        """Whether nothing in these files says what a broken target was: its value is a GUID file name
        no file has, no reference to it has link text, and no previous version knows it. An agent could
        only guess from the sentence around it."""
        refs = group["refs"]
        first = refs[0]
        if first["attribute"] not in ("href", "conref", "conrefend"):
            return False
        if not GUID_FILE.match(self.readable(first["value"]).split("#", 1)[0]):
            return False
        if any((r.get("link_text") or "").strip() for r in refs):
            return False
        target = repo.split_target(first)[0]
        return target not in repo.previous and not refheal.text_at(repo, first, first["value"], previous=True)

    def _removal_proven(self, repo, group):
        """Whether the files show that a target without a new value existed and was taken out: a previous
        version of its file, or of the element, is known. Without that it was only not found here."""
        first = group["refs"][0]
        if first["attribute"] in ("keyref", "conkeyref"):
            return bool(refheal.text_at(repo, first, first["value"], previous=True))
        target = repo.split_target(first)[0]
        return target in repo.previous or bool(refheal.text_at(repo, first, first["value"], previous=True))

    def _mark_unnamed(self, repo, groups):
        """Marks the groups of `groups` that nothing in the files names (see _nothing_names) as settled
        without agents, and says so in the plan. Groups with an earlier finding in the cache are left to
        it. Returns the groups it marked."""
        if self.trace_all:
            return []
        unnamed = [g for g in groups if not g["known"] and not (self.cache or {}).get(self._fingerprint(repo, g))
                   and self._nothing_names(repo, g)]
        for group in unnamed:
            group["known"] = {"new_value": None, "verdict": "none", "how": "planner", "caveat": "", "unnamed": True,
                              "reason": "Nothing in these files says what this was: the link names only a GUID, it has "
                                        "no link text and no previous version knows it. It may be in files outside "
                                        "this map, or removed. Check it where the content came from."}
        if unnamed:
            self.plan.append("Only a GUID, no link text and no previous version: %s (%s). Nothing here names them, so I "
                             "did not ask the agents to guess; they may be outside this map or removed." % (
                                 _count(len(unnamed), "broken target"), _count(sum(len(g["refs"]) for g in unnamed), "reference")))
        return unnamed

    def _leave_what_nothing_replaces(self, repo, groups):
        """Decides by code the groups a finder looked at and found nothing for, where nothing can be put
        back or taken out (no ways_out): leave broken, with that reason. The planner spent model calls
        writing the same decision for each of them (on a customer export, 17 to 22 groups a check)."""
        settled = [g for g in groups if g["known"] and not g["known"]["new_value"] and g["known"].get("how") == "finder"
                   and not g["decision"] and not self._ways(repo, g)["options"]]
        for group in settled:
            group["decision"] = "leave_broken"
            group["reason"] = "Nothing in these files replaces it and nothing can be put back; check where the content came from."
        if settled:
            self.plan.append("Code left %s broken (%s): the finder agents found nothing that replaces them and "
                             "nothing can be put back." % (_count(sum(len(g["refs"]) for g in settled), "reference"),
                                                           _count(len(settled), "target")))
        return settled

    def tool_overview(self, args):
        """The groups of this round. Targets that nothing names are settled first and given as one count,
        not one entry each: on a customer export they were 2,049 entries, about 250,000 tokens, and the
        planner read a list cut short."""
        groups = self.current["groups"]
        if args.get("group_ids"):
            # The full detail of the groups asked for, as much as fits one page.
            wanted = [groups[i] for i in args["group_ids"] if i in groups]
            page, size = [], 0
            for group in wanted:
                entry = self._describe(group)
                size += len(json.dumps(entry, ensure_ascii=False))
                if page and size > OVERVIEW_PAGE_CHARS:
                    break
                page.append(entry)
            out = {"groups": page}
            if len(page) < len(wanted):
                out["more"] = "Only the first %d fit; ask again for the others." % len(page)
            return out
        self._mark_unnamed(self.current["repo"], list(groups.values()))
        total = sum(len(g["refs"]) for g in groups.values())
        unnamed = [g for g in groups.values() if (g["known"] or {}).get("unnamed")]
        # In pages that fit what the agent loop passes on (agentloop.MAX_RESULT_CHARS): a page cut short
        # left the planner believing it had seen every group.
        listed = [g for g in groups.values() if g not in unnamed]
        decided = [g for g in listed if g["decision"]]
        waits = [g for g in listed if not g["decision"] and (g["known"] or {}).get("reason", "").startswith("Not looked at")]
        # Only the groups that still need a decision go on the pages; the decided and the waiting are
        # counted apart. On a customer export 226 of 249 listed groups were already decided by code and
        # filled 5 of 6 pages the planner read, and sent again, with every later call.
        open_groups = [g for g in listed if g not in decided and g not in waits]
        entries, short = self._entries(open_groups)
        pages, page, size = [], [], 0
        for entry in entries:
            length = len(json.dumps(entry, ensure_ascii=False))
            if page and size + length > OVERVIEW_PAGE_CHARS:
                pages.append(page)
                page, size = [], 0
            page.append(entry)
            size += length
        pages.append(page)
        number = min(max(1, int(args.get("page") or 1)), len(pages))
        if number == 1:
            self.log("overview: %d pages, %d groups to decide; %d already decided, %d waiting for the next check, "
                     "%d that nothing names, counted apart" % (
                         len(pages), len(open_groups), len(decided), len(waits), len(unnamed)))
        out = {"summary": "round %d: %d broken references in %d groups" % (len(self.rounds), total, len(groups)),
               "round": len(self.rounds), "broken_references": total, "left_for_the_author_so_far": len(self.left),
               "page": number, "pages": len(pages), "groups": pages[number - 1]}
        if short:
            out["short_entries"] = "Each group is given in a few words. Call overview with group_ids to read the full " \
                                   "detail (the old text, the ways out, the caveat) of the groups you decide on."
        if number < len(pages):
            out["more"] = "Groups on %d more page(s): call overview with page=%d. investigate with [\"all\"] takes every group " \
                          "without a repair, on every page." % (len(pages) - number, number + 1)
        if decided:
            out["already_decided"] = {
                "groups": len(decided), "references": sum(len(g["refs"]) for g in decided),
                "note": "Decided already (by code, from an earlier check, or by you) and not on the pages. Call overview "
                        "with group_ids only to look at one again."}
        if waits:
            out["waiting_for_the_next_check"] = {
                "groups": len(waits), "references": sum(len(g["refs"]) for g in waits),
                "note": "Not looked at in this check (its limit, the most it takes a check, or the model did not answer); the next "
                        "check looks at them by itself. They are not for the author to review: do not send the author to them."}
        if unnamed:
            out["nothing_names_them"] = {
                "groups": len(unnamed), "references": sum(len(g["refs"]) for g in unnamed),
                "note": "Already settled by code and listed for the author: each link names only a GUID no file has, "
                        "with no link text and no previous version. Do not investigate them or count them as unreviewed."}
        return out

    def tool_investigate(self, args):
        groups = self.current["groups"]
        ids = list(groups) if list(args.get("group_ids") or []) == ["all"] else args["group_ids"]
        wanted = [groups[i] for i in ids if i in groups and not groups[i]["known"]]
        unknown = [i for i in ids if i not in groups]
        repo = self.current["repo"]
        wanted.sort(key=lambda g: -len(g["refs"]))
        remembered = [g for g in wanted if self._from_cache(repo, g)]
        fresh = [g for g in wanted if g not in remembered]
        unnamed = self._mark_unnamed(repo, fresh)
        fresh = [g for g in fresh if g not in unnamed]
        waiting, fresh = fresh[self.max_groups:], fresh[:self.max_groups]
        for group in waiting:
            group["known"] = {"new_value": None, "verdict": "none", "how": "planner", "caveat": "", "reason":
                              "Not looked at in this check: finder agents take the %d broken targets with the most "
                              "references per check. Run the check again to continue." % self.max_groups}
        self.progress("Planner handed %d groups to finder agents. A reviewer agent checks each answer." % len(fresh))
        finished = []
        number = len(self.rounds)
        self.step("handed-%d" % number, "active", "Planner agent",
                  "Handed %s to finder agents, up to 8 at a time" % _count(len(fresh), "group"))
        for group in remembered:
            self.step(group["id"], "done", "Memory", "%s (found in an earlier check, nothing changed since)" % self._found(group))
        for group in fresh:
            self.step(group["id"], "waiting", "Finder agent", "%s: waiting" % self._short(group))

        # finders running, finished with an answer, and what those spent; ended: finished in any way
        running = {"now": 0, "done": 0, "spent": 0, "ended": 0}
        started_at = {}     # thread of a finder still running -> usage.position() when it started
        # Before any finder of this check is done: what a finder spent on average in an earlier check of
        # this content, else FINDER_TOKENS. On long topics a finder spent about 30,000, not 7,000, and
        # 8 finders started on the low guess took a 300,000 limit to 373,000.
        first_guess = ((self.cache or {}).get(FINDER_TOKENS_KEY) or {}).get("average") or FINDER_TOKENS
        # The planner still decides and checks again after the finders: that part of the limit is kept
        # for it. At most half the limit, so a small limit still lets finders start.
        reserve = min(self.planner_closing(), self.token_budget // 2)

        def projected_unlocked():
            """Tokens of this check so far, plus what the finders still running will likely spend still.
            Each running finder counts in all as the larger of what it has spent itself so far (its own
            calls, counted by thread) and the average of the finders done in this check or first_guess.
            What it has spent is already in the tokens so far, so only the rest is added: counting it
            twice stopped a customer check at 152,700 of 300,000 with 8 finders (21 Nov 2026: 108,104
            spent, of it 93,501 by 7 running finders, counted again on top). Without the running ones,
            8 finders at a time took a 300,000 limit to 638,663 on a customer export. The finders that
            end first are the cheap ones (21 Nov 2026: the first three about 24,000, the last three
            about 34,500), so the average of the finished alone took a check to 357,422.
            Called with count_lock held."""
            average = finder_guess()
            return usage.cost_since(self.token_mark) + sum(
                max(average - usage.cost_since(mark, thread=thread), 0) for thread, mark in started_at.items())

        def finder_guess():
            """What one finder will likely spend in all: the average of the finders done in this check,
            and never less than first_guess. Called with count_lock held."""
            return max(running["spent"] / running["done"], first_guess) if running["done"] else first_guess

        def at_limit():
            """Whether the check has spent its limit, the planner's part kept: a finder still running then
            finishes with what it found (agentloop should_stop). Starting a finder looks ahead; this does
            not, so a running finder is stopped only at the limit itself."""
            return bool(self.token_budget) and usage.cost_since(self.token_mark) >= self.token_budget - reserve

        def run(group):
            with self.count_lock:
                projected = projected_unlocked() if self.token_budget else 0
                # The finder about to start counts too: without it the last one started just under the
                # limit and took a customer check to 316,935 of 300,000 (21 Nov 2026), about one finder over.
                over = bool(self.token_budget) and projected + finder_guess() > self.token_budget - reserve
                if over and not running.get("held"):
                    # The first finder held back: what the limit was made of, to see which part stops it.
                    running["held"] = True
                    spent_so_far = usage.cost_since(self.token_mark)
                    self.log("finder limit reached: spent so far %s, %d finders running counted as %s more "
                             "(their own spend so far %s), kept for the planner %s, limit %s" % (
                                 format(round(spent_so_far), ","), len(started_at),
                                 format(round(projected - spent_so_far), ","),
                                 format(round(sum(usage.cost_since(mark, thread=thread)
                                                  for thread, mark in started_at.items())), ","),
                                 format(reserve, ","), format(self.token_budget, ",")))
                if not over:
                    running["now"] += 1
                    started_at[threading.get_ident()] = usage.position()
            if over:
                group["known"] = {"new_value": None, "verdict": "none", "how": "planner", "caveat": "", "reason":
                                  "Not looked at in this check: it reached its limit of %s in cost terms. Run the check "
                                  "again to continue." % format(self.token_budget, ",")}
                with self.count_lock:
                    self.over_budget.append(group)
                self.step(group["id"], "done", "Planner agent", "%s: waits for the next check (token limit)" % self._short(group))
                return group
            self.step(group["id"], "active", "Finder agent", "%s: searching files, ids, keys and the previous version"
                      % self._short(group))
            own, started = usage.position(), time.time()
            outcome = None
            try:
                outcome = refheal.heal_one(repo, group["refs"][0], self.backend, FINDER_MODEL or self.model, False, self.log,
                                           declined=self._declined(group["refs"][0]), should_stop=at_limit)
            finally:
                spent = usage.cost_since(own, thread=threading.get_ident())
                with self.count_lock:
                    running["now"] -= 1
                    started_at.pop(threading.get_ident(), None)
                    # A finder whose model calls failed spent nothing: it says nothing about what one costs.
                    if outcome is not None and not outcome.get("failed") and spent:
                        running["done"] += 1
                        running["spent"] += spent
                    running["ended"] += 1
                    ended = running["ended"]
                # Whether the finders that end late are the costly ones, which the average of the finished
                # ones does not yet know about: one line per finder in the sidecar log.
                self.log("finder %d done: %s in cost terms, after %d s" % (
                    ended, format(round(spent), ","), time.time() - started))
            searched = _searched(outcome.get("steps") or [])
            with self.count_lock:
                self.tool_uses.update(step["tool"] for step in searched)
            if outcome.get("over_limit"):
                # Stopped at the check's limit before it answered: like a finder that did not start.
                group["known"] = {"new_value": None, "verdict": "none", "how": "planner", "caveat": "", "reason":
                                  "Not looked at in this check: it reached its limit of %s in cost terms. Run the check "
                                  "again to continue." % format(self.token_budget, ",")}
                with self.count_lock:
                    self.over_budget.append(group)
                self.step(group["id"], "done", "Finder agent", "%s: stopped at the token limit" % self._short(group))
                return group
            if outcome.get("failed"):
                # The model did not answer: not a finding, so not "not found"; it waits for the next check.
                group["known"] = {"new_value": None, "verdict": "none", "how": "planner", "caveat": "", "failed": True,
                                  "reason": "Not looked at in this check: the model did not answer. Run the check again to continue."}
                with self.count_lock:
                    self.unanswered.append(group)
                self.step(group["id"], "done", "Finder agent", "%s: the model did not answer" % self._short(group))
                return group
            group["known"] = {"new_value": outcome["new_value"], "verdict": outcome["verdict"], "how": "finder",
                              "candidates": outcome["candidates"], "searched": searched,
                              "closest": outcome.get("closest"),
                              "reason": outcome["reason"], "caveat": outcome["caveat"],
                              "reviewer": (outcome["review"] or {}).get("agree")}
            self._to_cache(repo, group, failed=bool(outcome.get("failed")))
            self._settle(repo, group)
            self._keep_second_opinion(repo, group)
            finished.append(group["id"])
            self.step(group["id"], "done", "Finder + reviewer", self._found(group))
            self.progress("Finder and reviewer agents: %d of %d groups answered." % (len(finished), len(fresh)))
            return group

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            done = list(pool.map(run, fresh)) + remembered
        if self.cache is not None and running["done"]:
            self.cache[FINDER_TOKENS_KEY] = {"when": time.time(), "average": round(running["spent"] / running["done"])}
        self.finders_done = usage.position()
        self.reused += len(remembered)
        if remembered:
            self.reuse_line = len(self.plan)
            self.plan.append("%s: nothing changed since an earlier check, so I used what the agents found then." % (
                _count(len(remembered), "broken target")))
        if fresh and self.token_budget:
            self.plan.append("Limit for this check: %s in cost terms (cached input a tenth, output five times), "
                             "counting the finders still running; %s started." % (
                format(self.token_budget, ","), _count(len([g for g in fresh if g not in self.over_budget]), "finder agent")))
        stopped = [g for g in fresh if g in self.over_budget]
        if stopped:
            self.plan.append("%s wait for the next check (%s): this check reached its limit of %s in cost terms, so I "
                             "started no more finder agents." % (
                                 _count(len(stopped), "broken target"), _count(sum(len(g["refs"]) for g in stopped), "reference"),
                                 format(self.token_budget, ",")))
            fresh = [g for g in fresh if g not in self.over_budget]
        if waiting:
            self.plan.append("%s with fewer references wait for the next check (%s): I look at %d per check, the ones "
                             "that break the most references first." % (
                                 _count(len(waiting), "broken target"), _count(sum(len(g["refs"]) for g in waiting), "reference"),
                                 self.max_groups))
        split = [g for g in done if len(set((g.get("choice") or {}).values())) > 1]
        if split:
            self.plan.append("%s could mean two different pieces. I read the sentence around each reference and "
                             "chose per reference (%s)." % (_count(len(split), "broken target"), "; ".join(
                                 "%s: %s" % (self._short(g), " and ".join(str(n) for n in sorted(
                                     collections.Counter(g["choice"].values()).values(), reverse=True)))
                                 for g in split)))
        found = sum(1 for g in done if g["known"]["new_value"])
        self.step("handed-%d" % number, "done", "Planner agent", "Handed %s to finder agents: %d found, %d not found" % (
            _count(len(fresh), "group"), sum(1 for g in fresh if g["known"]["new_value"]),
            sum(1 for g in fresh if not g["known"]["new_value"])))
        if self.unanswered:
            failed = [g for g in fresh if g in self.unanswered]
            if failed:
                self.plan.append("%s wait for the next check (%s): the model did not answer their finder agents." % (
                    _count(len(failed), "broken target"), _count(sum(len(g["refs"]) for g in failed), "reference")))
            fresh = [g for g in fresh if g not in self.unanswered]
        if fresh:
            # "Removed" only with proof (a previous version of it); without it, it was only not found here.
            gone = [g for g in fresh if not g["known"]["new_value"]]
            proven = [g for g in gone if self._removal_proven(repo, g)]
            for group in gone:
                group["known"]["removed"] = group in proven
            self.plan.append("Sent %d to finder agents, each answer checked by a reviewer agent: %d found under "
                             "a new name or place, %d removed (a previous version shows them), %d not found in "
                             "these files." % (len(fresh), len(fresh) - len(gone), len(proven), len(gone) - len(proven)))
        left = self._leave_what_nothing_replaces(repo, done)
        return {"summary": "%d investigated, %d with a target" % (len(done), found), "unknown_ids": unknown,
                "left_broken_by_code": [g["id"] for g in left],
                "waiting_for_the_next_check": len(waiting), "nothing_names_them": len(unnamed),
                "groups": self._entries(done)[0]}

    def _settle(self, repo, group):
        """What code does with a finder's answer, fresh or remembered: drops what an author declined,
        weighs it against the text, splits it per reference where two pieces could be meant."""
        first, known = group["refs"][0], group["known"]
        _keep_key_scope(repo, first, known)
        self._drop_declined(first, known)
        self._weigh(repo, first, known)
        self._choose_per_reference(repo, group)
        self._source_option(repo, group)

    def _fingerprint(self, repo, group):
        """Changes whenever a remembered finding could be out of date: another broken value, another
        text behind it, or a change in the file (for a key: in the maps) the target lives in."""
        first = group["refs"][0]
        if first["attribute"] in refcheck.PATH_ATTRS:
            scope = [repo.split_target(first)[0]]
        else:
            scope = sorted(path for path in repo.files if path.endswith(".ditamap"))
        xml = {f["path"].lstrip("/"): f["xml"] for f in self.files}
        if first["attribute"] in refcheck.PATH_ATTRS:
            rests_on = [xml.get(p, "") for p in scope]
        else:
            # For a key: which keys the maps define and which file each one names. A repaired
            # reference elsewhere in a map (what "Fix all" writes) does not make the finding old.
            rests_on = [_key_definitions(xml.get(p, "")) for p in scope]
        parts = [first["attribute"], self.readable(first["value"]), first["element"],
                 refheal.text_at(repo, first, first["value"], previous=True, limit=100000)] + rests_on
        return hashlib.sha1(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()

    def _from_cache(self, repo, group):
        """Uses what the agents found for this group in an earlier check, if nothing it rests on changed."""
        entry = (self.cache or {}).get(self._fingerprint(repo, group))
        if not entry or time.time() - entry.get("when", 0) > CACHE_DAYS * 86400:
            return False
        declined = self._declined(group["refs"][0])
        left = [c for c in entry["known"].get("candidates") or [] if c.get("new_value") not in declined]
        if entry["known"].get("new_value") in declined and not left and declined - set(entry.get("declined_when_searched") or []):
            # An author declined what was found and there is no second candidate: search again, once
            # for each new "no". A search that already knew of the declined targets is not repeated.
            return False
        known = dict(entry["known"], how="finder", remembered=True)
        if known["new_value"] and repo.check(dict(group["refs"][0], value=known["new_value"])) is not None:
            return False
        group["known"] = known
        group["choice"] = {f: v for f, v in (entry.get("choice") or {}).items()
                           if repo.check(dict(group["refs"][0], value=v)) is None}
        self._settle(repo, group)
        return True

    def _to_cache(self, repo, group, failed=False):
        if self.cache is None or failed:
            return   # a search that broke down is not a finding
        known = group["known"]
        self.cache[self._fingerprint(repo, group)] = {"when": time.time(), "known": {
            k: known.get(k) for k in ("new_value", "verdict", "candidates", "reason", "caveat", "reviewer", "searched",
                                      "closest")},
            "declined_when_searched": sorted(self._declined(group["refs"][0]))}

    def _keep_second_opinion(self, repo, group):
        """A second finder run is part of the finding: remembered with it, not paid for again."""
        entry = (self.cache or {}).get(self._fingerprint(repo, group))
        if entry is not None and "second_run_agrees" in group["known"]:
            entry["known"]["second_run_agrees"] = group["known"]["second_run_agrees"]

    def _choose_per_reference(self, repo, group):
        """One old target, two pieces it could mean, many topics: each reference gets the candidate
        its own sentence asks for. The choice is a proposal; such a group is always for review."""
        known, refs = group["known"], group["refs"]
        candidates = (known.get("candidates") or [])[:3]
        if len(candidates) < 2 or len(refs) < 2 or group.get("choice"):
            return
        if len({(r["topic_title"], r["context"]) for r in refs}) < 2:
            return
        first = refs[0]
        described = [{"candidate": n, "target": refheal.target_label(repo, first, c["new_value"]),
                      "shows_now": refheal.text_at(repo, first, c["new_value"])[:300]} for n, c in enumerate(candidates, 1)]
        was = refheal.text_at(repo, first, first["value"], previous=True)[:400]
        if carries_whole(was, described[0]["shows_now"]):
            # The first candidate holds what the old target said: the content moved as a whole, so
            # there are no two pieces to choose between. Without this, a second candidate that fits
            # the sentence better took most references although it says something else (16 Nov 2026:
            # the old file's topic "Limits" for 48 of 54 links whose sentence is "Limits are listed in").
            return
        choice = {}
        for start in range(0, len(refs), 60):
            batch = refs[start:start + 60]
            try:
                picked = self.choose(was, described, [{"reference": n, "topic": r["topic_title"], "sentence": r["context"][:240]}
                                                      for n, r in enumerate(batch, 1)])
            except Exception as exc:
                self.log("choosing per reference failed: %s" % str(exc)[:120])
                return
            for n, ref in enumerate(batch, 1):
                index = picked.get(n, 1)
                choice[ref["file"]] = candidates[index - 1 if 1 <= index <= len(candidates) else 0]["new_value"]
        group["choice"] = choice
        if len(set(choice.values())) > 1:
            known.update(verdict="review", caveat=known["caveat"] or "Two pieces could be meant; the proposal differs "
                                                                     "by topic. Read both before accepting.")
            entry = (self.cache or {}).get(self._fingerprint(repo, group))
            if entry is not None:
                entry["choice"] = choice

    def _ask_which_candidate(self, was, candidates, references):
        """{reference number: candidate number}, from one model call."""
        import sidecar
        sidecar.BACKEND = self.backend
        with usage.as_agent("chooser"):
            answer = sidecar.call_model(CHOOSE_SYSTEM, json.dumps(
                {"old_target_showed": was, "candidates": candidates, "references": references}, ensure_ascii=False, indent=1), self.model)
        return {int(c["reference"]): int(c["candidate"]) for c in answer.get("choices") or []
                if str(c.get("reference", "")).isdigit() and str(c.get("candidate", "")).isdigit()}

    # ---- the planner's own decisions, remembered ------------------------------------------------

    def _decision_key(self, group):
        """Changes whenever the planner would see something else for this group: another value, another
        number of references, another finding, another way out, another answer of an author."""
        seen = {k: v for k, v in self._describe(group).items() if k not in ("id", "decided")}
        if seen.get("repair"):
            # The facts of a finding, not its wording: a finder that is asked again (after "Fix all"
            # changed the map) finds the same target and says so in other words.
            seen["repair"] = {k: v for k, v in seen["repair"].items() if k in ("new_value", "verdict", "text_unchanged")}
        return "decision:" + hashlib.sha1(json.dumps(seen, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def _earlier_decision(self, group):
        entry = (self.cache or {}).get(self._decision_key(group))
        if not entry or time.time() - entry.get("when", 0) > CACHE_DAYS * 86400:
            return None
        return entry

    def replay(self):
        """Settles rounds without the planner while it decided every group of the round before and
        nothing it saw has changed. Code checks each decision again. Returns how many groups."""
        settled = 0
        while self.cache and self.current["groups"] and len(self.rounds) <= MAX_ROUNDS:
            groups = self.current["groups"]
            if any(g["known"] and not self._earlier_decision(g) for g in groups.values()):
                break
            unknown = [g["id"] for g in groups.values() if not g["known"]]
            self.reuse_line = None
            if unknown:
                self.tool_investigate({"group_ids": unknown})
            earlier = {g["id"]: self._earlier_decision(g) for g in groups.values()}
            if not all(earlier.values()):
                break
            if self.reuse_line is not None:
                # The finders' answers were reused for groups whose decisions are reused too: the line
                # the caller writes for the decisions says it; the finders' own line would say it again.
                del self.plan[self.reuse_line]
                self.reuse_line = None
            self.replaying = True
            by_decision = {}
            for group_id, entry in earlier.items():
                by_decision.setdefault((entry["decision"], entry["reason"]), []).append(group_id)
            for (decision, reason), ids in by_decision.items():
                self.tool_decide({"decision": decision, "reason": reason, "group_ids": ids})
            self.replaying = False
            settled += len(groups)
            self.tool_apply_and_recheck({})
        return settled

    def _check_decision(self, group, action):
        """None when the action is allowed for the group, else why not."""
        known = group["known"]
        if action == "repair_references":
            if not known or not known["new_value"]:
                return "no repair is known; investigate it, or ask_author / leave_broken"
            if known["verdict"] != "fix":
                return "the repair has verdict \"%s\", not \"fix\"; use ask_author" % known["verdict"]
        if action == "repair_at_source" and not group["source"]:
            return "no safe edit at the source exists for this group; use repair_references"
        if action == "repair_at_source" and group["source"].get("mode") == "rename" and (known or {}).get("how") == "history":
            # Decided on 16 Nov 2026: a rename the version history proves was made on purpose. The
            # planner follows it; it does not put the old name back. In about one run of six it did,
            # for nine targets at once, which is the opposite of what the same planner says in the
            # other runs and makes "Fix all" edit the shared files. An author can still choose the
            # edit at the source from the panel.
            return ("the version history proves this was renamed on purpose; an edit at the source would undo "
                    "the rename. Use repair_references")
        if action in wayout.KINDS:
            if known and known["new_value"]:
                return "a repair is known for this group; a way out is for content that is gone"
            ways = self._ways(self.current["repo"], group)
            if wayout.KINDS[action] not in [o["kind"] for o in ways["options"]]:
                if action == "remove_references" and ways["safety"]:
                    return "this is safety content; its references are never removed. Use restore_at_source or keep_text_in_topics"
                return "this way out is not possible for the group; its ways_out lists what is"
        return None

    def _ways(self, repo, group):
        """The ways out for a group whose content is gone, worked out once."""
        if "ways" not in group:
            previous = {f["path"].lstrip("/"): f.get("previous") or [] for f in self.original}
            group["ways"] = wayout.ways_out(repo, group["refs"], previous)
        return group["ways"]

    def tool_decide(self, args):
        action, reason = args["decision"], args["reason"].strip()
        if action not in ACTIONS:
            return {"summary": "unknown decision", "error": "decision must be one of: %s" % ", ".join(ACTIONS)}
        accepted, rejected = [], {}
        self.progress("Planner is deciding: %s for %d groups." % (action.replace("_", " "), len(args["group_ids"])))
        for group_id in args["group_ids"]:
            group = self.current["groups"].get(group_id)
            problem = "no such group in this round" if not group else self._check_decision(group, action)
            if problem:
                rejected[group_id] = problem
                continue
            key = self._decision_key(group)
            group["decision"], group["reason"] = action, reason
            accepted.append(group_id)
            self.decided_keys.add(key)
            if self.cache is not None and not self.replaying:
                self.cache[key] = {"when": time.time(), "decision": action, "reason": reason}
        if accepted:
            references = sum(len(self.current["groups"][i]["refs"]) for i in accepted)
            self.plan.append("%s Why: %s" % ({
                "repair_references": "Decided to repair %s." % _count(references, "reference"),
                "repair_at_source": "Decided to repair %s with %s where the target lives." % (
                    _count(references, "reference"), _count(len(accepted), "edit")),
                "ask_author": "Decided to ask you about %s (%s)." % (
                    _count(references, "reference"), _count(len(accepted), "question")),
                "leave_broken": "Decided to leave %s broken." % _count(references, "reference"),
                "restore_at_source": "For %s whose content is gone I suggest putting the piece back." % _count(references, "reference"),
                "remove_references": "For %s whose content is gone I suggest removing them." % _count(references, "reference"),
                "keep_text_in_topics": "For %s whose content is gone I suggest keeping the text in the topics." % _count(references, "reference"),
            }[action], _one_sentence(reason)))
        undecided = [g["id"] for g in self.current["groups"].values() if not g["decision"]]
        counts = {}
        for group in self.current["groups"].values():
            if group["decision"]:
                counts[group["decision"]] = counts.get(group["decision"], 0) + len(group["refs"])
        words = {"repair_references": "repair", "repair_at_source": "repair at the source", "ask_author": "ask the author about",
                 "leave_broken": "leave broken", "restore_at_source": "suggest putting back",
                 "remove_references": "suggest removing", "keep_text_in_topics": "suggest keeping the text of"}
        self.step("decide-%d" % len(self.rounds), "active" if undecided else "done", "Planner agent", "Decided: " + ", ".join(
            "%s %s" % (words[action], format(count, ",")) for action, count in counts.items()))
        return {"summary": "%d accepted, %d rejected" % (len(accepted), len(rejected)), "accepted": accepted,
                "rejected": rejected, "still_undecided": len(undecided),
                "first_undecided": undecided[:LIST_IN_RESULT]}

    def _default(self, group):
        """The cautious decision for a group the planner did not decide."""
        known = group["known"]
        if known and known["new_value"] and known["verdict"] == "fix":
            return "repair_references"
        return "ask_author" if known and known["new_value"] else "leave_broken"

    def tool_apply_and_recheck(self, args):
        current = self.current
        repo, groups = current["repo"], current["groups"]
        self.progress("Planner is applying its plan to a working copy and checking again.")
        number = len(self.rounds)
        self.step("recheck-%d" % number, "active", "Planner agent", "Applying the plan to a copy and scanning again")
        defaulted = [g for g in groups.values() if not g["decision"]]
        for group in defaulted:
            group["decision"], group["reason"] = self._default(group), "not decided by the planner; cautious default"
        before = sum(len(g["refs"]) for g in groups.values())
        edits, by_file, sources = [], {}, 0
        for group in groups.values():
            if group["decision"] == "repair_references":
                for use in self._uses(repo, group):
                    edits.append(use)
                    by_file.setdefault(use[0], []).append(use[1:])
            elif group["decision"] == "repair_at_source":
                fix = group["source"]
                self.source_edits.append(dict(fix, groups=[group["id"]]))
                by_file.setdefault(fix["file"].lstrip("/"), []).append((fix["attribute"], self._current_value(fix), self._merged(fix)))
                sources += 1
            else:
                for ref in group["refs"]:
                    self.left[(ref["file"], ref["attribute"], ref["value"])] = group
        self.edits.append(edits)
        for entry in self.files:
            wanted = by_file.get(entry["path"].lstrip("/"))
            if wanted:
                entry["xml"], _ = apply_attribute_edits(entry["xml"], wanted)
        remaining = self._open_round()
        still = sum(len(g["refs"]) for g in remaining.values())
        left = len(self.left)
        handed_over = sum(len(g["refs"]) for g in groups.values() if g["decision"] in HANDED_OVER)
        self.plan.append("Tried the plan on a copy and checked again: %s work now, %s left for you%s." % (
            _count(before - still - handed_over, "reference"), format(handed_over, ","),
            ", %s still open" % format(still, ",") if still else ""))
        self.step("recheck-%d" % number, "done", "Planner agent", "Tried the plan on a copy: %s %s, %s left for the author%s" % (
            _count(before - still - handed_over, "reference"), "works" if before - still - handed_over == 1 else "work",
            format(handed_over, ","),
            ", %s still open" % format(still, ",") if still else ""))
        result = {"summary": "%d still to settle" % still, "reference_edits": len(edits), "edits_at_the_source": sources,
                  "left_for_the_author": left, "still_broken_and_undecided": still,
                  "defaulted_groups": len(defaulted),
                  "first_defaulted": [g["id"] for g in defaulted[:LIST_IN_RESULT]]}
        if still and len(self.rounds) <= MAX_ROUNDS:
            result["next"] = "Round %d has %d groups. Call overview." % (len(self.rounds), len(remaining))
        else:
            result["next"] = "Nothing left that you can settle. Call finish."
        return result

    def _current_value(self, fix):
        """The attribute's value in the working copy: an earlier source edit may have changed it."""
        if fix.get("mode") != "alias":
            return fix["current"]
        merged = [e for e in self.source_edits[:-1] if (e["file"], e["attribute"], e["current"]) == (fix["file"], "keys", fix["current"])]
        names = fix["current"].split()
        for earlier in merged:
            names += [n for n in earlier["new"].split() if n not in names]
        return " ".join(names)

    def _merged(self, fix):
        names = self._current_value(fix).split()
        names += [n for n in fix["new"].split() if n not in names]
        return " ".join(names) if fix.get("mode") == "alias" else fix["new"]

    def tools(self):
        string, array = {"type": "string"}, {"type": "array", "items": {"type": "string"}}
        return [
            {"name": "overview", "description": "The broken references of the current round, grouped by target, a page at a time.",
             "properties": {"page": {"type": "integer", "description": "1 for the first page"},
                            "group_ids": {"type": "array", "items": {"type": "string"},
                                          "description": "only these groups, in full detail"}},
             "required": [], "fn": self.tool_overview},
            {"name": "investigate", "description": "Hand groups that have no repair to finder agents; a reviewer agent checks each answer. Send all of them in one call: [\"all\"] takes every group without a repair, on every page.",
             "properties": {"group_ids": array}, "required": ["group_ids"], "fn": self.tool_investigate},
            # The parameter is not called "action": the CLI protocol uses that word for the tool's name.
            {"name": "decide", "description": "Decide what to do with groups. decision: repair_references, repair_at_source, ask_author, leave_broken, or for content that is gone one of restore_at_source, remove_references, keep_text_in_topics.",
             "properties": {"group_ids": array, "decision": string, "reason": string},
             "required": ["group_ids", "decision", "reason"], "fn": self.tool_decide},
            {"name": "apply_and_recheck", "description": "Apply the decisions of this round to the working copy and scan again.",
             "properties": {}, "required": [], "fn": self.tool_apply_and_recheck},
        ]

    # ---- what happened since the last check --------------------------------------------------

    def look_back(self, applied, now=None):
        """Compares what the last "Fix all" wrote with what the repository holds and reports now.
        Returns (lines for the plan, [(attribute, old, new)] repairs that did not hold, whether the
        record is finished with). A repair counts as not holding only when the repository still
        reports it broken in a second check, SETTLE_SECONDS or more after it was saved: AEM indexes
        saved files later, and checks soon after "Fix all" can still list them."""
        repo = self.rounds[0]["repo"]
        present = {(r["file"], r["attribute"], r["value"]) for r in repo.refs}
        broken = {(r["file"], r["attribute"], r["value"]) for g in self.current["groups"].values() for r in g["refs"]}
        if self.reported is not None:
            self.aem_only = sorted(key for key in self.reported if key in present and key not in broken)
        lines, failed = [], []
        edits = (applied or {}).get("edits") or []
        if edits:
            keys = [(e["file"].lstrip("/"), e["attribute"], e["old"], e["new"]) for e in edits]
            unsaved = [k for k in keys if (k[0], k[1], k[2]) in broken]
            still = [k for k in keys if (k[0], k[1], k[3]) in self.aem_only]
            # Saved: the new value is in the file and resolves here. Whether AEM's report already says
            # so is told apart below; counting only those would read as if the others had failed.
            saved = sum(1 for k in keys if (k[0], k[1], k[3]) in present)
            held = saved - len(still)
            if any(k[1] not in ("keys", "id") for k in keys):
                lines.append("Since the last Fix all: %s saved and %s in the files." % (
                    _count(saved, "repair"), "resolves" if saved == 1 else "resolve"))
            if unsaved:
                lines.append("%s from the last Fix all did not reach the repository (%s); they are in this list again."
                             % (_count(len(unsaved), "repair"), _count(len({k[0] for k in unsaved}), "file")))
            settled = applied.get("checks", 0) >= 1 and (now or time.time()) - applied.get("when", 0) >= SETTLE_SECONDS
            lagging = set()
            if still and settled:
                failed = sorted({(k[1], k[2], k[3]) for k in still})
                lines.append("AEM still reports %s I repaired as broken, in a second check. My check and AEM's disagree "
                             "there; I will not propose those repairs again." % _count(len(still), "reference"))
            elif still:
                self.waiting |= {(k[0], k[1], k[3]) for k in still}
                lines.append("%sAEM still lists %s just repaired. It has not indexed the change yet; counted as "
                             "waiting, not as findings." % ("AEM's report already agrees for %d of them. " % held
                                                            if held else "", _count(len(still), "reference")))
                # While AEM has not indexed the saved files, it may list their other references too, ones this
                # Fix did not touch. Seen once on 22 Nov 2026: 95 such rows right after a Fix all, gone in the
                # next check; most likely the same indexing. They wait too; the next check, made after AEM has
                # caught up, lists any that are really broken.
                saved = {k[0] for k in keys}
                lagging = {key for key in self.aem_only if key[0] in saved and key not in self.waiting}
                self.waiting |= lagging
                if lagging:
                    lines.append("AEM also lists %s of the files just saved that resolve here; counted as waiting "
                                 "until it has indexed them." % _count(len(lagging), "other reference"))
            # An edit at the source (a key or an id put back) changes no reference, so whether it held
            # shows only in what the repository still reports for references that resolve here.
            kinds = {"keys" if key[1] in ("keyref", "conkeyref") else "id" for key in self.aem_only
                     if (key[0], key[1]) not in {(k[0], k[1]) for k in still}}
            source = {e["attribute"] for e in edits if e["attribute"] in ("keys", "id")} & kinds
            other = len(self.aem_only) - len(still) - len(lagging)
            if source and settled:
                self.distrust = sorted(source)
                lines.append("AEM still reports %s as broken after the edit at the source that should have repaired "
                             "them (%s). That kind of edit does not hold in AEM; from now on I repair such references "
                             "one by one instead." % (_count(other, "reference"), " and ".join(
                                 "a key renamed back" if kind == "keys" else "an id put back" for kind in self.distrust)))
            elif source:
                # The edit at the source is in the repository; AEM needs time (more than ten minutes
                # was measured for keys) before its report follows. Until then these are not findings.
                wanted = {"keyref", "conkeyref"} if "keys" in source else set()
                wanted |= set(refcheck.PATH_ATTRS) if "id" in source else set()
                self.waiting |= {key for key in self.aem_only if key[1] in wanted}
                lines.append("AEM still lists %s repaired by the edit at the source. It has not indexed the change "
                             "yet; counted as waiting, not as findings." % _count(other, "reference"))
            elif other:
                lines.append("AEM also reports %s as broken that resolve in the files I was given. They are in the "
                             "list without a repair." % _count(other, "reference"))
            return lines, failed, (not still and not source) or settled
        if self.aem_only:
            lines.append("AEM reports %s as broken that resolve in the files I was given. They are in the list "
                         "without a repair." % _count(len(self.aem_only), "reference"))
        return lines, failed, True

    def _aem_only_repairs(self):
        repo, lines, formats = self.rounds[0]["repo"], {}, {}
        for ref in repo.refs:
            lines.setdefault((ref["file"], ref["attribute"], ref["value"]), ref["line"])
            formats.setdefault((ref["file"], ref["attribute"], ref["value"]), ref.get("format") or "")
        waiting = "Repaired by the last Fix all. AEM has not indexed the change yet; this leaves the list by itself."
        differs = ("AEM reports this reference as broken, but its target exists in the files of this map. AEM's check "
                   "and the planner's differ here.")
        # Seen on 15 Nov 2026: a key's definition was repaired in the map, and AEM kept listing the
        # topic's reference to that key until the topic itself was saved again.
        by_key = ("Nothing to edit here: the key is defined in the map and its target exists. AEM still lists this "
                  "reference because it worked out this topic's keys before the map was right; it does so again when "
                  "the topic is saved.")

        def wrong_format(key):
            """A link to DITA content that says it is something else. Seen on content that was not
            ours (17 Nov 2026): a link inside one topic marked format="html". The address is right;
            AEM does not follow it because of the format."""
            file, attribute, value = key
            marked = formats.get(key, "").lower()
            if attribute != "href" or marked in ("", "dita", "ditamap"):
                return ""
            path = value.partition("#")[0]
            if path and not refcheck.is_dita_path(path):
                return ""
            return ("The address is right: its target exists. The link is marked format=\"%s\", and AEM does not follow a "
                    "link to DITA content that is marked as something else. Set format to \"dita\" or remove the "
                    "attribute; the href stays as it is." % formats[key])

        def settled_by_rule(key):
            return (key[1] in ("keyref", "conkeyref") or bool(wrong_format(key))) and key not in self.waiting

        return [{"file": "/" + file, "line": lines.get((file, attribute, value), 0), "attribute": attribute, "old": value,
                 "new": None, "target": None, "caveat": "", "used_in": ["/" + file],
                 # Settled by a rule: it says what is the case, no search was made.
                 "stage": "rule" if settled_by_rule((file, attribute, value)) else "planner",
                 "verdict": "pending" if (file, attribute, value) in self.waiting else "none",
                 "reason": waiting if (file, attribute, value) in self.waiting
                 else by_key if attribute in ("keyref", "conkeyref")
                 else wrong_format((file, attribute, value)) or differs}
                for file, attribute, value in self.aem_only]

    # ---- the result ------------------------------------------------------------------------

    def finish_unfinished(self):
        """Closes rounds the planner left open, with the cautious default for undecided groups."""
        guard = 0
        while self.current["groups"] and guard < MAX_ROUNDS:
            before = len(self.left) + sum(len(e) for e in self.edits)
            self.tool_apply_and_recheck({})
            guard += 1
            if len(self.left) + sum(len(e) for e in self.edits) == before:
                break

    @staticmethod
    def _with_text_check(caveat, repo, ref, value, how):
        """The caveat, with the warning that the link's text is not found in the new target. Not for
        a rename the version history proves (the link was to that element before, whatever its text
        says), and not twice: the topic id rule says the same in its own words."""
        if how == "history" or not value:
            return caveat
        said = caveat.lower()
        text = "" if "text of the link" in said or "link text" in said else refheal.link_text_caveat(repo, ref, value)
        # An image that other topics already show, offered for a missing one with another name. Not for
        # the rule, which finds the same file name moved, where a shared image is the same image.
        image = "" if how == "rule" or "already used in" in said else refheal.asset_in_use_caveat(repo, ref, value)
        return " ".join(filter(None, [caveat, text, image]))

    def _tool_use_line(self):
        """Said once, at the end: the finders may be asked in more than one round of a check."""
        if not self.tool_uses:
            return []
        return ["How the finder agents searched in this check: %s." % ", ".join(
            "%s %d" % (tool, count) for tool, count in self.tool_uses.most_common())]

    @staticmethod
    def _held_back_line(held):
        """The plan says "decided to repair" and "works on the copy" of every repair it tried. Some of
        those are not applied by "Fix all" after all; without this line the plan and the list disagree."""
        if not held:
            return []
        return ["%s that I repaired on the copy %s shown to you for a look instead of being applied by \"Fix all\": "
                "the target's id is on more than one element, or the text of the link is not found in the target. "
                "They are listed as \"to review\"." % (_count(held, "reference").capitalize(), "is" if held == 1 else "are")]

    def result(self):
        first, final = self.rounds[0], self.rounds[-1]
        final_broken = {(r["file"], r["attribute"], r["value"]) for r in final["repo"].broken()}
        chains = [{(file, attribute, old): new for file, attribute, old, new in edits} for edits in self.edits]
        source_label = {}
        for edit in self.source_edits:
            for group_id in edit["groups"]:
                source_label[group_id] = edit["label"]
        repairs, details, held = [], {}, 0
        for group in first["groups"].values():
            used_in = sorted({"/" + r["file"] for r in group["refs"]})
            for ref in group["refs"]:
                value, how = ref["value"], (group["known"] or {}).get("how")
                for chain in chains:
                    value = chain.get((ref["file"], ref["attribute"], value), value)
                entry = {"file": "/" + ref["file"], "line": ref["line"], "attribute": ref["attribute"], "old": ref["value"],
                         "new": None, "target": None, "caveat": "", "used_in": used_in, "stage": how,
                         "detail": details.setdefault(group["id"], self._detail(group))}
                broken_now = (ref["file"], ref["attribute"], value) in final_broken
                last = self.left.get((ref["file"], ref["attribute"], value))
                if not broken_now and value != ref["value"]:
                    entry.update(verdict="fix", new=value, target=refheal.target_label(final["repo"], ref, value),
                                 reason=(group["known"] or {}).get("reason", ""))
                    # A target id that several elements carry: the repair is right for the first of
                    # them only, so it is shown for a look and not applied by "Fix all".
                    twice = refheal.duplicate_caveat(final["repo"], ref, value)
                    if twice:
                        entry.update(verdict="review", caveat=twice)
                    checked = self._with_text_check(entry["caveat"], final["repo"], ref, value, how)
                    if checked != entry["caveat"] and how == "finder":
                        # A finder's target that does not say what the link says is not applied by
                        # "Fix all": the author looks first (seen 17 Nov 2026: such a repair went in
                        # with 21 others and nobody read its warning).
                        entry["verdict"] = "review"
                    entry["caveat"] = checked
                    held += entry["verdict"] == "review"
                elif not broken_now:
                    entry.update(verdict="covered", stage="planner",
                                 reason="Repaired by one edit at the source. " + source_label.get(group["id"], ""))
                elif last and last["known"] and last["known"]["new_value"]:
                    proposal = next((new for file, attribute, old, new in self._uses(self._round_of(last)["repo"], last)
                                     if (file, attribute, old) == (ref["file"], ref["attribute"], value)), None)
                    entry.update(verdict="review", new=proposal, stage=last["known"]["how"],
                                 target=refheal.target_label(final["repo"], ref, proposal) if proposal else None,
                                 reason=last["known"]["reason"], caveat=" ".join(filter(None, [
                                     last["known"]["caveat"] or last["reason"],
                                     refheal.duplicate_caveat(final["repo"], ref, proposal)])))
                    entry["caveat"] = self._with_text_check(entry["caveat"], final["repo"], ref, proposal,
                                                            last["known"]["how"])
                else:
                    gone = last or group
                    known = gone["known"] or {}
                    entry.update(verdict="none", stage=known.get("how"), reason=known.get("reason") or gone["reason"])
                    if known.get("never_defined"):
                        # No piece was removed, so there is no way out to offer: the reason says what to add.
                        repairs.append(entry)
                        continue
                    if "ways_out" not in entry["detail"]:
                        entry["detail"]["ways_out"] = self._ways_out_detail(gone, group, chains)
                    suggested = entry["detail"]["ways_out"].get("recommended")
                    similar = next((o for o in entry["detail"]["ways_out"]["options"] if o["kind"] == "similar"), None)
                    if suggested:
                        entry["reason"] = "Suggested: %s. %s %s" % (
                            suggested["label"], _one_sentence(suggested["why"]), entry["reason"])
                    elif similar:
                        # Said first, so the row can show it: without it this row looks like every
                        # other "no repair found", and the author would not know to open it.
                        entry["reason"] = "A similar piece exists: %s. %s" % (similar["target"], entry["reason"])
                repairs.append(entry)
        return {"stats": {"files": len(first["repo"].files), "references": len(first["repo"].refs), "broken": len(repairs),
                          "groups": len(first["groups"]), "rounds": len(self.edits),
                          "reported_broken_only_by_the_repository": len(self.aem_only),
                          "reviewer_model": refheal.reviewer_model(self.backend, self.model)},
                "repairs": repairs + self._aem_only_repairs(), "source_fixes": self._source_fixes(),
                "plan": self.plan + self._tool_use_line() + self._held_back_line(held) + ([self.summary] if self.summary else [])}

    def _ways_out_detail(self, gone, group, chains):
        """The ways out for content that is gone, for the author to choose from: every possible one,
        which one the planner recommends and why, and for "restore" the edits the references need
        on top of it (a key that was renamed as well still has to be followed)."""
        repo = self._round_of(gone)["repo"]
        ways = self._ways(repo, gone) if (gone["known"] or {}).get("how") != "planner" else {"options": [], "safety": False, "was": ""}
        follow = {}
        for ref in group["refs"]:
            value = ref["value"]
            for chain in chains:
                value = chain.get((ref["file"], ref["attribute"], value), value)
            if ways.get("renamed_key") and value == ref["value"]:
                value = ways["renamed_key"] + "/" + ref["value"].partition("/")[2]
            if value != ref["value"]:
                follow[(ref["attribute"], ref["value"])] = value
        options = [dict(o, reference_edits=[{"attribute": a, "old": old, "new": new} for (a, old), new in follow.items()])
                   if o["kind"] == "restore" else o for o in ways["options"]]
        options = options + self._similar_option(repo, gone, group)
        kind = wayout.KINDS.get(gone.get("decision") or "")
        chosen = next((o for o in options if o["kind"] == kind), None)
        return {"safety": ways["safety"], "options": options,
                "recommended": {"kind": kind, "label": chosen["label"], "why": gone["reason"]} if chosen else None}

    def _similar_option(self, repo, gone, group):
        """A way out for content that is gone: point the references at the piece a finder named as
        the closest that exists (the same procedure for another line of business, say). Never the
        planner's recommendation and never applied by "Fix all": only the author can take it."""
        closest = (gone.get("known") or {}).get("closest") or {}
        first = group["refs"][0]
        value = closest.get("new_value")
        if not value or value in self._declined(first) or repo.check(dict(first, value=value)) is not None:
            return []
        edits = [{"attribute": attribute, "old": old, "new": value}
                 for attribute, old in sorted({(ref["attribute"], ref["value"]) for ref in group["refs"]})]
        target = refheal.target_label(repo, first, value)
        return [{"kind": "similar", "target": target, "why": _whole_sentences(closest.get("why") or "", 240),
                 "now": refheal.text_at(repo, first, value)[:300], "reference_edits": edits,
                 "label": "Point the %s at %s instead: a similar piece, not the same one" % (
                     _count(len(group["refs"]), "reference"), target)}]

    def _detail(self, group):
        """What an author needs to compare before accepting: what the reference showed before, the
        candidate targets ranked with what each shows now, and what the repair touches."""
        repo, first, known = self._round_of(group)["repo"], group["refs"][0], group["known"] or {}
        ranked = known.get("candidates") or ([{"new_value": known["new_value"], "likelihood": 100, "why": known["reason"]}]
                                             if known.get("new_value") else [])
        files = sorted({os.path.basename(r["file"]) for r in group["refs"]})
        return {"was": refheal.text_at(repo, first, first["value"], previous=True)[:300],
                "candidates": [{"value": c["new_value"], "target": refheal.target_label(repo, first, c["new_value"]),
                                "likelihood": c["likelihood"], "why": _whole_sentences(c["why"], 240),
                                "now": refheal.text_at(repo, first, c["new_value"])[:300]} for c in ranked[:3]],
                # What the reviewer agent said of the first candidate: True, False, or None when no
                # reviewer saw it (a rule, an earlier answer of an author). For the evaluation of
                # what an author accepts, and for a panel that wants to show it.
                "reviewer": known.get("reviewer"),
                # How a finder agent got there: the tools it used, what it asked and what came back.
                # Empty for a repair that a rule, the version history or an author settled.
                "searched": known.get("searched") or [],
                # For a key that was never defined: what is the case and what to add. The box then
                # says this instead of "before it broke" and "no candidate", which are not true of it.
                "missing_definition": known["reason"] if known.get("never_defined") else "",
                # What a key showed, for a reference by key: from the map, or its earlier version.
                "key_name": self.key_names.get(first["value"].split("/")[0], "")
                if first["attribute"] in ("keyref", "conkeyref") else "",
                "references": len(group["refs"]), "files": len(files), "file_names": files[:6],
                "published_under": self._published_under(repo, group),
                "outside": [os.path.basename(f) for f in self._used_outside(repo, group)[:6]],
                "outside_count": len(self._used_outside(repo, group))}

    def _published_under(self, repo, group):
        """The conditions the references of a group are published under, for the editor to hold
        against each output's filter: [{"references", "in_topic": [...], "in_map": [[...]]}].
        in_topic: condition attributes on the referencing element and its ancestors. in_map: the
        same for every place the map includes that topic. One entry per distinct combination."""
        combined = {}
        for ref in group["refs"]:
            entry = {"in_topic": ref.get("conditions") or [], "in_map": repo.map_conditions.get(ref["file"]) or []}
            key = json.dumps(entry, sort_keys=True)
            combined.setdefault(key, dict(entry, references=0))["references"] += 1
        return sorted(combined.values(), key=lambda e: -e["references"])[:20]

    def _round_of(self, group):
        return next(r for r in self.rounds if group["id"] in r["groups"])

    def _source_fixes(self):
        merged = {}
        for edit in self.source_edits:
            key = (edit["file"], edit["attribute"], edit["current"])
            entry = merged.setdefault(key, {"file": edit["file"], "element": edit["element"], "attribute": edit["attribute"],
                                            "current": edit["current"], "new": edit["current"], "references": 0,
                                            "labels": [], "chosen": True})
            if edit.get("mode") == "alias":
                names = entry["new"].split()
                entry["new"] = " ".join(names + [n for n in edit["new"].split() if n not in names])
            else:
                entry["new"] = edit["new"]
            entry["references"] += edit["references"]
            if edit["label"] not in entry["labels"]:
                entry["labels"].append(edit["label"])
        for entry in merged.values():
            labels = entry.pop("labels")
            entry["label"] = labels[0] if len(labels) == 1 else (
                "Fix at the source, chosen by the planner: one edit here repairs %d references." % entry["references"])
        return list(merged.values())


def _ask_planner(session, backend, model, log, progress):
    """Lets the planner agent settle what is open. Returns its steps."""
    groups = session.current["groups"]
    session.step("planner", "active", "Planner agent", "Reading the broken references and planning")
    progress("Planner agent is reading %d broken references in %d groups." % (
        sum(len(g["refs"]) for g in groups.values()), len(groups)))
    task = ("The map has %d broken references in %d groups. Repair what can be repaired safely and tell the author "
            "what is left. Start with overview." % (sum(len(g["refs"]) for g in groups.values()), len(groups)))
    with usage.as_agent("planner"):
        answer, steps, problem = agentloop.run(PLANNER_SYSTEM, task, session.tools(), FINISH, backend=backend, model=model,
                                               max_calls=MAX_PLANNER_CALLS, log=log)
    if not problem:
        session.keep_planner_closing(threading.get_ident())
    if problem:
        log("planner stopped: %s" % problem)
        session.plan.append("The planner stopped early (%s). What it had not decided got the safe default: repair when "
                            "proven, otherwise ask you." % problem)
    else:
        session.summary = "Next: " + _whole_sentences(answer["summary"], 260)
    session.step("planner", "done", "Planner agent", "Planned in %s" % _count(len(steps), "step") if not problem
                 else "Stopped early; the safe default is used for what it had not decided")
    return steps


def spellings_line(spelled):
    """The plan's line for names.spellings, in the words of the tab the author opens; the editor
    counts from "Names written two ways: N"."""
    def count(n, one, many=None):
        return "%s %s" % (format(n, ","), one if n == 1 else (many or one + "s"))
    spelling = [s for s in spelled if not s["case_only"]]
    capitals = len(spelled) - len(spelling)
    parts = []
    if spelling:
        first = spelling[0]
        parts.append("%s in %s, such as \"%s\" for \"%s\" (%s in %s)" % (
            format(len(spelling), ","), count(sum(s["places"] for s in spelling), "place"), first["forms"][1]["form"],
            first["main"], count(first["forms"][1]["count"], "place"), count(len(first["forms"][1]["files"]), "topic")))
    if capitals:
        parts.append("%s only in capital letters" % format(capitals, ","))
    return ("Names written two ways: %s %s written more than one way: %s. Open \"Names written two ways\" to make "
            "each one spelling." % (count(len(spelled), "name"), "is" if len(spelled) == 1 else "are", ", and ".join(parts)))


def plan_files(payload, backend="cli", model=None, log=print, progress=None, memory=None, timeline=None):
    """_plan_files, plus what the check cost and whether the model answered: both go into the
    plan the author reads, into "usage" of the answer and, for a stored check, into the usage log."""
    mark, started = usage.start(), time.time()
    try:
        out = _plan_files(payload, backend, model, log, progress, memory, timeline)
    except BaseException:
        usage.finish(mark)
        raise
    totals = usage.finish(mark)
    # Text copied across topics, and groups of references copied across maps: counted by code on
    # every check; the reuse agent is asked only when the author opens "Repeated text" (GET /copies).
    copied = duplicates.find(payload.get("files") or [])
    copied_maps = duplicates.find_maps(payload.get("files") or [])
    if copied or copied_maps:
        everything = copied + copied_maps
        copies = sum(len(g["copies"]) for g in everything)
        maps = " (%s of them groups of references in maps)" % format(len(copied_maps), ",") if copied_maps else ""
        # Said in the words of the tab the author opens; the editor counts from "Repeated text: N".
        out["plan"] = list(out.get("plan") or []) + ["Repeated text: %s %s repeated in several topics or maps%s: %s copies, "
                                                     "%s could be reused instead. Open \"Repeated text\" "
                                                     "to see which." % (
                                                         format(len(everything), ","), "text is" if len(everything) == 1 else "texts are",
                                                         maps, format(copies, ","), format(copies - len(everything), ","))]
        out.setdefault("stats", {}).update(copied_groups=len(copied), copied_map_groups=len(copied_maps))
    # Images whose alt text says nothing to a screen reader: found by code on every check; a model
    # sees an image only when the author asks for its alt in "Images without alt text" (POST /alt-suggest).
    weak_alts = alttext.images(payload.get("files") or [], payload.get("assets"), payload.get("missing_paths"))
    if weak_alts:
        places = sum(g["weak_uses"] for g in weak_alts)
        out["plan"] = list(out.get("plan") or []) + ["Images without alt text: %s %s, in %s %s, %s nothing to a screen "
                                                     "reader. Open \"Images without alt text\" to have one suggested." % (
                                                         format(len(weak_alts), ","), "image" if len(weak_alts) == 1 else "images",
                                                         format(places, ","), "place" if places == 1 else "places",
                                                         "says" if len(weak_alts) == 1 else "say")]
        out.setdefault("stats", {}).update(images_without_alt=len(weak_alts))
    # Names the topics write more than one way ("HX-200" and "HX 200"): found by code on every check,
    # in about 2.5 s for 57,782 files; "Names written two ways" shows each and makes the topics say one.
    spelled = names.spellings(payload.get("files") or [])
    if spelled:
        out["plan"] = list(out.get("plan") or []) + [spellings_line(spelled)]
        out.setdefault("stats", {}).update(names_written_two_ways=len(spelled))
    # Attribute values a subject scheme no longer allows: found and, where the scheme's previous
    # version proves a rename, repaired by code. They are not references, so AEM's report does not
    # list them and the planner's groups do not hold them.
    scheme = subjectscheme.check(payload.get("files") or [])
    if scheme["repairs"]:
        out["repairs"] = list(out.get("repairs") or []) + scheme["repairs"]
        out["plan"] = scheme["plan"] + list(out.get("plan") or [])
        stats = out.setdefault("stats", {})
        stats["subject_scheme_values"] = scheme["values"]
    warning = usage.warning(totals)
    out["plan"] = ([warning] if warning else []) + list(out.get("plan") or []) + [usage.sentence(totals)]
    out["usage"] = totals
    log("usage: %s" % json.dumps(totals))
    if memory is None:
        usage.record(payload.get("map"), totals, round(time.time() - started))
    return out


def _plan_files(payload, backend="cli", model=None, log=print, progress=None, memory=None, timeline=None):
    """For a repository server. Same input and output as refheal.heal_files, plus "plan".

    Optional in the payload: "reported" [{"file", "attribute", "value"}], what the repository's own
    report lists as broken; "used_outside" {path: [paths]}, files outside the map that point into
    one of its files.
    With memory=None the stored author answers and the record of the last "Fix all" are used and
    updated; a caller that passes its own memory (an evaluation) touches nothing on disk."""
    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list):
        raise ValueError("body must be a JSON object with a \"files\" list")
    started = time.time()
    progress = progress or (lambda text: None)
    progress("Scanning %d files for broken references." % len(files))
    stored = memory is None
    session = Session(files, backend, model, log, progress, load_memory() if stored else memory,
                      reported=payload.get("reported"), outside=payload.get("used_outside"), timeline=timeline,
                      assets=payload.get("assets"), missing=payload.get("missing_paths"), map_path=payload.get("map"))
    log("planner input: %d files, %s references reported by the repository, %d files with users outside the map"
        % (len(files), len(payload["reported"]) if isinstance(payload.get("reported"), list) else "no",
           sum(1 for v in (payload.get("used_outside") or {}).values() if v)))
    cache = (_read(CACHE_PATH) or {}) if stored else None
    session.cache = cache if isinstance(cache, dict) or cache is None else {}
    started_with = dict(session.cache or {})
    applied_file = applied_path(payload.get("map"))
    applied = _read(applied_file) if stored else None
    looked_back, failed, finished = session.look_back(applied)
    if stored and applied:
        for attribute, old, new in failed:
            reject(attribute, old, new)
        if session.distrust:
            with _LOCK:
                memory_now = load_memory()
                memory_now["no_source_edit"] = sorted(set(memory_now["no_source_edit"]) | set(session.distrust))
                _write(MEMORY_PATH, memory_now)
        if finished:
            os.remove(applied_file)
        else:
            _write(applied_file, dict(applied, checks=applied.get("checks", 0) + 1))
    first = session.current["groups"]
    if not first:
        out = session.result()
        out["plan"] = looked_back
        return out
    undefined = [g for g in first.values() if (g["known"] or {}).get("never_defined")]
    proven = sum(1 for g in first.values() if g["known"]) - len(undefined)
    changed = len(first) - len(undefined)
    references = sum(len(g["refs"]) for g in first.values())
    renamed = references - sum(len(g["refs"]) for g in undefined)
    origin = ("" if not changed else
              " They all come from %d ids and keys that were renamed, moved or removed." % changed if not undefined else
              " %s from %d ids and keys that were renamed, moved or removed." % (
                  "%s of them %s" % (format(renamed, ","), "comes" if renamed == 1 else "come"), changed))
    session.plan.append("Found %s in %d files.%s" % (
        _count(references, "broken reference"), len(session.rounds[0]["repo"].files), origin))
    if undefined:
        session.plan.append("%s to %s that this map does not define: the map defines no keys at all, now or in an earlier "
                            "version. Nothing was renamed, so there is nothing to repair and no agent searched for them. "
                            "Add the key definitions to the map, or include the map that holds them: %s." % (
                                _count(sum(len(g["refs"]) for g in undefined), "reference").capitalize() + (
                                    " points" if sum(len(g["refs"]) for g in undefined) == 1 else " point"),
                                _count(len(undefined), "key"),
                                ", ".join(sorted(g["refs"][0]["value"].partition("/")[0] for g in undefined))))
        session.step("undefined", "done", "Scanner", "%s not defined in this map: no agent needed" % _count(len(undefined), "key"))
    session.plan += looked_back
    outside = {f for g in first.values() for f in session._used_outside(session.current["repo"], g)}
    if outside:
        session.plan.append("%s outside this map also %s into the files that changed. I only see this map; those "
                            "references are not in this list." % (_count(len(outside), "file"), "points" if len(outside) == 1 else "point"))
    recalled = sum(1 for g in first.values() if g["known"] and g["known"]["how"] == "author")
    by_rule = sum(1 for g in first.values() if g["known"] and g["known"]["how"] == "rule"
                  and not g["known"].get("never_defined"))
    proven -= recalled + by_rule
    if proven:
        session.plan.append("%d of those %d were only renamed: the file's previous version proves it, no AI needed."
                            % (proven, len(first)))
    if by_rule:
        session.plan.append("%d%s %s settled by a rule in code that reads the files as they are now, no AI needed. "
                            "No previous version proves these." % (
                                by_rule, " more" if proven else " of those %d" % len(first), "was" if by_rule == 1 else "were"))
    if recalled:
        session.plan.append("%d more %s answered by an author in an earlier check; I used %s again." % (
            recalled, "was" if recalled == 1 else "were", "that answer" if recalled == 1 else "those answers"))
    session.step("scan", "done", "Scanner", "Found %s in %d files, from %d renamed, moved or removed ids and keys" % (
        _count(sum(len(g["refs"]) for g in first.values()), "broken reference"), len(session.rounds[0]["repo"].files), len(first)))
    if proven:
        session.step("history", "done", "Version history", "Proved %s from the previous versions, no AI" % _count(proven, "rename"))
    if by_rule:
        session.step("rule", "done", "Rule", "Settled %s from the files as they are, no AI" % _count(by_rule, "target"))
    if recalled:
        session.step("memory", "done", "Memory", "Reused %s an author gave in an earlier check" % _count(recalled, "answer"))
    at = len(session.plan)
    replayed = session.replay()
    if replayed:
        session.plan.insert(at, "Nothing changed for %s since an earlier check, so I kept the decisions I made then%s." % (
            _count(replayed, "broken target"), "" if session.current["groups"] else "; the planner agent was not asked again"))
        session.step("planner-memory", "done", "Memory", "Reused the planner's decisions for %s, each checked again by code"
                     % _count(replayed, "broken target"))
    steps = []
    # Keys that were never defined are settled by a rule; when nothing else is open, no agent is asked.
    open_groups = [g for g in session.current["groups"].values() if not (g["known"] or {}).get("never_defined")]
    if open_groups:
        steps = _ask_planner(session, backend, model, log, progress)
        if stored and session.cache is not None and session.summary:
            session.cache["summary"] = {"when": time.time(), "text": session.summary, "for": sorted(session.decided_keys)}
    else:
        kept = (session.cache or {}).get("summary") or {}
        if kept.get("for") == sorted(session.decided_keys):
            session.summary = kept["text"]
    progress("Planner finished. Building the report.")
    session.finish_unfinished()
    if stored and session.cache is not None:
        merge_cache(CACHE_PATH, started_with, session.cache)
    out = session.result()
    out["stats"].update(finder_tool_uses=dict(session.tool_uses))
    out["stats"].update(planner_steps=len(steps), planner_decisions_reused=replayed, seconds=round(time.time() - started),
                        findings_reused_from_an_earlier_check=session.reused)
    return out
