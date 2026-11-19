#!/usr/bin/env python3
"""Writes samples/dupes-demo: a small guide with text copied into its topics in every way the
reuse agent has to tell apart, and truth.json with the right answer for each group.

    python3 samples/gen_dupes.py samples/dupes-demo

Made-up product ("Ledgerline"); no customer content.
"""
import json
import os
import sys

HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE %s PUBLIC "-//OASIS//DTD DITA %s//EN" "%s.dtd">\n'

BACKUP = "Back up the ledger database before you close a period, so that you can go back if a posting is wrong."
DRIFT = "Record the change in the audit log and tell the controller which accounts it touched before the period closes"
RELEASE = "Ledgerline %s fixes the problems that customers reported in the previous release and adds no new settings."
KEEP = "The ledger keeps closed periods for %d days, after which they can no longer be reopened by anyone."
UI = "Select OK to close the dialog box and go back to the page where you started."
LIBRARY_NOTE = "Only a ledger administrator can reopen a closed period, and every reopening is written to the audit log."
DECOY_A = "Delete the export files after the period is closed, because they hold account numbers in plain text."
DECOY_B = "Keep the export files after the period is closed, because the auditors ask for them in the spring."


MAP_HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">\n'
CLOSING_GROUP = ('<topichead navtitle="Closing periods"><topicref href="../tasks/close_period.dita"/>'
                 '<topicref href="../tasks/reopen_period.dita"/><topicref href="../tasks/export_period.dita"/></topichead>')
RELTABLE = ('<reltable><relrow><relcell><topicref href="../tasks/close_period.dita"/></relcell>'
            '<relcell><topicref href="../tasks/reopen_period.dita"/></relcell></relrow></reltable>')


def task(tid, title, steps, extra=""):
    return (HEAD % ("task", "Task", "task") + '<task id="%s"><title>%s</title><taskbody>%s<steps>%s</steps></taskbody></task>\n'
            % (tid, title, extra, "".join("<step><cmd>%s</cmd></step>" % s for s in steps)))


def concept(cid, title, body):
    return HEAD % ("concept", "Concept", "concept") + '<concept id="%s"><title>%s</title><conbody>%s</conbody></concept>\n' % (cid, title, body)


def files():
    out = {}
    note = lambda text, kind="caution": '<note type="%s">%s</note>' % (kind, text)
    # A library topic that already holds one shared note, used by conref from one topic.
    out["reuse/library.dita"] = concept("library", "Shared notes", '<note id="n_reopen" type="important">%s</note>' % LIBRARY_NOTE)
    out["tasks/close_period.dita"] = task("close_period", "Close a period", ["Open Periods.", "Select Close."],
                                          "<context>%s%s</context>" % (note(BACKUP), note(KEEP % 90, "note")))
    out["tasks/reopen_period.dita"] = task("reopen_period", "Reopen a period", ["Open Periods.", "Select Reopen."],
                                           '<context>%s<note conref="../reuse/library.dita#library/n_reopen"/>%s</context>'
                                           % (note(BACKUP), note(KEEP % 90, "note")))
    out["tasks/post_entry.dita"] = task("post_entry", "Post a journal entry", ["Open Journal.", "Select Post."],
                                        "<context>%s<p>%s.</p></context>" % (note(BACKUP), DRIFT))
    out["tasks/reverse_entry.dita"] = task("reverse_entry", "Reverse a journal entry", ["Open Journal.", "Select Reverse."],
                                           "<context>%s<p>%s, and attach the reversal.</p><p>%s</p></context>" % (note(BACKUP), DRIFT, UI))
    out["tasks/import_rates.dita"] = task("import_rates", "Import exchange rates", ["Open Rates.", "Select Import."],
                                          "<context>%s<p>%s.</p><p>%s</p><note>%s</note></context>" % (note(BACKUP), DRIFT, UI, LIBRARY_NOTE))
    out["tasks/export_period.dita"] = task("export_period", "Export a period", ["Open Periods.", "Select Export."],
                                           "<context><p>%s</p><note>%s</note><p>%s</p></context>" % (UI, KEEP % 60, DECOY_A))
    out["tasks/archive_exports.dita"] = task("archive_exports", "Archive exports", ["Open Exports.", "Select Archive."],
                                             "<context><p>%s</p><p>%s</p></context>" % (UI, DECOY_B))
    for version in ("4.1", "4.2", "4.3"):
        tid = "release_" + version.replace(".", "_")
        out["release/%s.dita" % tid] = concept(tid, "Ledgerline %s" % version, "<p>%s</p>" % (RELEASE % version))
    # Two guides that copy the same group of topics and the same relationship table: a topic added
    # to one copy is missing from the other.
    for name, title, own in (("admin_guide", "Ledgerline administration", ["archive_exports"]),
                             ("user_guide", "Ledgerline daily use", ["post_entry", "reverse_entry"])):
        out["guides/%s.ditamap" % name] = MAP_HEAD + "<map><title>%s</title>%s%s%s</map>\n" % (
            title, CLOSING_GROUP, "".join('<topicref href="../tasks/%s.dita"/>' % t for t in own), RELTABLE)
    out["ledger_guide.ditamap"] = (MAP_HEAD + '<map><title>Ledgerline guide</title>%s%s</map>\n' % (
        "".join('<topicref href="%s"/>' % path for path in sorted(out) if path.endswith(".dita")),
        "".join('<mapref href="%s"/>' % path for path in sorted(out) if path.startswith("guides/"))))
    return out


TRUTH = [
    {"text_starts": "Back up the ledger database", "kind": "same", "files": 5, "decision": "share",
     "why": "a caution in 5 tasks, word for word"},
    {"text_starts": "The ledger keeps closed periods", "kind": "numbers", "files": 3, "decision": "ask",
     "why": "90 days in two topics, 60 in one: a contradiction, never merged without the author"},
    {"text_starts": "Ledgerline 4.", "kind": "numbers", "files": 3, "decision": "variable",
     "why": "the release number is meant to differ: one shared sentence with the number as a variable"},
    {"text_starts": "Select OK to close the dialog box", "kind": "same", "files": 4, "decision": "skip",
     "why": "a generic interface line: sharing it adds a conref for nothing"},
    {"text_starts": "Record the change in the audit log", "kind": "wording", "files": 3, "decision": "share",
     "why": "the same instruction, one copy added words: share the common one and keep the addition"},
    {"text_starts": "Only a ledger administrator", "kind": "same", "files": 2, "decision": "use existing",
     "why": "already shared as reuse/library.dita#library/n_reopen: conref the copy to it"},
]
NOT_A_GROUP = [DECOY_A[:40], DECOY_B[:40]]
MAP_GROUPS = [
    {"tag": "topichead", "navtitle": "Closing periods", "maps": 2, "refs": 3,
     "why": "the same three topics under the same heading in both guides"},
    {"tag": "reltable", "navtitle": "", "maps": 2, "refs": 2,
     "why": "the same relationship table in both guides"},
]


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "samples/dupes-demo"
    for path, xml in files().items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as handle:
            handle.write(xml)
    with open(os.path.join(root, "truth.json"), "w") as handle:
        json.dump({"groups": TRUTH, "not_a_group": NOT_A_GROUP, "map_groups": MAP_GROUPS}, handle, indent=1)
    print("wrote %s: %d files, %d groups, %d decoys, %d map groups" % (
        root, len(files()), len(TRUTH), len(NOT_A_GROUP), len(MAP_GROUPS)))


if __name__ == "__main__":
    main()
