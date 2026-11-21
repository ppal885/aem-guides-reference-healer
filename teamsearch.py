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
old files gone): without this tool the finder missed the same 3 of 10 in both runs; with it,
none (after the shorter pieces below were added; before, "Open a Bluebird ticket" was missed). A hit is not
proof: the finder reads the candidate, the reviewer checks the answer, and nothing found this way
is applied without the usual checks.
"""
import json
import os
import re
import urllib.error
import urllib.request

URL = os.environ.get("REFHEAL_SEARCH_URL", "")
TIMEOUT = 15
TOP = 8
PIECES = 8      # at most this many shorter pieces are asked when the whole phrase finds nothing
# Small words that name nothing; a piece that starts or ends with one is not asked.
SMALL = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "in", "into", "is", "it", "its", "of",
         "on", "or", "our", "the", "this", "to", "what", "when", "with", "you", "your"}


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


def _pieces(query):
    """Shorter runs of query's words, longest first and left to right, without those that start or
    end with a small word: "Open a Bluebird ticket" -> "Open a Bluebird", "Bluebird ticket", "Open",
    "Bluebird", "ticket". A team's name may be one word ("Bluebird") or several ("red card
    procedure"), so the pieces keep several words together before they try one alone."""
    words = re.findall(r"[^\W_][\w'-]*", query)
    pieces = []
    for length in range(len(words) - 1, 0, -1):
        for start in range(len(words) - length + 1):
            run = words[start:start + length]
            piece = " ".join(run)
            if run[0].lower() in SMALL or run[-1].lower() in SMALL or len(piece) < 3 or piece.lower() in (p.lower() for p in pieces):
                continue
            pieces.append(piece)
    return pieces[:PIECES]


def search(repo, query):
    """What the finder gets: files of this repository the team's search finds for query, best first.
    Results that are not in this repository are counted, not listed.

    The service's word search finds a file only when every word of the query is in it or in the
    vocabulary: "Open a Bluebird ticket" finds nothing where "Bluebird" alone finds the help desk
    (measured on 21 Nov 2026). So when the whole phrase finds nothing, shorter pieces of it are asked,
    longest first, until one finds a file of this repository; the finder is told which piece found it."""
    try:
        results = _ask(query).get("results") or []
    except urllib.error.HTTPError as exc:
        return {"summary": "the team search did not answer (HTTP %s)" % exc.code, "files": []}
    except Exception as exc:  # no network, timeout, a reply that is not JSON
        return {"summary": "the team search is not reachable (%s)" % (exc.__class__.__name__,), "files": []}
    files, elsewhere = _mapped(repo, results)
    piece, tried = None, []
    if not files:
        for candidate in _pieces(query):
            tried.append(candidate)
            try:
                more = _ask(candidate).get("results") or []
            except Exception:  # one piece not answered: the next may be
                continue
            found, outside = _mapped(repo, more)
            elsewhere += outside
            if found:
                files, piece = found, candidate
                break
    summary = "%d files" % len(files) + (" (%d more outside this map)" % elsewhere if elsewhere else "")
    if piece:
        summary += "; the whole phrase found nothing, these were found by \"%s\"" % piece
        for f in files:
            f["found_by_piece"] = piece
    elif tried:
        summary += "; the whole phrase found nothing, nor did: %s" % ", ".join('"%s"' % t for t in tried)
    return {"summary": summary, "files": files,
            "note": "found through the team's vocabulary; not proof: read a candidate (outline) before you propose it"}


def _mapped(repo, results):
    """The repository files among results, in order and without repeats, and how many were not ours."""
    files, elsewhere = [], 0
    for item in results:
        path = _file_of(repo, item.get("asset_id"))
        if path is None or path not in repo.files:
            elsewhere += 1
            continue
        if path not in (f["path"] for f in files):
            entry = repo.files[path]
            files.append({"path": path, "title": entry["title"], "type": entry["tag"], "topic_ids": list(entry["topics"])[:4]})
    return files, elsewhere
