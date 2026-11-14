#!/usr/bin/env python3
"""Writes a large DITA sample for the reference healer demo (garage-week PoC). Stdlib only.

    python3 samples/gen_large.py samples/large-demo

Produces two versions of the same documentation set for a made-up product:

    v1/  the set as it was: every reference resolves
    v2/  the set after a clean-up of the shared content: ids and keys were renamed, and a few
         reused pieces were reworded, removed, merged or moved to a new file. Nobody updated
         the topics that use them

The topics are generated from templates, so the prose is repetitive. What matters for the demo is
the shape: a few shared files and one map of keys, used from a few hundred topics by conref,
conkeyref, keyref and xref. Only the shared files and the map differ between v1 and v2
(v2 also has two new files).

Also writes expected.json: for each renamed or removed thing, what a correct repair is.
"""
import json
import os
import random
import sys

TOPIC = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">\n'
TASK = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">\n'
MAP = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">\n'

AREAS = [("accounts", "Accounts"), ("billing", "Billing"), ("storage", "Storage"), ("compute", "Compute"),
         ("networking", "Networking"), ("security", "Security"), ("monitoring", "Monitoring"),
         ("backup", "Backup"), ("api", "API"), ("cli", "Command line"), ("migration", "Migration")]
ACTIONS = ["Create", "Configure", "Rename", "Delete", "Share", "Export", "Restore", "Rotate", "Audit", "Resize",
           "Move", "Tag", "Lock", "Schedule", "Monitor", "Clone", "Archive", "Upgrade", "Limit", "Test"]
THINGS = {"accounts": "a user account", "billing": "a payment method", "storage": "a storage bucket",
          "compute": "a virtual machine", "networking": "a private network", "security": "an access key",
          "monitoring": "an alert rule", "backup": "a backup plan", "api": "an API token", "cli": "a CLI profile",
          "migration": "a migration job"}

# Reused notes: (id, type, text). Used by conref and, through the key "warnings", by conkeyref.
WARNINGS = [
    ("data-loss", "warning", "This action permanently deletes data. It cannot be undone."),
    ("downtime", "caution", "The service is unavailable for a few minutes while this change is applied."),
    ("billing-impact", "note", "This change can increase your monthly bill."),
    ("admin-only", "note", "Only an administrator of the organisation can do this."),
    ("region-lock", "note", "The region cannot be changed after the resource is created."),
    ("slow-operation", "note", "This operation can take up to an hour for large resources."),
    ("quota", "note", "Your plan limits how many resources of this kind you can create."),
    ("audit-logged", "note", "This action is recorded in the audit log."),
    ("mfa-required", "important", "You are asked for a second sign-in factor before this change is saved."),
    ("irreversible-key", "warning", "A deleted key cannot be restored. Applications that use it stop working at once."),
]
# Reused paragraphs: (id, text). Used by conref.
PARAS = [
    ("open-console", "Sign in to the console and select your organisation in the top bar."),
    ("need-help", "If the problem continues, contact support and include the request ID shown in the error."),
    ("propagation", "Changes can take up to five minutes to reach every region."),
    ("naming-rules", "Names can contain lowercase letters, digits and hyphens, and must start with a letter."),
    ("cli-install", "Install the command-line tool before you run the commands in this topic."),
    ("default-region", "Unless you choose otherwise, new resources are created in your default region."),
    ("trial-limits", "Trial organisations have lower limits than paid organisations."),
    ("legacy-ui", "The old settings page is still available until the end of the year."),
]
# Keys with text: (name, keyword).
KEYS = [
    ("product-name", "Atlas Cloud"), ("console-name", "Atlas Console"), ("cli-name", "atlasctl"),
    ("support-email", "support@atlas.example"), ("company-name", "Atlas Systems"), ("api-version", "v3"),
    ("free-plan", "Starter plan"), ("paid-plan", "Business plan"), ("max-buckets", "100"),
    ("retention-days", "30 days"), ("default-region", "eu-west-1"), ("sso-product", "Atlas Identity"),
    ("mobile-app", "Atlas Mobile"), ("status-page", "status.atlas.example"),
]
# Sections of the two reference topics that other topics link to: (id, title, body).
LIMITS = [
    ("api-rate-limits", "API rate limits", "Each token can make 600 requests per minute."),
    ("storage-limits", "Storage limits", "A bucket can hold objects of up to 5 TB each."),
    ("account-limits", "Account limits", "An organisation can have up to 500 user accounts."),
    ("network-limits", "Network limits", "Each region can have up to 20 private networks."),
]
ERRORS = [
    ("permission-denied", "Permission denied", "Your role does not allow this action."),
    ("quota-exceeded", "Quota exceeded", "You reached the limit of your plan."),
    ("resource-locked", "Resource locked", "Another change is still being applied to this resource."),
    ("invalid-name", "Invalid name", "The name does not follow the naming rules."),
]

