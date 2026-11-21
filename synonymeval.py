#!/usr/bin/env python3
"""Does the finder need a search by meaning? (garage-week PoC)

    python3 synonymeval.py [--runs 2] [--backend cli|sdk] [--model opus] [--out eval/refs/synonym-eval.json]

The finder's search tools match words: file names, titles, ids and element text. This sample is
written so that words do not help. Ten links point at pieces that were renamed and reworded in a
clean-up; the link's text, the old id and the old file name share no word with the new id, the new
title or the new text ("Sign in" is now "Log on to the console", id "authenticate"). Two more links
point at content that was removed and has no replacement. Three pieces are decoys: they share a
word with an old name and mean something else ("Password policy" for "Reset a forgotten password").
There are no previous versions, so nothing can be proven from history.

Per reference:

    right     the proposed target is the one the link meant (or nothing is proposed for removed content)
    wrong     a target is proposed and it is not the right one
    missed    a right target exists and nothing is proposed

and whether a wrong target was applied without asking (verdict "fix"), which must be 0.

If the finder is right here, a search by meaning (embeddings) would add little: the model already
supplies the meaning when it chooses what to search for. If it misses, that is the case for one.
Twelve made-up cases, written for this question.
"""
import argparse
import collections
import json
import os
import time

import meaning
import refplan
import teamsearch
import usage

HERE = os.path.dirname(os.path.abspath(__file__))
HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">\n'

# (link text, old address, right new address or None, the sentence around the link)
CASES = [
    ("Sign in", "access.dita#access/sign-in", "access.dita#access/authenticate", "First, %s with your work address."),
    ("Reset a forgotten password", "access.dita#access/reset-password", "access.dita#access/recover-entry",
     "If you are locked out, see %s."),
    ("Two-factor authentication", "access.dita#access/two-factor", "access.dita#access/second-step",
     "Administrators can require %s for everyone."),
    ("Delete your account", "profile.dita#profile/delete-account", "profile.dita#profile/close-membership",
     "To leave the service for good, see %s."),
    ("Billing address", "profile.dita#profile/billing-address", "profile.dita#profile/invoice-recipient",
     "Change where we send paperwork in %s."),
    ("Contact support", "profile.dita#profile/contact-support", "profile.dita#profile/reach-our-team",
     "If none of this works, %s."),
    ("System requirements", "setup.dita#setup/system-requirements", "setup.dita#setup/supported-machines",
     "Check the %s before you start."),
    ("Uninstall the agent", "setup.dita#setup/uninstall-agent", "setup.dita#setup/take-off-client",
     "To free a seat, %s on the old computer."),
    ("Troubleshoot slow uploads", "setup.dita#setup/slow-uploads", "setup.dita#setup/transfer-speed",
     "Large folders take long? See %s."),
    ("Pricing", "pricing.dita", "plans_and_fees.dita", "What each tier costs is listed under %s."),
    ("Send us a fax", "profile.dita#profile/fax-number", None, "You can also %s."),
    ("Notes for version 1", "setup.dita#setup/v1-notes", None, "Older installations: read the %s."),
]


