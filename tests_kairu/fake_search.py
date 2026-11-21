"""A stand-in for the web, on 127.0.0.1, for the research tests. Nothing leaves the PC.

Kairu reaches it through KAIRU_TEST_SEARCH (kairu/research/search.py): a search comes here as GET /search?q=..., and
it answers with results that point at pages it also serves. tools/research_gate.py uses it for the gate test's test
page and the stop. A test can set a page's words, headers and status, make the search or a page slow, and read every
search and page read it got.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


class FakeSearch:
    def __init__(self):
        self.queries: list[dict] = []  # {"q", "recent"}
        self.read: list[str] = []  # the paths of the pages read
        self.results: list[dict] = []
        self.pages: dict[str, tuple[int, dict, bytes]] = {}
        self.search_delay = 0.0
        self.page_delay = 0.0
        self.search_status = 200
        self._lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                parts = urlsplit(self.path)
                if parts.path == "/search":
                    words = parse_qs(parts.query)
                    with fake._lock:
                        fake.queries.append({"q": words.get("q", [""])[0], "recent": words.get("recent", [""])[0]})
                    time.sleep(fake.search_delay)
                    self._answer(fake.search_status, {"Content-Type": "application/json"}, json.dumps(fake.results).encode())
                    return
                with fake._lock:
                    fake.read.append(parts.path)
                time.sleep(fake.page_delay)
                status, headers, body = fake.pages.get(parts.path, (404, {"Content-Type": "text/html"}, b"gone"))
                self._answer(status, headers, body)

            def _answer(self, status, headers, body):
                try:
                    self.send_response(status)
                    for name, value in headers.items():
                        self.send_header(name, value)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except OSError:
                    pass  # the search was stopped on its way: nobody is listening any more

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def page(self, name: str, title: str, words: str, snippet: str = "", status: int = 200,
             headers: dict | None = None) -> str:
        """A page, listed in the search's results. Its address."""
        html = f"<html><head><title>{title}</title></head><body><p>{words}</p></body></html>".encode()
        self.pages[f"/{name}"] = (status, {"Content-Type": "text/html; charset=utf-8", **(headers or {})}, html)
        self.results.append({"title": title, "href": f"{self.url}/{name}", "body": snippet or words[:80]})
        return f"{self.url}/{name}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