# What the clean-up changed. kind:
#   rename  new id, content untouched (an earlier version of the file proves it)
#   reword  new id and reworded
#   remove  gone, nothing replaces it
#   move    moved to another file (new file, new topic id, new id), reworded on the way
#   merge   two pieces became one; both old ids now mean the merged piece
#   split   one piece became two; either may be what a topic meant (the first one named is the
#           closer match, the second is the other half)
CHANGES = {
    "warnings": {
        "data-loss": ("rename", "permanent-delete", None),
        "downtime": ("rename", "service-interruption", None),
        "billing-impact": ("rename", "cost-increase", None),
        "admin-only": ("reword", "requires-org-admin", "You need the organisation administrator role for this."),
        "mfa-required": ("rename", "second-factor", None),
        "slow-operation": ("remove", None, None),
        "region-lock": ("merge", "plan-and-region-limits", None),
        "quota": ("merge", "plan-and-region-limits", None),
    },
    "paras": {
        "open-console": ("rename", "sign-in-console", None),
        "need-help": ("rename", "contact-support", None),
        "propagation": ("reword", "regional-delay", "A change reaches every region within about five minutes."),
        "legacy-ui": ("remove", None, None),
        "cli-install": ("move", "shared/setup.dita#setup/install-cli", None),
        "trial-limits": ("split", "trial-resource-limits", "trial-support-level"),
    },
    "keys": {
        "console-name": ("rename", "web-console-name", None),
        "cli-name": ("rename", "cli-tool-name", None),
        "free-plan": ("rename", "plan-starter", None),
        "retention-days": ("rename", "backup-retention", None),
        "sso-product": ("reword", "identity-product", "Atlas Identity Hub"),
        "warnings": ("rename", "shared-warnings", None),
    },
    "limits": {
        "api-rate-limits": ("rename", "rate-limits", None),
        "account-limits": ("reword", "organisation-limits", "Organisation limits"),
        "storage-limits": ("move", "reference/storage.dita#storage/object-size", None),
    },
    "errors": {
        "permission-denied": ("rename", "error-403", None),
        "quota-exceeded": ("rename", "error-quota", None),
    },
}


def apply(items, changes, text_index):
    """items after the clean-up."""
    result = []
    for item in items:
        kind, new_id, new_text = changes.get(item[0], (None, None, None))
        if kind in ("remove", "move", "merge", "split"):
            continue
        item = list(item)
        if kind:
            item[0] = new_id
        if kind == "reword":
            item[text_index] = new_text
        result.append(tuple(item))
    return result


