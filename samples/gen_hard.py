#!/usr/bin/env python3
"""Writes a small sample where the obvious new target is the wrong one (garage-week PoC).

    python3 samples/gen_hard.py [samples/hard-demo]

The other samples hold no case where the finder agent's first candidate is wrong, so they cannot
show what the reviewer agent is for. Here every broken reference has a decoy: a piece of the new
content whose name or wording is closer to the old one than the right target is. v1 is the
content before a clean-up, v2 after it. What is right follows from what the old piece said and
from the topic the reference sits in (expected.json; "right": null means the content is gone
and nothing replaces it). hardeval.py scores the agents against it.

Each case is something a writing team does: rewords a piece and gives it a better id, splits a
warning by product, moves a limit to another file, retires a piece and adds a similar one.
"""
import json
import os
import sys

HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE %s PUBLIC "-//OASIS//DTD DITA %s//EN" "%s.dtd">\n'


def topic(topic_id, title, body):
    return HEAD % ("topic", "Topic", "topic") + '<topic id="%s">\n  <title>%s</title>\n  <body>\n%s  </body>\n</topic>\n' % (
        topic_id, title, "".join("    %s\n" % line for line in body))


def pieces(items):
    return ['<%s id="%s">%s</%s>' % (tag, name, text, tag) for name, tag, text in items]


LIB_V1 = [
    ("timeout", "p", "A request that takes longer than 30 seconds is cancelled."),
    ("warn-power", "note", "Disconnect the power before you open the cabinet."),
    ("beta-note", "note", "Scheduled exports are in beta. Do not rely on them for audits."),
    ("tls-required", "p", "Connections must use TLS 1.2 or later."),
    ("restart-note", "note", "Restart the agent after you change its configuration file."),
]
LIB_V2 = [
    # timeout: the decoy keeps the word in its id; the right one says what the old one said.
    ("session-timeout", "p", "A session ends after 30 minutes without activity."),
    ("request-limit", "p", "The service cancels any request that runs for more than 30 seconds."),
    # warn-power: split by product; the topic says which product it is about.
    ("warn-power-a100", "note", "Disconnect the power before you open the A100 cabinet."),
    ("warn-power-b200", "note", "Disconnect both power feeds before you open the B200 cabinet."),
    # beta-note: gone for good (exports left beta); the decoy is about another feature.
    ("preview-note", "note", "Scheduled reports are in preview. Their format can change."),
    # tls-required: the decoy shares the words and says the opposite.
    ("tls-optional", "p", "TLS is optional for connections inside the private network."),
    ("min-tls", "p", "The lowest TLS version the service accepts is 1.2."),
    # restart-note: the decoy has the same sentence shape, for another thing.
    ("restart-after-cert", "note", "Restart the agent after you replace its certificate."),
    ("reload-config", "note", "After you edit the configuration file of the agent, restart it."),
]
LIMITS_V1 = [("max-users", "p", "A workspace holds up to 500 users.")]
LIMITS_V2 = [("max-guests", "p", "A workspace holds up to 50 guests.")]           # the decoy stays in the old file
QUOTAS_V2 = [("user-quota", "p", "Each workspace is limited to 500 users.")]       # the limit moved here
KEYS_V1 = [("support-email", "support@atlas.example")]
KEYS_V2 = [("support-phone", "+1 555 0100"), ("help-contact", "help@atlas.example")]