# The harder set (--moved): the old files are gone and each piece lives in another file under another
# name, so the old address gives no hint where to look.
MOVED = [
    ("Sign in", "login.dita#login/sign-in", "entry.dita#entry/authenticate", "First, %s with your work address."),
    ("Reset a forgotten password", "login.dita#login/reset-password", "lockouts.dita#lockouts/recover-entry",
     "If you are locked out, see %s."),
    ("Two-factor authentication", "security.dita#security/two-factor", "identity_checks.dita#identity_checks/second-step",
     "Administrators can require %s for everyone."),
    ("Delete your account", "account.dita#account/delete-account", "leaving.dita#leaving/close-membership",
     "To leave the service for good, see %s."),
    ("Billing address", "billing.dita#billing/billing-address", "paperwork.dita#paperwork/invoice-recipient",
     "Change where we send paperwork in %s."),
    ("Contact support", "support.dita#support/contact-support", "people.dita#people/reach-our-team",
     "If none of this works, %s."),
    ("System requirements", "install.dita#install/system-requirements", "machines.dita#machines/supported-machines",
     "Check the %s before you start."),
    ("Uninstall the agent", "install.dita#install/uninstall-agent", "cleanup.dita#cleanup/take-off-client",
     "To free a seat, %s on the old computer."),
    ("Troubleshoot slow uploads", "troubleshooting.dita#troubleshooting/slow-uploads", "speed.dita#speed/transfer-speed",
     "Large folders take long? See %s."),
    ("Pricing", "pricing.dita", "plans_and_fees.dita", "What each tier costs is listed under %s."),
    ("Send us a fax", "support.dita#support/fax-number", None, "You can also %s."),
    ("Notes for version 1", "install.dita#install/v1-notes", None, "Older installations: read the %s."),
]
MOVED_FILES = {
    "entry.dita": ("entry", "Getting into the console", [
        ("authenticate", "Log on to the console", "Enter your work address and your secret phrase, then choose Continue."),
        ("session-length", "How long you stay logged on", "After eight idle hours the console asks you again."),
        ("trusted-device", "Remember this computer", "A remembered computer skips the code for thirty days.")]),
    "lockouts.dita": ("lockouts", "When the console will not let you in", [
        ("recover-entry", "Get back in when you are locked out", "Ask for a recovery link; it arrives by mail within a minute."),
        ("too-many-tries", "Too many tries", "After five wrong tries the console waits ten minutes.")]),
    "identity_checks.dita": ("identity_checks", "Proving who you are", [
        ("second-step", "Confirm it is you with a code", "After the secret phrase, enter the six digits from your phone."),
        ("password-policy", "Password policy", "A secret phrase needs twelve characters and must change every year."),
        ("backup-codes", "Codes for when your phone is away", "Print ten single-use codes and keep them safe.")]),
    "leaving.dita": ("leaving", "Ending your membership", [
        ("close-membership", "Leave the service for good", "Closing removes your data after thirty days and cannot be undone."),
        ("pause-membership", "Take a break", "A paused membership keeps your data and costs nothing.")]),
    "paperwork.dita": ("paperwork", "Invoices and receipts", [
        ("invoice-recipient", "Where we send invoices", "Give the street, city and tax number that must appear on each invoice."),
        ("account-overview", "Account overview", "The first page shows your tier, your seats and your last invoice."),
        ("receipt-copies", "Copies of receipts", "Download any receipt of the last seven years.")]),
    "people.dita": ("people", "Talking to us", [
        ("reach-our-team", "Get help from a person", "Write to the help desk or call during office hours."),
        ("office-hours", "Office hours", "The help desk answers on weekdays from eight to six.")]),
    "machines.dita": ("machines", "What the client runs on", [
        ("supported-machines", "Computers and operating systems we support", "The client runs on current desktops with four gigabytes of memory."),
        ("network-needs", "What the network must allow", "The client needs outgoing connections on port 443.")]),
    "cleanup.dita": ("cleanup", "Taking the client away", [
        ("take-off-client", "Remove the client from a computer", "Removing the client frees its seat for another computer."),
        ("leftover-files", "Files that stay behind", "Your synced folder stays; delete it yourself if you wish.")]),
    "speed.dita": ("speed", "When things are slow", [
        ("transfer-speed", "Make transfers faster", "Wired networks and fewer small files shorten a transfer."),
        ("upload-limits", "Upload limits", "One file may be up to five gigabytes.")]),
    "plans_and_fees.dita": ("plans_and_fees", "Plans and fees", [
        ("tiers", "The three tiers", "Starter, Team and Enterprise differ in seats and storage."),
        ("taxes", "Taxes", "Fees are shown without tax.")]),
}