def shared_files(version):
    changed = version == "v2"
    warnings = apply(WARNINGS, CHANGES["warnings"], 2) if changed else WARNINGS
    paras = apply(PARAS, CHANGES["paras"], 1) if changed else PARAS
    limits = apply(LIMITS, CHANGES["limits"], 1) if changed else LIMITS
    errors = apply(ERRORS, CHANGES["errors"], 1) if changed else ERRORS
    files = {}
    merged = ('    <note id="plan-and-region-limits" type="note">Your plan limits how many resources of this kind you can '
              'create, and a resource stays in the region it was created in.</note>\n') if changed else ""
    files["shared/warnings.dita"] = TOPIC + '<topic id="warnings">\n  <title>Shared warnings and notes</title>\n  <body>\n' + "".join(
        '    <note id="%s" type="%s">%s</note>\n' % w for w in warnings) + merged + "  </body>\n</topic>\n"
    if changed:
        files["shared/setup.dita"] = TOPIC + ('<topic id="setup">\n  <title>Shared set-up paragraphs</title>\n  <body>\n'
            '    <p id="install-cli">Install the atlasctl command-line tool before you run the commands in this topic.</p>\n'
            '  </body>\n</topic>\n')
        files["reference/storage.dita"] = TOPIC + ('<topic id="storage">\n  <title>Storage reference</title>\n  <body>\n'
            '    <section id="object-size"><title>Object size limits</title><p>A bucket can hold objects of up to 5 TB each.</p></section>\n'
            '  </body>\n</topic>\n')
    halves = ('    <p id="trial-resource-limits">Trial organisations can create fewer resources than paid organisations.</p>\n'
              '    <p id="trial-support-level">Trial organisations get email support only.</p>\n') if changed else ""
    files["shared/paragraphs.dita"] = TOPIC + '<topic id="paragraphs">\n  <title>Shared paragraphs</title>\n  <body>\n' + "".join(
        '    <p id="%s">%s</p>\n' % p for p in paras) + halves + "  </body>\n</topic>\n"
    files["reference/limits.dita"] = TOPIC + '<topic id="limits">\n  <title>Limits</title>\n  <body>\n' + "".join(
        '    <section id="%s"><title>%s</title><p>%s</p></section>\n' % s for s in limits) + "  </body>\n</topic>\n"
    files["reference/errors.dita"] = TOPIC + '<topic id="errors">\n  <title>Error messages</title>\n  <body>\n' + "".join(
        '    <section id="%s"><title>%s</title><p>%s</p></section>\n' % s for s in errors) + "  </body>\n</topic>\n"
    return files


def topic_file(rng, area, area_title, action, number):
    """One task topic. Returns (relative path, xml). Identical in v1 and v2."""
    thing = THINGS[area]
    name = "%s_%s_%02d" % (area, action.lower(), number)
    warn = rng.sample(WARNINGS, 2)
    para = rng.sample(PARAS, 2)
    keys = rng.sample(KEYS, 3)
    limit, error = rng.choice(LIMITS), rng.choice(ERRORS)
    up = "../"
    xml = TASK + """<task id="%(id)s">
  <title>%(action)s %(thing)s</title>
  <shortdesc>How to %(action_lower)s %(thing)s in <ph keyref="%(k0)s"/>.</shortdesc>
  <taskbody>
    <prereq>
      <p conref="%(up)sshared/paragraphs.dita#paragraphs/%(p0)s"/>
      <note conref="%(up)sshared/warnings.dita#warnings/%(w0)s"%(internal)s/>
    </prereq>
    <steps>
      <step><cmd>Open the %(area_title)s page.</cmd>
        <info>You can also use <ph keyref="%(k1)s"/> for this step.</info></step>
      <step><cmd>Select %(thing)s and choose %(action)s.</cmd>
        <info><note conkeyref="warnings/%(w1)s"/></info></step>
      <step><cmd>Confirm the change.</cmd>
        <info>Limits are listed in <xref href="%(up)sreference/limits.dita#limits/%(limit)s"/>.</info></step>
    </steps>
    <result>
      <p conref="%(up)sshared/paragraphs.dita#paragraphs/%(p1)s"/>
      <p>This applies to the <ph keyref="%(k2)s"/> as well. If you see an error, read
        <xref href="%(up)sreference/errors.dita#errors/%(error)s"/>.</p>
    </result>
  </taskbody>
</task>
""" % {"id": name, "action": action, "action_lower": action.lower(), "thing": thing, "area_title": area_title,
       "up": up, "w0": warn[0][0], "w1": warn[1][0], "p0": para[0][0], "p1": para[1][0],
       "k0": keys[0][0], "k1": keys[1][0], "k2": keys[2][0], "limit": limit[0], "error": error[0],
       # Every fifth topic keeps its first warning for internal readers only: an output that filters
       # audience="internal" does not publish that reference, so a repair to it does not reach that output.
       "internal": ' audience="internal"' if number % 5 == 0 else ""}
    return "%s/%s.dita" % (area, name), xml


