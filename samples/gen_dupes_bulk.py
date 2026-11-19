#!/usr/bin/env python3
"""Writes samples/dupes-bulk: 120 made-up topics that share three notes word for word, and a map.
Used to time "Fix all safe" (how long a run of 100 topics takes in AEM), not to score the agent.

    python3 samples/gen_dupes_bulk.py samples/dupes-bulk
    ROOT=/content/dam/dupes-bulk ./samples/load_dupes_bulk.sh

Made-up product ("Ledgerline"); no customer content.
"""
import os
import sys

TOPICS = 120
HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">\n'
NOTES = [
    "Back up the ledger database before you change a posting rule, so that you can go back if the rule is wrong.",
    "Only a ledger administrator can change a posting rule, and every change is written to the audit log.",
    "A posting rule takes effect at the start of the next period, not in the period that is open now.",
]


def files():
    out = {}
    for n in range(1, TOPICS + 1):
        notes = "".join('<note type="caution">%s</note>' % note for note in NOTES)
        out["rules/rule_%03d.dita" % n] = HEAD + (
            '<topic id="rule_%03d"><title>Posting rule %d</title><body><p>Posting rule %d moves amounts between '
            'account group %d and account group %d.</p>%s</body></topic>\n' % (n, n, n, n, n + 1, notes))
    out["bulk_guide.ditamap"] = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" '
                                 '"map.dtd">\n<map><title>Ledgerline posting rules</title>%s</map>\n' % "".join(
                                     '<topicref href="%s"/>' % path for path in sorted(out)))
    return out


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "samples/dupes-bulk"
    for path, xml in files().items():
        full = os.path.join(root, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w") as handle:
            handle.write(xml)
    print("wrote %s: %d topics, %d notes copied into each" % (root, TOPICS, len(NOTES)))


if __name__ == "__main__":
    main()
