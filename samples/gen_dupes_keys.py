#!/usr/bin/env python3
"""Writes samples/dupes-keys: made-up topics of a team that reuses by key (conkeyref), with text
copied into several topics. Used to check that "Share" and "Fix all safe" pull the shared piece by
key there, and keep a conref where a key would not reach:

- keys_guide.ditamap: a key for the existing library topic ("notes"), a submap, and a key scope
  that defines its own "shared-content" (so the new key takes another name);
- library/notes.dita: a note topic t1 already pulls by conkeyref (the team's way);
- topics t1..t6: three groups of copies (a caution in all six, an audit sentence in t2..t4, a
  step result in t5 and t6), and copies of the library's note in t3 and t4;
- other_manual.ditamap: another map that uses t6, so t6 keeps a conref.

    python3 samples/gen_dupes_keys.py samples/dupes-keys
    ROOT=/content/dam/dupes-keys ./samples/load_dupes_keys.sh

Made-up product ("Ledgerline"); no customer content. truth.json says what a run must do.
"""
import json
import os
import sys

TOPIC_HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">\n'
MAP_HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">\n'
CAUTION = "Back up the ledger database before you change a posting rule, so that you can go back if the rule is wrong."
AUDIT = "Every change to a posting rule is written to the audit log with the name of the person who made it."
RESULT = "The rule is saved and takes effect at the start of the next period."
LIBRARY_NOTE = "Only a ledger administrator can change a posting rule."


def topic(n, body):
    return TOPIC_HEAD + ('<topic id="t%d"><title>Posting rule %d</title><body><p>Posting rule %d moves amounts '
                         'between account group %d and account group %d.</p>%s</body></topic>\n' % (n, n, n, n, n + 1, body))


def files():
    out = {"library/notes.dita": TOPIC_HEAD + '<topic id="notes"><title>Shared notes</title><body>'
                                              '<note id="note_admin" type="important">%s</note></body></topic>\n' % LIBRARY_NOTE}
    for n in range(1, 7):
        body = '<note type="caution">%s</note>' % CAUTION
        if n == 1:
            body += '<note conkeyref="notes/note_admin"/>'
        if 2 <= n <= 4:
            body += "<p>%s</p>" % AUDIT
        if n in (3, 4):
            body += '<note type="important">%s</note>' % LIBRARY_NOTE      # a copy of the library's note
        if n >= 5:
            body += "<p>%s</p>" % RESULT
        out["topics/t%d.dita" % n] = topic(n, body)
    out["sub.ditamap"] = MAP_HEAD + ('<map><title>Ledgerline rules, part two</title>'
                                     '<topicref href="topics/t4.dita"/><topicref href="topics/t5.dita"/></map>\n')
    out["keys_guide.ditamap"] = MAP_HEAD + (
        '<map><title>Ledgerline posting rules by key</title>'
        '<keydef keys="notes" href="library/notes.dita"/>'
        '<topicref href="topics/t1.dita"/><topicref href="topics/t2.dita"/><topicref href="topics/t3.dita"/>'
        '<mapref href="sub.ditamap"/>'
        '<topicgroup keyscope="archive"><keydef keys="shared-content" href="library/notes.dita"/>'
        '<topicref href="topics/t6.dita"/></topicgroup></map>\n')
    out["other_manual.ditamap"] = MAP_HEAD + ('<map><title>Ledgerline year-end manual</title>'
                                              '<topicref href="topics/t6.dita"/></map>\n')
    return out


TRUTH = {
    "map": "keys_guide.ditamap",
    "key_for_shared_content": "shared-content-2",
    "by_key": ["topics/t1.dita", "topics/t2.dita", "topics/t3.dita", "topics/t4.dita", "topics/t5.dita"],
    "keeps_conref": {"topics/t6.dita": "other_manual.ditamap uses it"},
    "existing_piece_by_key": {"library/notes.dita#note_admin": "pulled by conkeyref notes/note_admin in t1; "
                                                               "its copies in t3 and t4 become conkeyref notes/note_admin"},
    "groups": {"caution": 6, "audit": 3, "result": 2},
}


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "samples/dupes-keys"
    for path, xml in files().items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as handle:
            handle.write(xml)
    with open(os.path.join(root, "truth.json"), "w") as handle:
        json.dump(TRUTH, handle, indent=1)
    print("wrote %d files to %s" % (len(files()) + 1, root))


if __name__ == "__main__":
    main()
