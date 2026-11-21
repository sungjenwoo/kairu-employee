"""research.web_read: reads the text of up to 3 web pages, as one Guardian action in its own process.

Each page gets 8 seconds and at most 200 KB, read with Python's own urllib and html.parser. It keeps text only:
nothing from a page is run, and nothing is saved as a file. A page that is not text (a download, a program, a PDF)
is refused before its body is read. Scripts, styles, hidden parts and forms are left out, because a page can hide
words there that no person sees.

The address leaves this PC, so it is checked first, and each redirect again: web addresses only (http, https, ports
80 and 443), no user name or password in them, nothing the privacy filter calls a secret. Every address a site name
turns into must be on the public internet, and that checked address is the one connected to, so a page or a
search result cannot point Kairu at this PC, your router or anything else on your own network.

Three pages at once, in one process, because each page in its own process would cost three times the memory.
What it reads goes to data/research.db for the question that asked, as data (kairu/research/quarantine.py). Guardian's
log never gets an address: the audit log keeps their hash (policy.yaml: private). KAIRU_TEST_SEARCH also lets it read
pages from that one stand-in on this PC (kairu/research/search.py).
"""

import http.client
import ipaddress
import re
import socket
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from kairu.brain import privacy
from kairu.research.search import JOB, MOST_URL, stand_in
from kairu.research.store import ResearchStore

PAGE_SECONDS = 8
MOST_BYTES = 200 * 1024
MOST_TEXT = 40_000  # characters kept of one page
MOST_REDIRECTS = 3
PORTS = {"http": 80, "https": 443}
KINDS = ("text/html", "application/xhtml+xml", "text/plain")
USER_AGENT = "Mozilla/5.0 (compatible; Kairu/1; a personal assistant reading one page for its owner)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9",
           "Accept-Language": "en-IN,en;q=0.9"}
SKIP = {"script", "style", "noscript", "template", "svg", "math", "iframe", "object", "embed", "canvas", "audio", "video",
        "nav", "footer", "aside", "form", "button", "select", "textarea", "dialog"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BREAK = {"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table", "section", "article", "br", "hr",
         "blockquote", "pre", "header", "main", "dd", "dt", "figcaption"}
HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|opacity\s*:\s*0(?:\.0+)?\s*(?:;|$)", re.I)


class NotPublic(OSError):
    """An address this reader may not reach. Its text is a label, never the address."""


def main(data_dir: str, job: str, url1: str = "", url2: str = "", url3: str = "") -> None:
    if not JOB.fullmatch(job):
        print("research.web_read: not a read it can do", file=sys.stderr)
        raise SystemExit(1)
    ResearchStore(data_dir).put(job, "pages", {"pages": read_all([url for url in (url1, url2, url3) if url])})


def read_all(urls: list[str], seconds: float = PAGE_SECONDS) -> list[dict]:
    """The pages, in the same order: {"url", "title", "text"}, or {"url", "problem"}. At most `seconds` in all."""
    opener = make_opener()
    pages: list[dict | None] = [None] * len(urls)

    def read_one(place: int, url: str) -> None:
        pages[place] = read_page(url, opener, seconds)

    threads = [threading.Thread(target=read_one, args=item, daemon=True) for item in enumerate(urls)]
    deadline = time.monotonic() + seconds + 0.25
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))
    return [page or {"url": url, "problem": f"took longer than {seconds:g} s"} for page, url in zip(pages, urls)]


def read_page(url: str, opener, seconds: float = PAGE_SECONDS) -> dict:
    """One page's text, or why not (a label)."""
    deadline = time.monotonic() + seconds
    try:
        check_address(url)
        with opener.open(urllib.request.Request(url, headers=HEADERS), timeout=seconds) as response:
            why = why_not_text(response.headers)
            if why:
                return {"url": url, "problem": why}
            raw = read_some(response, deadline)
            final = response.url
            charset = response.headers.get_content_charset()
            plain_text = response.headers.get_content_type() == "text/plain"
    except urllib.error.HTTPError as error:
        error.close()
        return {"url": url, "problem": f"the site answered HTTP {error.code}"}
    except urllib.error.URLError as error:
        reason = error.reason
        return {"url": url, "problem": str(reason) if isinstance(reason, NotPublic) else _failed(reason)}
    except NotPublic as error:
        return {"url": url, "problem": str(error)}
    except (OSError, http.client.HTTPException, ValueError) as error:
        return {"url": url, "problem": _failed(error)}
    text = decode(raw, charset)
    if plain_text:
        return {"url": final, "title": "", "text": text[:MOST_TEXT]}
    title, body = extract(text)
    return {"url": final, "title": title, "text": body}


def _failed(error) -> str:
    return "it took too long" if isinstance(error, TimeoutError) else f"it could not be read ({type(error).__name__})"


def why_not_text(headers) -> str:
    """A page is text; anything else is a download, and is not read."""
    if headers.get_content_type() not in KINDS or not headers.get("Content-Type"):
        return "it is not a text page, so it was not read"
    if headers.get_content_disposition() == "attachment":
        return "it is a download, so it was not read"
    if (headers.get("Content-Encoding") or "identity").strip().lower() != "identity":
        return "it came compressed, so it was not read"
    return ""


def read_some(response, deadline: float) -> bytes:
    """At most MOST_BYTES, and nothing after the deadline: a slow site is cut off, and what came is kept."""
    raw = b""
    while len(raw) < MOST_BYTES and time.monotonic() < deadline:
        try:
            piece = response.read1(MOST_BYTES - len(raw))
        except TimeoutError:
            break
        if not piece:
            break
        raw += piece
    return raw


