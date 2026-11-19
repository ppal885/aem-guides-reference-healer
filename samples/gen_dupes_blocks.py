#!/usr/bin/env python3
"""Writes samples/dupes-blocks: whole lists and whole steps copied word for word, to check that a
Fix shares the whole block with one conref instead of one for each item.

  - a list (three items, one in bold) copied into three concepts: one piece, the whole list;
  - the same list with its last item different in a fourth concept: left to its items;
  - a list copied into two concepts where another topic links to one of its items (an id): left to
    its items, so the link keeps its target;
  - a whole step (command and its info) copied into three tasks: one piece, the whole step;
  - the same command with a different info in two more tasks: only the command is shared.

    python3 samples/gen_dupes_blocks.py samples/dupes-blocks
    ./samples/load_dupes_blocks.sh

Made-up product ("Ledgerline"); no customer content.
"""
import os
import sys

TASK = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">\n'
CONCEPT = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">\n'

ITEMS = ["Post every open journal entry for the period before you start.",
         "Run the <b>trial balance</b> report and check that it balances.",
         "Ask the controller to approve the close in the approvals queue."]
LAST = "Ask the auditor to approve the close in the audit queue instead."
KEPT = ['<li id="keep_days">The ledger keeps every posting for ninety days after the close.</li>',
        "<li>Postings older than ninety days move to the archive every night.</li>"]
CMD = "Open <uicontrol>Periods</uicontrol> and select the period that you want to close now."
INFO = "<info><p>Only a period with no open journal entries can be closed by the ledger.</p></info>"
OTHER_INFO = {"adjustments": "<info><p>Adjustments that are still open keep the period from closing.</p></info>",
              "corrections": "<info><p>A correction that waits for approval keeps the period open.</p></info>"}


def concept(name, body):
    return CONCEPT + '<concept id="%s"><title>About %s</title><conbody>%s</conbody></concept>\n' % (name, name, body)


def task(name, step):
    return TASK + ('<task id="%s"><title>Close the %s</title><taskbody><steps>%s<step><cmd>Review the summary '
                   'for the %s.</cmd></step></steps></taskbody></task>\n' % (name, name.replace("_", " "), step, name))


def files():
    out = {}
    whole = "<ul>%s</ul>" % "".join("<li>%s</li>" % item for item in ITEMS)
    for name in ("periods", "postings", "audits"):
        out["concepts/%s.dita" % name] = concept(name, "<p>Before you close a period:</p>" + whole)
    out["concepts/reports.dita"] = concept("reports", "<p>Before you close a period:</p><ul>%s</ul>" % "".join(
        "<li>%s</li>" % item for item in ITEMS[:2] + [LAST]))
    out["concepts/retention.dita"] = concept("retention", "<ul>%s</ul>" % "".join(KEPT))
    out["concepts/archive.dita"] = concept("archive", "<ul>%s</ul>" % "".join(KEPT).replace(' id="keep_days"', ""))
    out["concepts/limits.dita"] = concept("limits", '<p>See <xref href="retention.dita#retention/keep_days"/> for how '
                                                    'long the ledger keeps a posting.</p>')
    for name in ("month_end", "quarter_end", "year_end"):
        out["tasks/%s.dita" % name] = task(name, "<step><cmd>%s</cmd>%s</step>" % (CMD, INFO))
    for name, info in OTHER_INFO.items():
        out["tasks/%s.dita" % name] = task(name, "<step><cmd>%s</cmd>%s</step>" % (CMD, info))
    out["blocks_guide.ditamap"] = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" '
                                   '"map.dtd">\n<map><title>Ledgerline closing lists</title>%s</map>\n' % "".join(
                                       '<topicref href="%s"/>' % path for path in sorted(out)))
    return out


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "samples/dupes-blocks"
    for path, xml in files().items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as handle:
            handle.write(xml)
    print("wrote %s: %d files" % (root, len(files())))


if __name__ == "__main__":
    main()
