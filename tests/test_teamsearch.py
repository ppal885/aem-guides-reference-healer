"""The team search tool: offered only when set up, maps results to this repository's files, and
never stops a check when the service does not answer."""
import http.server
import json
import os
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import refcheck  # noqa: E402
import refheal  # noqa: E402
import teamsearch  # noqa: E402

HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">\n'


def repo():
    files = [{"id": "GUID-a1", "path": "/content/dam/t/console_install.dita",
              "xml": HEAD + '<topic id="ci"><title>Putting the billing console in place</title><body>'
                     '<section id="install-console"><title>Install the billing console</title></section></body></topic>'},
             {"id": "GUID-a2", "path": "/content/dam/t/display.dita",
              "xml": HEAD + '<topic id="d"><title>Display</title><body><p id="night-mode">Night mode</p></body></topic>'}]
    return refcheck.Repo(files=files)


class Service:
    """A stand-in for the search service on a local port: answers with the given results, or the given status."""

    def __init__(self, results=None, status=200):
        seen = self.seen = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append((self.headers.get("Authorization"), json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                body = json.dumps({"results": results or [], "total": len(results or [])}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d/search" % self.server.server_port
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class TeamSearch(unittest.TestCase):
    def setUp(self):
        self.repo = repo()

    def with_service(self, service, key="test-key"):
        return mock.patch.multiple(teamsearch, URL=service.url), mock.patch.dict(os.environ, {"REFHEAL_SEARCH_KEY": key})

    def test_not_offered_without_an_address_and_a_key(self):
        names = lambda: [spec["name"] for spec in refheal.tool_specs(refheal.Tools(self.repo), False)]
        with mock.patch.object(teamsearch, "URL", ""), mock.patch.dict(os.environ, {"REFHEAL_SEARCH_KEY": "k"}):
            self.assertNotIn("find_in_team_search", names())
        with mock.patch.object(teamsearch, "URL", "http://127.0.0.1:1/search"), mock.patch.dict(os.environ, {}, clear=True):
            self.assertNotIn("find_in_team_search", names())
        with mock.patch.object(teamsearch, "URL", "http://127.0.0.1:1/search"), mock.patch.dict(os.environ, {"REFHEAL_SEARCH_KEY": "k"}):
            self.assertIn("find_in_team_search", names())

    def test_results_become_files_of_this_repository(self):
        service = Service([{"asset_id": "GUID-a1.dita", "title": "Putting the billing console in place"},
                           {"asset_id": "GUID-a1", "title": "the same file again"},
                           {"asset_id": "GUID-elsewhere", "title": "a topic of another map"}])
        url, env = self.with_service(service)
        with url, env:
            found = refheal.Tools(self.repo).find_in_team_search({"query": "Kestrel setup"})
        service.stop()
        self.assertEqual([f["path"] for f in found["files"]], ["content/dam/t/console_install.dita"])
        self.assertEqual(found["summary"], "1 files (1 more outside this map)")
        key, body = service.seen[0]
        self.assertEqual(key, "Bearer test-key")
        self.assertEqual((body["query"], body["search_type"], body["vocabulary_mode"]), ("Kestrel setup", "FULL_TEXT", "on"))

    def test_a_service_error_is_said_and_the_finder_goes_on(self):
        service = Service(status=500)
        url, env = self.with_service(service)
        with url, env:
            found = teamsearch.search(self.repo, "Kestrel setup")
        service.stop()
        self.assertEqual(found, {"summary": "the team search did not answer (HTTP 500)", "files": []})

    def test_a_wrong_key_is_said_like_any_refusal(self):
        service = Service(status=401)
        url, env = self.with_service(service, key="wrong")
        with url, env:
            self.assertIn("HTTP 401", teamsearch.search(self.repo, "x")["summary"])
        service.stop()

    def test_no_service_on_the_address(self):
        with mock.patch.object(teamsearch, "URL", "http://127.0.0.1:1/search"), \
                mock.patch.dict(os.environ, {"REFHEAL_SEARCH_KEY": "k"}):
            found = teamsearch.search(self.repo, "x")
        self.assertTrue(found["summary"].startswith("the team search is not reachable"))
        self.assertEqual(found["files"], [])


if __name__ == "__main__":
    unittest.main()