# (file, title, body with the reference, attribute, old value, right new value or None, the decoy)
CASES = [
    ("api_errors.dita", "API errors", '<p>A 504 means the call ran too long.</p><p conref="lib.dita#lib/timeout"/>',
     "conref", "lib.dita#lib/timeout", "lib.dita#lib/request-limit", "lib.dita#lib/session-timeout"),
    ("service_b200.dita", "Service the B200", '<p>Before you replace a fan of the B200:</p><note conref="lib.dita#lib/warn-power"/>',
     "conref", "lib.dita#lib/warn-power", "lib.dita#lib/warn-power-b200", "lib.dita#lib/warn-power-a100"),
    ("exports.dita", "Schedule an export", '<p>You can schedule an export for every night.</p><note conref="lib.dita#lib/beta-note"/>',
     "conref", "lib.dita#lib/beta-note", None, "lib.dita#lib/preview-note"),
    ("security.dita", "Security requirements", '<p>Clients that connect from the internet:</p><p conref="lib.dita#lib/tls-required"/>',
     "conref", "lib.dita#lib/tls-required", "lib.dita#lib/min-tls", "lib.dita#lib/tls-optional"),
    ("tune_agent.dita", "Tune the agent", '<p>Set <codeph>workers</codeph> in <filepath>agent.conf</filepath>.</p>'
     '<note conref="lib.dita#lib/restart-note"/>',
     "conref", "lib.dita#lib/restart-note", "lib.dita#lib/reload-config", "lib.dita#lib/restart-after-cert"),
    ("invite_users.dita", "Invite users", '<p>You cannot invite more people than the plan allows. '
     'See <xref href="limits.dita#limits/max-users"/>.</p>',
     "href", "limits.dita#limits/max-users", "quotas.dita#quotas/user-quota", "limits.dita#limits/max-guests"),
    ("failed_upgrade.dita", "If the upgrade fails", '<p>Send the log file to <keyword keyref="support-email"/>.</p>',
     "keyref", "support-email", "help-contact", "support-phone"),
    ("move_linux.dita", "Move to a new server", '<p>On the new server, follow <xref href="install_linux.dita"/>.</p>',
     "href", "install_linux.dita", "linux_setup.dita", "install_linux_arm.dita"),
]


def write(root, version, name, text):
    os.makedirs(os.path.join(root, version), exist_ok=True)
    with open(os.path.join(root, version, name), "w", encoding="utf-8") as handle:
        handle.write(text)


def keymap(keys, files):
    lines = ['  <keydef keys="%s"><topicmeta><keywords><keyword>%s</keyword></keywords></topicmeta></keydef>' % key for key in keys]
    lines += ['  <topicref href="%s"/>' % name for name in files]
    return HEAD % ("map", "Map", "map") + '<map id="guide">\n  <title>Atlas guide</title>\n%s\n</map>\n' % "\n".join(lines)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "hard-demo")
    users = [case[0] for case in CASES]
    install = ['<p>Download the package for x86 servers and run the installer as root.</p>']
    for version, lib, limits, keys in (("v1", LIB_V1, LIMITS_V1, KEYS_V1), ("v2", LIB_V2, LIMITS_V2, KEYS_V2)):
        write(root, version, "lib.dita", topic("lib", "Shared notes", pieces(lib)))
        write(root, version, "limits.dita", topic("limits", "Limits", pieces(limits)))
        for name, title, body, _, _, _, _ in CASES:
            write(root, version, name, topic(name[:-5], title, [body]))
    write(root, "v1", "install_linux.dita", topic("install_linux", "Install on Linux", install))
    write(root, "v1", "guide.ditamap", keymap(KEYS_V1, ["lib.dita", "limits.dita", "install_linux.dita"] + users))
    # install_linux.dita: renamed; the decoy keeps the old name's words.
    write(root, "v2", "linux_setup.dita", topic("linux_setup", "Install on Linux", install))
    write(root, "v2", "install_linux_arm.dita", topic("install_linux_arm", "Install on Linux (ARM)",
                                                      ['<p>Download the package for ARM servers and run the installer as root.</p>']))
    write(root, "v2", "quotas.dita", topic("quotas", "Quotas", pieces(QUOTAS_V2)))
    write(root, "v2", "guide.ditamap", keymap(KEYS_V2, ["lib.dita", "limits.dita", "quotas.dita", "linux_setup.dita",
                                                        "install_linux_arm.dita"] + users))
    with open(os.path.join(root, "expected.json"), "w", encoding="utf-8") as handle:
        json.dump([{"file": name, "attribute": attribute, "old": old, "right": right, "decoy": decoy}
                   for name, _, _, attribute, old, right, decoy in CASES], handle, indent=1)
    print("Wrote %d cases to %s" % (len(CASES), root))


if __name__ == "__main__":
    main()