# The team set (--team): the links use a team's own names (a project's code name, a nickname for a
# tool), which no dictionary knows and only the team's vocabulary maps to the plain title. The old
# files are gone and each piece is in another file, as in --moved. Three decoys share a word with a
# team name and mean something else ("Atlas of regions" for "the Atlas report").
TEAM = [
    ("Kestrel setup", "kestrel.dita#kestrel/setup", "console_install.dita#console_install/install-console",
     "Before your first invoice run, finish the %s."),
    ("the Q-close", "finance.dita#finance/q-close", "books.dita#books/close-quarter", "Do not change prices during %s."),
    ("Open a Bluebird ticket", "bluebird.dita#bluebird/open-ticket", "help.dita#help/ask-help-desk",
     "If a payment is stuck, %s."),
    ("the Atlas report", "atlas.dita#atlas/report", "usage.dita#usage/monthly-usage", "Seat counts come from %s."),
    ("the night batch", "batch.dita#batch/night", "schedules.dita#schedules/two-am-transfers",
     "Large files are moved in %s."),
    ("the gold path", "paths.dita#paths/gold", "recommended.dita#recommended/most-teams", "New customers follow %s."),
    ("the red card procedure", "safety.dita#safety/red-card", "emergency.dita#emergency/stop-all",
     "If data goes to the wrong customer, start %s."),
    ("Harbor login", "harbor.dita#harbor/login", "partners.dita#partners/partner-logon", "Resellers use %s."),
    ("Pinecone sync", "pinecone.dita#pinecone/sync", "offices.dita#offices/keep-in-step",
     "Branch offices rely on %s."),
    ("Falcon tiers", "falcon.dita", "plans_and_fees.dita", "Sales quotes use the %s."),
    ("the Juniper export", "juniper.dita#juniper/export", None, "Auditors used to ask for %s."),
    ("Otter alerts", "otter.dita#otter/alerts", None, "On-call staff subscribe to %s."),
]
TEAM_FILES = {
    "console_install.dita": ("console_install", "Putting the billing console in place", [
        ("install-console", "Install the billing console", "Download the installer, enter the licence and choose a database.")]),
    "books.dita": ("books", "Closing the books", [
        ("close-quarter", "Close the quarter's books", "Lock the ledger, reconcile the bank and export the totals.")]),
    "help.dita": ("help", "Getting help", [
        ("ask-help-desk", "Ask the help desk", "Describe the problem and attach the invoice number.")]),
    "usage.dita": ("usage", "Reports", [
        ("monthly-usage", "Monthly usage report", "Seats, storage and transfers for each month.")]),
    "regions.dita": ("regions", "Where your data lives", [
        ("atlas-of-regions", "Atlas of regions", "A map of the countries where we keep data.")]),
    "schedules.dita": ("schedules", "Scheduled work", [
        ("two-am-transfers", "Scheduled transfers at 2 a.m.", "Files over a gigabyte are moved while offices are closed.")]),
    "display.dita": ("display", "Display", [
        ("night-mode", "Night mode", "Dark colours for working late.")]),
    "recommended.dita": ("recommended", "Recommended setup", [
        ("most-teams", "Recommended setup for most teams", "One console, two administrators and weekly backups.")]),
    "emergency.dita": ("emergency", "Emergencies", [
        ("stop-all", "Stop all transfers in an emergency", "Press Stop everything; nothing leaves until an administrator resumes.")]),
    "partners.dita": ("partners", "For resellers", [
        ("partner-logon", "Log on to the partner portal", "Resellers use the address and code from their contract.")]),
    "offices.dita": ("offices", "Working across offices", [
        ("keep-in-step", "Keep folders in step across offices", "Each office sees the same folders within a minute.")]),
    "cards.dita": ("cards", "Payment cards", [
        ("red-card", "Red payment cards", "Cards from some banks are red; they work the same.")]),
    "plans_and_fees.dita": ("plans_and_fees", "Plans and fees", [
        ("tiers", "The three tiers", "Starter, Team and Enterprise differ in seats and storage.")]),
}


def team_payload():
    links = "".join("<p>%s</p>" % (sentence % '<xref href="%s">%s</xref>' % (old, text)) for text, old, _, sentence in TEAM)
    files = {"guide.dita": HEAD + '<topic id="guide"><title>Getting around</title><body>%s</body></topic>\n' % links}
    for name, (topic_id, title, sections) in TEAM_FILES.items():
        files[name] = topic(topic_id, title, sections)
    files["guide.ditamap"] = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">\n'
                              '<map><title>Billing guide</title>%s</map>\n' % "".join(
                                  '<topicref href="%s"/>' % name for name in files if name.endswith(".dita")))
    return {"files": [{"id": "GUID-team-%02d" % n, "path": "/content/dam/team-demo/" + name, "xml": xml, "previous": []}
                      for n, (name, xml) in enumerate(files.items())]}


