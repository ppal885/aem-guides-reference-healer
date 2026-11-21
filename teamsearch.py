"""The team's own search, for the finder agents (garage-week PoC). Optional, off by default.

A team's names for its products, tools and procedures ("Kestrel" for the billing console, "the
night batch" for the transfers at 2 a.m.) are in no dictionary, so neither word matching nor the
model's own knowledge can turn a link's old wording into the right topic. A search service that
holds the team's vocabulary can: it widens the query with the other names the vocabulary gives a
term. This module asks such a service and maps what it returns to the files the finder knows.

    REFHEAL_SEARCH_URL   the search endpoint of the site that holds this content
    REFHEAL_SEARCH_KEY   the key for it; read from the environment only, never written anywhere

Without both, the tool is not offered and the finder works as before. When the service does not
answer, the tool says so and the finder goes on with its other tools; a check never stops for it.

Measured on 21 Nov 2026 on the team set of synonymeval.py (ten links in a team's own words, the
old files gone): without this tool the finder missed the same 3 of 10 in both runs. A hit is not
proof: the finder reads the candidate, the reviewer checks the answer, and nothing found this way
is applied without the usual checks.
"""
import json
import os
import urllib.error
import urllib.request

URL = os.environ.get("REFHEAL_SEARCH_URL", "")
TIMEOUT = 15
TOP = 8


def available():
    return bool(URL and os.environ.get("REFHEAL_SEARCH_KEY"))


def _ask(query):
    """The service's results for query, or raises with a short reason."""
    body = json.dumps({"query": query, "search_type": "FULL_TEXT", "top_k": TOP, "vocabulary_mode": "on"}).encode()
    request = urllib.request.Request(URL, data=body, method="POST", headers={
        "Authorization": "Bearer " + os.environ.get("REFHEAL_SEARCH_KEY", ""), "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read() or b"{}")


def _file_of(repo, asset_id):
    """The repository path of a result, by the asset's GUID: the service may name it with or
    without the file extension."""
    if not asset_id:
        return None
    name = os.path.basename(asset_id)
    for candidate in (name, name + ".dita", name + ".ditamap", os.path.splitext(name)[0]):
        path = repo.alias.get(candidate)
        if path:
            return path
    stem = os.path.splitext(name)[0]
    return next((path for path, entry in repo.files.items()
                 if entry.get("id") in (name, stem) or os.path.splitext(os.path.basename(path))[0] == stem), None)


def search(repo, query):
    """What the finder gets: files of this repository the team's search finds for query, best first.
    Results that are not in this repository are counted, not listed."""
    try:
        out = _ask(query)
    except urllib.error.HTTPError as exc:
        return {"summary": "the team search did not answer (HTTP %s)" % exc.code, "files": []}
    except Exception as exc:  # no network, timeout, a reply that is not JSON
        return {"summary": "the team search is not reachable (%s)" % (exc.__class__.__name__,), "files": []}
    files, elsewhere = [], 0
    for item in out.get("results") or []:
        path = _file_of(repo, item.get("asset_id"))
        if path is None or path not in repo.files:
            elsewhere += 1
            continue
        if path not in (f["path"] for f in files):
            entry = repo.files[path]
            files.append({"path": path, "title": entry["title"], "type": entry["tag"], "topic_ids": list(entry["topics"])[:4]})
    summary = "%d files" % len(files) + (" (%d more outside this map)" % elsewhere if elsewhere else "")
    return {"summary": summary, "files": files,
            "note": "found through the team's vocabulary; not proof: read a candidate (outline) before you propose it"}
