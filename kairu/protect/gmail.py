"""The Gmail monitor: reads your inbox through Google's Gmail API with the read-only permission, and nothing else.

Connecting (`kairu protect connect-gmail`, High tier: "yes" and your PIN). Guardian runs connect():
your browser opens Google's own sign-in page; you sign in there yourself and allow read-only access
(Kairu never sees your password). Google sends a one-time code back to this PC only, on 127.0.0.1,
checked with a random "state" and PKCE, and Kairu swaps it for a key that can only read mail.
The key is sealed on this PC (kairu/protect/sealed.py). You can remove it with
`kairu protect disconnect-gmail`, or in your Google Account (Security, Third-party connections).

Watching (GmailMonitor, inside protect.watch): every few minutes it asks Gmail what arrived in the
inbox since the last look (Gmail's change history), reads each new email, and runs the fixed rules
(kairu/protect/mailrules.py and kairu/protect/deadlines.py) on this PC. After a gap, such as the
PC being off, it catches up from where it stopped and marks those alerts "found late".

What it never does, enforced in Google.request(): send, delete, move, label or mark mail (those are
not read-only, and only GET requests to the Gmail API are made); open links or attachments; send
email text anywhere. The only other requests are to Google's sign-in service, for the key itself.
"""

import base64
import hashlib
import html.parser
import http.server
import json
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path

from kairu.protect import deadlines, mailrules, sealed
from kairu.protect.store import ACTIVE, NOT_SET_UP, Finding, ProtectStore

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://gmail.googleapis.com/gmail/v1/users/me/"
SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
KEY_NAME = "protect-gmail.key"
SIGN_IN_SECONDS = 600  # Google may ask for a phone check first
FIRST_LOOK = "in:inbox newer_than:2d"  # the first check after connecting also looks at the last two days
MOST_MESSAGES = 500  # in one check
BODY_LIMIT = 300_000  # characters of an email's text read, at most
SIGNING_IN = "Signing in"
ACCOUNT = "gmail:account"  # in protection.db's settings: the address Kairu reads, shown by `kairu protect status`


class PermissionRemoved(Exception):
    """Gmail no longer lets Kairu read: the key was removed in your Google Account, or expired."""


class Unreachable(Exception):
    """Google could not be reached, or answered with an error that may pass."""


class NotFound(Exception):
    pass


class ConnectError(Exception):
    pass


def https_request(method: str, url: str, data: bytes | None = None, headers: dict | None = None, timeout: float = 30):
    """(status, body) of one HTTPS request. Raises Unreachable when there is no answer."""
    request = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(5_000_000)
    except urllib.error.HTTPError as error:
        return error.code, error.read(100_000)
    except (urllib.error.URLError, OSError) as error:
        raise Unreachable(str(getattr(error, "reason", error))) from None


def allowed(method: str, url: str) -> bool:
    """The only requests the Gmail monitor makes: reading the Gmail API, and Google's sign-in key service."""
    if method == "GET":
        return url.startswith(API)
    return method == "POST" and url in (TOKEN_URL, REVOKE_URL)


def _send(transport, method: str, url: str, form: dict | None = None, headers: dict | None = None):
    if not allowed(method, url):
        raise PermissionError(f"the Gmail monitor may not make this request: {method} {url.split('?')[0]}")
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    sent = {"Content-Type": "application/x-www-form-urlencoded"} if form is not None else {}
    sent.update(headers or {})
    return transport(method, url, data, sent)


def _json(body: bytes) -> dict:
    try:
        answer = json.loads(body or b"{}")
    except ValueError:
        return {}
    return answer if isinstance(answer, dict) else {}


