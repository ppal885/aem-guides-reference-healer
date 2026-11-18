#!/usr/bin/env python3
"""Writes samples/coverage-demo: one book that uses every kind of map and reference the owner asked
for (bookmap, part, chapter, appendix, frontmatter/backmatter, submap by mapref and by topicref,
topichead, topicgroup, reltable, keyscope, keydef in a submap; xref, link, conref, conrefend,
keyref, conkeyref, abbreviated-form), and breaks each kind once.

    python3 samples/gen_coverage.py samples/coverage-demo

v1 is the book as written; v2 is after a clean-up. truth.json lists each break: where, the kind of
map or reference, the old value and the value it should have now. Plain files, no customer content.
"""
import json
import os
import sys

TOPIC = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE %s PUBLIC "-//OASIS//DTD DITA %s//EN" "%s.dtd">\n'
MAP = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">\n'
BOOKMAP = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE bookmap PUBLIC "-//OASIS//DTD DITA BookMap//EN" "bookmap.dtd">\n'


def concept(cid, title, body):
    return TOPIC % ("concept", "Concept", "concept") + '<concept id="%s"><title>%s</title><conbody>%s</conbody></concept>\n' % (cid, title, body)


def task(tid, title, steps, related=""):
    return (TOPIC % ("task", "Task", "task") + '<task id="%s"><title>%s</title><taskbody><steps>%s</steps></taskbody>%s</task>\n'
            % (tid, title, steps, related))


def files(v2):
    """{path: xml} for one state of the book."""
    n = lambda old, new: new if v2 else old          # a name that the clean-up changed
    out = {}
    out["topics/notices.dita"] = concept("notices", "Notices", "<p>All rights reserved.</p>")
    out["topics/glossary.dita"] = concept("glossary", "Glossary", "<p>Terms used in this book.</p>")
    out["topics/gloss_sla.dita"] = (TOPIC % ("glossentry", "Glossary", "glossentry") +
                                    '<glossentry id="gloss_sla"><glossterm>Service level agreement</glossterm>'
                                    '<glossdef>The response times we promise.</glossdef>'
                                    '<glossBody><glossAlt><glossAcronym>SLA</glossAcronym></glossAlt></glossBody></glossentry>\n')
    out["reuse/warnings.dita"] = concept("warnings", "Shared warnings",
        '<note id="%s" type="warning">Back up the database before you upgrade.</note>'
        '<ol id="upgrade_steps"><li id="%s">Stop the service.</li><li id="li_copy">Copy the new files.</li>'
        '<li id="%s">Start the service.</li></ol>' % (n("note_backup", "note_take_backup"), n("li_stop", "li_halt"),
                                                      n("li_start", "li_resume")))
    out["topics/%s" % n("overview.dita", "product_overview.dita")] = concept("overview", "Product overview",
        '<p>The service answers within the <abbreviated-form keyref="%s"/>.</p>' % "sla")
    out["topics/install.dita"] = task("install", "Install the service",
        '<step><cmd>Read the <xref href="overview.dita">overview</xref> first.</cmd></step>'
        '<step><cmd>Check the <xref keyref="sys-req">system requirements</xref>.</cmd></step>'
        '<step><cmd>Back up first.</cmd><info><note conref="../reuse/warnings.dita#warnings/note_backup"/></info></step>',
        '<related-links><link href="upgrade.dita#upgrade"><linktext>Upgrade the service</linktext></link></related-links>')
    out["topics/upgrade.dita"] = task("upgrade", "Upgrade the service",
        '<step><cmd>Follow the shared steps.</cmd><info><ol><li conref="../reuse/warnings.dita#warnings/li_stop" '
        'conrefend="../reuse/warnings.dita#warnings/li_start"/></ol></info></step>'
        '<step><cmd>See the <xref keyref="admin.settings">settings</xref>.</cmd></step>')
    out["topics/requirements.dita"] = concept(n("requirements", "system_requirements"), "System requirements",
        '<p id="p_ram">8 GB of memory.</p>')
    out["topics/settings.dita"] = concept("settings", "Settings",
        '<note conkeyref="%s/note_backup"/><p>Settings are kept per site.</p>' % "warn-lib")
    out["topics/backup.dita"] = concept("backup", "Back up the service", "<p>Back up every night.</p>")
    out["topics/restore.dita"] = concept("restore", "Restore from a backup", "<p>Restore the last good copy.</p>")
    out["topics/faq.dita"] = concept("faq", "Questions", "<p>Answers to common questions.</p>")
    # A submap, reached from the book by mapref; it has its own key scope and key definitions.
    out["maps/%s" % n("admin.ditamap", "administration.ditamap")] = MAP + (
        '<map><title>Administration</title>'
        '<keydef keys="%s" href="../topics/settings.dita"/>'
        '<topicref href="../topics/backup.dita"/>'
        '<topichead navtitle="Recovery"><topicref href="../topics/restore.dita#%s"/></topichead>'
        '</map>\n' % (n("settings", "site-settings"), "restore"))
    out["book.ditamap"] = BOOKMAP + (
        '<bookmap><booktitle><mainbooktitle>Service guide</mainbooktitle></booktitle>'
        '<keydef keys="sys-req" href="topics/requirements.dita#%s"/>'
        '<keydef keys="%s" href="reuse/warnings.dita"/>'
        '<keydef keys="sla" href="topics/gloss_sla.dita"/>'
        '<frontmatter><notices href="topics/notices.dita"/></frontmatter>'
        '<chapter href="topics/%s"/>'
        '<part navtitle="Running the service"><chapter href="topics/install.dita"><topicref href="topics/upgrade.dita"/></chapter></part>'
        '<chapter navtitle="Administration"><mapref href="maps/admin.ditamap" keyscope="admin"/></chapter>'
        '<appendix href="topics/requirements.dita"/>'
        '<topicgroup><topicref href="topics/faq.dita"/></topicgroup>'
        '<reltable><relrow><relcell><topicref href="topics/install.dita"/></relcell>'
        '<relcell><topicref href="topics/backup.dita"/></relcell></relrow></reltable>'
        '<backmatter><booklists><glossarylist href="topics/glossary.dita"/></booklists></backmatter>'
        '</bookmap>\n' % ("requirements", n("warn-lib", "warnings-lib"), n("overview.dita", "overview.dita")))
    return out