def moved_payload():
    links = "".join("<p>%s</p>" % (sentence % '<xref href="%s">%s</xref>' % (old, text)) for text, old, _, sentence in MOVED)
    files = {"guide.dita": HEAD + '<topic id="guide"><title>Getting around</title><body>%s</body></topic>\n' % links}
    for name, (topic_id, title, sections) in MOVED_FILES.items():
        files[name] = topic(topic_id, title, sections)
    files["guide.ditamap"] = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">\n'
                              '<map><title>Console guide</title>%s</map>\n' % "".join(
                                  '<topicref href="%s"/>' % name for name in files if name.endswith(".dita")))
    return {"files": [{"id": "GUID-mov-%02d" % n, "path": "/content/dam/moved-demo/" + name, "xml": xml, "previous": []}
                      for n, (name, xml) in enumerate(files.items())]}


def topic(topic_id, title, sections):
    body = "".join('<section id="%s"><title>%s</title><p>%s</p></section>' % s for s in sections)
    return HEAD + '<topic id="%s"><title>%s</title><body>%s</body></topic>\n' % (topic_id, title, body)


def payload():
    links = "".join("<p>%s</p>" % (sentence % '<xref href="%s">%s</xref>' % (old, text)) for text, old, _, sentence in CASES)
    files = {
        "guide.dita": HEAD + '<topic id="guide"><title>Getting around</title><body>%s</body></topic>\n' % links,
        "access.dita": topic("access", "Getting into the console", [
            ("authenticate", "Log on to the console", "Enter your work address and your secret phrase, then choose Continue."),
            ("recover-entry", "Get back in when you are locked out", "Ask for a recovery link; it arrives by mail within a minute."),
            ("second-step", "Confirm it is you with a code", "After the secret phrase, enter the six digits from your phone."),
            ("password-policy", "Password policy", "A secret phrase needs twelve characters and must change every year."),
            ("session-length", "How long you stay logged on", "After eight idle hours the console asks you again."),
        ]),
        "profile.dita": topic("profile", "Your membership", [
            ("close-membership", "Leave the service for good", "Closing removes your data after thirty days and cannot be undone."),
            ("invoice-recipient", "Where we send invoices", "Give the street, city and tax number that must appear on each invoice."),
            ("reach-our-team", "Get help from a person", "Write to the help desk or call during office hours."),
            ("account-overview", "Account overview", "The first page shows your tier, your seats and your last invoice."),
            ("display-name", "The name others see", "Change how colleagues see you in shared folders."),
        ]),
        "setup.dita": topic("setup", "Putting the client on a computer", [
            ("supported-machines", "Computers and operating systems we support", "The client runs on current desktops with four gigabytes of memory."),
            ("take-off-client", "Remove the client from a computer", "Removing the client frees its seat for another computer."),
            ("transfer-speed", "Make transfers faster", "Wired networks and fewer small files shorten a transfer."),
            ("upload-limits", "Upload limits", "One file may be up to five gigabytes."),
            ("first-run", "The first start", "The client asks for a folder to keep in step."),
        ]),
        "plans_and_fees.dita": topic("plans_and_fees", "Plans and fees", [
            ("tiers", "The three tiers", "Starter, Team and Enterprise differ in seats and storage."),
            ("taxes", "Taxes", "Fees are shown without tax."),
        ]),
        "guide.ditamap": ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">\n'
                          '<map><title>Console guide</title><topicref href="guide.dita"/><topicref href="access.dita"/>'
                          '<topicref href="profile.dita"/><topicref href="setup.dita"/><topicref href="plans_and_fees.dita"/></map>\n'),
    }
    return {"files": [{"id": "GUID-syn-%02d" % n, "path": "/content/dam/synonym-demo/" + name, "xml": xml, "previous": []}
                      for n, (name, xml) in enumerate(files.items())]}


def last_part(address):
    """What names the target, whatever form the file part has: the element id, else the file."""
    return address.rsplit("/", 1)[-1] if "#" in address else None


