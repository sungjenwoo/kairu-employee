"""A small stand-in for an ntfy server, on 127.0.0.1, for the Kairu Link tests. Nothing leaves the PC.

It speaks the part of ntfy's HTTP API Kairu uses:
    POST /TOPIC                        keep a message ({"id", "time", "event": "message", "topic", "message"})
    GET  /T1,T2/json?since=X[&poll=1]  the kept messages since X (a unix time, a message id, or "all"), one JSON
                                       per line; without poll=1 the connection stays open for new ones, with a
                                       "keepalive" line every `keepalive` seconds, as ntfy does
A test can make it answer 429 ("too many requests") for the next requests, or keep a message with an
older time, as if it had waited in the queue.
"""

import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


class FakeRelay:
    def __init__(self, keepalive: float = 1.0):
        self.messages: list[dict] = []
        self.keepalive = keepalive
        self.refuse_next, self.retry_after = 0, 1
        self.requests: list[tuple[str, str]] = []
        self._changed = threading.Condition()
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                relay.requests.append(("POST", self.path))
                # read the message first, even to refuse it: closing with it unread makes Windows abort the connection
                body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")
                if relay._refusing(self):
                    return
                kept = relay.publish(self.path.strip("/"), body)
                self._send(200, json.dumps(kept).encode())

            def do_GET(self):
                relay.requests.append(("GET", self.path))
                if relay._refusing(self):
                    return
                parts = urlsplit(self.path)
                topics = parts.path.strip("/").removesuffix("/json").split(",")
                query = parse_qs(parts.query)
                since, poll = query.get("since", ["all"])[0], query.get("poll", ["0"])[0] == "1"
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                try:
                    if not poll:
                        self._line({"id": secrets.token_hex(6), "time": int(time.time()), "event": "open",
                                    "topic": ",".join(topics)})
                    with relay._changed:
                        count = len(relay.messages)
                        sent = relay._since(relay.messages[:count], topics, since)
                    for message in sent:
                        self._line(message)
                    if poll:
                        return
                    while not relay.closed:
                        with relay._changed:
                            relay._changed.wait(relay.keepalive)
                        new = relay.messages[count:]
                        count += len(new)
                        for message in new:
                            if message["topic"] in topics:
                                self._line(message)
                        if not new:
                            self._line({"id": secrets.token_hex(6), "time": int(time.time()), "event": "keepalive",
                                        "topic": ",".join(topics)})
                except OSError:
                    pass

            def _line(self, data):
                self.wfile.write(json.dumps(data).encode() + b"\n")
                self.wfile.flush()

            def _send(self, status, body):
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.closed = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def publish(self, topic: str, text: str, when: float | None = None) -> dict:
        kept = {"id": secrets.token_hex(6), "time": int(time.time() if when is None else when), "event": "message",
                "topic": topic, "message": text}
        with self._changed:
            self.messages.append(kept)
            self._changed.notify_all()
        return kept

    def on(self, topic: str) -> list[dict]:
        return [message for message in self.messages if message["topic"] == topic]

    @staticmethod
    def _since(messages, topics, since):
        mine = [message for message in messages if message["topic"] in topics]
        if since == "all":
            return mine
        if since.isdigit():
            return [message for message in mine if message["time"] >= int(since)]
        ids = [message["id"] for message in mine]
        return mine[ids.index(since) + 1:] if since in ids else mine

    def _refusing(self, handler) -> bool:
        if self.refuse_next <= 0:
            return False
        self.refuse_next -= 1
        handler.send_response(429)
        handler.send_header("Retry-After", str(self.retry_after))
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return True

    def close(self) -> None:
        self.closed = True
        with self._changed:
            self._changed.notify_all()
        self.server.shutdown()
        self.server.server_close()
