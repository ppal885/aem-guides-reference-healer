#!/usr/bin/env python3
"""The sidecar AEM Guides calls for reference repairs, and the one place a model is called from
(garage-week PoC). Stdlib only.

    python3 -u sidecar.py --serve 8766 [--backend cli|sdk] [--model NAME]

    POST /heal-refs   the files of a map -> repairs, source fixes and the planner's plan
    POST /schematron-fix {findings: [{id, rule, message, test, element, allowed, title, context, feedback}]}
                      -> a model's fixed element for each Schematron finding without a quick fix
    POST /feedback    an author accepted a repair, or took an earlier answer back
    POST /applied     what "Fix all" wrote
    GET  /progress    what the agents are doing right now; ?map=<path> for one map's check
    POST /audit       the references an author changed, and who accepted them
    GET  /audit       the audit record; ?map=<path>, &format=csv for a download
    GET  /memory      what the planner remembers of authors' answers
    GET  /copies      ?map=<path>[&judge=<n>][&ids=g1,g7]: the text copied across the map's topics (most
                      removable copies first; n more groups judged, none when not given), and what the reuse
                      agent says about each group (asked on request, kept until the files change)
    POST /copies-keep {map, mode | keep | unkeep}: "Keep copies" for a map, or one group kept as it is
    GET  /alt         ?map=<path>: the images of the map's last check whose alt text says nothing (no model)
    POST /alt-suggest {map, id, image_base64, media_type}: one alt text from a model that sees the image
    GET  /health

It listens on 127.0.0.1 only. The model is called through the local `claude` CLI by default, or
through the Claude API with --backend sdk (claudeapi.py).
"""
import argparse
import json
import os
import re
import subprocess
import tempfile
import urllib.parse


def _log(message):
    print(message, flush=True)


# ---- Model ---------------------------------------------------------------------------------

# "cli" calls the model through the local `claude` CLI; "sdk" uses the Claude API (claudeapi.py).
BACKEND = "cli"


IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}


def call_model(system, user, model=None, image=None):
    """One model call that must answer with a JSON object. Every call, good or failed, is noted
    in usage.py, so a check can say what it cost and whether the model answered. `image`: (bytes,
    media type) for a call that must see a picture (alttext.py)."""
    import usage
    if BACKEND == "sdk":
        import claudeapi
        return claudeapi.call_model(system, user, model, image=image)
    # --strict-mcp-config: the agents get no MCP servers. Without it the CLI adds the tool lists of
    # every MCP server of the person who started the sidecar whenever they connect in time: measured
    # on 15 Nov 2026, the same one-line call was 930 or 34,700 input tokens, by chance.
    # With an image the CLI may read that one file and nothing else: the folder holds only it.
    tools = ["--tools", "Read", "--allowedTools", "Read"] if image else ["--tools", ""]
    cmd = ["claude", "-p", "--output-format", "json", "--system-prompt", system,
           *tools, "--no-session-persistence", "--strict-mcp-config"]
    if model:
        cmd += ["--model", model]
    envelope = {}
    try:
        with tempfile.TemporaryDirectory() as cwd:
            if image:
                name = "image" + IMAGE_TYPES.get(image[1], ".png")
                with open(os.path.join(cwd, name), "wb") as f:
                    f.write(image[0])
                user = "The image is the file %s in the current folder: read it first.\n\n%s" % (name, user)
            proc = subprocess.run(cmd, input=user, capture_output=True, text=True, timeout=600, cwd=cwd)
        if proc.returncode != 0:
            raise RuntimeError("claude CLI failed: %s" % (proc.stderr or proc.stdout)[:400])
        envelope = json.loads(proc.stdout)
        if envelope.get("is_error"):
            raise RuntimeError("claude CLI error: %s" % str(envelope.get("result"))[:400])
        answer = parse_json(envelope.get("result", ""))
    except Exception as exc:
        usage.note(False, *usage.tokens_of(envelope.get("usage") or {}), cost_usd=envelope.get("total_cost_usd"), error=exc,
                   cached=usage.cached_of(envelope.get("usage") or {}))
        raise
    usage.note(True, *usage.tokens_of(envelope.get("usage") or {}), cost_usd=envelope.get("total_cost_usd"),
               cached=usage.cached_of(envelope.get("usage") or {}))
    return answer


def parse_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("No JSON object in model output: %s" % text[:200])
    return json.loads(text[start:end + 1])



