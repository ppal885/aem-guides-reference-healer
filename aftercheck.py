#!/usr/bin/env python3
"""After a Fix: does AEM's own broken-link report agree that what it wrote resolves?

Reads the audit record (out/audit-log.jsonl) for the map's last press of a button (or every press
since --since), runs the map's health check in AEM as the editor does, and matches AEM's broken
references against the references that press wrote. No model.

    python3 aftercheck.py --map /content/dam/dupes-keys/keys_guide.ditamap
    python3 aftercheck.py --map /content/dam/dupes-bulk/bulk_guide.ditamap --since 2026-11-19

Why: on 19 Nov 2026 a "Fix all safe" run wrote 360 conrefs that AEM's report then called broken,
though the editor showed the text; nobody ran a check after it, so it was seen three days later.

A conkeyref to a key the same press added is listed as broken by AEM until it reads the new key
(about 11 minutes, measured 22 Nov 2026): when only those are broken, it checks again every
3 minutes, up to 12 minutes, before it says so.

Exit 0: none of the written references is broken. 1: some are (listed). 2: nothing to check.
AEM_URL (default http://127.0.0.1:4502) and AEM_USER / AEM_PASSWORD (default: the local
author's default login) say which AEM. The rows go to out/aftercheck-<map name>.json.
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request

import audit

PROFILE = "global-profile"
KEY_WAIT = {"every": 180, "up_to": 720}
POLL = {"every": 3, "up_to": 900}


class Aem:
    """The few AEM calls the editor's Health check makes, with basic authentication."""

    def __init__(self, url=None, user=None, password=None):
        self.url = (url or os.environ.get("AEM_URL") or "http://127.0.0.1:4502").rstrip("/")
        login = "%s:%s" % (user or os.environ.get("AEM_USER") or "admin",
                           password or os.environ.get("AEM_PASSWORD") or "admin")
        self.auth = "Basic " + base64.b64encode(login.encode()).decode()

    def _call(self, url_path, body=None, headers=None):
        request = urllib.request.Request(self.url + url_path, data=body, headers=dict(headers or {}, Authorization=self.auth))
        with urllib.request.urlopen(request, timeout=60) as answer:
            return json.loads(answer.read().decode("utf-8") or "null")

    def get(self, url_path, **query):
        return self._call(url_path + ("?" + urllib.parse.urlencode(query) if query else ""))

    def post(self, url_path, data):
        token = self.get("/libs/granite/csrf/token.json").get("token", "")
        return self._call(url_path, json.dumps(data).encode("utf-8"), {"Content-Type": "application/json", "CSRF-Token": token})

    def last_result(self, map_path):
        return self.get("/bin/guides/v1/contenthealth/report/result", profileId=PROFILE, path=map_path) or {}

    def run_check(self, map_path, preset=None):
        """Starts the map's check with its last preset (or `preset`) and waits for a newer result."""
        last = self.last_result(map_path)
        details = last.get("mapDetails") or {"path": map_path}
        preset = preset or last.get("presetId")
        if not preset:
            raise SystemExit("no preset: run the map's health check once in the editor, or give --preset")
        started = time.time() * 1000
        rules = last.get("presetRules") or ["BROKEN_LINK"]
        self.post("/bin/guides/v1/contenthealth/report/generate",
                  {"profileId": PROFILE, "mapDetails": details, "presetId": preset, "rules": rules})
        for _ in range(POLL["up_to"] // POLL["every"]):
            time.sleep(POLL["every"])
            result = self.last_result(map_path)
            if result.get("status") == "FINISHED" and (result.get("startTime") or 0) >= started - 5000:
                return result
        raise SystemExit("the check did not finish in %d s" % POLL["up_to"])


def written(rows, map_path, since=None):
    """The references the map's last press wrote (every press since `since`, a date or time)."""
    mine = [r for r in rows if r.get("map") == map_path and r.get("attribute") in ("conref", "conkeyref", "href", "keyref")]
    if not mine:
        return [], []
    if since:
        presses = [r for r in mine if r.get("when", "") >= since]
    else:
        last = max(r.get("when", "") for r in mine)
        presses = [r for r in mine if r.get("when") == last]
    when = sorted({r.get("when", "") for r in presses})
    keys = {r.get("now", "").split(" = ")[0] for r in rows if r.get("map") == map_path
            and r.get("attribute") == "keydef" and r.get("when", "") >= (when[0] if when else "")}
    refs = [dict(file=r["file"], attribute=r["attribute"], value=r.get("now", ""), when=r.get("when", "")) for r in presses]
    return refs, sorted(keys)


def broken(result):
    """AEM's broken references: (file, value)."""
    out = []
    for rule in result.get("result") or []:
        for asset in rule.get("assetResults") or []:
            for failure in asset.get("failures") or []:
                reason = failure.get("reason") or ""
                if reason.startswith("Broken reference: "):
                    out.append((asset.get("assetPath") or "", reason[len("Broken reference: "):]))
    return out


def match(refs, found):
    """The written references AEM lists as broken, and how many broken ones the press did not write."""
    found_set = set(found)
    bad = [r for r in refs if (r["file"], r["value"]) in found_set]
    mine = {(r["file"], r["value"]) for r in refs}
    return bad, sum(1 for f in found if f not in mine)


def waiting_on_new_keys(bad, new_keys):
    """Only conkeyrefs to keys the press added are broken: AEM may not have read the keys yet."""
    by_new_key = [r["attribute"] == "conkeyref" and r["value"].split("/")[0] in new_keys for r in bad]
    return bool(bad) and all(by_new_key)


def check(aem, map_path, since=None, preset=None, rows=None, wait=KEY_WAIT, sleep=time.sleep, log=print):
    refs, new_keys = written(audit.entries(map_path) if rows is None else rows, map_path, since)
    if not refs:
        return {"code": 2, "line": "no Fix or Share for %s in the audit record%s" % (map_path, " since " + since if since else "")}
    result = aem.run_check(map_path, preset)
    bad, other = match(refs, broken(result))
    waited = 0
    while waiting_on_new_keys(bad, new_keys) and waited < wait["up_to"]:
        log("%d conkeyrefs to the new key(s) %s are listed as broken; AEM reads a new key late: checking again in %d s"
            % (len(bad), ", ".join(new_keys), wait["every"]))
        sleep(wait["every"])
        waited += wait["every"]
        result = aem.run_check(map_path, preset)
        bad, other = match(refs, broken(result))
    checked = time.strftime("%H:%M", time.localtime((result.get("startTime") or 0) / 1000))
    presses = sorted({r["when"] for r in refs})
    by_key = sum(r["attribute"] == "conkeyref" for r in refs)
    which = "Fix of " + presses[-1][11:16] if len(presses) == 1 else "%d presses since %s" % (len(presses), presses[0][:16])
    line = "%s: %d references written%s, %d broken in AEM's report (checked %s); %d other broken references" % (
        which, len(refs), " (%d by key)" % by_key if by_key else "", len(bad), checked, other)
    return {"code": 1 if bad else 0, "line": line, "broken": bad, "written": len(refs), "other_broken": other,
            "new_keys": new_keys, "waited_s": waited, "checked": result.get("startTime")}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--map", required=True)
    parser.add_argument("--since", help="every press since this time (2026-11-19 or 2026-11-22T02:09)")
    parser.add_argument("--preset", help="the preset id (default: the map's last check's)")
    args = parser.parse_args()
    out = check(Aem(), args.map, args.since, args.preset)
    print(out["line"])
    for ref in out.get("broken", [])[:10]:
        print("  broken: %s  %s=\"%s\"" % (ref["file"], ref["attribute"], ref["value"]))
    if len(out.get("broken", [])) > 10:
        print("  … and %d more" % (len(out["broken"]) - 10))
    name = os.path.splitext(os.path.basename(args.map))[0]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "aftercheck-%s.json" % name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        json.dump(out, handle, indent=1)
    sys.exit(out["code"])


if __name__ == "__main__":
    main()