def decode(raw: bytes, charset: str | None) -> str:
    named = re.search(rb"charset=[\"']?([A-Za-z0-9_-]{2,40})", raw[:2048])
    for candidate in (charset, named.group(1).decode("ascii") if named else None, "utf-8"):
        if candidate:
            try:
                return raw.decode(candidate, errors="replace")
            except LookupError:
                continue
    return raw.decode("utf-8", errors="replace")


# --- the text of a page ---------------------------------------------------------------------------------

class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.parts, self.size, self._in_title = "", [], 0, False
        self._skipping, self._depth = None, 0

    def handle_starttag(self, tag, attrs):
        if self._skipping:
            if tag == self._skipping:
                self._depth += 1
            return
        if tag not in VOID and (tag in SKIP or _hidden(attrs)):
            self._skipping, self._depth = tag, 1
        elif tag == "title" and not self.title:
            self._in_title = True
        elif tag in BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self._skipping:
            if tag == self._skipping:
                self._depth -= 1
                if not self._depth:
                    self._skipping = None
            return
        if tag == "title":
            self._in_title = False
        elif tag in BREAK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skipping:
            return
        if self._in_title:
            self.title += data
        elif self.size < MOST_TEXT:
            self.parts.append(re.sub(r"\s+", " ", data))  # a line break in a page's source is only a space
            self.size += len(data)


def _hidden(attrs) -> bool:
    found = dict(attrs)
    return ("hidden" in found or (found.get("aria-hidden") or "").lower() == "true"
            or bool(HIDDEN_STYLE.search(found.get("style") or "")))


def extract(html: str) -> tuple[str, str]:
    """(title, the words a person would read). Comments, scripts, styles and hidden parts are left out."""
    parser = _Text()
    try:
        parser.feed(html)
        parser.close()
    except (AssertionError, ValueError):  # a page that breaks the parser: what was read so far is what there is
        pass
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    return " ".join(parser.title.split())[:200], "\n".join(line for line in lines if line)[:MOST_TEXT]


# --- where a read may go -------------------------------------------------------------------------------

def check_address(url: str) -> None:
    """Raises NotPublic for what is not a plain public web address, before anything leaves this PC."""
    if len(url) > MOST_URL:
        raise NotPublic("its address is too long")
    try:
        parts = urllib.parse.urlsplit(url)
        port = parts.port
    except ValueError:
        raise NotPublic("its address could not be read") from None
    if parts.scheme not in PORTS or not parts.hostname:
        raise NotPublic("it is not a web address")
    if parts.username is not None or parts.password is not None:
        raise NotPublic("its address has a user name or password in it")
    if privacy.secrets_in(url):
        raise NotPublic("its address looks as if it holds a key or a code")
    if port not in (None, *PORTS.values()) and _stand_in_at() != (parts.hostname, port):
        raise NotPublic("its address uses a port that is not for the web")


def public_address(address: str) -> bool:
    """True for an address on the public internet: not this PC, your network, a multicast or a reserved one."""
    ip = ipaddress.ip_address(address.split("%")[0])
    if ip.version == 6:
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip.sixtofour is not None or ip.teredo is not None or ip in ipaddress.ip_network("64:ff9b::/96"):
            return False  # an old way of carrying an IPv4 address inside an IPv6 one: not needed, and it could hide one
    return ip.is_global and not ip.is_multicast


def _stand_in_at() -> tuple[str, int] | None:
    address = stand_in()
    if not address:
        return None
    parts = urllib.parse.urlsplit(address)
    return parts.hostname, parts.port


def _connect(address, timeout=PAGE_SECONDS, source_address=None):
    """A connection only to public addresses of the web's ports, checked at the moment of connecting: a site name that
    changes its answer after a first check, or a redirect to this PC, still gets nowhere."""
    host, port = address
    local_test = _stand_in_at() == (host, port)
    if port not in PORTS.values() and not local_test:
        raise NotPublic("its address uses a port that is not for the web")
    try:
        found = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except UnicodeError:
        raise NotPublic("its address could not be read") from None
    if not found or not (local_test or all(public_address(item[4][0]) for item in found)):
        raise NotPublic("its address is not on the public internet")
    problem = None
    for family, kind, proto, _, where in found:
        connection = socket.socket(family, kind, proto)
        try:
            connection.settimeout(timeout if isinstance(timeout, (int, float)) else PAGE_SECONDS)  # never without a limit
            connection.connect(where)
            return connection
        except OSError as error:
            problem = error
            connection.close()
    raise problem


class _Http(http.client.HTTPConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connect


class _Https(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._create_connection = _connect


class _HttpHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(_Http, req)


class _HttpsHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_Https, req, context=self._context)


class _Redirects(urllib.request.HTTPRedirectHandler):
    max_redirections = MOST_REDIRECTS

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_address(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def make_opener() -> urllib.request.OpenerDirector:
    """Web addresses only: no files, no FTP, no proxy, no cookies. Certificates are checked as usual."""
    opener = urllib.request.OpenerDirector()
    for handler in (_HttpHandler(), _HttpsHandler(context=ssl.create_default_context()), _Redirects(),
                    urllib.request.HTTPDefaultErrorHandler(), urllib.request.HTTPErrorProcessor(),
                    urllib.request.UnknownHandler()):
        opener.add_handler(handler)
    return opener