# What the agents are doing right now, for the editor to show while a check runs (prototype only).
# What the agents are doing, per map: {map path: {"running", "lines", "timeline"}}. Two checks on
# two maps run side by side, and each editor panel asks for its own map.
PROGRESS = {}
IDLE = {"running": False, "lines": [], "timeline": []}


# The files of the last check of each map, for the reuse agent to read when the author opens
# "Copied content" (GET /copies), and what it decided, kept until the files change.
LAST_FILES = {}
LAST_ASSETS = {}     # map path: (the assets that are not DITA, the paths dangling names stood for)
COPIES = {}          # map path: (fingerprint of its files, the groups found in them)
DECISIONS = {}       # reuse.decision_key: the reuse agent's decision, kept for the next page and check


FULL_UP_TO = 200      # groups sent with their copies at once; above that, a summary and copies on request

# "Keep copies": a team that does not want conrefs keeps its copies and is shown only the groups whose
# copies no longer say the same. Per map: the mode the author chose, and the groups the author said
# to keep as they are (by reuse.decision_key, so a group keeps that answer in the next check).
KEEP_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "keep-copies.json")
_KEEP_LOCK = __import__("threading").Lock()


def _keep_state():
    try:
        with open(KEEP_PATH) as f:
            state = json.load(f)
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def keep_of(map_path):
    entry = _keep_state().get(map_path or "", {})
    return {"mode": entry.get("mode") or "share", "kept": list(entry.get("kept") or [])}


def set_keep(body):
    """The author's "Keep copies" choices for a map: {"map", "mode": "keep"|"share"} chooses the mode;
    {"map", "keep": key} or {"map", "unkeep": key} says to keep one group's copies as they are, or not."""
    map_path = body.get("map") or ""
    if not map_path:
        raise ValueError("map is required")
    with _KEEP_LOCK:
        state = _keep_state()
        entry = state.setdefault(map_path, {"mode": "share", "kept": []})
        if body.get("mode") is not None:
            if body["mode"] not in ("keep", "share"):
                raise ValueError("mode is keep or share")
            entry["mode"] = body["mode"]
        kept = set(entry.get("kept") or [])
        if body.get("keep"):
            kept.add(str(body["keep"]))
        if body.get("unkeep"):
            kept.discard(str(body["unkeep"]))
        entry["kept"] = sorted(kept)
        os.makedirs(os.path.dirname(KEEP_PATH), exist_ok=True)
        temporary = KEEP_PATH + ".tmp"
        with open(temporary, "w") as f:
            json.dump(state, f, indent=1)
        os.replace(temporary, KEEP_PATH)
    return keep_of(map_path)


def copies_of(map_path, model=None, judge=None, ids=None):
    """The copied text of a map's last check, most removable copies first, and the reuse agent's
    word on each group judged so far: `judge` more groups are asked this time, none when not given.
    Opening "Copied content" sends nothing to the model; the author asks for it ("Judge next 100"):
    on 19 Nov 2026 a default of 100 sent 800 groups of customer content to the model unasked. A map with more than FULL_UP_TO groups gets a summary of each (17.6 MB in
    full on the customer sample); `ids` ("g1,g7") names the groups to send with their copies."""
    import hashlib
    import reuse
    files = LAST_FILES.get(map_path or "")
    if not files:
        return {"groups": [], "note": "Run the health check first: the agents have not seen this map's files."}
    fingerprint = hashlib.sha1("".join(f.get("path", "") + (f.get("xml") or "") for f in files).encode("utf-8")).hexdigest()
    judge = 0 if judge is None else max(0, int(judge))
    cached = COPIES.get(map_path)
    if not (cached and cached[0] == fingerprint and judge == 0):
        groups = reuse.decide(files, lambda system, user: call_model(system, user, model), _log, judge=judge, cache=DECISIONS)
        titles = reuse._titles(files)
        cached = (fingerprint, [dict(_compact(g), topics=[{"file": "/" + f.lstrip("/"), "title": titles.get(f.lstrip("/"), "")}
                                                          for f in g["files"]]) for g in groups])
        COPIES[map_path] = cached
    full = cached[1]
    try:
        import fixrate
        fixrate.record_shown(map_path, full)     # what the author was offered, for the fix rate (fixrate.py)
    except (OSError, KeyError, TypeError) as exc:
        _log("copies shown not recorded: %s" % exc)
    wanted = set((ids or "").split(",")) - {""}
    small = len(full) <= FULL_UP_TO
    keep = keep_of(map_path)
    kept = set(keep["kept"])
    drifted = [g for g in full if g["kind"] in ("numbers", "wording")]
    return {"groups": [dict(g if small or g["id"] in wanted else _summary(g), kept=g["key"] in kept) for g in full],
            "total": len(full), "mode": keep["mode"],
            "drifted": sum(1 for g in drifted if g["key"] not in kept), "kept": sum(1 for g in drifted if g["key"] in kept),
            "unjudged": sum(1 for g in full if g["decision"] == "unjudged"),
            "copies": sum(len(g["copies"]) for g in full), "removable": sum(max(0, len(g["copies"]) - 1) for g in full)}


