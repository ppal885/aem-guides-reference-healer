#!/usr/bin/env python3
"""How long AEM's Broken links report takes to show a change, for each kind of change.

Loads a small made-up sample into the local AEM (/content/dam/index-timing), then for each case
breaks one reference, waits until the report counts it, repairs it and waits until the report
drops it, saving the way the editor's "Fix all" does (POST /bin/guides/v1/asset/update). Prints one
JSON line per run: the case, how the file was saved, seconds to show the break and to show the
repair, or null when the report did not change within the limit.

    python3 samples/index_timing.py --runs 3 [--limit 900] [--cases href,conref,target,key,upload]

Local AEM on 127.0.0.1 with its default login only. No model, no customer content.
"""
import argparse
import base64
import gzip
import json
import time
import urllib.parse
import urllib.request
import uuid

AEM = "http://127.0.0.1:4502"
AUTH = "Basic " + base64.b64encode(b"admin:admin").decode()
ROOT = "/content/dam/index-timing"
MAP = ROOT + "/m.ditamap"
POLL = 2

TOPIC = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">\n'
MAPHEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">\n'
FILES = {
    "a.dita": TOPIC + '<topic id="a"><title>Alpha</title><body><p id="p1">The alpha paragraph.</p></body></topic>\n',
    "lib.dita": TOPIC + '<topic id="lib"><title>Library</title><body><note id="n1">A shared note.</note></body></topic>\n',
    "b.dita": TOPIC + ('<topic id="b"><title>Beta</title><body><p>See <xref href="a.dita#a/p1"/>.</p>'
                       '<note conref="lib.dita#lib/n1"/><p>Product: <ph keyref="prod"/>.</p></body></topic>\n'),
    "m.ditamap": MAPHEAD + ('<map><title>Index timing</title><keydef keys="prod" href="a.dita"/>'
                            '<topicref href="a.dita"/><topicref href="b.dita"/><topicref href="lib.dita"/></map>\n'),
}


def call(path, data=None, headers=None, method=None):
    request = urllib.request.Request(AEM + path, data=data, method=method, headers=dict({"Authorization": AUTH}, **(headers or {})))
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def token():
    return json.loads(call("/libs/granite/csrf/token.json"))["token"]


def multipart(fields):
    boundary = uuid.uuid4().hex
    body = b""
    for name, (filename, content, ctype) in fields.items():
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"%s\r\n%s\r\n" % (
            boundary, name, "; filename=\"%s\"" % filename if filename else "",
            "Content-Type: %s\r\n" % ctype if ctype else "")).encode() + content + b"\r\n"
    return body + ("--%s--\r\n" % boundary).encode(), "multipart/form-data; boundary=" + boundary


def upload(name, xml):
    body, ctype = multipart({"file": (name, xml.encode(), "application/xml"), "fileName": (None, name.encode(), None)})
    call(urllib.parse.quote(ROOT) + ".createasset.html", body, {"Content-Type": ctype, "CSRF-Token": token()})


def save(path, xml):
    """The editor's save (assets.ts saveAssetGzip)."""
    body, ctype = multipart({"file": ("blob", gzip.compress(xml.encode()), "application/gzip"),
                             "resourceType": (None, b"GUIDES_RESOURCE", None), "path": (None, path.encode(), None)})
    call("/bin/guides/v1/asset/update", body, {"Content-Type": ctype, "CSRF-Token": token()})


def read(path):
    return call(urllib.parse.quote(path) + "/jcr:content/renditions/original").decode("utf-8")


def broken():
    answer = call("/bin/guides/v1/map/reports/brokenlink/rowcount", json.dumps({"asset": MAP}).encode(),
                  {"Content-Type": "application/json", "CSRF-Token": token()}, "POST")
    return json.loads(answer)["totalRows"]


def wait_for(count, limit):
    start = time.time()
    while time.time() - start < limit:
        if broken() == count:
            return round(time.time() - start, 1)
        time.sleep(POLL)
    return None


def load():
    try:
        call(ROOT, method="DELETE")
        time.sleep(5)
    except Exception:
        pass
    body = urllib.parse.urlencode({"jcr:primaryType": "sling:Folder", "jcr:title": "Index timing (made up)"}).encode()
    call(ROOT, body, {"CSRF-Token": token()})
    for name in ("a.dita", "lib.dita", "b.dita", "m.ditamap"):
        upload(name, FILES[name])
        time.sleep(3)
    # AEM rebuilds a map's key space when the map is saved through the Guides API, not on upload.
    save(MAP, read(MAP))
    time.sleep(10)


# Each case: (file to change, (old, new)); the break is old -> new, the repair new -> old.
CASES = {
    "href": ("b.dita", ("#a/p1", "#a/nope"), "save"),
    "conref": ("b.dita", ("#lib/n1", "#lib/gone"), "save"),
    # The target changes; the topic that points at it is not saved again.
    "target": ("a.dita", ('id="p1"', 'id="p9"'), "save"),
    "key": ("m.ditamap", ('keys="prod"', 'keys="prod2"'), "save"),
    "upload": ("b.dita", ("#a/p1", "#a/nope"), "upload"),
}


def change(case, forward):
    name, (old, new), how = CASES[case]
    path = ROOT + "/" + name
    xml = read(path)
    a, b = (old, new) if forward else (new, old)
    if a not in xml:
        raise RuntimeError("%s: %r not in %s" % (case, a, name))
    xml = xml.replace(a, b, 1)
    upload(name, xml) if how == "upload" else save(path, xml)
    return how


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--limit", type=int, default=900, help="seconds to wait for the report each time")
    parser.add_argument("--cases", default=",".join(CASES))
    parser.add_argument("--no-load", action="store_true")
    args = parser.parse_args()
    if not args.no_load:
        load()
    base = wait_for(0, args.limit)
    print(json.dumps({"loaded": True, "clean_after_s": base, "broken_now": broken()}), flush=True)
    for run in range(1, args.runs + 1):
        for case in args.cases.split(","):
            how = change(case, True)
            shown = wait_for(1, args.limit)
            change(case, False)
            cleared = wait_for(0, args.limit)
            print(json.dumps({"run": run, "case": case, "saved_by": how, "break_shown_s": shown,
                              "repair_shown_s": cleared}), flush=True)
            if cleared is None:
                wait_for(0, args.limit)


if __name__ == "__main__":
    main()