def score(case, repair, files=None):
    text, old, right, _ = case
    new = repair.get("new") or ""
    if not new:
        return "right" if right is None else "missed"
    if right is None:
        return "wrong"
    if "#" in right:
        return "right" if new.rsplit("/", 1)[-1] == last_part(right) else "wrong"
    # A link to a whole file: the repair names it by its GUID-style id or by its path.
    target = next(f for f in (files or payload()["files"]) if f["path"].endswith("/" + right))
    return "right" if (target["id"] in new or right in new) and "#" not in new.replace("#" + right.split(".")[0], "") else "wrong"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--backend", default="cli", choices=["cli", "sdk"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--out", default=os.path.join(HERE, "eval", "refs", "synonym-eval.json"))
    parser.add_argument("--moved", action="store_true",
                        help="the harder set: the old files are gone and each piece is in another file under another name")
    parser.add_argument("--team", action="store_true",
                        help="the team set: links use a team's own names that only its vocabulary maps to plain titles")
    parser.add_argument("--meaning", action="store_true",
                        help="give the finder the search by meaning (meaning.py; needs model2vec)")
    args = parser.parse_args()
    if args.meaning:
        meaning.ENABLED = True
        if not meaning.available():
            raise SystemExit("The search by meaning cannot be loaded: %s" % meaning.why_not())
    cases, build = (TEAM, team_payload) if args.team else (MOVED, moved_payload) if args.moved else (CASES, payload)
    if args.out.endswith("synonym-eval.json") and (args.moved or args.team):
        args.out = args.out.replace("synonym-eval.json", "synonym-team-eval.json" if args.team else "synonym-moved-eval.json")
    by_old = {old: case for case in cases for old in [case[1]]}
    runs = []
    for number in range(1, args.runs + 1):
        started, before = time.time(), len(usage._calls)
        data = build()
        out = refplan.plan_files(json.loads(json.dumps(data)), backend=args.backend, model=args.model, log=lambda message: None, memory={})
        rows = []
        for repair in out["repairs"]:
            case = next((c for old, c in by_old.items() if repair["old"].endswith(old.split("/", 1)[-1]) or repair["old"] == old), None)
            if case is None:
                continue
            rows.append({"link": case[0], "old": case[1], "proposed": repair.get("new") or "", "verdict": repair["verdict"],
                         "score": score(case, repair, data["files"]), "found_by": repair.get("stage")})
        counts = collections.Counter(row["score"] for row in rows)
        calls = usage._calls[before:]
        runs.append({"run": number, "seconds": round(time.time() - started), "references": len(rows), "scores": dict(counts),
                     "applied_without_asking_and_wrong": sum(1 for r in rows if r["score"] == "wrong" and r["verdict"] == "fix"),
                     "verdicts": dict(collections.Counter(r["verdict"] for r in rows)),
                     "model_calls": len(calls), "failed_calls": sum(1 for c in calls if not c["ok"]),
                     "input_tokens": sum(c["in"] for c in calls), "output_tokens": sum(c["out"] for c in calls),
                     "cost_usd": round(sum(c["cost"] or 0 for c in calls), 2), "rows": rows})
        print("run %d: %3d s  %s  verdicts %s  %d model calls (%d failed), $%.2f" % (
            number, runs[-1]["seconds"], "  ".join("%s %d" % kv for kv in sorted(counts.items())), runs[-1]["verdicts"],
            runs[-1]["model_calls"], runs[-1]["failed_calls"], runs[-1]["cost_usd"]))
        for row in rows:
            if row["score"] != "right":
                print("   %-6s %-28s -> %s (%s)" % (row["score"], row["link"], row["proposed"][-44:] or "(nothing)", row["verdict"]))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as handle:
        json.dump({"cases": len(cases), "set": "team" if args.team else "moved" if args.moved else "same file", "search_by_meaning": meaning.ENABLED, "team_search": teamsearch.available(), "backend": args.backend, "model": args.model or "the CLI's default", "runs": runs}, handle, indent=1)
    print("Wrote %s" % args.out)


if __name__ == "__main__":
    main()