def alt_of(map_path):
    """The images of a map's last check whose alt text says nothing (alttext.py). No model."""
    import alttext
    files = LAST_FILES.get(map_path or "")
    if not files:
        return {"images": [], "note": "Run the health check first: the agents have not seen this map's files."}
    assets, missing = LAST_ASSETS.get(map_path or "", (None, None))
    found = alttext.images(files, assets, missing)
    return {"images": found, "uses": sum(len(g["uses"]) for g in found), "weak_uses": sum(g["weak_uses"] for g in found)}


def schematron_fix(body, model=None):
    """A model's fix for each Schematron finding AEM sends (schematronfix.py): asked only when the
    author asks, checked by AEM before the author sees it; nothing is written here."""
    import schematronfix
    import usage
    mark = usage.start()
    try:
        with usage.as_agent("schematron"):
            answer = schematronfix.suggest(body, lambda system, user: call_model(system, user, model))
    finally:
        cost = usage.finish(mark)
    return dict(answer, input_tokens=cost["input_tokens"], output_tokens=cost["output_tokens"], cost_usd=cost["cost_usd"])


def suggest_alt(body, model=None):
    """One alt text for one image of the map's last check, from a model that sees the image. The
    editor sends the picture it read from AEM (base64) and the id from alt_of. Asked only when the
    author asks; nothing is written."""
    import base64
    import alttext
    import usage
    group = next((g for g in alt_of(body.get("map")).get("images", []) if g["id"] == body.get("id")), None)
    if group is None:
        raise ValueError("no such image in the map's last check: %s" % body.get("id"))
    media = body.get("media_type") or "image/png"
    if media not in IMAGE_TYPES:
        raise ValueError("not an image type the model reads: %s" % media)
    data = base64.b64decode(body.get("image_base64") or "", validate=True)
    if not data or len(data) > 5 * 1024 * 1024:
        raise ValueError("the image is empty or larger than 5 MB")
    mark = usage.start()
    try:
        with usage.as_agent("alt"):
            answer = call_model(alttext.SYSTEM, alttext.prompt_for(group), model, image=(data, media))
    finally:
        cost = usage.finish(mark)
    return dict(alttext.clean(answer, group["image"]), id=group["id"], image=group["image"],
                model_calls=cost["model_calls"], input_tokens=cost["input_tokens"],
                output_tokens=cost["output_tokens"], cost_usd=cost["cost_usd"])


def _summary(group):
    """A group without its copies: what the list of groups shows."""
    out = {k: v for k, v in group.items() if k not in ("copies", "files", "topics", "variants")}
    out.update(text=group["text"][:300], summary=True, topic_count=len(group["files"]), copy_count=len(group["copies"]),
               wordings=len(group["variants"]))
    return out


def _compact(group):
    """A group as the editor reads it. Each copy names its wording by index into "variants" (the full
    text, which the editor compares before it replaces a copy) instead of repeating it."""
    slash = lambda path: "/" + path.lstrip("/")
    variants = [v["text"] for v in group["variants"]]
    copies = []
    for c in group["copies"]:
        copy = {"file": slash(c["file"]), "location": c["location"]}
        if c.get("markup"):
            copy["mk"] = c["markup"]          # the markup inside it, when there is any (duplicates.markup_of)
        if c["text"] in variants:
            copy["v"] = variants.index(c["text"])
        else:
            copy["text"] = c["text"]
        copies.append(copy)
    import reuse
    return {"id": group["id"], "key": reuse.decision_key(group), "kind": group["kind"], "tag": group["tag"],
            "decision": group["decision"],
            "text": group.get("variant_text") or group["text"], "differs": group.get("differs", ""),
            "reason": group.get("reason", ""), "decided_by": group.get("decided_by", ""),
            "existing": dict(group["existing"], path=slash(group["existing"]["path"])) if group.get("existing") else None,
            "files": [slash(f) for f in group["files"]], "copies": copies,
            "variants": [{"text": v["text"], "count": v["count"]} for v in group["variants"]],
            "navtitle": group.get("navtitle", ""), "refs": group.get("refs", 0)}


