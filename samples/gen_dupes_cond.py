#!/usr/bin/env python3
"""Writes samples/dupes-cond: copies with the same words for other readers, to check that a Fix
never makes them one piece and that each copy keeps its own conditions and attributes.

  - a note for external readers copied into two concepts, and the same words for internal readers
    in two more: two pieces, one for each audience;
  - a paragraph copied into two concepts, and once more with product="payroll": the two plain copies
    are one piece, the payroll one is left as it is;
  - a note copied into two concepts, once with type="caution" and once without: one piece, and each
    copy keeps its own type.

    python3 samples/gen_dupes_cond.py samples/dupes-cond
    ./samples/load_dupes_cond.sh

Made-up product ("Ledgerline"); no customer content.
"""
import os
import sys

CONCEPT = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">\n'

ACCESS = "Ask the ledger administrator to give you access to the closing workspace first."
REPORT = "The closing report lists every journal entry that was posted after the cutoff date."
BACKUP = "Back up the ledger database before you close the period, every single time."


def concept(name, body):
    return CONCEPT + '<concept id="%s"><title>About %s</title><conbody>%s</conbody></concept>\n' % (
        name, name.replace("_", " "), body)


def files():
    out = {}
    for name, audience in (("ext_access", "external"), ("ext_setup", "external"),
                           ("int_access", "internal"), ("int_setup", "internal")):
        out["concepts/%s.dita" % name] = concept(name, '<p>Read this first.</p><note audience="%s">%s</note>' % (audience, ACCESS))
    out["concepts/report_ledger.dita"] = concept("report_ledger", "<p>%s</p>" % REPORT)
    out["concepts/report_close.dita"] = concept("report_close", "<p>%s</p>" % REPORT)
    out["concepts/report_payroll.dita"] = concept("report_payroll", '<p product="payroll">%s</p>' % REPORT)
    out["concepts/backup_close.dita"] = concept("backup_close", '<note type="caution">%s</note>' % BACKUP)
    out["concepts/backup_reopen.dita"] = concept("backup_reopen", "<note>%s</note>" % BACKUP)
    refs = "".join('<topicref href="%s"/>' % path for path in sorted(out))
    out["cond_guide.ditamap"] = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" '
                                 '"map.dtd">\n<map><title>Ledgerline access for each audience</title>%s</map>\n' % refs)
    return out


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "dupes-cond")
    for path, text in files().items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(text)
    print("wrote %d files to %s" % (len(files()), root))
