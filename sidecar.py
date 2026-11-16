#!/usr/bin/env python3
"""The sidecar AEM Guides calls for reference repairs, and the one place a model is called from
(garage-week PoC). Stdlib only.

    python3 -u sidecar.py --serve 8766 [--backend cli|sdk] [--model NAME]

    POST /heal-refs   the files of a map -> repairs, source fixes and the planner's plan
    POST /feedback    an author accepted a repair, or took an earlier answer back
    POST /applied     what "Fix all" wrote
    GET  /progress    what the agents are doing right now; ?map=<path> for one map's check
    POST /audit       the references an author changed, and who accepted them
    GET  /audit       the audit record; ?map=<path>, &format=csv for a download
    GET  /memory      what the planner remembers of authors' answers
    GET  /health

It listens on 127.0.0.1 only. The model is called through the local `claude` CLI by default, or
through the Claude API with --backend sdk (claudeapi.py).
"""
import argparse
import json
import re
import subprocess
import tempfile
import urllib.parse


def _log(message):
    print(message, flush=True)


# ---- Model ---------------------------------------------------------------------------------

# "cli" calls the model through the local `claude` CLI; "sdk" uses the Claude API (claudeapi.py).
BACKEND = "cli"


def call_model(system, user, model=None):
    """One model call that must answer with a JSON object. Every call, good or failed, is noted
    in usage.py, so a check can say what it cost and whether the model answered."""
    import usage
    if BACKEND == "sdk":
        import claudeapi
        return claudeapi.call_model(system, user, model)
    # --strict-mcp-config: the agents get no MCP servers. Without it the CLI adds the tool lists of
    # every MCP server of the person who started the sidecar whenever they connect in time: measured
    # on 15 Nov 2026, the same one-line call was 930 or 34,700 input tokens, by chance.
    cmd = ["claude", "-p", "--output-format", "json", "--system-prompt", system,
           "--tools", "", "--no-session-persistence", "--strict-mcp-config"]
    if model:
        cmd += ["--model", model]
    envelope = {}
    try:
        with tempfile.TemporaryDirectory() as cwd:
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
            if self.path in ("/feedback", "/applied"):
                # From the editor, as text/plain so the browser needs no preflight request.
                #   /feedback  an author accepted a repair ("rejected": the candidates passed over),
                #              or took an earlier answer back ("forget": true)
                #   /applied   what "Fix all" wrote, so the next check can see what became of it
                try:
                    import refplan
                    length = int(self.headers.get("Content-Length", "0"))
                    body = json.loads(self.rfile.read(length).decode("utf-8"))
                    if self.path == "/applied":
                        stored = refplan.record_applied(body.get("edits"), body.get("failed"), map_path=body.get("map"))
                        _log("Fix all recorded: %d edits" % stored)
                        self.send_json(200, {"recorded": stored})
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
