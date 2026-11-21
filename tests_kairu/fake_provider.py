"""A stand-in for the free AI providers, on 127.0.0.1, for the brain tests. Nothing leaves the PC.

Kairu reaches it through KAIRU_TEST_PROVIDERS (kairu/brain/providers.py): every provider's requests come
here as POST /NAME/PATH, with the same OpenAI-style body and Authorization header the real one would get (Gemini's own
generateContent address, kairu/brain/providers.py gemini_url, gets Gemini's own kind of answer).
A test can set what each provider answers, make one answer 429 ("at its free limit") or another status,
and read every request it got.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeProviders:
    def __init__(self):
        self.requests: list[dict] = []  # {"provider", "path", "authorization", "body"}
        self.answers: dict[str, str] = {}
        self.script: dict[str, list[str]] = {}  # provider -> answers given first, one for each request, in order
        self.status: dict[str, tuple[int, dict, dict]] = {}  # provider -> (HTTP status, headers, JSON body)
        self.delay = 0.0
        self._lock = threading.Lock()
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                provider = self.path.strip("/").split("/", 1)[0]
                try:
                    parsed = json.loads(body)
                except ValueError:
                    parsed = None
                with fake._lock:
                    fake.requests.append({"provider": provider, "path": self.path, "body": parsed,
                                          "authorization": self.headers.get("Authorization", "")})
                if fake.delay:
                    import time
                    time.sleep(fake.delay)
                status, headers, data = fake.status.get(provider) or (200, {}, None)
                if data is None:
                    with fake._lock:
                        scripted = fake.script[provider].pop(0) if fake.script.get(provider) else None
                    said = scripted or fake.answers.get(provider, f"An answer from {provider}.")
                    data = {"id": "x", "object": "chat.completion", "choices": [{"index": 0, "message": {
                        "role": "assistant", "content": said}}],
                        "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150}}
                    if provider == "gemini" and self.path.endswith(":generateContent"):  # Google's own address and answer
                        data = {"candidates": [{"content": {"role": "model", "parts": [{"text": said}]}, "finishReason": "STOP"}],
                                "usageMetadata": {"promptTokenCount": 1400, "candidatesTokenCount": 40}}
                    if provider == "groq":
                        headers = {"x-ratelimit-limit-requests": "1000", "x-ratelimit-remaining-requests": "988",
                                   "x-ratelimit-reset-requests": "2m59.56s", **headers}
                raw = json.dumps(data).encode()
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    for name, value in headers.items():
                        self.send_header(name, value)
                    self.end_headers()
                    self.wfile.write(raw)
                except OSError:
                    pass  # the question was stopped on its way: nobody is listening any more

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def limited(self, provider: str, retry_after: float = 600) -> None:
        """Answer 429, as a provider at its free limit does."""
        self.status[provider] = (429, {"retry-after": str(retry_after)},
                                 {"error": {"message": "Rate limit reached: requests per day", "type": "requests"}})

    def heard(self, provider: str | None = None) -> list[dict]:
        with self._lock:
            return [request for request in self.requests if provider in (None, request["provider"])]

    def text_heard(self) -> str:
        """Everything the providers were sent, as one text: to check what never left."""
        return json.dumps(self.heard())

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