class Google:
    """Gmail, read-only, with a key from sign_in()."""

    def __init__(self, secret: dict, transport=https_request):
        self.secret, self.transport = secret, transport
        self._access, self._expires = None, 0.0

    def token(self) -> str:
        if self._access and time.monotonic() < self._expires - 60:
            return self._access
        status, body = _send(self.transport, "POST", TOKEN_URL, {
            "client_id": self.secret["client_id"], "client_secret": self.secret.get("client_secret", ""),
            "refresh_token": self.secret["refresh_token"], "grant_type": "refresh_token"})
        answer = _json(body)
        if answer.get("error") in ("invalid_grant", "unauthorized_client", "invalid_client"):
            raise PermissionRemoved(f"Google no longer accepts Kairu's key ({answer['error']}): connect Gmail again")
        if status != 200 or not isinstance(answer.get("access_token"), str):
            raise Unreachable(f"Google's sign-in service answered {status}")
        if SCOPE not in str(answer.get("scope", SCOPE)).split():
            raise PermissionRemoved("read-only Gmail access is no longer granted: connect Gmail again")
        self._access, self._expires = answer["access_token"], time.monotonic() + float(answer.get("expires_in", 3600))
        return self._access

    def get(self, path: str, **params) -> dict:
        url = API + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
        status, body = 0, b""
        for attempt in (1, 2):
            status, body = _send(self.transport, "GET", url, headers={"Authorization": f"Bearer {self.token()}"})
            if status != 401 or attempt == 2:
                break
            self._access = None  # an old access token: get a fresh one once
        if status == 200:
            return _json(body)
        if status == 404:
            raise NotFound(path)
        text = body.decode("utf-8", "replace")[:500]
        if status == 401 or (status == 403 and re.search(r"insufficient|forbidden|PERMISSION_DENIED", text, re.I)
                             and "rateLimit" not in text):
            raise PermissionRemoved("Gmail refused to let Kairu read: connect Gmail again")
        raise Unreachable(f"Gmail answered {status}")


# --- signing in -----------------------------------------------------------------------------------

def read_client(client_file: str) -> dict:
    """The client id and secret from the file Google Cloud gave you (OAuth client, type Desktop app)."""
    path = Path(client_file)
    try:
        if path.stat().st_size > 100_000:
            raise ConnectError(f"{path.name} is too large to be a Google OAuth client file")
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConnectError(f"there is no file {path}") from None
    except (OSError, ValueError) as error:
        raise ConnectError(f"{path.name} could not be read ({error})") from None
    if not isinstance(data, dict) or not isinstance(data.get("installed"), dict):
        if isinstance(data, dict) and "web" in data:
            raise ConnectError("this key is for a web application; in Google Cloud make an OAuth client of type "
                               "\"Desktop app\" and download its file")
        raise ConnectError(f"{path.name} is not a Google OAuth client file (it has no \"installed\" section)")
    client = data["installed"]
    if not isinstance(client.get("client_id"), str):
        raise ConnectError(f"{path.name} has no client_id")
    return {"client_id": client["client_id"], "client_secret": str(client.get("client_secret", ""))}


class _Loopback(http.server.HTTPServer):
    """The page on 127.0.0.1 that Google sends you back to, with the one-time code. Answers only the right state."""

    def __init__(self, state: str):
        self.state, self.code, self.refused = state, None, None
        super().__init__(("127.0.0.1", 0), _Back)
        self.timeout = 0.5

    @property
    def port(self) -> int:
        return self.server_address[1]

    def wait(self, seconds: float) -> str:
        deadline = time.monotonic() + seconds
        while self.code is None and self.refused is None:
            if time.monotonic() > deadline:
                raise ConnectError(f"no answer from Google's sign-in page within {seconds:g} s; try again")
            self.handle_request()
        if self.refused:
            raise ConnectError(self.refused)
        return self.code


class _Back(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 (the name http.server calls)
        parts = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parts.query)
        if parts.path != "/" or query.get("state", [""])[0] != self.server.state:
            return self._answer(404, "Not a Kairu sign-in answer.")
        if "error" in query:
            self.server.refused = ("you did not allow read-only Gmail access" if query["error"][0] == "access_denied"
                                   else f"Google refused the sign-in ({query['error'][0]})")
            return self._answer(200, f"Kairu: Gmail was not connected ({self.server.refused}). You can close this tab.")
        if "code" not in query:
            return self._answer(400, "No code in this answer.")
        self.server.code = query["code"][0]
        self._answer(200, "Kairu: thank you. You can close this tab and go back to the terminal.")

    def _answer(self, status: int, text: str):
        page = f"<!doctype html><meta charset=utf-8><title>Kairu</title><p style='font:16px sans-serif'>{text}</p>"
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page.encode())

    def log_message(self, *args):  # nothing about the request is printed or kept
        pass


