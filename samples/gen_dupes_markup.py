#!/usr/bin/env python3
"""Writes samples/dupes-markup: copied text that holds markup, to check that a shared piece keeps it.

  - a step's command copied into four tasks, with <uicontrol> and <b>; in one task the same words
    have no <b> (other markup: left as it is);
  - a paragraph with a link (<xref>) to a topic in another folder, copied into three concepts.

    python3 samples/gen_dupes_markup.py samples/dupes-markup
    ./samples/load_dupes_markup.sh

Made-up product ("Ledgerline"); no customer content.
"""
import os
import sys

TASK = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">\n'
CONCEPT = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">\n'
REFERENCE = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "reference.dtd">\n'

CMD = 'Open <uicontrol>Periods</uicontrol> and select <b>Close</b> for the period that you want to close now.'
CMD_PLAIN = 'Open <uicontrol>Periods</uicontrol> and select Close for the period that you want to close now.'
LINK = ('Before you close a period, read <xref href="../reference/limits.dita" format="dita">Ledger limits</xref> '
        'so that you know what the ledger keeps.')


def files():
    out = {}
    for n, (name, cmd) in enumerate([("month_end", CMD), ("quarter_end", CMD), ("year_end", CMD), ("adjustments", CMD_PLAIN)], 1):
        out["tasks/%s.dita" % name] = TASK + (
            '<task id="%s"><title>Close the %s</title><taskbody><steps><step><cmd>%s</cmd></step>'
            '<step><cmd>Review the summary for step %d.</cmd></step></steps></taskbody></task>\n' % (name, name.replace("_", " "), cmd, n))
    for name in ("periods", "postings", "audits"):
        out["concepts/%s.dita" % name] = CONCEPT + (
            '<concept id="%s"><title>About %s</title><conbody><p>%s</p></conbody></concept>\n' % (name, name, LINK))
    out["reference/limits.dita"] = REFERENCE + (
        '<reference id="limits"><title>Ledger limits</title><refbody><section><p>The ledger keeps 90 days.</p>'
        '</section></refbody></reference>\n')
    out["steps_guide.ditamap"] = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" '
                                  '"map.dtd">\n<map><title>Ledgerline closing steps</title>%s</map>\n' % "".join(
                                      '<topicref href="%s"/>' % path for path in sorted(out)))
    return out


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "samples/dupes-markup"
    for path, xml in files().items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as handle:
            handle.write(xml)
    print("wrote %s: %d files" % (root, len(files())))


if __name__ == "__main__":
    main()