def progress_of(map_path):
    return PROGRESS.setdefault(map_path or "", {"running": False, "lines": [], "timeline": []})


def serve(port, model=None):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, status, body):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            # The editor's dev page reads /progress from another local port.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.split("?")[0] == "/progress":
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                self.send_json(200, PROGRESS.get((query.get("map") or [""])[0], IDLE))
            elif self.path.split("?")[0] == "/copies":
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                try:
                    judge = (query.get("judge") or [None])[0]
                    self.send_json(200, copies_of((query.get("map") or [""])[0], model,
                                                  int(judge) if judge and judge.isdigit() else None,
                                                  (query.get("ids") or [""])[0]))
                except Exception as exc:
                    _log("copies failed: %s" % exc)
                    self.send_json(500, {"error": str(exc)})
            elif self.path.split("?")[0] == "/alt":
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                try:
                    self.send_json(200, alt_of((query.get("map") or [""])[0]))
                except Exception as exc:
                    _log("alt failed: %s" % exc)
                    self.send_json(500, {"error": str(exc)})
            elif self.path == "/memory":
                import refplan
                self.send_json(200, refplan.load_memory())
            elif self.path.split("?")[0] == "/audit":
                # The audit record of one map (or of all): ?map=<path>&format=csv for a download.
                import audit
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                rows = audit.entries((query.get("map") or [None])[0])
                if (query.get("format") or ["json"])[0] == "csv":
                    data = ("\ufeff" + audit.as_csv(rows)).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Content-Type", "text/csv; charset=utf-8")
                    self.send_header("Content-Disposition", "attachment; filename=\"reference-repairs-audit.csv\"")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_json(200, {"summary": audit.summary(rows), "entries": rows})
            elif self.path == "/usage":
                # What each check cost: model calls, failed calls, tokens, money when known.
                import usage
                self.send_json(200, {"checks": usage.entries()[-50:]})
            elif self.path == "/health":
                # Also says how the model is reached: "cli" waits for each whole answer, "sdk"
                # streams it. last_stream: how the last streamed answer arrived (empty before one).
                state = {"status": "ok", "backend": BACKEND, "streaming": BACKEND == "sdk"}
                if BACKEND == "sdk":
                    import claudeapi
                    state["last_stream"] = dict(claudeapi.LAST_STREAM)
                # Whether the finder has the search by meaning: "on", "off" (not asked for), or
                # why it was asked for and could not be loaded.
                import meaning
                state["search_by_meaning"] = ("off" if not meaning.ENABLED else
                                              "on" if meaning.available() else "not loaded: %s" % meaning.why_not())
                self.send_json(200, state)
            else:
                self.send_json(404, {"error": "not found"})

        def do_POST(self):
            if self.path == "/audit":
                # From the editor: the references an author just changed, and who that author is.
                try:
                    import audit
                    length = int(self.headers.get("Content-Length", "0"))
                    body = json.loads(self.rfile.read(length).decode("utf-8"))
                    stored = audit.record(body.get("map"), body.get("accepted_by"), body.get("entries"))
                    _log("audit record: %d references added" % stored)
                    self.send_json(200, {"recorded": stored})
                except (ValueError, AttributeError, TypeError) as exc:
                    self.send_json(400, {"error": str(exc)})
                return
            if self.path == "/schematron-fix":
                # From AEM (Content Health): Schematron findings without a quick fix, when the author asks.
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    self.send_json(200, schematron_fix(json.loads(self.rfile.read(length).decode("utf-8")), model))
                except (ValueError, AttributeError, TypeError) as exc:
                    self.send_json(400, {"error": str(exc)})
                except Exception as exc:
                    _log("schematron fix failed: %s" % exc)
                    self.send_json(502, {"error": "The model did not answer: %s" % " ".join(str(exc).split())[:200]})
                return
            if self.path == "/alt-suggest":
                # From the editor, as text/plain so the browser needs no preflight request.
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    body = json.loads(self.rfile.read(length).decode("utf-8"))
                    self.send_json(200, suggest_alt(body, model))
                except (ValueError, AttributeError, TypeError) as exc:
                    self.send_json(400, {"error": str(exc)})
                except Exception as exc:
                    _log("alt suggestion failed: %s" % exc)
                    self.send_json(502, {"error": "The model did not answer: %s" % " ".join(str(exc).split())[:200]})
                return
            if self.path == "/copies-keep":
                # From the editor: the "Keep copies" mode of a map, or a group to keep as it is.
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    self.send_json(200, set_keep(json.loads(self.rfile.read(length).decode("utf-8"))))
                except (ValueError, AttributeError, TypeError) as exc:
                    self.send_json(400, {"error": str(exc)})
                return
            if self.path in ("/feedback", "/applied"):
                # From the editor, as text/plain so the browser needs no preflight request.
                #   /feedback  an author accepted a repair ("rejected": the candidates passed over),
                #              or took an earlier answer back ("forget": true),
                #              or said none of the proposed targets is right ("decline": true, "values")
                #   /applied   what "Fix all" wrote, so the next check can see what became of it
                try:
                    import refplan
                    length = int(self.headers.get("Content-Length", "0"))
                    body = json.loads(self.rfile.read(length).decode("utf-8"))
                    if self.path == "/applied":
                        stored = refplan.record_applied(body.get("edits"), body.get("failed"), map_path=body.get("map"))
                        _log("Fix all recorded: %d edits" % stored)
                        self.send_json(200, {"recorded": stored})
                    elif body.get("decline"):
                        # An author looked at the proposed targets and said none of them is it.
                        values = [v for v in body.get("values") or [] if isinstance(v, str) and v]
                        if not values or not body.get("attribute") or not body.get("old"):
                            raise ValueError("decline needs attribute, old and at least one value")
                        for value in values:
                            refplan.reject(body.get("attribute"), body.get("old"), value)
                        _log("author declined %d target(s) for %s" % (len(values), body.get("attribute")))
                        self.send_json(200, {"declined": len(values)})
                    elif body.get("forget"):
                        forgotten = refplan.forget(body.get("attribute"), body.get("old"))
                        _log("author answer forgotten: %s" % forgotten)
                        self.send_json(200, {"forgotten": forgotten})
                    else:
                        stored = refplan.remember(body.get("attribute"), body.get("old"), body.get("new"),
                                                  rejected=body.get("rejected"))
                        _log("author answer stored (%d in all)" % stored)
                        self.send_json(200, {"stored": stored})
                except (ValueError, AttributeError, TypeError) as exc:
                    self.send_json(400, {"error": str(exc)})
                return
            if self.path != "/heal-refs":
                self.send_json(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                # The planner agent by default; "mode": "pipeline" runs the fixed order of refheal.
                if payload.get("mode") == "pipeline":
                    import refheal
                    self.send_json(200, refheal.heal_files(payload, BACKEND, model, _log))
                    return
                import refplan
                LAST_FILES[payload.get("map") or ""] = payload.get("files") or []
                LAST_ASSETS[payload.get("map") or ""] = (payload.get("assets"), payload.get("missing_paths"))
                state = progress_of(payload.get("map"))
                state.update(running=True, lines=[], timeline=[])
                try:
                    self.send_json(200, refplan.plan_files(
                        payload, BACKEND, model, _log,
                        lambda text: state.update(lines=(state["lines"] + [text])[-12:]),
                        timeline=lambda steps: state.update(timeline=steps)))
                finally:
                    state["running"] = False
            except ValueError:
                self.send_json(400, {"error": "body is not valid JSON"})
            except Exception as exc:  # the rule reports the references without repairs on any non-200
                _log("repair failed: %s" % exc)
                self.send_json(500, {"error": str(exc)})

        def log_message(self, fmt, *args):
            _log("%s %s" % (self.address_string(), fmt % args))

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    _log("Reference repair sidecar on http://127.0.0.1:%d" % port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _log("\nSidecar stopped.")
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--serve", type=int, metavar="PORT", required=True, help="port to listen on, on 127.0.0.1")
    parser.add_argument("--model")
    parser.add_argument("--backend", choices=["cli", "sdk"], default="cli",
                        help="cli: local claude CLI (default). sdk: Claude API; needs the anthropic package and credentials")
    args = parser.parse_args()
    global BACKEND
    BACKEND = args.backend
    serve(args.serve, args.model)


if __name__ == "__main__":
    main()