def sign_in(client: dict, transport=https_request, open_browser=webbrowser.open, show=None, seconds: float = SIGN_IN_SECONDS) -> dict:
    """Google's sign-in in your browser; the sealed-to-be key: {client_id, client_secret, refresh_token, email}."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    server = _Loopback(state)
    try:
        redirect = f"http://127.0.0.1:{server.port}/"
        url = AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": client["client_id"], "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
            "access_type": "offline", "prompt": "consent", "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256"})
        if show:
            show(url)
        open_browser(url)
        code = server.wait(seconds)
    finally:
        server.server_close()
    status, body = _send(transport, "POST", TOKEN_URL, {
        "code": code, "client_id": client["client_id"], "client_secret": client["client_secret"],
        "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier})
    answer = _json(body)
    if status != 200 or not isinstance(answer.get("refresh_token"), str):
        raise ConnectError(f"Google gave no key ({answer.get('error_description') or answer.get('error') or status})")
    granted = str(answer.get("scope", "")).split()
    if SCOPE not in granted:
        raise ConnectError("read-only Gmail access was not allowed: tick its box on Google's page and try again")
    if set(granted) - {SCOPE}:
        raise ConnectError("Google granted more than read-only Gmail access, so Kairu did not keep the key")
    secret = {**client, "refresh_token": answer["refresh_token"]}
    google = Google(secret, transport)
    google._access, google._expires = answer.get("access_token"), time.monotonic() + float(answer.get("expires_in", 3600))
    email = google.get("profile").get("emailAddress")
    if not isinstance(email, str):
        raise ConnectError("Gmail did not say which account this is")
    return {**secret, "email": email}


def connect(data_dir: str, client_file: str) -> None:
    """protect.connect_email: what Guardian runs once you approved it with "yes" and your PIN."""
    store = ProtectStore(data_dir)
    store.set_source("gmail", SIGNING_IN, "starting")
    try:
        client = read_client(client_file)
        # Your terminal (`kairu protect connect-gmail`) opens the page: a browser started from here would run
        # inside this action's Job Object and be closed with it.
        secret = sign_in(client, open_browser=lambda url: None, show=lambda url: store.set_source("gmail", SIGNING_IN, url))
    except (ConnectError, Unreachable, PermissionRemoved, NotFound) as error:
        store.set_source("gmail", NOT_SET_UP, f"not connected: {error}")
        raise SystemExit(1) from None
    sealed.write(Path(data_dir) / KEY_NAME, secret)
    store.set_checkpoint("gmail:history", None)  # the first check looks at the last two days
    store.set_setting(ACCOUNT, secret["email"])
    store.set_source("gmail", ACTIVE, f"connected as {secret['email']}, read-only", failures=0)


def disconnect(data_dir: str, transport=https_request) -> None:
    """protect.disconnect_email: ask Google to cancel the key, then delete it here."""
    store = ProtectStore(data_dir)
    path = Path(data_dir) / KEY_NAME
    note = ""
    try:
        secret = sealed.read(path)
    except sealed.SealBroken:
        secret = None
    if secret:
        try:
            status, _ = _send(transport, "POST", REVOKE_URL, {"token": secret["refresh_token"]})
            note = "" if status == 200 else f"; Google answered {status} to cancelling it, so also remove it in your Google Account"
        except Unreachable:
            note = "; Google could not be reached to cancel it, so also remove it in your Google Account"
    sealed.delete(path)
    store.set_checkpoint("gmail:history", None)
    store.set_setting(ACCOUNT, None)
    store.set_source("gmail", NOT_SET_UP, f"disconnected: the key was deleted{note}", failures=0)


# --- reading emails -------------------------------------------------------------------------------

class _Page(html.parser.HTMLParser):
    """An email's HTML as text, and its links as (the text shown, the real address). Nothing is fetched."""
    SKIP = {"script", "style", "head", "title"}
    BREAK = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "table", "section"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text, self.links, self._href, self._shown, self._skip = [], [], None, [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag == "a":
            self._href, self._shown = dict(attrs).get("href"), []
        elif tag in self.BREAK:
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag == "a" and self._href is not None:
            self.links.append((" ".join("".join(self._shown).split()), self._href))
            self._href = None
        elif tag in self.BREAK:
            self.text.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        self.text.append(data)
        if self._href is not None:
            self._shown.append(data)


URL = re.compile(r"https?://[^\s<>\"')\]]+", re.I)


def parse_message(message: dict) -> mailrules.Mail:
    """One message from the Gmail API (format=full) as a Mail. Attachments are only named, never downloaded."""
    payload = message.get("payload") or {}
    headers = {}
    for header in payload.get("headers") or []:
        headers.setdefault(str(header.get("name", "")).lower(), str(header.get("value", "")))
    name, address = parseaddr(headers.get("from", ""))
    plain, pages, attachments, budget = [], [], [], [BODY_LIMIT]

    def walk(part: dict):
        if part.get("filename"):
            attachments.append(str(part["filename"]))
        elif part.get("mimeType") in ("text/plain", "text/html") and (part.get("body") or {}).get("data") and budget[0] > 0:
            text = _decode(part["body"]["data"])[:budget[0]]
            budget[0] -= len(text)
            (plain if part["mimeType"] == "text/plain" else pages).append(text)
        for child in part.get("parts") or []:
            walk(child)

    walk(payload)
    links = []
    if pages:
        page = _Page()
        try:
            page.feed("\n".join(pages))
            page.close()
        except Exception:  # a broken page: keep what was read
            pass
        text, links = "".join(page.text), page.links
    else:
        text = "\n".join(plain)
    links += [(url, url) for url in URL.findall("\n".join(plain))]
    received = None
    if str(message.get("internalDate", "")).isdigit():
        received = datetime.fromtimestamp(int(message["internalDate"]) / 1000, tz=timezone.utc)
    return mailrules.Mail(
        id=str(message.get("id", "")), sender_name=name, sender=address, subject=headers.get("subject", ""),
        received=received, reply_to=parseaddr(headers.get("reply-to", ""))[1],
        auth=headers.get("authentication-results", ""), text=re.sub(r"[ \t]+", " ", text)[:50_000],
        links=links[:300], attachments=attachments[:50], labels=tuple(message.get("labelIds") or ()))


def _decode(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
    except (ValueError, TypeError):
        return ""


# --- the monitor ----------------------------------------------------------------------------------

class GmailMonitor:
    name = "gmail"

    def __init__(self, store: ProtectStore, data_dir, transport=https_request):
        self.store, self.transport = store, transport
        self.key_path = Path(data_dir) / KEY_NAME
        self.gap: tuple[datetime, datetime] | None = None  # (watching stopped, watching started again)

    def set_up(self) -> bool:
        return self.key_path.exists()

    def check(self) -> list[Finding]:
        """The findings for every email that reached the inbox since the last check. Raises PermissionRemoved, Unreachable."""
        try:
            secret = sealed.read(self.key_path)
        except sealed.SealBroken as error:
            raise PermissionRemoved(str(error)) from None
        if not secret:
            return []
        google = Google(secret, self.transport)
        history = self.store.checkpoint("gmail:history")
        if history is None:
            ids, latest = self._list(google, FIRST_LOOK), google.get("profile").get("historyId")
        else:
            try:
                ids, latest = self._history(google, history)
            except NotFound:  # Gmail keeps its change history for about a week; after a longer gap, look by date
                since = self.gap[0] if self.gap else datetime.now(timezone.utc)
                ids = self._list(google, f"in:inbox after:{int(since.timestamp()) - 3600}")
                latest = google.get("profile").get("historyId")
        findings = []
        for message_id in ids[:MOST_MESSAGES]:
            try:
                mail = parse_message(google.get(f"messages/{message_id}", format="full"))
            except NotFound:  # deleted meanwhile
                continue
            if "INBOX" not in mail.labels:
                continue
            try:
                findings += self.judge(mail)
            except Exception as error:  # one odd email never stops the monitor; it is skipped, and said so
                print(f"protect.watch: email {message_id} could not be checked ({type(error).__name__}: {error})",
                      file=sys.stderr)
        if latest:
            self.store.set_checkpoint("gmail:history", str(latest))
        return findings

    def _history(self, google: Google, start: str) -> tuple[list[str], str]:
        ids, token, latest = [], None, start
        while True:
            params = {"startHistoryId": start, "historyTypes": ["messageAdded", "labelAdded"], "labelId": "INBOX",
                      "maxResults": 500}
            if token:
                params["pageToken"] = token
            page = google.get("history", **params)
            latest = str(page.get("historyId") or latest)
            for record in page.get("history") or []:
                for added in record.get("messagesAdded") or []:
                    ids.append(str(added["message"]["id"]))
                for labelled in record.get("labelsAdded") or []:
                    if "INBOX" in (labelled.get("labelIds") or []):
                        ids.append(str(labelled["message"]["id"]))
            token = page.get("nextPageToken")
            if not token or len(ids) >= MOST_MESSAGES:
                return list(dict.fromkeys(ids)), latest

    def _list(self, google: Google, query: str) -> list[str]:
        ids, token = [], None
        for _ in range(5):
            params = {"q": query, "maxResults": 100}
            if token:
                params["pageToken"] = token
            page = google.get("messages", **params)
            ids += [str(m["id"]) for m in page.get("messages") or []]
            token = page.get("nextPageToken")
            if not token:
                break
        return list(reversed(ids))  # oldest first

    def judge(self, mail: mailrules.Mail) -> list[Finding]:
        """The alerts one email gives, from the fixed rules, and any deadline it states (stored as yours to see)."""
        late = bool(self.gap and mail.received and mail.received < self.gap[1])
        frm = f"\"{mail.sender_name}\" <{mail.sender}>" if mail.sender_name else mail.sender
        lines = [("From", frm), ("Subject", mail.subject or "(no subject)")]
        if mail.received:
            lines.append(("Received", _local(mail.received)))
        if mail.attachments:
            lines.append(("Attachments", ", ".join(mail.attachments[:5])))
        if late:
            lines.append(("Found late", "it arrived while Kairu was not watching"))
        findings, phishing = [], False
        for result in mailrules.check(mail):
            if result.kind == "phishing":
                phishing = True
                high = result.points >= mailrules.HIGH_AT
                not_checked = ["the pages behind the links: Kairu never opens links"]
                if mail.attachments:
                    not_checked.append("what the attachments contain: Kairu never opens attachments")
                claim = f" If it claims to be from {result.brand}, check with them in their own app or by typing their " \
                        "address yourself." if result.brand else ""
                findings.append(Finding(
                    key=f"gmail:{mail.id}:phishing", source="gmail", kind="phishing", severity="high" if high else "warning",
                    classification="Suspected", confidence="high" if high else "medium",
                    confidence_reason=f"{len(result.why)} warning signs ({result.points} points; an alert needs "
                                      f"{mailrules.ALERT_AT}, high confidence {mailrules.HIGH_AT})",
                    title=f"Suspected phishing: {_short(mail.subject)}", lines=lines, why=result.why,
                    not_checked=not_checked, found_late=late,
                    you_can=f"Leave its links and attachments alone.{claim} You can report it as phishing in Gmail. "
                            "Kairu changed nothing."))
            elif result.kind == "ai_instructions":
                findings.append(Finding(
                    key=f"gmail:{mail.id}:ai", source="gmail", kind="ai_instructions", severity="warning",
                    classification="Suspected", confidence="medium", title=f"An email gives orders to an AI: "
                                                                           f"{_short(mail.subject)}",
                    lines=lines + [("Words", f"\"{result.quote}\"")], why=result.why, found_late=late,
                    confidence_reason="these words match a fixed pattern; they may be harmless",
                    not_checked=["why the sender wrote them"],
                    you_can="Nothing to do unless you know the sender. Kairu never follows instructions found in "
                            "emails or web pages; it only reports them. Kairu changed nothing."))
            elif result.kind == "account_alert":
                findings.append(Finding(
                    key=f"gmail:{mail.id}:account", source="gmail", kind="account_alert", severity="warning",
                    classification="Confirmed fact", title=f"{result.brand} reports: {_short(mail.subject)}",
                    lines=lines, why=result.why, found_late=late, not_checked=["whether it was you"],
                    you_can=f"If it was you, nothing to do. If not, open {result.brand}'s app or type its address "
                            "yourself, and check your account's security there; do not use the email's links for "
                            "this. Kairu changed nothing."))
        if not phishing:
            found = deadlines.from_email(mail)
            if found:
                due, sentence, ambiguous = found
                number = self.store.add_deadline(_short(mail.subject, 120), due, "email", f"gmail:{mail.id}", sentence)
                if number:
                    finding = deadlines.email_finding(mail, due, sentence, ambiguous, number)
                    finding.found_late = late
                    findings.append(finding)
        return findings


def _local(moment: datetime) -> str:
    local = moment.astimezone()
    return f"{local.strftime('%a')} {local.day} {local.strftime('%b %Y')}, {local.strftime('%H:%M')}"


def _short(text: str, most: int = 80) -> str:
    text = " ".join((text or "(no subject)").split())
    return text if len(text) <= most else text[:most - 1] + "…"