INTERNAL_AREA = "monitoring"
DITAVAL = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE val PUBLIC "-//OASIS//DTD DITA DITAVAL//EN" "ditaval.dtd">\n'
           '<val>\n  <prop att="audience" val="internal" action="exclude"/>\n</val>\n')


def map_file(version, topic_paths):
    changed = version == "v2"
    keys = apply(KEYS, CHANGES["keys"], 1) if changed else KEYS
    warnings_key = CHANGES["keys"]["warnings"][1] if changed else "warnings"
    lines = [MAP + '<map id="atlas_guide">', "  <title>Atlas Cloud Administrator Guide</title>"]
    for name, keyword in keys:
        lines.append('  <keydef keys="%s"><topicmeta><keywords><keyword>%s</keyword></keywords></topicmeta></keydef>' % (name, keyword))
    lines.append('  <keydef keys="%s" href="shared/warnings.dita" processing-role="resource-only"/>' % warnings_key)
    # A key definition that points at one section. Its target id is renamed in v2 and the
    # definition is not updated: the broken reference sits on the key definition itself.
    lines.append('  <keydef keys="rate-limits-section" href="reference/limits.dita#limits/api-rate-limits"/>')
    lines.append('  <topicref href="shared/paragraphs.dita" processing-role="resource-only"/>')
    if changed:
        lines.append('  <topicref href="shared/setup.dita" processing-role="resource-only"/>')
    current = None
    for path in topic_paths:
        area = path.split("/")[0]
        if area != current:
            if current:
                lines.append("  </topichead>")
            # One whole area is for internal readers only.
            lines.append('  <topichead navtitle="%s"%s>' % (dict(AREAS)[area], ' audience="internal"' if area == INTERNAL_AREA else ""))
            current = area
        lines.append('    <topicref href="%s"/>' % path)
    lines.append("  </topichead>")
    lines.append('  <topichead navtitle="Reference">')
    lines.append('    <topicref href="reference/limits.dita"/>')
    lines.append('    <topicref href="reference/errors.dita"/>')
    if changed:
        lines.append('    <topicref href="reference/storage.dita"/>')
    lines.append("  </topichead>")
    lines.append("</map>")
    return "\n".join(lines) + "\n"


def expected():
    """For each old name: the new name, or None when it was removed. With how it changed."""
    result = {}
    for group, changes in CHANGES.items():
        for old, (kind, new, _text) in changes.items():
            result["%s:%s" % (group, old)] = {"kind": kind, "new": new}
    return result


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "large-demo"
    rng = random.Random(2026)
    topics = []
    for area, area_title in AREAS:
        for number, action in enumerate(ACTIONS, 1):
            topics.append(topic_file(rng, area, area_title, action, number))
    for version in ("v1", "v2"):
        files = dict(topics)
        files.update(shared_files(version))
        files["atlas_guide.ditamap"] = map_file(version, [path for path, _ in topics])
        for path, xml in files.items():
            full = os.path.join(out, version, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as handle:
                handle.write(xml)
    # Next to the two versions, not inside them: a filter for an output preset, not part of the map.
    with open(os.path.join(out, "customer.ditaval"), "w", encoding="utf-8") as handle:
        handle.write(DITAVAL)
    with open(os.path.join(out, "expected.json"), "w") as handle:
        json.dump(expected(), handle, indent=1)
    print("Wrote %d files per version to %s" % (len(topics) + 5, out))


if __name__ == "__main__":
    main()