TRUTH = [
    # where, kind of map or reference, attribute, old value, value now (None: no target any more)
    ("topics/install.dita", "xref to a topic whose file was renamed", "href", "overview.dita", "product_overview.dita"),
    ("book.ditamap", "chapter in a bookmap, file renamed", "href", "topics/overview.dita", "topics/product_overview.dita"),
    ("book.ditamap", "mapref to a submap that was renamed", "href", "maps/admin.ditamap", "maps/administration.ditamap"),
    ("book.ditamap", "keydef whose topic id was renamed", "href", "topics/requirements.dita#requirements",
     "topics/requirements.dita#system_requirements"),
    ("topics/install.dita", "conref to a renamed element", "conref", "../reuse/warnings.dita#warnings/note_backup",
     "../reuse/warnings.dita#warnings/note_take_backup"),
    ("topics/upgrade.dita", "conref range: start renamed", "conref", "../reuse/warnings.dita#warnings/li_stop",
     "../reuse/warnings.dita#warnings/li_halt"),
    ("topics/upgrade.dita", "conref range: end renamed", "conrefend", "../reuse/warnings.dita#warnings/li_start",
     "../reuse/warnings.dita#warnings/li_resume"),
    ("topics/upgrade.dita", "scoped keyref into a submap whose key was renamed", "keyref", "admin.settings",
     "admin.site-settings"),
    ("topics/settings.dita", "conkeyref whose key was renamed", "conkeyref", "warn-lib/note_backup",
     "warnings-lib/note_take_backup"),
]


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "samples/coverage-demo"
    for state in ("v1", "v2"):
        for path, xml in files(state == "v2").items():
            full = os.path.join(root, state, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as handle:
                handle.write(xml)
    with open(os.path.join(root, "truth.json"), "w") as handle:
        json.dump([dict(zip(("file", "kind", "attribute", "old", "now"), row)) for row in TRUTH], handle, indent=1)
    print("wrote %s: %d breaks" % (root, len(TRUTH)))


if __name__ == "__main__":
    main()
