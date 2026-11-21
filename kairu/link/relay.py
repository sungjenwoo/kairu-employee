"""The Gate's relay: an ntfy server (https://ntfy.sh to start, your own later; LINK.md), over HTTPS.

    publish(topic, text)        POST {relay}/{topic}: one message of at most 4,096 bytes
    subscribe(topics, since)    GET {relay}/{t1,t2}/json?since=T: the messages waiting since T first, then
                                each new one as it comes, on one long-lived connection (a long poll; ntfy
                                sends a "keepalive" line every 45 s, so a silent connection is a dead one)
    poll(topics, since)         the same, but only what is waiting now

ntfy keeps a message for 12 hours on ntfy.sh: that is the Gate's queue. Each topic is 128 random bits;
anyone who learns one can post to it or read its envelopes, but cannot open or forge them
(kairu/link/message.py). When the relay answers "too many requests" (HTTP 429), the caller waits:
Backoff gives how long (the relay's Retry-After, or longer each time).

The base address comes from config.yaml (link.relay), so a home ntfy server can replace ntfy.sh.
Standard library only.
"""

import http.client
import json
import socket
import ssl
import threading
from urllib.parse import urlsplit

from kairu.link.kinds import MAX_ENVELOPE_BYTES, TOPIC

USER_AGENT = "kairu-link/1"
READ_SECONDS = 70  # one read may wait this long: longer than ntfy's 45-second keepalive
SEND_SECONDS = 20


class RelayError(Exception):
    pass


class RateLimited(RelayError):
    def __init__(self, retry_after: float | None):
        super().__init__("the relay says too many requests (HTTP 429)")
        self.retry_after = retry_after


class Backoff:
    """How long to wait after a failure: 2 s, 4 s, 8 s ... at most 5 minutes; at least what the relay asked."""

    def __init__(self, first: float = 2, most: float = 300):
        self.first, self.most, self.wait = first, most, 0.0

    def next(self, retry_after: float | None = None, rate_limited: bool = False) -> float:
        self.wait = min(self.most, max(self.first * (5 if rate_limited else 1), self.wait * 2))
        return min(self.most, max(self.wait, retry_after or 0))

    def reset(self) -> None:
        self.wait = 0.0


class Relay:
    def __init__(self, base: str, read_seconds: float = READ_SECONDS):
        parts = urlsplit(base.rstrip("/"))
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.query or parts.fragment:
            raise RelayError(f"not a relay address: {base!r}")
        self.base, self.secure, self.host, self.port = base.rstrip("/"), parts.scheme == "https", parts.hostname, parts.port
        self.path, self.read_seconds = parts.path, read_seconds

    def _connect(self, timeout: float) -> http.client.HTTPConnection:
        if self.secure:
            return http.client.HTTPSConnection(self.host, self.port, timeout=timeout, context=ssl.create_default_context())
        return http.client.HTTPConnection(self.host, self.port, timeout=timeout)

    def publish(self, topic: str, text: str) -> dict:
        """Post one message. Its reply ({"id", "time", ...}). Raises RateLimited or RelayError."""
        _check_topic(topic)
        body = text.encode("utf-8")
        if len(body) > MAX_ENVELOPE_BYTES:
            raise RelayError("the message is too long for the relay")
        connection = self._connect(SEND_SECONDS)
        try:
            # Firebase: no - ntfy.sh need not pass it on to Google for its own Android app; Kairu does not use that
            connection.request("POST", f"{self.path}/{topic}", body=body, headers={
                "User-Agent": USER_AGENT, "Content-Type": "text/plain; charset=utf-8", "Firebase": "no"})
            response = connection.getresponse()
            answer = response.read(65536)
            _check_status(response)
            return json.loads(answer)
        except (OSError, http.client.HTTPException, ValueError) as error:
            raise RelayError(f"could not reach the relay ({type(error).__name__}: {error})") from None
        finally:
            connection.close()

    def subscribe(self, topics: list[str], since: int | str = "all") -> "Subscription":
        """Open the long poll. Raises RateLimited or RelayError."""
        return Subscription(self, topics, since, poll=False)

    def poll(self, topics: list[str], since: int | str = "all") -> list[dict]:
        with Subscription(self, topics, since, poll=True) as subscription:
            return [event for event in subscription if event.get("event") == "message"]


class Subscription:
    """One open connection to the relay: iterate it for events ({"event": "message", "id", "time", "message", ...}).

    close() may be called from another thread: the connection is cut and the iteration ends.
    """

    def __init__(self, relay: Relay, topics: list[str], since, poll: bool):
        for topic in topics:
            _check_topic(topic)
        if not topics:
            raise RelayError("no topics to read")
        self._closed = threading.Event()
        self._connection = relay._connect(relay.read_seconds)
        query = f"since={since}" + ("&poll=1" if poll else "")
        try:
            self._connection.request("GET", f"{relay.path}/{','.join(topics)}/json?{query}",
                                     headers={"User-Agent": USER_AGENT})
            self._response = self._connection.getresponse()
            if self._response.status != 200:
                self._response.read(65536)
            _check_status(self._response)
        except (OSError, http.client.HTTPException) as error:
            self._connection.close()
            raise RelayError(f"could not reach the relay ({type(error).__name__}: {error})") from None
        except RelayError:
            self._connection.close()
            raise

    def __iter__(self):
        while not self._closed.is_set():
            try:
                line = self._response.readline(MAX_ENVELOPE_BYTES * 4)
            except (OSError, http.client.HTTPException, ValueError) as error:
                if self._closed.is_set():
                    return
                raise RelayError(f"the relay connection broke ({type(error).__name__})") from None
            if not line:
                return  # the relay ended the connection
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                yield event

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def close(self) -> None:
        self._closed.set()
        sock = self._connection.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)  # wakes a read waiting in another thread
            except OSError:
                pass
        self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _check_topic(topic: str) -> None:
    if not TOPIC.fullmatch(topic or ""):
        raise RelayError("a Gate topic is 32 hex digits")


def _check_status(response) -> None:
    if response.status == 429:
        try:
            retry_after = float(response.getheader("Retry-After") or "")
        except ValueError:
            retry_after = None
        raise RateLimited(retry_after)
    if response.status != 200:
        raise RelayError(f"the relay answered HTTP {response.status}")
