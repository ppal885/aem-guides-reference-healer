#!/usr/bin/env python3
"""Writes a small sample where every broken reference has two plausible new targets (garage-week PoC).

    python3 samples/gen_rank.py [samples/rank-demo]

The large sample has one such case. This one has eight, to measure ranking: v1 is the content
before a clean-up, v2 after it. In v2 each old id, key or file is gone and two pieces could be
what a topic meant. Which one is right follows from the sentence the reference sits in, so the
right answer per reference is known (expected.json). rankeval.py scores the finder against it.
"""
import json
import os
import sys

HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE %s PUBLIC "-//OASIS//DTD DITA %s//EN" "%s.dtd">\n'


def topic(topic_id, title, body):
    return HEAD % ("topic", "Topic", "topic") + '<topic id="%s">\n  <title>%s</title>\n  <body>\n%s  </body>\n</topic>\n' % (
        topic_id, title, "".join("    %s\n" % line for line in body))


# Shared content: (id, element, text) per version.
LIB_V1 = [
    ("backup-note", "note", "Back up your data before you upgrade. Backups are kept for 30 days."),
    ("restore-note", "note", "Restore takes up to an hour. Restoring replaces all data written after the backup."),
    ("api-rate-limit", "p", "The API accepts 600 requests per minute for each key."),
    ("burn-warning", "note", "The plate is hot during operation. Do not touch it."),
]
LIB_V2 = [
    ("backup-before-upgrade", "note", "Back up your data before you upgrade."),
    ("backup-retention", "note", "Backups are kept for 30 days."),
    ("restore-duration", "note", "Restore takes up to an hour."),
    ("restore-overwrites", "note", "Restoring replaces all data written after the backup."),
    ("api-request-limit", "p", "Each key may send 600 requests per minute to the API."),
    ("api-burst-limit", "p", "A key may send a burst of 100 requests in one second."),
    ("hot-plate", "note", "The plate stays hot during and after operation. Do not touch it."),
    ("fire-hazard", "note", "Keep paper and cloth away from the plate. They can catch fire."),
]
INSTALL_V1 = [("install-linux", "section", "Install on Linux", "Download the package and run the installer as root.")]
INSTALL_V2 = [
    ("install-on-linux-x86", "section", "Install on Linux (x86)", "Download the x86 package and run the installer as root."),
    ("install-on-linux-arm", "section", "Install on Linux (ARM)", "Download the ARM package and run the installer as root."),
]
KEYS_V1 = [("product-admin", "Admin Console"), ("support-email", "support@atlas.example")]
KEYS_V2 = [("admin-console", "Admin Console"), ("admin-api", "Admin API"),
           ("support-contact", "the support portal"), ("sales-contact", "your sales contact")]

# One referencing topic per case: (file, title, body with the reference, attribute, old value, right new value).
CASES = [
    ("upgrade.dita", "Upgrade to version 5", '<p>Before you start the upgrade:</p><note conref="lib.dita#lib/backup-note"/>',
     "conref", "lib.dita#lib/backup-note", "lib.dita#lib/backup-before-upgrade"),
    ("retention.dita", "How long data is kept", '<p>Old backups are removed automatically.</p><note conref="lib.dita#lib/backup-note"/>',
     "conref", "lib.dita#lib/backup-note", "lib.dita#lib/backup-retention"),
    ("plan_downtime.dita", "Plan the downtime", '<p>Tell your users how long the service is unavailable.</p><note conref="lib.dita#lib/restore-note"/>',
     "conref", "lib.dita#lib/restore-note", "lib.dita#lib/restore-duration"),
    ("throttling.dita", "Throttling", '<p>Calls above the steady limit are rejected with 429.</p><p conref="lib.dita#lib/api-rate-limit"/>',
     "conref", "lib.dita#lib/api-rate-limit", "lib.dita#lib/api-request-limit"),
    ("cleaning.dita", "Clean the device", '<p>Wait ten minutes after you switch it off.</p><note conref="lib.dita#lib/burn-warning"/>',
     "conref", "lib.dita#lib/burn-warning", "lib.dita#lib/hot-plate"),
    ("arm_servers.dita", "Run on ARM servers", '<p>ARM servers need their own package, see <xref href="install.dita#install/install-linux"/>.</p>',
     "href", "install.dita#install/install-linux", "install.dita#install/install-on-linux-arm"),
    ("manage_users.dita", "Manage users", '<p>Open <ph keyref="product-admin"/> and choose Users.</p>',
     "keyref", "product-admin", "admin-console"),
    ("get_help.dita", "Get help", '<p>If the error stays, write to <ph keyref="support-email"/> and attach the log.</p>',
     "keyref", "support-email", "support-contact"),
    ("change_card.dita", "Change your card", '<p>To replace the card on file, see <xref href="billing_overview.dita"/>.</p>',
     "href", "billing_overview.dita", "billing_payment_methods.dita"),
]


def shared(version):
    lib = LIB_V1 if version == 1 else LIB_V2
    install = INSTALL_V1 if version == 1 else INSTALL_V2
    files = {
        "lib.dita": topic("lib", "Shared notes", ['<%s id="%s">%s</%s>' % (tag, i, text, tag) for i, tag, text in lib]),
        "install.dita": topic("install", "Install", ['<section id="%s"><title>%s</title><p>%s</p></section>' % (i, t, text)
                                                    for i, _, t, text in install]),
    }
    if version == 1:
        files["billing_overview.dita"] = topic("billing_overview", "Billing overview", ["<p>Invoices, and the card or bank account you pay with.</p>"])
    else:
        files["billing_invoices.dita"] = topic("billing_invoices", "Invoices", ["<p>Where to find and download your invoices.</p>"])
        files["billing_payment_methods.dita"] = topic("billing_payment_methods", "Payment methods",
                                                      ["<p>Add, replace or remove the card or bank account you pay with.</p>"])
    keys = KEYS_V1 if version == 1 else KEYS_V2
    refs = sorted(set(files) | {case[0] for case in CASES})
    files["guide.ditamap"] = HEAD % ("map", "Map", "map") + "<map>\n  <title>Atlas guide</title>\n" + "".join(
        '  <keydef keys="%s"><topicmeta><keywords><keyword>%s</keyword></keywords></topicmeta></keydef>\n' % k for k in keys) + "".join(
        '  <topicref href="%s"/>\n' % name for name in refs) + "</map>\n"
    return files


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "rank-demo")
    for version in (1, 2):
        files = shared(version)
        for name, title, body, _, _, _ in CASES:
            files[name] = topic(name[:-5], title, [body])
        folder = os.path.join(out, "v%d" % version)
        os.makedirs(folder, exist_ok=True)
        for name, xml in files.items():
            with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
                handle.write(xml)
    with open(os.path.join(out, "expected.json"), "w", encoding="utf-8") as handle:
        json.dump([{"file": c[0], "attribute": c[3], "old": c[4], "right": c[5]} for c in CASES], handle, indent=1)
    print("Wrote %s: %d cases, each with two plausible targets" % (out, len(CASES)))


if __name__ == "__main__":
    main()
