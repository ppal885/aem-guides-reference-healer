#!/usr/bin/env python3
"""Writes samples/dupes-drift: copies of one sentence that no longer match, for the "Keep copies"
mode (no conref: the author makes the copies say the same, or keeps them as they are).

  - a number that differs (90 days in two topics, 60 in one): facts differ;
  - one copy with words added ("and the attachments"): the wording drifted;
  - the same sentence for two products (Payroll, Ledger): meant to differ;
  - a sentence with a link, one copy ending "to the auditor" for "to the controller": drifted;
  - copies for internal readers (audience="internal"), one drifted: drifted, the condition kept;
  - a copy that adds a whole step (11 words and more): a longer sentence, not a drifted copy;
  - copies that are the same: not listed in this mode.

truth.json gives, for each group, the label a person would give and the wording that is right
where one is.

    python3 samples/gen_dupes_drift.py samples/dupes-drift
    ./samples/load_dupes_drift.sh

Made-up product ("Ledgerline"); no customer content.
"""
import json
import os
import sys

HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">\n'

KEEP = "Closed periods are kept for %d days, after which nobody can reopen them or change their postings."
BACKUP = "Back up the ledger database%s before you close the period, every time, even for a short period."
PRODUCT = "Open %s, select the period that you want to close and check that no entries are still open."
LINK = ('Read the <xref href="checklist.dita">closing checklist</xref> before you close the period and send the '
        'signed copy to the %s.')
UNLOCK = "Ask the IT %s to unlock the ledger before you reopen a period that was closed by mistake."
EXPORT = "Export the trial balance to the reporting folder before you close the period%s."
EXPORT_MORE = (", then email the controller, attach the signed approval form and wait for the controller to answer "
               "before you continue")
SAME = "Every posting in a closed period keeps the name of the person who approved it and the time of approval."


def concept(name, title, paragraphs):
    return HEAD + '<concept id="%s"><title>%s</title><conbody>%s</conbody></concept>\n' % (
        name, title, "".join(paragraphs))


def p(text, audience=None):
    return '<p%s>%s</p>' % (' audience="%s"' % audience if audience else "", text)


def files():
    return {
        "topics/close_month.dita": concept("close_month", "Close the month", [
            p(KEEP % 90), p(BACKUP % ""), p(PRODUCT % "Ledger"), p(LINK % "controller"), p(EXPORT % ""), p(SAME)]),
        "topics/close_quarter.dita": concept("close_quarter", "Close the quarter", [
            p(KEEP % 90), p(BACKUP % ""), p(LINK % "controller"), p(EXPORT % ""), p(SAME)]),
        "topics/close_year.dita": concept("close_year", "Close the year", [
            p(KEEP % 60), p(BACKUP % " and the attachments"), p(LINK % "auditor"), p(EXPORT % EXPORT_MORE)]),
        "topics/payroll_close.dita": concept("payroll_close", "Close a payroll period", [p(PRODUCT % "Payroll")]),
        "topics/reopen_internal.dita": concept("reopen_internal", "Reopen a period (internal)", [
            p(UNLOCK % "service desk", "internal")]),
        "topics/unlock_internal.dita": concept("unlock_internal", "Unlock the ledger (internal)", [
            p(UNLOCK % "service desk", "internal")]),
        "topics/unlock_admins.dita": concept("unlock_admins", "Unlock for administrators (internal)", [
            p(UNLOCK % "help desk", "internal")]),
        "topics/checklist.dita": concept("checklist", "Closing checklist", [p("The items to check before a close.")]),
        "drift_guide.ditamap": ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" '
                                '"map.dtd">\n<map><title>Ledgerline closing (copies that drifted)</title>%s</map>\n' % "".join(
                                    '<topicref href="topics/%s.dita"/>' % n for n in (
                                        "close_month", "close_quarter", "close_year", "payroll_close", "reopen_internal",
                                        "unlock_internal", "unlock_admins", "checklist"))),
    }


# For each group: its first words, the label a person gives, and the right wording where there is one.
TRUTH = [
    {"text_starts": "Closed periods are kept for", "label": "facts differ", "right": None,
     "why": "90 days in two topics, 60 in one: which is true is the author's to say"},
    {"text_starts": "Back up the ledger database", "label": "drifted", "right": "Back up the ledger database and the attachments",
     "why": "one copy gained three words; the others should say the same"},
    {"text_starts": "Open Ledger, select the period", "label": "meant to differ", "right": None,
     "why": "the product name is meant to change by topic"},
    {"text_starts": "Read the closing checklist", "label": "drifted", "right": None,
     "why": "one copy sends the copy to the auditor, two to the controller; the link is kept"},
    {"text_starts": "Ask the IT", "label": "drifted", "right": None, "audience": "internal",
     "why": "copies for internal readers; one says help desk; the condition must stay"},
    {"text_starts": "Export the trial balance", "label": "not the same text", "right": None,
     "why": "one copy adds a whole step: another sentence, not a copy that drifted"},
]
NOT_LISTED = [SAME[:40]]


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "dupes-drift")
    for path, text in files().items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as f:
            f.write(text)
    with open(os.path.join(root, "truth.json"), "w") as f:
        json.dump({"groups": TRUTH, "not_listed": NOT_LISTED}, f, indent=1)
    print("wrote %s: %d files, %d groups" % (root, len(files()), len(TRUTH)))


if __name__ == "__main__":
    main()
